"""Forward-only migration runner.

Execution sits behind the Executor protocol in `masdar.db.sql`, so planning and ordering
are unit-testable without a database.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from masdar.db.sql import (
    CREATE_SCHEMA_MIGRATIONS,
    INSERT_APPLIED_MIGRATION,
    SELECT_APPLIED_MIGRATIONS,
    Executor,
)

MIGRATION_FILENAME = re.compile(r"^(?P<version>\d+)_(?P<slug>[A-Za-z0-9_\-]+)\.sql$")


class MigrationError(Exception):
    """Base for every condition that must stop a migration run."""


class MalformedMigrationName(MigrationError):
    """A .sql file in the migrations directory has no `NNNN_slug.sql` name.

    Skipping it silently would mean a migration that never runs and never complains.
    """


class DuplicateMigrationVersion(MigrationError):
    """Two files claim the same version prefix, so the applied set is ambiguous."""


class ChecksumMismatch(MigrationError):
    """An already applied migration's file no longer matches what was recorded.

    Editing an applied migration means the database and the repository have silently
    diverged: every environment that migrated earlier is now running different SQL.
    This is an error, never a warning.
    """


class MissingMigrationFile(MigrationError):
    """schema_migrations records a version that has no file in the repository."""


class OutOfOrderMigration(MigrationError):
    """An unapplied migration sorts before one that already ran.

    Applying it now would produce a schema no other environment ever had: the later
    migration was written against a database this one had not yet touched.
    """


@dataclass(frozen=True)
class Migration:
    """One migration file on disk."""

    version: str
    path: Path
    sql: str
    checksum: str

    @property
    def name(self) -> str:
        return self.path.name


def checksum_of(sql: str) -> str:
    """sha256 of the migration body, as stored in schema_migrations.checksum."""
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def discover_migrations(directory: Path) -> list[Migration]:
    """Return every migration in `directory`, ordered by numeric version prefix."""
    found: list[Migration] = []
    for path in sorted(directory.glob("*.sql")):
        match = MIGRATION_FILENAME.match(path.name)
        if match is None:
            raise MalformedMigrationName(
                f"{path.name}: migration filenames must look like 0001_init.sql"
            )
        sql = path.read_text(encoding="utf-8")
        found.append(
            Migration(
                version=match.group("version"),
                path=path,
                sql=sql,
                checksum=checksum_of(sql),
            )
        )
    ordered = sorted(found, key=lambda m: int(m.version))
    _reject_duplicate_versions(ordered)
    return ordered


def _reject_duplicate_versions(ordered: list[Migration]) -> None:
    seen: dict[str, Path] = {}
    for migration in ordered:
        previous = seen.get(migration.version)
        if previous is not None:
            raise DuplicateMigrationVersion(
                f"version {migration.version} is claimed by both "
                f"{previous.name} and {migration.name}"
            )
        seen[migration.version] = migration.path


def plan(
    discovered: Sequence[Migration], applied: Mapping[str, str]
) -> list[Migration]:
    """Return the migrations still to apply, in order, or raise if the set is unsound."""
    for migration in discovered:
        recorded = applied.get(migration.version)
        if recorded is not None and recorded != migration.checksum:
            raise ChecksumMismatch(
                f"{migration.name} was applied as {recorded} but now hashes to "
                f"{migration.checksum}; an applied migration must never be edited"
            )
    known = {m.version for m in discovered}
    for version in sorted(applied, key=int):
        if version not in known:
            raise MissingMigrationFile(
                f"version {version} is recorded as applied but has no file on disk"
            )

    pending = [m for m in discovered if m.version not in applied]
    if applied:
        newest_applied = max(int(v) for v in applied)
        for migration in pending:
            if int(migration.version) < newest_applied:
                raise OutOfOrderMigration(
                    f"{migration.name} is unapplied but sorts before applied version "
                    f"{newest_applied:04d}; renumber it above the newest applied migration"
                )
    return pending


def ensure_migrations_table(executor: Executor) -> None:
    """Create schema_migrations if it is not there yet."""
    executor.execute(CREATE_SCHEMA_MIGRATIONS)


def applied_migrations(executor: Executor) -> dict[str, str]:
    """Return version -> checksum for everything schema_migrations records."""
    rows = executor.fetchall(SELECT_APPLIED_MIGRATIONS)
    return {str(version): str(checksum) for version, checksum in rows}


def migrate(
    executor: Executor, directory: Path, *, now: datetime | None = None
) -> list[str]:
    """Apply every pending migration in order and return the versions applied."""
    stamp = now if now is not None else datetime.now(UTC)
    ensure_migrations_table(executor)
    pending = plan(discover_migrations(directory), applied_migrations(executor))

    done: list[str] = []
    for migration in pending:
        # One transaction per migration: a failure leaves that migration entirely
        # unapplied and everything before it committed.
        with executor.transaction():
            executor.execute(migration.sql)
            executor.execute(
                INSERT_APPLIED_MIGRATION,
                (migration.version, stamp, migration.checksum),
            )
        done.append(migration.version)
    return done
