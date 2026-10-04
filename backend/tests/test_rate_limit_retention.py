"""Expired abuse-control keys do not grow indefinitely or reset live quotas."""
from datetime import datetime,timedelta,timezone
from sqlalchemy import select
from app.models import RateLimitBucket


def test_daily_cleanup_removes_only_expired_rate_limit_keys(integration,monkeypatch):
    from app import worker
    factory=integration['SessionLocal'];now=datetime.now(timezone.utc)
    expired='a'*64;fresh='b'*64;future='c'*64
    with factory() as db:
        db.add_all([
            RateLimitBucket(key_hash=expired,window_started=now-timedelta(days=3),count=999),
            RateLimitBucket(key_hash=fresh,window_started=now-timedelta(minutes=30),count=29),
            RateLimitBucket(key_hash=future,window_started=now+timedelta(minutes=1),count=10),
        ]);db.commit()
    monkeypatch.setattr(worker,'SessionLocal',factory)
    worker._cleanup_retention()
    with factory() as db:
        assert db.get(RateLimitBucket,expired) is None
        assert db.get(RateLimitBucket,fresh).count==29
        assert db.get(RateLimitBucket,future).count==10
