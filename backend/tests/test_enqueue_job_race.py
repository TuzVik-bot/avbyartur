import threading

from sqlalchemy import func, select

from app.models import WorkerJob
from app.services import enqueue_job

BLOCKED_INSERT_WAIT_SECONDS = 0.5
THREAD_JOIN_TIMEOUT_SECONDS = 10


def test_enqueue_job_returns_existing_job_for_repeated_key(integration):
    factory = integration["SessionLocal"]
    with factory() as db:
        first = enqueue_job(db, "test.kind", "test:repeat", {"n": 1})
        second = enqueue_job(db, "test.kind", "test:repeat", {"n": 2})
        db.commit()

    assert second.id == first.id
    assert second.payload == {"n": 1}


def test_concurrent_enqueue_with_same_key_returns_the_committed_job(integration):
    factory = integration["SessionLocal"]
    outcome: dict = {}

    def enqueue_in_other_transaction() -> None:
        try:
            with factory() as other:
                job = enqueue_job(other, "test.kind", "test:race", {"from": "second"})
                outcome["job_id"] = job.id
                other.commit()
        except Exception as exc:  # noqa: BLE001 - surfaced by the assertion below
            outcome["error"] = exc

    with factory() as db:
        first = enqueue_job(db, "test.kind", "test:race", {"from": "first"})
        # The other transaction cannot see this uncommitted row, so its insert
        # waits on the unique key until this transaction commits.
        worker = threading.Thread(target=enqueue_in_other_transaction)
        worker.start()
        worker.join(BLOCKED_INSERT_WAIT_SECONDS)
        db.commit()
        first_id = first.id
    worker.join(THREAD_JOIN_TIMEOUT_SECONDS)

    assert "error" not in outcome, repr(outcome.get("error"))
    assert outcome["job_id"] == first_id
    with factory() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(WorkerJob)
                .where(WorkerJob.job_key == "test:race")
            )
            == 1
        )
