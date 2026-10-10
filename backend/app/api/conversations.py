"""Authenticated, participant-scoped conversations attached to listings."""

from collections.abc import Iterable
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session, aliased

from app.api.dependencies import get_current_user, require_csrf
from app.conversation_schemas import (
    ConversationActionOut,
    ConversationCreateInput,
    ConversationCreateOut,
    ConversationDetailOut,
    ConversationListOut,
    ConversationMessageInput,
    ConversationMessageOut,
    ConversationMessageResponseOut,
)
from app.db import get_db
from app.models import (
    Conversation,
    ConversationMessage,
    ConversationParticipantState,
    IdempotencyRecord,
    Listing,
    NotificationOutbox,
    User,
    UserSession,
)
from app.services import consume_rate_limit, enqueue_job, fail, listing_is_public


router = APIRouter(prefix="/api/v1", tags=["conversations"])
_MESSAGE_NOTIFICATION_PREVIEW = 240
_MESSAGE_SEND_LIMIT_PER_HOUR = 60


def _validated_idempotency_key(value: str | None) -> str:
    if (
        value is None
        or not value.strip()
        or len(value.strip()) > 120
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
    ):
        fail(422, "idempotency_required", "Idempotency-Key header is required")
    return value.strip()


def _idempotency_scope(action: str, *, resource_id: UUID | None = None) -> str:
    return f"conversation.{action}" + (f":{resource_id}" if resource_id else "")


def _prior_request(db: Session, actor_id: UUID, scope: str, key: str) -> IdempotencyRecord | None:
    return db.scalar(
        select(IdempotencyRecord).where(
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.scope == scope,
            IdempotencyRecord.key == key,
        )
    )


def _record_request(db: Session, actor_id: UUID, scope: str, key: str, resource_id: UUID) -> None:
    db.add(
        IdempotencyRecord(
            actor_id=actor_id,
            scope=scope,
            key=key,
            resource_id=resource_id,
        )
    )


def _require_participant(conversation: Conversation, user_id: UUID) -> None:
    if user_id not in {conversation.buyer_id, conversation.seller_id}:
        fail(404, "not_found", "Conversation not found")


def _locked_conversation(db: Session, conversation_id: UUID, user_id: UUID) -> Conversation:
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.id == conversation_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if conversation is None:
        fail(404, "not_found", "Conversation not found")
    _require_participant(conversation, user_id)
    return conversation


def _require_unblocked(db: Session, conversation: Conversation) -> None:
    if any(state.blocked_at is not None for state in _states_for(db, conversation).values()):
        fail(409, "conversation_blocked", "Messages cannot be sent in a blocked conversation")


def _consume_message_send_limit(db: Session, user: User) -> None:
    consume_rate_limit(
        db,
        "conversation-message-send",
        str(user.id),
        _MESSAGE_SEND_LIMIT_PER_HOUR,
        timedelta(hours=1),
    )


def _states_for(
    db: Session,
    conversation: Conversation,
    *,
    create_missing: bool = False,
) -> dict[UUID, ConversationParticipantState]:
    states = db.scalars(
        select(ConversationParticipantState).where(
            ConversationParticipantState.conversation_id == conversation.id
        )
    ).all()
    result = {state.user_id: state for state in states}
    if create_missing:
        for user_id in (conversation.buyer_id, conversation.seller_id):
            if user_id not in result:
                state = ConversationParticipantState(
                    conversation_id=conversation.id,
                    user_id=user_id,
                )
                db.add(state)
                result[user_id] = state
        db.flush()
    return result


def _marker_messages(
    db: Session,
    states: Iterable[ConversationParticipantState],
) -> dict[UUID, ConversationMessage]:
    marker_ids = {state.last_read_message_id for state in states if state.last_read_message_id}
    if not marker_ids:
        return {}
    return {
        message.id: message
        for message in db.scalars(
            select(ConversationMessage).where(ConversationMessage.id.in_(marker_ids))
        ).all()
    }


def _ensure_state(
    db: Session,
    conversation: Conversation,
    user_id: UUID,
) -> ConversationParticipantState:
    state = db.scalar(
        select(ConversationParticipantState).where(
            ConversationParticipantState.conversation_id == conversation.id,
            ConversationParticipantState.user_id == user_id,
        )
    )
    if state is None:
        state = ConversationParticipantState(conversation_id=conversation.id, user_id=user_id)
        db.add(state)
        db.flush()
    return state


def _unread_counts(
    db: Session,
    conversation_ids: list[UUID],
    user_id: UUID,
) -> dict[UUID, int]:
    if not conversation_ids:
        return {}
    state = aliased(ConversationParticipantState)
    marker = aliased(ConversationMessage)
    rows = db.execute(
        select(ConversationMessage.conversation_id, func.count(ConversationMessage.id))
        .outerjoin(
            state,
            and_(
                state.conversation_id == ConversationMessage.conversation_id,
                state.user_id == user_id,
            ),
        )
        .outerjoin(marker, marker.id == state.last_read_message_id)
        .where(
            ConversationMessage.conversation_id.in_(conversation_ids),
            ConversationMessage.sender_id != user_id,
            or_(
                state.last_read_message_id.is_(None),
                ConversationMessage.sequence > marker.sequence,
            ),
        )
        .group_by(ConversationMessage.conversation_id)
    ).all()
    return {conversation_id: int(count) for conversation_id, count in rows}


def _message_read_at(
    message: ConversationMessage,
    conversation: Conversation,
    states: dict[UUID, ConversationParticipantState],
    markers: dict[UUID, ConversationMessage],
) -> datetime | None:
    reader_id = conversation.seller_id if message.sender_id == conversation.buyer_id else conversation.buyer_id
    state = states.get(reader_id)
    marker = markers.get(state.last_read_message_id) if state and state.last_read_message_id else None
    if marker is None:
        return None
    if marker.sequence < message.sequence:
        return None
    return state.last_read_at


def _serialise_message(
    message: ConversationMessage,
    conversation: Conversation,
    states: dict[UUID, ConversationParticipantState],
    markers: dict[UUID, ConversationMessage],
) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "sender_id": message.sender_id,
        "body": message.body,
        "created_at": message.created_at,
        "read_at": _message_read_at(message, conversation, states, markers),
    }


def _summary(
    db: Session,
    conversation: Conversation,
    viewer_id: UUID,
    *,
    listing: Listing | None = None,
    participants: dict[UUID, User] | None = None,
    last_message: ConversationMessage | None = None,
    unread_count: int | None = None,
    states: dict[UUID, ConversationParticipantState] | None = None,
    markers: dict[UUID, ConversationMessage] | None = None,
) -> dict:
    listing = listing or db.get(Listing, conversation.listing_id)
    participant_rows = participants or {}
    if participants is None:
        users = db.scalars(
            select(User).where(User.id.in_([conversation.buyer_id, conversation.seller_id]))
        ).all()
        participant_rows = {user.id: user for user in users}
    states = states if states is not None else _states_for(db, conversation)
    if markers is None:
        markers = _marker_messages(db, states.values())
    if last_message is None:
        last_message = db.scalar(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation.id)
            .order_by(ConversationMessage.sequence.desc())
            .limit(1)
        )
    if unread_count is None:
        unread_count = _unread_counts(db, [conversation.id], viewer_id).get(conversation.id, 0)
    blocked_state = states.get(viewer_id)
    result = {
        "id": conversation.id,
        "listing": {
            "id": listing.id,
            "title": listing.title,
            "slug": listing.slug,
            "category_code": listing.category_code or "cars",
        },
        "buyer_id": conversation.buyer_id,
        "seller_id": conversation.seller_id,
        "participants": [
            {"id": user_id, "display_name": participant_rows[user_id].display_name}
            for user_id in (conversation.buyer_id, conversation.seller_id)
            if user_id in participant_rows
        ],
        "last_message": (
            _serialise_message(last_message, conversation, states, markers)
            if last_message is not None
            else None
        ),
        "last_message_at": conversation.last_message_at,
        "unread_count": unread_count,
        "blocked_by_me": bool(blocked_state and blocked_state.blocked_at),
        "is_blocked": any(state.blocked_at is not None for state in states.values()),
    }
    return result


def _enqueue_chat_notification(
    db: Session,
    conversation: Conversation,
    message: ConversationMessage,
) -> None:
    recipient_id = conversation.seller_id if message.sender_id == conversation.buyer_id else conversation.buyer_id
    message_preview = message.body[:_MESSAGE_NOTIFICATION_PREVIEW]
    outbox_id = db.scalar(
        pg_insert(NotificationOutbox)
        .values(
            id=uuid4(),
            dedupe_key=f"conversation:{conversation.id}:message:{message.id}",
            saved_search_id=None,
            conversation_id=conversation.id,
            user_id=recipient_id,
            listing_id=conversation.listing_id,
            channel="web",
            status="queued",
            payload={
                "title": "Новое сообщение по объявлению",
                "body": message_preview,
                "url": f"/account/messages/{conversation.id}",
                "conversation_id": str(conversation.id),
                "listing_id": str(conversation.listing_id),
            },
            attempts=0,
        )
        .on_conflict_do_nothing(constraint="uq_notification_outbox_dedupe")
        .returning(NotificationOutbox.id)
    )
    if outbox_id is not None:
        enqueue_job(
            db,
            "notification.deliver",
            f"notification.deliver:{outbox_id}",
            {"outbox_id": str(outbox_id)},
        )


def _send_message(
    db: Session,
    conversation: Conversation,
    sender: User,
    body: str,
    *,
    scope: str,
    key: str,
) -> ConversationMessage:
    states = _states_for(db, conversation, create_missing=True)
    if any(state.blocked_at is not None for state in states.values()):
        fail(409, "conversation_blocked", "Messages cannot be sent in a blocked conversation")
    message = ConversationMessage(
        conversation_id=conversation.id,
        sender_id=sender.id,
        body=body,
        sequence=conversation.last_message_sequence + 1,
        created_at=func.clock_timestamp(),
    )
    conversation.last_message_sequence = message.sequence
    db.add(message)
    db.flush()
    conversation.last_message_at = message.created_at
    conversation.updated_at = datetime.now(timezone.utc)
    _enqueue_chat_notification(db, conversation, message)
    _record_request(db, sender.id, scope, key, message.id)
    db.commit()
    db.refresh(message)
    return message


@router.get("/conversations", response_model=ConversationListOut)
def list_conversations(
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=100),
) -> dict:
    conversations = db.scalars(
        select(Conversation)
        .where(or_(Conversation.buyer_id == user.id, Conversation.seller_id == user.id))
        .order_by(Conversation.last_message_at.desc(), Conversation.id.desc())
        .limit(limit)
    ).all()
    if not conversations:
        return {"items": []}

    ids = [conversation.id for conversation in conversations]
    participant_ids = {participant_id for conversation in conversations for participant_id in (conversation.buyer_id, conversation.seller_id)}
    listings = {
        listing.id: listing
        for listing in db.scalars(select(Listing).where(Listing.id.in_({conversation.listing_id for conversation in conversations}))).all()
    }
    participants = {
        participant.id: participant
        for participant in db.scalars(select(User).where(User.id.in_(participant_ids))).all()
    }
    states_by_conversation: dict[UUID, dict[UUID, ConversationParticipantState]] = {}
    all_states = db.scalars(
        select(ConversationParticipantState).where(ConversationParticipantState.conversation_id.in_(ids))
    ).all()
    for state in all_states:
        states_by_conversation.setdefault(state.conversation_id, {})[state.user_id] = state
    ranked = (
        select(
            ConversationMessage.id.label("message_id"),
            func.row_number()
            .over(
                partition_by=ConversationMessage.conversation_id,
                order_by=ConversationMessage.sequence.desc(),
            )
            .label("message_rank"),
        )
        .where(ConversationMessage.conversation_id.in_(ids))
        .subquery()
    )
    latest = {
        message.conversation_id: message
        for message in db.scalars(
            select(ConversationMessage)
            .join(ranked, ranked.c.message_id == ConversationMessage.id)
            .where(ranked.c.message_rank == 1)
        ).all()
    }
    unread = _unread_counts(db, ids, user.id)
    markers = _marker_messages(db, all_states)

    return {
        "items": [
            _summary(
                db,
                conversation,
                user.id,
                listing=listings.get(conversation.listing_id),
                participants=participants,
                last_message=latest.get(conversation.id),
                unread_count=unread.get(conversation.id, 0),
                states=states_by_conversation.get(conversation.id, {}),
                markers=markers,
            )
            for conversation in conversations
            if listings.get(conversation.listing_id) is not None
        ]
    }


@router.post("/conversations", response_model=ConversationCreateOut)
def create_conversation(
    payload: ConversationCreateInput,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    del csrf
    key = _validated_idempotency_key(idempotency_key)
    scope = _idempotency_scope("create", resource_id=payload.listing_id)
    prior = _prior_request(db, user.id, scope, key)
    if prior is not None:
        conversation = db.get(Conversation, prior.resource_id)
        if conversation is None:
            fail(409, "idempotency_resource_missing", "The idempotent conversation no longer exists")
        _require_participant(conversation, user.id)
        return {"conversation": _summary(db, conversation, user.id)}

    # The rate-limit helper commits its Session. Keep this preflight read-only
    # and acquire mutation locks only after the account bucket has been consumed.
    listing = db.get(Listing, payload.listing_id)
    if listing is None:
        fail(404, "not_found", "Listing not found")
    if listing.owner_id == user.id:
        fail(409, "self_chat", "You cannot start a conversation about your own listing")
    existing = db.scalar(
        select(Conversation).where(
            Conversation.buyer_id == user.id,
            Conversation.listing_id == listing.id,
        )
    )
    if existing is not None:
        _require_participant(existing, user.id)
        _require_unblocked(db, existing)
    elif listing.status != "active" or not listing_is_public(db, listing):
        fail(404, "not_found", "Active listing not found")
    _consume_message_send_limit(db, user)

    listing = db.scalar(
        select(Listing)
        .where(Listing.id == payload.listing_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if listing is None:
        fail(404, "not_found", "Listing not found")
    if listing.owner_id == user.id:
        fail(409, "self_chat", "You cannot start a conversation about your own listing")
    conversation = db.scalar(
        select(Conversation)
        .where(Conversation.buyer_id == user.id, Conversation.listing_id == listing.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if conversation is None:
        if listing.status != "active" or not listing_is_public(db, listing):
            fail(404, "not_found", "Active listing not found")
        conversation = Conversation(
            listing_id=listing.id,
            buyer_id=user.id,
            seller_id=listing.owner_id,
        )
        db.add(conversation)
        db.flush()
        db.add_all(
            [
                ConversationParticipantState(conversation_id=conversation.id, user_id=user.id),
                ConversationParticipantState(conversation_id=conversation.id, user_id=listing.owner_id),
            ]
        )
        db.flush()
    else:
        _require_participant(conversation, user.id)

    # The listing row serializes competing starts for this listing. Check the
    # key again after the lock so a retry cannot append the first message twice.
    prior = _prior_request(db, user.id, scope, key)
    if prior is not None:
        conversation = db.get(Conversation, prior.resource_id)
        if conversation is None:
            fail(409, "idempotency_resource_missing", "The idempotent conversation no longer exists")
        return {"conversation": _summary(db, conversation, user.id)}
    states = _states_for(db, conversation, create_missing=True)
    if any(state.blocked_at is not None for state in states.values()):
        fail(409, "conversation_blocked", "Messages cannot be sent in a blocked conversation")
    message = ConversationMessage(
        conversation_id=conversation.id,
        sender_id=user.id,
        body=payload.message,
        sequence=conversation.last_message_sequence + 1,
        created_at=func.clock_timestamp(),
    )
    conversation.last_message_sequence = message.sequence
    db.add(message)
    db.flush()
    conversation.last_message_at = message.created_at
    _enqueue_chat_notification(db, conversation, message)
    _record_request(db, user.id, scope, key, conversation.id)
    db.commit()
    db.refresh(conversation)
    return {"conversation": _summary(db, conversation, user.id)}


@router.get("/conversations/{conversation_id}", response_model=ConversationDetailOut)
def get_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
    limit: int = Query(default=50, ge=1, le=100),
    before_sequence: int | None = Query(default=None, ge=1),
) -> dict:
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        fail(404, "not_found", "Conversation not found")
    _require_participant(conversation, user.id)
    listing = db.get(Listing, conversation.listing_id)
    participants = {
        participant.id: participant
        for participant in db.scalars(
            select(User).where(User.id.in_([conversation.buyer_id, conversation.seller_id]))
        ).all()
    }
    messages_query = select(ConversationMessage).where(
        ConversationMessage.conversation_id == conversation.id
    )
    if before_sequence is not None:
        messages_query = messages_query.where(ConversationMessage.sequence < before_sequence)
    descending_page = db.scalars(
        messages_query.order_by(ConversationMessage.sequence.desc()).limit(limit + 1)
    ).all()
    has_more = len(descending_page) > limit
    messages = list(reversed(descending_page[:limit]))
    latest_message = db.scalar(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.sequence.desc())
        .limit(1)
    )
    states = _states_for(db, conversation)
    markers = _marker_messages(db, states.values())
    summary = _summary(
        db,
        conversation,
        user.id,
        listing=listing,
        participants=participants,
        last_message=latest_message,
        unread_count=_unread_counts(db, [conversation.id], user.id).get(conversation.id, 0),
        states=states,
        markers=markers,
    )
    return {
        "conversation": summary,
        "messages": [
            _serialise_message(message, conversation, states, markers)
            for message in messages
        ],
        "has_more": has_more,
        "next_before_sequence": messages[0].sequence if has_more and messages else None,
    }


@router.post("/conversations/{conversation_id}/messages", response_model=ConversationMessageResponseOut)
def send_message(
    conversation_id: UUID,
    payload: ConversationMessageInput,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    del csrf
    key = _validated_idempotency_key(idempotency_key)
    scope = _idempotency_scope("message", resource_id=conversation_id)
    conversation = db.get(Conversation, conversation_id)
    if conversation is None:
        fail(404, "not_found", "Conversation not found")
    _require_participant(conversation, user.id)
    prior = _prior_request(db, user.id, scope, key)
    if prior is not None:
        message = db.get(ConversationMessage, prior.resource_id)
        if message is None or message.conversation_id != conversation.id or message.sender_id != user.id:
            fail(409, "idempotency_resource_missing", "The idempotent message no longer exists")
        states = _states_for(db, conversation)
        return {"message": _serialise_message(message, conversation, states, _marker_messages(db, states.values()))}
    _require_unblocked(db, conversation)
    _consume_message_send_limit(db, user)

    conversation = _locked_conversation(db, conversation_id, user.id)
    prior = _prior_request(db, user.id, scope, key)
    if prior is not None:
        message = db.get(ConversationMessage, prior.resource_id)
        if message is None or message.conversation_id != conversation.id or message.sender_id != user.id:
            fail(409, "idempotency_resource_missing", "The idempotent message no longer exists")
        states = _states_for(db, conversation)
        return {"message": _serialise_message(message, conversation, states, _marker_messages(db, states.values()))}
    message = _send_message(
        db,
        conversation,
        user,
        payload.message,
        scope=scope,
        key=key,
    )
    states = _states_for(db, conversation)
    markers = _marker_messages(db, states.values())
    return {"message": _serialise_message(message, conversation, states, markers)}


@router.post("/conversations/{conversation_id}/read", response_model=ConversationActionOut)
def mark_conversation_read(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    del csrf
    key = _validated_idempotency_key(idempotency_key)
    scope = _idempotency_scope("read", resource_id=conversation_id)
    conversation = _locked_conversation(db, conversation_id, user.id)
    if _prior_request(db, user.id, scope, key) is not None:
        return {"ok": True}
    latest = db.scalar(
        select(ConversationMessage)
        .where(ConversationMessage.conversation_id == conversation.id)
        .order_by(ConversationMessage.sequence.desc())
        .limit(1)
    )
    if latest is not None:
        state = _ensure_state(db, conversation, user.id)
        state.last_read_at = latest.created_at
        state.last_read_message_id = latest.id
    _record_request(db, user.id, scope, key, conversation.id)
    db.commit()
    return {"ok": True}


@router.post("/conversations/{conversation_id}/block", response_model=ConversationActionOut)
def block_conversation(
    conversation_id: UUID,
    user: Annotated[User, Depends(get_current_user)],
    csrf: Annotated[UserSession, Depends(require_csrf)],
    db: Annotated[Session, Depends(get_db)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict:
    del csrf
    key = _validated_idempotency_key(idempotency_key)
    scope = _idempotency_scope("block", resource_id=conversation_id)
    conversation = _locked_conversation(db, conversation_id, user.id)
    if _prior_request(db, user.id, scope, key) is not None:
        return {"ok": True}
    state = _ensure_state(db, conversation, user.id)
    if state.blocked_at is None:
        state.blocked_at = datetime.now(timezone.utc)
    _record_request(db, user.id, scope, key, conversation.id)
    db.commit()
    return {"ok": True}
