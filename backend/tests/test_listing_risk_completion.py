import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.models import AuditEvent, Listing, User
from app.security import hash_password


def _add_user(factory) -> User:
    email = f"listing-risk-completion-{uuid.uuid4().hex[:12]}@example.com"
    with factory() as db:
        user = User(
            email=email,
            display_name="Listing risk completion",
            password_hash=hash_password("listing-risk-completion-password-123"),
            role="user",
            status="active",
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.expunge(user)
    return user


def _add_listing(factory, owner_id, *, description: str) -> Listing:
    with factory() as db:
        listing = Listing(
            owner_id=owner_id,
            slug=f"listing-risk-completion-{uuid.uuid4().hex}",
            status="pending_review",
            revision=3,
            submitted_revision=3,
            title="Risk completion test listing",
            description=description,
            contact_phone="+375291234567",
            damaged=False,
            parts_only=False,
        )
        db.add(listing)
        db.commit()
        db.refresh(listing)
        db.expunge(listing)
    return listing


def test_configured_stop_word_signal_is_advisory_and_does_not_echo_word(integration, monkeypatch):
    from types import SimpleNamespace

    import app.risk_signals as risk_signals

    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(
        factory,
        owner.id,
        description="Обычное описание. Оплата только через надёжный_агентский_тест.",
    )
    monkeypatch.setattr(
        risk_signals,
        "get_settings",
        lambda: SimpleNamespace(listing_stop_words_csv="надёжный_агентский_тест, запрещённая-фраза"),
    )

    with factory() as db:
        signals = risk_signals.collect_listing_risk_signals(db, [db.get(Listing, listing.id)])[listing.id]
        persisted = db.get(Listing, listing.id)

    configured = [signal for signal in signals if signal["code"] == "configured_stop_word"]
    assert len(configured) == 1
    assert configured[0]["severity"] == "low"
    assert "надёжный_агентский_тест" not in str(configured)
    assert "запрещённая-фраза" not in str(configured)
    assert persisted.status == "pending_review"


def test_change_risk_signals_use_only_latest_sanitized_audit_event(integration):
    from app.risk_signals import collect_listing_risk_signals

    factory = integration["SessionLocal"]
    owner = _add_user(factory)
    listing = _add_listing(factory, owner.id, description="Ordinary description")
    stale_city_listing = _add_listing(factory, owner.id, description="Another ordinary description")
    now = datetime.now(UTC)
    with factory() as db:
        db.add_all(
            [
                AuditEvent(
                    actor_id=owner.id,
                    entity_type="listing",
                    entity_id=listing.id,
                    action="listing_edited",
                    created_at=now - timedelta(minutes=2),
                    details={
                        "revision": 2,
                        "reason": "seller_edit",
                        "from_status": "active",
                        "to_status": "draft",
                        "changed_field_keys": ["city_id"],
                        "changes": [{"field": "city_id", "before": "Minsk", "after": "Gomel"}],
                    },
                ),
                AuditEvent(
                    actor_id=owner.id,
                    entity_type="listing",
                    entity_id=listing.id,
                    action="listing_edited",
                    created_at=now - timedelta(minutes=1),
                    details={
                        "revision": 3,
                        "reason": "seller_edit",
                        "from_status": "active",
                        "to_status": "draft",
                        "changed_field_keys": ["seller_type", "manual_city"],
                        "changes": [{"field": "seller_type", "before": "private", "after": "company"}],
                    },
                ),
                AuditEvent(
                    actor_id=owner.id,
                    entity_type="listing",
                    entity_id=stale_city_listing.id,
                    action="listing_edited",
                    created_at=now - timedelta(minutes=2),
                    details={
                        "revision": 2,
                        "reason": "seller_edit",
                        "from_status": "active",
                        "to_status": "draft",
                        "changed_field_keys": ["city_id"],
                        "changes": [{"field": "city_id", "before": "Minsk", "after": "Gomel"}],
                    },
                ),
                AuditEvent(
                    actor_id=owner.id,
                    entity_type="listing",
                    entity_id=stale_city_listing.id,
                    action="listing_edited",
                    created_at=now - timedelta(minutes=1),
                    details={
                        "revision": 3,
                        "reason": "seller_edit",
                        "from_status": "draft",
                        "to_status": "draft",
                        "changed_field_keys": ["description"],
                        "changes": [{"field": "description", "before": {"length": 3}, "after": {"length": 4}}],
                    },
                ),
            ]
        )
        db.commit()
        signals = collect_listing_risk_signals(
            db,
            [db.get(Listing, listing.id), db.get(Listing, stale_city_listing.id)],
        )
        persisted = db.get(Listing, listing.id)
        latest = db.scalar(
            select(AuditEvent)
            .where(AuditEvent.entity_id == listing.id, AuditEvent.action == "listing_edited")
            .order_by(AuditEvent.created_at.desc())
        )

    codes = {signal["code"] for signal in signals[listing.id]}
    assert "suspicious_seller_change" in codes
    assert "suspicious_city_change" in codes
    stale_city_codes = {signal["code"] for signal in signals[stale_city_listing.id]}
    assert "suspicious_city_change" not in stale_city_codes
    assert "suspicious_seller_change" not in stale_city_codes
    assert persisted.status == "pending_review"
    assert latest.details["revision"] == 3
    assert all(
        "Gomel" not in signal["summary"]
        for listing_signals in signals.values()
        for signal in listing_signals
    )


def test_photo_edits_cannot_hide_the_latest_sensitive_change_and_malformed_keys_are_safe(integration):
    from app.risk_signals import collect_listing_risk_signals
    factory=integration['SessionLocal'];owner=_add_user(factory);listing=_add_listing(factory,owner.id,description='Plain fixture');bad=_add_listing(factory,owner.id,description='Plain malformed fixture');now=datetime.now(UTC)
    with factory() as db:
        db.add_all([
            AuditEvent(actor_id=owner.id,entity_type='listing',entity_id=listing.id,action='listing_edited',created_at=now-timedelta(minutes=2),details={'reason':'seller_edit','revision':2,'from_status':'active','to_status':'draft','changed_field_keys':['city_id']}),
            AuditEvent(actor_id=owner.id,entity_type='listing',entity_id=listing.id,action='listing_edited',created_at=now-timedelta(minutes=1),details={'reason':'seller_photo_edit','revision':3,'from_status':'draft','to_status':'draft','changed_field_keys':['photos']}),
            AuditEvent(actor_id=owner.id,entity_type='listing',entity_id=bad.id,action='listing_edited',details={'reason':'seller_edit','revision':2,'from_status':'active','changed_field_keys':[{'secret':'payload'}]}),
        ]);db.commit();signals=collect_listing_risk_signals(db,[db.get(Listing,listing.id),db.get(Listing,bad.id)])
    assert 'suspicious_city_change' in {s['code'] for s in signals[listing.id]}
    assert 'secret' not in str(signals)
