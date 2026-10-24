"""Unit tests for the Postgres job queue.

No database: the queue builds SQL and decides control flow, and a fake Executor records
what it was handed. Everything asserted here is a property of the statements the queue
sends, not of what Postgres does with them.
"""

from __future__ import annotations

import os
from collections import deque
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from masdar.db.queue import (
    BACKOFF_CAP_SECONDS,
    Dead,
    Job,
    Retry,
    UnknownJob,
    backoff_seconds,
    claim,
    complete,
    fail,
    heartbeat,
    reap_expired,
)

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
LEASE_END = NOW + timedelta(seconds=600)
TOKEN = "tok-a"


def job_at(job_id: int = 7, *, attempts: int = 1, token: str = TOKEN) -> Job:
    """A job as a worker holds it: an id plus the token proving the lease is still ours."""
    return Job(
        id=job_id, kind="transcribe", payload={}, attempts=attempts,
        locked_until=LEASE_END, token=token,
    )


class FakeExecutor:
    """Records statements; answers fetchall from a queue of prepared result sets."""

    def __init__(self, results: Sequence[Sequence[tuple[object, ...]]] = ()) -> None:
        self._results: deque[Sequence[tuple[object, ...]]] = deque(results)
        self.statements: list[tuple[str, tuple[object, ...]]] = []
        self.events: list[str] = []

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        self.statements.append((sql, tuple(params)))

    def fetchall(self, sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
        self.statements.append((sql, tuple(params)))
        if not self._results:
            return []
        return list(self._results.popleft())

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        self.events.append("commit")

    @property
    def last_sql(self) -> str:
        return self.statements[-1][0]

    @property
    def last_params(self) -> tuple[object, ...]:
        return self.statements[-1][1]


def test_claim_with_no_kinds_raises_instead_of_claiming_anything() -> None:
    executor = FakeExecutor()

    with pytest.raises(ValueError, match="kinds"):
        claim(executor, kinds=[], lease_seconds=60, now=NOW)

    assert executor.statements == []


def test_claim_with_a_non_positive_lease_raises() -> None:
    executor = FakeExecutor()

    with pytest.raises(ValueError, match="lease_seconds"):
        claim(executor, kinds=["transcribe"], lease_seconds=0, now=NOW)

    assert executor.statements == []


def test_claim_sql_locks_one_pending_due_row_with_skip_locked() -> None:
    executor = FakeExecutor()

    claim(executor, kinds=["transcribe"], lease_seconds=900, now=NOW)

    sql = " ".join(executor.last_sql.split())
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "state = 'pending'" in sql
    assert "run_after <= %s" in sql
    assert "LIMIT 1" in sql


def test_claim_binds_the_lease_deadline_the_clock_and_the_kinds() -> None:
    executor = FakeExecutor()

    claim(executor, kinds=["transcribe", "embed"], lease_seconds=900, now=NOW, token=TOKEN)

    assert executor.last_params == (
        NOW + timedelta(seconds=900),
        TOKEN,
        NOW,
        ["transcribe", "embed"],
    )


def test_claim_returns_none_when_no_job_is_runnable() -> None:
    executor = FakeExecutor(results=[[]])

    assert claim(executor, kinds=["transcribe"], lease_seconds=900, now=NOW) is None


def test_claim_returns_the_job_it_locked_with_the_incremented_attempt_count() -> None:
    lease_end = NOW + timedelta(seconds=900)
    executor = FakeExecutor(
        results=[[(7, "transcribe", {"entry_id": "x-1"}, 1, lease_end, TOKEN)]]
    )

    job = claim(executor, kinds=["transcribe"], lease_seconds=900, now=NOW)

    assert job == Job(
        id=7,
        kind="transcribe",
        payload={"entry_id": "x-1"},
        attempts=1,
        locked_until=lease_end,
        token=TOKEN,
    )


def test_backoff_seconds_for_a_zeroth_attempt_raises() -> None:
    with pytest.raises(ValueError, match="attempts"):
        backoff_seconds(0)


def test_backoff_seconds_doubles_with_every_attempt() -> None:
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]


def test_backoff_seconds_is_capped_so_a_retry_never_drifts_out_of_reach() -> None:
    assert backoff_seconds(40) == BACKOFF_CAP_SECONDS
    assert BACKOFF_CAP_SECONDS == 3600


def test_fail_on_a_job_id_that_does_not_exist_raises() -> None:
    executor = FakeExecutor(results=[[]])

    with pytest.raises(UnknownJob, match="99"):
        fail(executor, job_at(99), error="boom", now=NOW)


def test_fail_with_the_attempt_budget_spent_marks_the_job_failed_for_good() -> None:
    executor = FakeExecutor(results=[[(5,)], [(7,)]])

    outcome = fail(executor, job_at(), error="asr timed out", max_attempts=5, now=NOW)

    assert outcome == Dead(job_id=7, attempts=5, error="asr timed out")
    sql, params = executor.statements[-1]
    assert "state = 'failed'" in " ".join(sql.split())
    assert params == ("asr timed out", 7, TOKEN)


def test_fail_below_the_budget_reschedules_the_job_after_the_backoff() -> None:
    executor = FakeExecutor(results=[[(2,)], [(7,)]])

    outcome = fail(executor, job_at(), error="asr 503", max_attempts=5, now=NOW)

    assert outcome == Retry(
        job_id=7,
        attempts=2,
        run_after=NOW + timedelta(seconds=60),
        delay_seconds=60,
    )
    sql, params = executor.statements[-1]
    flat = " ".join(sql.split())
    assert "state = 'pending'" in flat
    assert "locked_until = NULL" in flat
    assert params == (NOW + timedelta(seconds=60), "asr 503", 7, TOKEN)


def test_fail_delay_grows_between_consecutive_attempts_of_the_same_job() -> None:
    delays = []
    for attempts in (1, 2, 3):
        executor = FakeExecutor(results=[[(attempts,)], [(7,)]])
        outcome = fail(executor, job_at(), error="flaky", max_attempts=5, now=NOW)
        assert isinstance(outcome, Retry)
        delays.append(outcome.delay_seconds)

    assert delays == sorted(delays) and len(set(delays)) == 3


def test_complete_marks_the_job_done_and_releases_the_lease() -> None:
    executor = FakeExecutor(results=[[(7,)]])

    assert complete(executor, job_at()) is True

    flat = " ".join(executor.last_sql.split())
    assert "state = 'done'" in flat
    assert "locked_until = NULL" in flat
    assert executor.last_params == (7, TOKEN)


def test_heartbeat_with_a_non_positive_lease_raises() -> None:
    executor = FakeExecutor()

    with pytest.raises(ValueError, match="lease_seconds"):
        heartbeat(executor, job_at(), lease_seconds=0, now=NOW)

    assert executor.statements == []


def test_heartbeat_reports_false_when_the_job_is_no_longer_running() -> None:
    executor = FakeExecutor(results=[[]])

    assert heartbeat(executor, job_at(), lease_seconds=900, now=NOW) is False
    assert "state = 'running'" in " ".join(executor.last_sql.split())


def test_heartbeat_pushes_the_lease_deadline_forward_from_now() -> None:
    executor = FakeExecutor(results=[[(7,)]])

    assert heartbeat(executor, job_at(), lease_seconds=900, now=NOW) is True
    assert executor.last_params == (NOW + timedelta(seconds=900), 7, TOKEN)


def test_reap_expired_returns_nothing_when_no_lease_has_run_out() -> None:
    executor = FakeExecutor(results=[[]])

    assert reap_expired(executor, now=NOW) == []


def test_reap_expired_puts_jobs_with_a_lapsed_lease_back_to_pending() -> None:
    executor = FakeExecutor(results=[[(7,), (9,)]])

    assert reap_expired(executor, now=NOW) == [7, 9]

    flat = " ".join(executor.last_sql.split())
    assert "state = 'pending'" in flat
    assert "state = 'running'" in flat
    assert "locked_until < %s" in flat
    assert executor.last_params == (NOW,)


# ------------------------------------------------------------------ integration
#
# Everything above asserts what the queue *sends*. SKIP LOCKED semantics and the
# interval arithmetic are properties of Postgres, so they can only be checked here.

REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
SCHEMA = "masdar_qtest"

requires_database = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="integration test: set DATABASE_URL to a Postgres with pgvector",
)


@contextmanager
def migrated_schema() -> Iterator[tuple[Any, Any]]:
    """A throwaway schema with every migration applied, dropped on the way out."""
    import psycopg

    from masdar.db.migrate import migrate
    from masdar.db.sql import PsycopgExecutor

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        connection.execute(f"CREATE SCHEMA {SCHEMA}")
        try:
            connection.execute(f"SET search_path TO {SCHEMA}, public")
            executor = PsycopgExecutor(connection)
            migrate(executor, REPO_MIGRATIONS)
            yield connection, executor
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


@requires_database
def test_integration_claim_heartbeat_complete_round_trip() -> None:
    with migrated_schema() as (connection, executor):
        connection.execute("INSERT INTO job (kind, payload) VALUES ('transcribe', '{}')")

        job = claim(executor, kinds=["transcribe"], lease_seconds=60)
        assert job is not None
        assert (job.kind, job.attempts) == ("transcribe", 1)

        assert heartbeat(executor, job, lease_seconds=120) is True
        complete(executor, job)

        assert claim(executor, kinds=["transcribe"], lease_seconds=60) is None
        assert heartbeat(executor, job, lease_seconds=120) is False


@requires_database
def test_integration_expired_lease_is_reaped_and_claimable_again() -> None:
    with migrated_schema() as (connection, executor):
        connection.execute("INSERT INTO job (kind) VALUES ('transcribe')")
        start = datetime.now(UTC)

        job = claim(executor, kinds=["transcribe"], lease_seconds=1, now=start)
        assert job is not None

        assert reap_expired(executor, now=start + timedelta(seconds=30)) == [job.id]

        again = claim(executor, kinds=["transcribe"], lease_seconds=60, now=start)
        assert again is not None
        assert again.attempts == 2


@requires_database
def test_integration_a_second_worker_skips_the_row_the_first_one_locked() -> None:
    import psycopg

    from masdar.db.sql import PsycopgExecutor

    url = os.environ["DATABASE_URL"]
    with migrated_schema() as (connection, _):
        connection.execute("INSERT INTO job (kind) VALUES ('transcribe')")

        with psycopg.connect(url) as first_conn, psycopg.connect(url) as second_conn:
            for conn in (first_conn, second_conn):
                conn.execute(f"SET search_path TO {SCHEMA}, public")

            with first_conn.transaction():
                first = claim(
                    PsycopgExecutor(first_conn), kinds=["transcribe"], lease_seconds=60
                )
                # Still inside the first transaction, so the row lock is held.
                second = claim(
                    PsycopgExecutor(second_conn), kinds=["transcribe"], lease_seconds=60
                )

            assert first is not None
            assert second is None


# A long transcription outlives its lease, reap_expired hands the job to a second worker,
# and the first one then finishes. Updating by id alone, the straggler overwrites a job
# another worker is actively running: it marks done work that is still in flight, or
# reschedules a job that is already running, which runs the same audio through ASR twice.
# Finishing requires proving you still hold the lease.


def test_claim_records_the_token_that_proves_ownership() -> None:
    executor = FakeExecutor([[(7, "asr", {}, 1, LEASE_END, "tok-a")]])
    job = claim(executor, ["asr"], 600, now=NOW, token="tok-a")
    assert job is not None
    assert job.token == "tok-a"
    assert "tok-a" in executor.statements[0][1]


def test_complete_refuses_when_the_lease_was_handed_to_another_worker() -> None:
    executor = FakeExecutor([[]])  # the guarded UPDATE matches no row
    job = Job(id=7, kind="asr", payload={}, attempts=2, locked_until=LEASE_END, token="tok-a")
    assert complete(executor, job) is False
    sql, params = executor.statements[0]
    assert "locked_by" in sql
    assert "tok-a" in params


def test_complete_reports_success_while_the_lease_is_still_held() -> None:
    executor = FakeExecutor([[(7,)]])
    job = Job(id=7, kind="asr", payload={}, attempts=1, locked_until=LEASE_END, token="tok-a")
    assert complete(executor, job) is True


def test_fail_refuses_to_reschedule_a_job_it_no_longer_holds() -> None:
    executor = FakeExecutor([[(2,)], []])  # attempts read, then the guarded UPDATE misses
    job = Job(id=7, kind="asr", payload={}, attempts=2, locked_until=LEASE_END, token="tok-a")
    from masdar.db import queue

    assert isinstance(fail(executor, job, "boom", now=NOW), queue.LeaseLost)
