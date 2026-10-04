from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from io import BytesIO
import json
import uuid

import pytest
from sqlalchemy import select

import app.worker as worker
from app.models import ExchangeRate, WorkerJob


TODAY = date(2026, 9, 30)


def nbrb_payload(*, rate_date: str = "2026-09-30T00:00:00", rate=3.4512, scale=1) -> dict:
    return {"Date": rate_date, "Cur_OfficialRate": rate, "Cur_Scale": scale}


def test_parse_accepts_current_and_past_official_rates():
    assert worker._parse_nbrb_usd_rate(nbrb_payload(), today=TODAY) == (
        "2026-09-30", Decimal("3.4512"), 1,
    )
    assert worker._parse_nbrb_usd_rate(
        nbrb_payload(rate_date="2026-09-29T00:00:00", rate=34.5678, scale=10),
        today=TODAY,
    ) == ("2026-09-29", Decimal("34.5678"), 10)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (nbrb_payload(rate_date="2026-10-01T00:00:00"), "future"),
        (nbrb_payload(rate_date="not-a-date"), "valid date"),
        (nbrb_payload(rate=0), "positive"),
        (nbrb_payload(rate=-1), "positive"),
        (nbrb_payload(rate="NaN"), "finite"),
        (nbrb_payload(rate="Infinity"), "finite"),
        (nbrb_payload(scale=0), "positive integer"),
        (nbrb_payload(scale=-1), "positive integer"),
        (nbrb_payload(scale=1.5), "positive integer"),
        (nbrb_payload(scale=True), "positive integer"),
    ],
)
def test_parse_rejects_future_or_invalid_official_rates(payload, message):
    with pytest.raises(ValueError, match=message):
        worker._parse_nbrb_usd_rate(payload, today=TODAY)


def test_refresh_rejects_future_rate_before_opening_a_database_session(monkeypatch):
    future_date = (datetime.now(UTC).date() + timedelta(days=7)).isoformat()
    payload = nbrb_payload(rate_date=f"{future_date}T00:00:00")
    monkeypatch.setattr(
        worker.urllib.request,
        "urlopen",
        lambda *_args, **_kwargs: BytesIO(json.dumps(payload).encode()),
    )
    monkeypatch.setattr(worker, "SessionLocal", lambda: pytest.fail("invalid rate reached database upsert"))

    with pytest.raises(ValueError, match="future"):
        worker._refresh_usd_rate()


def test_latest_rate_query_excludes_future_rows_from_refresh_scheduling():
    statement = worker._latest_usd_rate_statement(TODAY)
    compiled = statement.compile()

    assert "exchange_rates.rate_date <=" in str(compiled)
    assert "2026-09-30" in compiled.params.values()


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        fixed = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
        return fixed if tz is None else fixed.astimezone(tz)


def _seed_future_rate_and_daily_job(factory, *, status: str) -> tuple[uuid.UUID, datetime, str]:
    now = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)
    job_key = f"rates.refresh:{now.date().isoformat()}"
    job_id = uuid.uuid4()
    with factory() as db:
        db.add(ExchangeRate(
            id=uuid.uuid4(),
            currency="USD",
            rate_date=(now.date() + timedelta(days=1)).isoformat(),
            official_rate=Decimal("3.20"),
            scale=1,
            source="test",
            fetched_at=now,
        ))
        db.add(WorkerJob(
            id=job_id,
            job_key=job_key,
            kind="rates.refresh",
            payload={},
            status=status,
            attempts=6,
            max_attempts=6,
            run_after=now - timedelta(hours=1),
            last_error="previous attempt failed",
        ))
        db.commit()
    return job_id, now, job_key


def test_scheduler_requeues_succeeded_daily_job_when_only_future_rate_exists(integration, monkeypatch):
    factory = integration["SessionLocal"]
    job_id, now, job_key = _seed_future_rate_and_daily_job(factory, status="succeeded")
    monkeypatch.setattr(worker, "datetime", FrozenDateTime)

    worker._schedule_daily_rates()

    with factory() as db:
        jobs = db.scalars(select(WorkerJob).where(WorkerJob.job_key == job_key)).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == job_id
        assert job.status == "queued"
        assert job.attempts == 0
        assert job.max_attempts == 6
        assert job.run_after == now
        assert job.updated_at == now
        assert job.last_error is None
        assert job.locked_by is None
        assert job.lease_until is None


def test_scheduler_does_not_reset_failed_daily_job_when_only_future_rate_exists(integration, monkeypatch):
    factory = integration["SessionLocal"]
    job_id, now, job_key = _seed_future_rate_and_daily_job(factory, status="failed")
    monkeypatch.setattr(worker, "datetime", FrozenDateTime)

    worker._schedule_daily_rates()

    with factory() as db:
        jobs = db.scalars(select(WorkerJob).where(WorkerJob.job_key == job_key)).all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.id == job_id
        assert job.status == "failed"
        assert job.attempts == 6
        assert job.max_attempts == 6
        assert job.run_after == now - timedelta(hours=1)
        assert job.last_error == "previous attempt failed"
