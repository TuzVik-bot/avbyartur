import threading
import time
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from app import models, worker
from sqlalchemy import delete, select, update

LATE_UTC_EVENING = datetime(2026, 9, 30, 22, 30, tzinfo=timezone.utc)
TEST_JOB_KIND = "test.reliability"
CONCURRENT_JOB_COUNT = 20
THREAD_JOIN_TIMEOUT_SECONDS = 30


class _LateEveningDatetime(datetime):
    """22:30 UTC on Sep 30 is already 01:30 on Oct 1 in Minsk."""

    @classmethod
    def now(cls, tz=None):
        return LATE_UTC_EVENING if tz is None else LATE_UTC_EVENING.astimezone(tz)


def test_rate_dated_today_in_minsk_is_accepted_before_utc_midnight(monkeypatch):
    monkeypatch.setattr(worker, "datetime", _LateEveningDatetime)

    parsed = worker._parse_nbrb_usd_rate(
        {"Date": "2026-10-01T00:00:00", "Cur_OfficialRate": 3.1, "Cur_Scale": 1}
    )

    assert parsed[0] == date(2026, 10, 1).isoformat()


def test_schedulers_run_at_most_once_per_interval(monkeypatch):
    calls: list[str] = []
    clock = SimpleNamespace(now=1_000.0)
    monkeypatch.setattr(worker, "_schedule_daily_rates", lambda: calls.append("rates"))
    monkeypatch.setattr(
        worker, "_schedule_onliner_sync", lambda: calls.append("onliner")
    )
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(worker, "_schedulers_last_run", None)

    worker._run_schedulers_if_due()
    clock.now += worker.SCHEDULER_INTERVAL_SECONDS - 1
    worker._run_schedulers_if_due()
    assert calls == ["rates", "onliner"]

    clock.now += 1
    worker._run_schedulers_if_due()
    assert calls == ["rates", "onliner", "rates", "onliner"]


@pytest.fixture
def clean_jobs(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        db.execute(delete(models.WorkerJob))
        db.execute(delete(models.WorkerHeartbeat))
        db.commit()
    yield factory
    with factory() as db:
        db.execute(
            delete(models.WorkerJob).where(models.WorkerJob.kind == TEST_JOB_KIND)
        )
        db.commit()


def _add_jobs(factory, count: int) -> list[uuid.UUID]:
    with factory() as db:
        jobs = [
            models.WorkerJob(
                job_key=f"{TEST_JOB_KIND}:{uuid.uuid4()}",
                kind=TEST_JOB_KIND,
                payload={},
                status="queued",
                attempts=0,
                max_attempts=3,
            )
            for _ in range(count)
        ]
        db.add_all(jobs)
        db.commit()
        return [job.id for job in jobs]


def test_heartbeat_is_upserted_and_throttled(clean_jobs, monkeypatch):
    clock = SimpleNamespace(now=5_000.0)
    monkeypatch.setattr(worker.time, "monotonic", lambda: clock.now)
    monkeypatch.setattr(worker, "_heartbeat_last_written", None)

    worker._record_heartbeat("host:1")
    with clean_jobs() as db:
        first = db.scalar(select(models.WorkerHeartbeat.last_seen_at))
        db.execute(
            update(models.WorkerHeartbeat).values(
                last_seen_at=first - timedelta(hours=1)
            )
        )
        db.commit()

    clock.now += worker.HEARTBEAT_INTERVAL_SECONDS - 1
    worker._record_heartbeat("host:1")
    with clean_jobs() as db:
        assert db.scalar(
            select(models.WorkerHeartbeat.last_seen_at)
        ) == first - timedelta(hours=1)

    clock.now += 1
    worker._record_heartbeat("host:1")
    with clean_jobs() as db:
        rows = db.execute(
            select(
                models.WorkerHeartbeat.worker_id, models.WorkerHeartbeat.last_seen_at
            )
        ).all()
    assert [row.worker_id for row in rows] == ["host:1"]
    assert rows[0].last_seen_at >= first


def test_two_worker_loops_never_process_a_job_twice(clean_jobs, monkeypatch):
    job_ids = _add_jobs(clean_jobs, CONCURRENT_JOB_COUNT)
    processed: Counter = Counter()
    processed_by: dict[str, set] = {"a": set(), "b": set()}
    counter_lock = threading.Lock()

    def slow_dispatch(job_id, kind, payload):
        assert kind == TEST_JOB_KIND
        time.sleep(0.02)
        with counter_lock:
            processed[job_id] += 1
            processed_by[threading.current_thread().name].add(job_id)

    monkeypatch.setattr(worker, "_dispatch_job", slow_dispatch)
    monkeypatch.setattr(worker, "_run_schedulers_if_due", lambda: None)
    monkeypatch.setattr(worker, "_record_heartbeat", lambda _worker_id: None)
    errors: list[BaseException] = []

    def loop(worker_id: str) -> None:
        try:
            while worker._work_once(worker_id, sleep=lambda _seconds: None):
                pass
        except BaseException as exc:  # noqa: BLE001 - surfaced by the assertion below
            errors.append(exc)

    threads = [
        threading.Thread(target=loop, args=(f"worker-{name}",), name=name)
        for name in ("a", "b")
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(THREAD_JOIN_TIMEOUT_SECONDS)

    assert errors == []
    assert processed == Counter({job_id: 1 for job_id in job_ids})
    assert processed_by["a"] and processed_by["b"], (
        "both loops should have worked concurrently"
    )
    with clean_jobs() as db:
        rows = db.execute(
            select(models.WorkerJob.status, models.WorkerJob.attempts).where(
                models.WorkerJob.id.in_(job_ids)
            )
        ).all()
    assert {(row.status, row.attempts) for row in rows} == {("succeeded", 1)}


@pytest.fixture
def short_lease(monkeypatch):
    monkeypatch.setattr(worker, "LEASE", timedelta(seconds=1))
    monkeypatch.setattr(worker, "LEASE_RENEWAL_INTERVAL_SECONDS", 0.2)
    monkeypatch.setattr(worker, "_record_heartbeat", lambda _worker_id: None)


def _run_long_job_with_intruder(
    factory, monkeypatch
) -> tuple[uuid.UUID | None, uuid.UUID]:
    (job_id,) = _add_jobs(factory, 1)
    intruder_claims: list[uuid.UUID | None] = []

    def long_job(_job_id, _kind, _payload):
        # Longer than the one-second lease: without renewal it would expire.
        time.sleep(1.6)
        intruder_claims.append(worker._claim_one("intruder"))

    monkeypatch.setattr(worker, "_dispatch_job", long_job)
    claimed = worker._claim_one("owner")
    assert claimed == job_id
    worker._run_job(job_id, "owner")
    return intruder_claims[0], job_id


def test_running_job_lease_is_renewed_so_no_other_worker_can_claim_it(
    clean_jobs, monkeypatch, short_lease
):
    intruder_claim, job_id = _run_long_job_with_intruder(clean_jobs, monkeypatch)

    assert intruder_claim is None
    with clean_jobs() as db:
        job = db.get(models.WorkerJob, job_id)
        assert (job.status, job.attempts, job.locked_by) == ("succeeded", 1, None)


def test_without_lease_renewal_the_long_job_would_be_stolen(
    clean_jobs, monkeypatch, short_lease
):
    # Control for the test above: proves the scenario really outlives the lease.
    monkeypatch.setattr(worker, "_renew_job_lease", lambda _job_id, _worker_id: True)

    intruder_claim, job_id = _run_long_job_with_intruder(clean_jobs, monkeypatch)

    assert intruder_claim == job_id
    with clean_jobs() as db:
        job = db.get(models.WorkerJob, job_id)
        # The original worker must not overwrite the job the intruder now owns.
        assert (job.status, job.locked_by) == ("running", "intruder")


def test_failure_of_a_taken_over_job_does_not_reset_its_state(clean_jobs, monkeypatch):
    (job_id,) = _add_jobs(clean_jobs, 1)

    def failing_after_takeover(_job_id, _kind, _payload):
        with clean_jobs() as db:
            db.execute(
                update(models.WorkerJob)
                .where(models.WorkerJob.id == job_id)
                .values(
                    status="failed", locked_by=None, last_error="cancelled_elsewhere"
                )
            )
            db.commit()
        raise RuntimeError("boom")

    monkeypatch.setattr(worker, "_dispatch_job", failing_after_takeover)
    monkeypatch.setattr(worker, "_record_heartbeat", lambda _worker_id: None)
    assert worker._claim_one("owner") == job_id
    worker._run_job(job_id, "owner")

    with clean_jobs() as db:
        job = db.get(models.WorkerJob, job_id)
        assert (job.status, job.last_error) == ("failed", "cancelled_elsewhere")
