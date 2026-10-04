import runpy
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from app import models
from app.api import conversations as conversation_api
from app.conversation_schemas import ConversationMessageInput
from app.db import Base
from app.main import app
from app.security import hash_password
from app.worker import _run_job

PASSWORD = "conversation-integration-password-123"


def add_user(factory, email: str) -> models.User:
    user = models.User(
        email=email,
        display_name=email.split("@", 1)[0],
        password_hash=hash_password(PASSWORD),
        role="user",
        status="active",
    )
    with factory() as db:
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def test_sms_auth_migration_is_safe_on_current_metadata_bootstrap(integration):
    migration_path = Path(__file__).resolve().parents[1] / "alembic/versions/0011_sms_otp_auth.py"
    upgrade = runpy.run_path(str(migration_path))["upgrade"]

    with integration["engine"].begin() as connection:
        context = MigrationContext.configure(connection)
        with Operations.context(context):
            upgrade()


def add_listing(factory, owner_id: uuid.UUID, *, status: str = "active") -> models.Listing:
    listing = models.Listing(
        owner_id=owner_id,
        slug=f"chat-{uuid.uuid4().hex}",
        status=status,
        revision=1,
        title="BMW 320d",
        year=2020,
        mileage_km=50_000,
        fuel="diesel",
        transmission="automatic",
        drive="rear",
        condition="used",
        damaged=False,
        parts_only=False,
        price_amount=Decimal("20000"),
        currency="USD",
        description="Listing for a conversation test",
        contact_phone="",
    )
    with factory() as db:
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def login(email: str) -> tuple[TestClient, str]:
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client, response.json()["csrf_token"]


def write_headers(csrf: str, key: str) -> dict[str, str]:
    return {"X-CSRF-Token": csrf, "Idempotency-Key": key}


def start_conversation(client: TestClient, csrf: str, listing_id: uuid.UUID, *, key: str = "start-1", message: str = "Is the car available?"):
    return client.post(
        "/api/v1/conversations",
        json={"listing_id": str(listing_id), "message": message},
        headers=write_headers(csrf, key),
    )


def test_conversation_start_is_csrf_protected_idempotent_and_unique(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"chat-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"chat-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    client, csrf = login(buyer.email)

    missing_csrf = client.post(
        "/api/v1/conversations",
        json={"listing_id": str(listing.id), "message": "Hello"},
        headers={"Idempotency-Key": "missing-csrf"},
    )
    assert missing_csrf.status_code == 403
    assert missing_csrf.json()["code"] == "csrf_failed"

    created = start_conversation(client, csrf, listing.id, key="start-retry")
    assert created.status_code == 200, created.text
    conversation = created.json()["conversation"]
    conversation_id = conversation["id"]
    assert conversation["listing"] == {"id": str(listing.id), "title": "BMW 320d", "slug": listing.slug}
    assert conversation["buyer_id"] == str(buyer.id)
    assert conversation["seller_id"] == str(seller.id)
    assert conversation["last_message"]["body"] == "Is the car available?"

    retried = start_conversation(client, csrf, listing.id, key="start-retry")
    assert retried.status_code == 200, retried.text
    assert retried.json()["conversation"]["id"] == conversation_id

    reused = start_conversation(client, csrf, listing.id, key="second-start", message="Could I see it tomorrow?")
    assert reused.status_code == 200, reused.text
    assert reused.json()["conversation"]["id"] == conversation_id
    with factory() as db:
        assert db.scalar(select(func.count(models.Conversation.id)).where(models.Conversation.buyer_id == buyer.id, models.Conversation.listing_id == listing.id)) == 1
        assert db.scalar(select(func.count(models.ConversationMessage.id)).where(models.ConversationMessage.conversation_id == uuid.UUID(conversation_id))) == 2


def test_conversation_history_uses_bounded_sequence_cursor_pages(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"pages-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"pages-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    seller_client, seller_csrf = login(seller.email)
    created = start_conversation(buyer_client, buyer_csrf, listing.id, message="Message 1")
    assert created.status_code == 200, created.text
    conversation_id = created.json()["conversation"]["id"]

    for index in range(2, 6):
        sent = seller_client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": f"Message {index}"},
            headers=write_headers(seller_csrf, f"pages-message-{index}"),
        )
        assert sent.status_code == 200, sent.text

    latest = buyer_client.get(f"/api/v1/conversations/{conversation_id}?limit=2")
    assert latest.status_code == 200, latest.text
    assert [message["body"] for message in latest.json()["messages"]] == ["Message 4", "Message 5"]
    assert latest.json()["has_more"] is True
    assert latest.json()["next_before_sequence"] == 4

    middle = buyer_client.get(
        f"/api/v1/conversations/{conversation_id}?limit=2&before_sequence=4"
    )
    assert middle.status_code == 200, middle.text
    assert [message["body"] for message in middle.json()["messages"]] == ["Message 2", "Message 3"]
    assert middle.json()["conversation"]["last_message"]["body"] == "Message 5"
    assert middle.json()["has_more"] is True
    assert middle.json()["next_before_sequence"] == 2

    oldest = buyer_client.get(
        f"/api/v1/conversations/{conversation_id}?limit=2&before_sequence=2"
    )
    assert oldest.status_code == 200, oldest.text
    assert [message["body"] for message in oldest.json()["messages"]] == ["Message 1"]
    assert oldest.json()["has_more"] is False
    assert oldest.json()["next_before_sequence"] is None
    assert buyer_client.get(f"/api/v1/conversations/{conversation_id}?limit=101").status_code == 422


def test_message_send_limit_is_per_account_and_does_not_commit_rejected_messages(integration, monkeypatch):
    factory = integration["SessionLocal"]
    monkeypatch.setattr(conversation_api, "_MESSAGE_SEND_LIMIT_PER_HOUR", 3)
    seller = add_user(factory, f"limit-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"limit-buyer-{uuid.uuid4().hex[:8]}@example.com")
    other_buyer = add_user(factory, f"limit-other-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    other_client, other_csrf = login(other_buyer.email)

    created = start_conversation(buyer_client, buyer_csrf, listing.id, message="First message")
    assert created.status_code == 200, created.text
    conversation_id = created.json()["conversation"]["id"]
    retried_start = start_conversation(buyer_client, buyer_csrf, listing.id, message="First message")
    assert retried_start.status_code == 200, retried_start.text
    assert retried_start.json()["conversation"]["id"] == conversation_id
    first_reply = buyer_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Second message"},
        headers=write_headers(buyer_csrf, "limit-second-message"),
    )
    assert first_reply.status_code == 200, first_reply.text

    retry = buyer_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Second message"},
        headers=write_headers(buyer_csrf, "limit-second-message"),
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["message"]["id"] == first_reply.json()["message"]["id"]

    last_allowed = buyer_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Third message"},
        headers=write_headers(buyer_csrf, "limit-third-message"),
    )
    assert last_allowed.status_code == 200, last_allowed.text
    rejected = buyer_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Must not be stored"},
        headers=write_headers(buyer_csrf, "limit-fourth-message"),
    )
    assert rejected.status_code == 429
    assert rejected.json()["code"] == "rate_limited"

    with factory() as db:
        assert db.scalar(
            select(func.count(models.ConversationMessage.id)).where(
                models.ConversationMessage.conversation_id == uuid.UUID(conversation_id)
            )
        ) == 3
        assert db.scalar(
            select(func.count(models.NotificationOutbox.id)).where(
                models.NotificationOutbox.conversation_id == uuid.UUID(conversation_id)
            )
        ) == 3

    second_listing = add_listing(factory, seller.id)
    rejected_start = start_conversation(
        buyer_client,
        buyer_csrf,
        second_listing.id,
        key="limit-rejected-start",
    )
    assert rejected_start.status_code == 429
    with factory() as db:
        assert db.scalar(
            select(func.count(models.Conversation.id)).where(
                models.Conversation.buyer_id == buyer.id,
                models.Conversation.listing_id == second_listing.id,
            )
        ) == 0

    other_account_start = start_conversation(other_client, other_csrf, listing.id, key="other-account-start")
    assert other_account_start.status_code == 200, other_account_start.text


def test_conversation_is_participant_scoped_and_new_chat_requires_active_listing(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"scope-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"scope-buyer-{uuid.uuid4().hex[:8]}@example.com")
    outsider = add_user(factory, f"scope-outsider-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    draft = add_listing(factory, seller.id, status="draft")
    buyer_client, buyer_csrf = login(buyer.email)
    outsider_client, _ = login(outsider.email)
    seller_client, seller_csrf = login(seller.email)

    active = start_conversation(buyer_client, buyer_csrf, listing.id)
    assert active.status_code == 200, active.text
    conversation_id = active.json()["conversation"]["id"]
    assert outsider_client.get(f"/api/v1/conversations/{conversation_id}").status_code == 404
    assert outsider_client.get(f"/api/v1/conversations/{conversation_id}?limit=1&before_sequence=1").status_code == 404
    assert outsider_client.get("/api/v1/conversations").json()["items"] == []
    assert seller_client.get(f"/api/v1/conversations/{conversation_id}").status_code == 200

    self_chat = start_conversation(seller_client, seller_csrf, listing.id, key="self-chat")
    assert self_chat.status_code == 409
    assert self_chat.json()["code"] == "self_chat"

    inactive = start_conversation(buyer_client, buyer_csrf, draft.id, key="draft-listing")
    assert inactive.status_code == 404
    assert inactive.json()["code"] == "not_found"


def test_conversation_unread_counts_and_read_receipts_are_participant_scoped(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"read-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"read-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    seller_client, seller_csrf = login(seller.email)
    created = start_conversation(buyer_client, buyer_csrf, listing.id, message="First contact")
    conversation_id = created.json()["conversation"]["id"]

    seller_item = seller_client.get("/api/v1/conversations").json()["items"][0]
    buyer_item = buyer_client.get("/api/v1/conversations").json()["items"][0]
    assert seller_item["unread_count"] == 1
    assert buyer_item["unread_count"] == 0

    marked_seller = seller_client.post(
        f"/api/v1/conversations/{conversation_id}/read",
        headers=write_headers(seller_csrf, "seller-read-1"),
    )
    assert marked_seller.status_code == 200, marked_seller.text
    assert seller_client.get("/api/v1/conversations").json()["items"][0]["unread_count"] == 0

    sent = seller_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Yes, it is available."},
        headers=write_headers(seller_csrf, "seller-message-1"),
    )
    assert sent.status_code == 200, sent.text
    assert buyer_client.get("/api/v1/conversations").json()["items"][0]["unread_count"] == 1
    details_before_read = buyer_client.get(f"/api/v1/conversations/{conversation_id}").json()
    assert details_before_read["messages"][-1]["read_at"] is None

    marked_buyer = buyer_client.post(
        f"/api/v1/conversations/{conversation_id}/read",
        headers=write_headers(buyer_csrf, "buyer-read-1"),
    )
    assert marked_buyer.status_code == 200, marked_buyer.text
    assert buyer_client.get("/api/v1/conversations").json()["items"][0]["unread_count"] == 0
    seller_details = seller_client.get(f"/api/v1/conversations/{conversation_id}").json()
    assert seller_details["messages"][-1]["read_at"] is not None


def test_conversation_list_preserves_read_cursors_across_conversations(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"multi-read-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"multi-read-buyer-{uuid.uuid4().hex[:8]}@example.com")
    first_listing = add_listing(factory, seller.id)
    second_listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    seller_client, seller_csrf = login(seller.email)

    first = start_conversation(
        buyer_client,
        buyer_csrf,
        first_listing.id,
        key="multi-read-first-start",
    )
    assert first.status_code == 200, first.text
    first_id = uuid.UUID(first.json()["conversation"]["id"])
    first_reply = seller_client.post(
        f"/api/v1/conversations/{first_id}/messages",
        json={"message": "First seller reply"},
        headers=write_headers(seller_csrf, "multi-read-first-reply"),
    )
    assert first_reply.status_code == 200, first_reply.text
    first_read = buyer_client.post(
        f"/api/v1/conversations/{first_id}/read",
        headers=write_headers(buyer_csrf, "multi-read-first-read"),
    )
    assert first_read.status_code == 200, first_read.text

    second = start_conversation(
        buyer_client,
        buyer_csrf,
        second_listing.id,
        key="multi-read-second-start",
    )
    assert second.status_code == 200, second.text
    second_id = uuid.UUID(second.json()["conversation"]["id"])
    second_reply = seller_client.post(
        f"/api/v1/conversations/{second_id}/messages",
        json={"message": "Second seller reply"},
        headers=write_headers(seller_csrf, "multi-read-second-reply"),
    )
    assert second_reply.status_code == 200, second_reply.text
    second_read = buyer_client.post(
        f"/api/v1/conversations/{second_id}/read",
        headers=write_headers(buyer_csrf, "multi-read-second-read"),
    )
    assert second_read.status_code == 200, second_read.text

    with factory() as db:
        read_states = {
            state.conversation_id: state
            for state in db.scalars(
                select(models.ConversationParticipantState).where(
                    models.ConversationParticipantState.user_id == buyer.id,
                    models.ConversationParticipantState.conversation_id.in_([first_id, second_id]),
                )
            ).all()
        }
        assert set(read_states) == {first_id, second_id}
        assert read_states[first_id].last_read_message_id != read_states[second_id].last_read_message_id
        expected_read_at = {
            conversation_id: state.last_read_at
            for conversation_id, state in read_states.items()
        }

    list_response = buyer_client.get("/api/v1/conversations")
    assert list_response.status_code == 200, list_response.text
    summaries = {
        uuid.UUID(item["id"]): item
        for item in list_response.json()["items"]
        if uuid.UUID(item["id"]) in expected_read_at
    }
    assert set(summaries) == {first_id, second_id}
    for conversation_id, expected in expected_read_at.items():
        actual = summaries[conversation_id]["last_message"]["read_at"]
        assert actual is not None
        assert datetime.fromisoformat(actual.replace("Z", "+00:00")) == expected


def test_unread_cursor_uses_message_sequence_when_timestamps_are_equal(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"same-time-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"same-time-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    seller_client, seller_csrf = login(seller.email)
    created = start_conversation(buyer_client, buyer_csrf, listing.id, message="First")
    conversation_id = uuid.UUID(created.json()["conversation"]["id"])
    reply = seller_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Second"},
        headers=write_headers(seller_csrf, "same-time-reply"),
    )
    assert reply.status_code == 200, reply.text

    fixed_time = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)
    with factory() as db:
        db.execute(
            update(models.ConversationMessage)
            .where(models.ConversationMessage.conversation_id == conversation_id)
            .values(created_at=fixed_time)
        )
        db.commit()

    marked = seller_client.post(
        f"/api/v1/conversations/{conversation_id}/read",
        headers=write_headers(seller_csrf, "same-time-read"),
    )
    assert marked.status_code == 200, marked.text
    third = buyer_client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message": "Third"},
        headers=write_headers(buyer_csrf, "same-time-third"),
    )
    assert third.status_code == 200, third.text
    with factory() as db:
        db.execute(
            update(models.ConversationMessage)
            .where(models.ConversationMessage.id == uuid.UUID(third.json()["message"]["id"]))
            .values(created_at=fixed_time)
        )
        db.commit()

    assert seller_client.get("/api/v1/conversations").json()["items"][0]["unread_count"] == 1
    detail = seller_client.get(f"/api/v1/conversations/{conversation_id}").json()
    assert [message["body"] for message in detail["messages"]] == ["First", "Second", "Third"]
    assert detail["messages"][0]["created_at"] == detail["messages"][1]["created_at"] == detail["messages"][2]["created_at"]
    # read_at means the recipient read the message; the buyer has not read the seller's reply.
    assert detail["messages"][0]["read_at"] is not None
    assert detail["messages"][1]["read_at"] is None
    assert detail["messages"][2]["read_at"] is None


def test_parallel_messages_are_serialized_with_unique_sequences(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"parallel-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"parallel-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    second_client, second_csrf = login(buyer.email)
    seller_client, _ = login(seller.email)
    created = start_conversation(buyer_client, buyer_csrf, listing.id)
    conversation_id = uuid.UUID(created.json()["conversation"]["id"])

    requests = (
        (buyer_client, buyer_csrf, "parallel-one", "Parallel one"),
        (second_client, second_csrf, "parallel-two", "Parallel two"),
    )

    def send(request):
        client, csrf, key, body = request
        return client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": body},
            headers=write_headers(csrf, key),
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, requests))
    assert [response.status_code for response in responses] == [200, 200]

    with factory() as db:
        conversation = db.get(models.Conversation, conversation_id)
        sequences = db.scalars(
            select(models.ConversationMessage.sequence)
            .where(models.ConversationMessage.conversation_id == conversation_id)
            .order_by(models.ConversationMessage.sequence)
        ).all()
        assert conversation.last_message_sequence == 3
        assert sequences == [1, 2, 3]
    assert seller_client.get("/api/v1/conversations").json()["items"][0]["unread_count"] == 3


def test_block_is_participant_scoped_and_prevents_sending_for_both_users(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"block-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"block-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    seller_client, seller_csrf = login(seller.email)
    created = start_conversation(buyer_client, buyer_csrf, listing.id)
    conversation_id = created.json()["conversation"]["id"]

    blocked = seller_client.post(
        f"/api/v1/conversations/{conversation_id}/block",
        headers=write_headers(seller_csrf, "seller-block-1"),
    )
    assert blocked.status_code == 200, blocked.text
    assert seller_client.post(
        f"/api/v1/conversations/{conversation_id}/block",
        headers=write_headers(seller_csrf, "seller-block-1"),
    ).status_code == 200
    seller_summary = seller_client.get("/api/v1/conversations").json()["items"][0]
    buyer_summary = buyer_client.get("/api/v1/conversations").json()["items"][0]
    assert seller_summary["blocked_by_me"] is True
    assert seller_summary["is_blocked"] is True
    assert buyer_summary["blocked_by_me"] is False
    assert buyer_summary["is_blocked"] is True

    for client, csrf, key in ((buyer_client, buyer_csrf, "blocked-buyer-message"), (seller_client, seller_csrf, "blocked-seller-message")):
        response = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message": "This must not send"},
            headers=write_headers(csrf, key),
        )
        assert response.status_code == 409
        assert response.json()["code"] == "conversation_blocked"


def test_chat_message_enqueues_and_delivers_existing_in_app_notification(integration):
    factory = integration["SessionLocal"]
    seller = add_user(factory, f"notify-seller-{uuid.uuid4().hex[:8]}@example.com")
    buyer = add_user(factory, f"notify-buyer-{uuid.uuid4().hex[:8]}@example.com")
    listing = add_listing(factory, seller.id)
    buyer_client, buyer_csrf = login(buyer.email)
    seller_client, _ = login(seller.email)
    created = start_conversation(buyer_client, buyer_csrf, listing.id, message="Please send more photos")
    conversation_id = uuid.UUID(created.json()["conversation"]["id"])

    with factory() as db:
        outbox = db.scalar(select(models.NotificationOutbox).where(models.NotificationOutbox.conversation_id == conversation_id))
        assert outbox is not None
        assert outbox.user_id == seller.id
        assert outbox.saved_search_id is None
        assert outbox.status == "queued"
        job = db.scalar(select(models.WorkerJob).where(models.WorkerJob.kind == "notification.deliver", models.WorkerJob.payload["outbox_id"].as_string() == str(outbox.id)))
        assert job is not None
        job_id = job.id
        job.status = "running"
        job.locked_by = "conversation-test-worker"
        job.attempts = 1
        job.lease_until = datetime.now(timezone.utc) + timedelta(minutes=3)
        db.commit()

    _run_job(job_id, "conversation-test-worker")
    response = seller_client.get("/api/v1/me/notifications")
    assert response.status_code == 200, response.text
    notification = response.json()["items"][0]
    assert notification["conversation_id"] == str(conversation_id)
    assert notification["listing_id"] == str(listing.id)
    assert notification["saved_search_id"] is None
    assert notification["url"] == f"/account/messages/{conversation_id}"
    with factory() as db:
        outbox = db.scalar(select(models.NotificationOutbox).where(models.NotificationOutbox.conversation_id == conversation_id))
        assert outbox.status == "delivered"
        assert db.scalar(select(models.UserNotification.id).where(models.UserNotification.conversation_id == conversation_id)) is not None


def test_chat_message_validation_and_model_migration_metadata():
    try:
        ConversationMessageInput(message="<script>alert(1)</script>")
    except ValueError:
        pass
    else:
        raise AssertionError("HTML markup should be rejected in plain-text messages")

    constraint_names = {
        constraint.name
        for table_name in (
            "conversations",
            "conversation_messages",
            "conversation_participant_states",
            "notification_outbox",
            "user_notifications",
        )
        for constraint in Base.metadata.tables[table_name].constraints
    }
    assert "uq_conversation_buyer_listing" in constraint_names
    assert "uq_conversation_message_sequence" in constraint_names
    assert "ck_conversation_distinct_participants" in constraint_names
    assert "ck_notification_outbox_source" in constraint_names
    assert "ck_user_notification_source" in constraint_names
    assert Base.metadata.tables["notification_outbox"].c.saved_search_id.nullable is True
    assert Base.metadata.tables["user_notifications"].c.conversation_id.nullable is True

    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    revision = scripts.get_revision("0010_conversations")
    assert revision is not None
    assert revision.down_revision == "0009_notification_outbox"

    schema = app.openapi()
    assert schema["paths"]["/api/v1/conversations"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConversationListOut"
    }
    assert schema["paths"]["/api/v1/conversations/{conversation_id}"]["get"]["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/ConversationDetailOut"
    }
    assert set(schema["components"]["schemas"]["ConversationSummaryOut"]["properties"]) == {
        "id",
        "listing",
        "buyer_id",
        "seller_id",
        "participants",
        "last_message",
        "last_message_at",
        "unread_count",
        "blocked_by_me",
        "is_blocked",
    }
