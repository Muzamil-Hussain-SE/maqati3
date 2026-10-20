"""The database seam, plus the SQL that the db package sends through it.

Keeping the statements here as text means the migration runner and the job queue can be
unit-tested on what they *send*, without a running Postgres. `Executor` is deliberately
narrow: three methods, nothing driver-specific, so a test can satisfy it in twenty lines.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from contextlib import AbstractContextManager, contextmanager
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from psycopg import Connection


@runtime_checkable
class Executor(Protocol):
    """Whatever can run SQL. Implemented by psycopg in production, by a fake in tests."""

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        """Run a statement that returns no rows."""

    def fetchall(self, sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
        """Run a statement and return every row, including `RETURNING` output."""

    def transaction(self) -> AbstractContextManager[None]:
        """Open a transaction. Leaving the block with an exception must roll back."""


# ------------------------------------------------------------------ migrations

CREATE_SCHEMA_MIGRATIONS = (
    "CREATE TABLE IF NOT EXISTS schema_migrations ("
    "version text PRIMARY KEY, "
    "applied_at timestamptz NOT NULL, "
    "checksum text NOT NULL)"
)

SELECT_APPLIED_MIGRATIONS = "SELECT version, checksum FROM schema_migrations"

INSERT_APPLIED_MIGRATION = (
    "INSERT INTO schema_migrations (version, applied_at, checksum) VALUES (%s, %s, %s)"
)

__all__ = [
    "CLAIM_JOB",
    "CREATE_SCHEMA_MIGRATIONS",
    "INSERT_APPLIED_MIGRATION",
    "SELECT_APPLIED_MIGRATIONS",
    "HEARTBEAT_JOB",
    "MARK_JOB_DONE",
    "MARK_JOB_FAILED",
    "REAP_EXPIRED_JOBS",
    "RESCHEDULE_JOB",
    "SELECT_JOB_ATTEMPTS",
    "Executor",
    "PsycopgExecutor",
]


class PsycopgExecutor:
    """`Executor` backed by a live psycopg connection.

    Not exercised by the unit tests — they use a fake. The integration tests guarded on
    DATABASE_URL are what cover this class.
    """

    def __init__(self, connection: Connection[Any]) -> None:
        self._connection = connection

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        # A migration file holds many statements, and psycopg only allows that on the
        # simple query protocol — which it uses when params is None, not when it is ().
        self._connection.execute(sql, tuple(params) if params else None)

    def fetchall(self, sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
        with self._connection.cursor() as cursor:
            cursor.execute(sql, tuple(params) if params else None)
            return [tuple(row) for row in cursor.fetchall()]

    def transaction(self) -> AbstractContextManager[None]:
        return _silence(self._connection.transaction())


@contextmanager
def _silence(inner: AbstractContextManager[object]) -> Iterator[None]:
    """Narrow a context manager's yielded value to None so it satisfies `Executor`."""
    with inner:
        yield


# ------------------------------------------------------------------ job queue

# One statement, not two: the inner SELECT takes the row lock and SKIP LOCKED makes
# concurrent workers step over each other's rows instead of serialising on them.
# attempts is incremented here, on claim, so that a worker that dies without calling
# fail() still counts against max_attempts and cannot loop forever.
CLAIM_JOB = """
UPDATE job
   SET state = 'running',
       locked_until = %s,
       attempts = attempts + 1
 WHERE id = (
         SELECT id
           FROM job
          WHERE state = 'pending'
            AND run_after <= %s
            AND kind = ANY(%s)
          ORDER BY run_after, id
          LIMIT 1
          FOR UPDATE SKIP LOCKED
       )
RETURNING id, kind, payload, attempts, locked_until
"""

SELECT_JOB_ATTEMPTS = "SELECT attempts FROM job WHERE id = %s"

MARK_JOB_FAILED = (
    "UPDATE job SET state = 'failed', locked_until = NULL, last_error = %s WHERE id = %s"
)

RESCHEDULE_JOB = (
    "UPDATE job SET state = 'pending', locked_until = NULL, run_after = %s, "
    "last_error = %s WHERE id = %s"
)

MARK_JOB_DONE = (
    "UPDATE job SET state = 'done', locked_until = NULL, last_error = NULL WHERE id = %s"
)

# RETURNING id, so the caller can tell an extended lease from one that was already
# reaped and handed to another worker.
HEARTBEAT_JOB = (
    "UPDATE job SET locked_until = %s WHERE id = %s AND state = 'running' RETURNING id"
)

REAP_EXPIRED_JOBS = """
UPDATE job
   SET state = 'pending',
       locked_until = NULL
 WHERE state = 'running'
   AND locked_until IS NOT NULL
   AND locked_until < %s
RETURNING id
"""
