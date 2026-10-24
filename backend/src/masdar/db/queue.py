"""The job queue: one Postgres table, `SELECT … FOR UPDATE SKIP LOCKED`.

Chosen over a broker in `docs/ARCHITECTURE.md`. Control flow lives here, the statements
in `masdar.db.sql`, and execution behind the `Executor` protocol — so the claim/retry
logic is testable without a database.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from masdar.db.sql import (
    CLAIM_JOB,
    HEARTBEAT_JOB,
    MARK_JOB_DONE,
    MARK_JOB_FAILED,
    REAP_EXPIRED_JOBS,
    RESCHEDULE_JOB,
    SELECT_JOB_ATTEMPTS,
    Executor,
)

BACKOFF_BASE_SECONDS = 30
BACKOFF_CAP_SECONDS = 3600


class UnknownJob(LookupError):
    """No job row with that id — the caller is working from a stale id."""


# No jitter: at this scale there is one worker process per kind, so there is no herd to
# spread out, and a deterministic delay is one a test can assert on exactly.
def backoff_seconds(attempts: int) -> int:
    """Seconds to wait before retrying a job that has already failed `attempts` times."""
    if attempts < 1:
        raise ValueError("attempts must be at least 1 before a backoff applies")
    # Shift rather than ** so a large attempts cannot build an absurd integer.
    doublings = min(attempts - 1, 20)
    return min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS << doublings)


@dataclass(frozen=True)
class Dead:
    """The job is out of attempts and will not be retried."""

    job_id: int
    attempts: int
    error: str


@dataclass(frozen=True, slots=True)
class LeaseLost:
    """The job was reaped and handed on while this worker was still running it.

    The worker must discard its result rather than write it: another worker is doing the
    same job right now, and the row belongs to that one.
    """

    job_id: int


@dataclass(frozen=True, slots=True)
class Retry:
    """The job goes back to pending and becomes runnable again at `run_after`."""

    job_id: int
    attempts: int
    run_after: datetime
    delay_seconds: int


@dataclass(frozen=True)
class Job:
    """A claimed unit of work, held until `locked_until`."""

    id: int
    kind: str
    payload: dict[str, Any]
    attempts: int
    locked_until: datetime
    #: Proof that this worker still holds the lease. Required to finish the job.
    token: str


def claim(
    executor: Executor,
    kinds: Sequence[str],
    lease_seconds: int,
    now: datetime | None = None,
    token: str | None = None,
) -> Job | None:
    """Take one runnable job of `kinds` and hold it for `lease_seconds`.

    `token` is the proof of possession stored on the row and required to finish the job.
    It is generated per claim; pass one only to make a test deterministic.
    """
    lease_token = token if token is not None else uuid4().hex
    if not kinds:
        raise ValueError("kinds must name at least one job kind")
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    stamp = now if now is not None else datetime.now(UTC)

    rows = executor.fetchall(
        CLAIM_JOB,
        (stamp + timedelta(seconds=lease_seconds), lease_token, stamp, list(kinds)),
    )
    if not rows:
        return None
    row = rows[0]
    return Job(
        id=cast(int, row[0]),
        kind=cast(str, row[1]),
        payload=cast("dict[str, Any]", row[2]),
        attempts=cast(int, row[3]),
        locked_until=cast(datetime, row[4]),
        token=cast(str, row[5]),
    )


def fail(
    executor: Executor,
    job: Job,
    error: str,
    max_attempts: int = 5,
    now: datetime | None = None,
) -> Retry | Dead | LeaseLost:
    """Record a failed run: retry with backoff, or give up once the budget is spent.

    Returns `LeaseLost` when the job is no longer this worker's to finish.
    """
    if max_attempts < 1:
        raise ValueError("max_attempts must be at least 1")
    stamp = now if now is not None else datetime.now(UTC)

    # attempts was already incremented at claim time, so it counts this run.
    rows = executor.fetchall(SELECT_JOB_ATTEMPTS, (job.id,))
    if not rows:
        raise UnknownJob(f"no job with id {job.id}")
    attempts = cast(int, rows[0][0])

    if attempts >= max_attempts:
        # Terminal on purpose: an endlessly retried job burns ASR budget and buries the
        # queue behind a row that will never succeed.
        if not executor.fetchall(MARK_JOB_FAILED, (error, job.id, job.token)):
            return LeaseLost(job_id=job.id)
        return Dead(job_id=job.id, attempts=attempts, error=error)

    delay = backoff_seconds(attempts)
    run_after = stamp + timedelta(seconds=delay)
    if not executor.fetchall(RESCHEDULE_JOB, (run_after, error, job.id, job.token)):
        return LeaseLost(job_id=job.id)
    return Retry(job_id=job.id, attempts=attempts, run_after=run_after, delay_seconds=delay)


def complete(executor: Executor, job: Job) -> bool:
    """Mark a finished job done and release its lease.

    False means the lease had already been reaped and the job handed to another worker,
    which is still running it. Overwriting its state from here would mark in-flight work
    as done; the straggler must drop its result instead.
    """
    return bool(executor.fetchall(MARK_JOB_DONE, (job.id, job.token)))


def heartbeat(
    executor: Executor,
    job: Job,
    lease_seconds: int,
    now: datetime | None = None,
) -> bool:
    """Extend the lease. False means the lease was lost and the worker must stop.

    A 40-minute transcription outlives any sane lease, so a long-running worker has to
    call this periodically. Without it the lease expires mid-run, reap_expired() puts the
    job back to pending, and a second worker starts the same transcription — paid twice,
    and two writers racing on the same entry.
    """
    if lease_seconds <= 0:
        raise ValueError("lease_seconds must be positive")
    stamp = now if now is not None else datetime.now(UTC)
    rows = executor.fetchall(
        HEARTBEAT_JOB, (stamp + timedelta(seconds=lease_seconds), job.id, job.token)
    )
    return bool(rows)


def reap_expired(executor: Executor, now: datetime | None = None) -> list[int]:
    """Return jobs whose lease has lapsed to pending and report which ones moved.

    attempts is not touched: it was already incremented when the job was claimed, so a
    worker that dies silently still runs out of attempts instead of looping forever.
    """
    stamp = now if now is not None else datetime.now(UTC)
    rows = executor.fetchall(REAP_EXPIRED_JOBS, (stamp,))
    return [cast(int, row[0]) for row in rows]
