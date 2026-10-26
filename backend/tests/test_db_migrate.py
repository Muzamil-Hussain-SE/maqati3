"""Unit tests for the migration runner.

No database: execution sits behind the Executor protocol, filled here by a fake that
records every statement it is handed.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

import pytest

from maqati3.db.migrate import (
    ChecksumMismatch,
    DuplicateMigrationVersion,
    MalformedMigrationName,
    MissingMigrationFile,
    OutOfOrderMigration,
    discover_migrations,
    migrate,
    plan,
)


def write_migration(directory: Path, filename: str, sql: str = "SELECT 1;") -> Path:
    path = directory / filename
    path.write_text(sql, encoding="utf-8")
    return path


def test_discover_migrations_orders_by_numeric_prefix_not_by_string(tmp_path: Path) -> None:
    write_migration(tmp_path, "0010_tenth.sql")
    write_migration(tmp_path, "0002_second.sql")
    write_migration(tmp_path, "0001_init.sql")

    found = discover_migrations(tmp_path)

    assert [m.version for m in found] == ["0001", "0002", "0010"]


def test_discover_migrations_unparseable_filename_raises_instead_of_skipping(
    tmp_path: Path,
) -> None:
    write_migration(tmp_path, "0001_init.sql")
    write_migration(tmp_path, "add_index.sql")

    with pytest.raises(MalformedMigrationName) as excinfo:
        discover_migrations(tmp_path)

    assert "add_index.sql" in str(excinfo.value)


def test_discover_migrations_duplicate_version_prefix_raises(tmp_path: Path) -> None:
    write_migration(tmp_path, "0001_init.sql")
    write_migration(tmp_path, "0001_also_init.sql")

    with pytest.raises(DuplicateMigrationVersion) as excinfo:
        discover_migrations(tmp_path)

    assert "0001" in str(excinfo.value)


def test_discover_migrations_records_sha256_of_file_contents(tmp_path: Path) -> None:
    body = "CREATE TABLE t (id int);\n"
    write_migration(tmp_path, "0001_init.sql", body)

    (found,) = discover_migrations(tmp_path)

    assert found.checksum == hashlib.sha256(body.encode("utf-8")).hexdigest()
    assert found.sql == body


def test_plan_applied_migration_whose_file_changed_raises_checksum_mismatch(
    tmp_path: Path,
) -> None:
    write_migration(tmp_path, "0001_init.sql", "CREATE TABLE t (id int);\n")
    discovered = discover_migrations(tmp_path)

    with pytest.raises(ChecksumMismatch) as excinfo:
        plan(discovered, applied={"0001": "a" * 64})

    message = str(excinfo.value)
    assert "0001_init.sql" in message
    assert "a" * 64 in message


def test_plan_applied_version_with_no_file_on_disk_raises(tmp_path: Path) -> None:
    write_migration(tmp_path, "0001_init.sql")
    discovered = discover_migrations(tmp_path)
    applied = {"0001": discovered[0].checksum, "0002": "b" * 64}

    with pytest.raises(MissingMigrationFile) as excinfo:
        plan(discovered, applied=applied)

    assert "0002" in str(excinfo.value)


def test_plan_unapplied_migration_older_than_the_newest_applied_one_raises(
    tmp_path: Path,
) -> None:
    write_migration(tmp_path, "0001_init.sql")
    write_migration(tmp_path, "0002_late_arrival.sql")
    write_migration(tmp_path, "0003_jobs.sql")
    discovered = discover_migrations(tmp_path)
    by_version = {m.version: m.checksum for m in discovered}
    applied = {"0001": by_version["0001"], "0003": by_version["0003"]}

    with pytest.raises(OutOfOrderMigration) as excinfo:
        plan(discovered, applied=applied)

    assert "0002_late_arrival.sql" in str(excinfo.value)


def test_plan_returns_only_unapplied_migrations_and_tolerates_numbering_gaps(
    tmp_path: Path,
) -> None:
    write_migration(tmp_path, "0001_init.sql")
    write_migration(tmp_path, "0005_jobs.sql")
    write_migration(tmp_path, "0009_chunks.sql")
    discovered = discover_migrations(tmp_path)
    applied = {"0001": discovered[0].checksum}

    pending = plan(discovered, applied=applied)

    assert [m.version for m in pending] == ["0005", "0009"]


def test_plan_on_an_empty_database_returns_every_migration_in_order(
    tmp_path: Path,
) -> None:
    write_migration(tmp_path, "0002_second.sql")
    write_migration(tmp_path, "0001_init.sql")

    pending = plan(discover_migrations(tmp_path), applied={})

    assert [m.version for m in pending] == ["0001", "0002"]


class FakeDatabaseError(Exception):
    """Stands in for whatever the driver raises."""


class FakeExecutor:
    """Records statements and transaction boundaries instead of touching a database."""

    def __init__(
        self,
        applied: Sequence[tuple[str, str]] = (),
        fail_on: str | None = None,
    ) -> None:
        self.applied = list(applied)
        self.fail_on = fail_on
        self.events: list[str] = []
        self.statements: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: Sequence[object] = ()) -> None:
        if self.fail_on is not None and self.fail_on in sql:
            raise FakeDatabaseError(f"refusing: {self.fail_on}")
        self.statements.append((sql, tuple(params)))
        self.events.append(f"execute:{sql.split(None, 3)[0:3]}")

    def fetchall(self, sql: str, params: Sequence[object] = ()) -> list[tuple[object, ...]]:
        self.statements.append((sql, tuple(params)))
        return [tuple(row) for row in self.applied]

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.events.append("begin")
        try:
            yield
        except BaseException:
            self.events.append("rollback")
            raise
        self.events.append("commit")

    def recorded_versions(self) -> list[str]:
        return [
            str(params[0])
            for sql, params in self.statements
            if "INSERT INTO schema_migrations" in sql
        ]


def test_migrate_on_empty_database_applies_every_migration_in_order(tmp_path: Path) -> None:
    write_migration(tmp_path, "0001_init.sql", "CREATE TABLE a (id int);\n")
    write_migration(tmp_path, "0002_more.sql", "CREATE TABLE b (id int);\n")
    executor = FakeExecutor()

    applied = migrate(executor, tmp_path, now=datetime(2026, 10, 20, 12, 0, tzinfo=UTC))

    assert applied == ["0001", "0002"]
    assert executor.recorded_versions() == ["0001", "0002"]
    bodies = [sql for sql, _ in executor.statements]
    assert "CREATE TABLE a (id int);\n" in bodies
    assert "CREATE TABLE b (id int);\n" in bodies


def test_migrate_second_run_applies_nothing(tmp_path: Path) -> None:
    write_migration(tmp_path, "0001_init.sql", "CREATE TABLE a (id int);\n")
    (first,) = discover_migrations(tmp_path)
    executor = FakeExecutor(applied=[("0001", first.checksum)])

    applied = migrate(executor, tmp_path)

    assert applied == []
    assert executor.recorded_versions() == []
    assert "begin" not in executor.events


def test_migrate_failing_migration_rolls_back_and_leaves_earlier_ones_applied(
    tmp_path: Path,
) -> None:
    write_migration(tmp_path, "0001_init.sql", "CREATE TABLE good (id int);\n")
    write_migration(tmp_path, "0002_broken.sql", "CREATE TABLE bad (oops);\n")
    executor = FakeExecutor(fail_on="CREATE TABLE bad")

    with pytest.raises(FakeDatabaseError):
        migrate(executor, tmp_path)

    assert executor.recorded_versions() == ["0001"]
    assert executor.events.count("commit") == 1
    assert executor.events[-1] == "rollback"


REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"

requires_database = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="integration test: set DATABASE_URL to a Postgres with pgvector",
)


@requires_database
def test_integration_repo_migrations_apply_from_scratch_and_are_idempotent() -> None:
    import psycopg

    from maqati3.db.sql import PsycopgExecutor

    schema = "maqati3_itest"
    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
        connection.execute(f"CREATE SCHEMA {schema}")
        try:
            connection.execute(f"SET search_path TO {schema}, public")
            executor = PsycopgExecutor(connection)

            first = migrate(executor, REPO_MIGRATIONS)
            assert first == [m.version for m in discover_migrations(REPO_MIGRATIONS)]

            assert migrate(executor, REPO_MIGRATIONS) == []
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(f"DROP SCHEMA IF EXISTS {schema} CASCADE")
