"""Pending bulk uploads, and dedup layers 2 and 3 checking them like entries.

The common duplicate is one WhatsApp clip saved by several brothers, who all upload it
before an admin has registered the first copy. A check against registered entries alone
lets every copy through, so submissions count too. See docs/ARCHITECTURE.md
("Revidiert 2026-10-25").

The key helpers are unit-tested; everything that is a property of Postgres -- the
constraints, the ON CONFLICT race, the cascade -- runs only against a real database.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from masdar.api.uploads import InvalidMetadata
from masdar.db.submissions import (
    PgFingerprintIndex,
    PgKnownHashes,
    PgSubmissions,
    SubmissionMetadata,
    is_submission_key,
    submission_key,
)
from masdar.dedup.fingerprint import WindowFingerprint
from masdar.domain import Attribution


def test_a_submission_key_is_distinguishable_from_an_entry_id() -> None:
    assert submission_key("abc123") == "submission:abc123"
    assert is_submission_key("submission:abc123") is True
    # Entry ids are '<scholar-id>-<6 digits>' and never contain a colon.
    assert is_submission_key("uthaymin-000421") is False


REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
SCHEMA = "masdar_subtest"

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


def windows(*names: str) -> list[WindowFingerprint]:
    return [
        WindowFingerprint(window_idx=i, offset_ms=i * 15_000, fingerprint=name.encode())
        for i, name in enumerate(names)
    ]


def seed_entry(connection: Any, entry_id: str, sha256: str, *prints: str) -> None:
    connection.execute(
        "INSERT INTO scholar (id, name_ar, name_en) VALUES ('ibn-uthaymin', 'ابن عثيمين', "
        "'Ibn Uthaymin') ON CONFLICT DO NOTHING"
    )
    connection.execute(
        "INSERT INTO entry (id, scholar_id, sha256) VALUES (%s, 'ibn-uthaymin', %s)",
        (entry_id, sha256),
    )
    for i, name in enumerate(prints):
        connection.execute(
            "INSERT INTO entry_fingerprint (entry_id, window_idx, offset_ms, fingerprint) "
            "VALUES (%s, %s, %s, %s)",
            (entry_id, i, i * 15_000, name.encode()),
        )


METADATA = SubmissionMetadata(
    contributor="Abdullah",
    scholar_id="ibn-uthaymin",
    scholar_other=None,
    topic_id=None,
    claimed_attribution=Attribution.PROBABLY,
    source_note="from the Uthaymin WhatsApp group",
    note=None,
)


@requires_database
def test_integration_a_recorded_submission_starts_awaiting_a_decision() -> None:
    with migrated_schema() as (connection, executor):
        submissions = PgSubmissions(executor)

        assert submissions.record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=windows("w0", "w1"),
            candidate_keys=[],
        )

        state = connection.execute("SELECT state FROM submission WHERE sha256 = 'aaa'")
        assert state.fetchone()[0] == "awaiting_decision"


@requires_database
def test_integration_the_second_upload_of_the_same_bytes_loses_the_race() -> None:
    # Two brothers upload the same clip at the same moment: both pass the known-hashes
    # check, only one insert may win. The loser is told, not silently merged.
    with migrated_schema() as (_, executor):
        submissions = PgSubmissions(executor)
        args = {
            "sha256": "aaa",
            "original_name": "clip.mp4",
            "duration_ms": 90_000,
            "fingerprints": windows("w0"),
            "candidate_keys": [],
        }

        assert submissions.record(staged_path=Path("/staging/1.mp4"), **args) is True
        assert submissions.record(staged_path=Path("/staging/2.mp4"), **args) is False


@requires_database
def test_integration_known_hashes_cover_entries_and_pending_submissions() -> None:
    with migrated_schema() as (connection, executor):
        seed_entry(connection, "uthaymin-000421", "entryhash")
        PgSubmissions(executor).record(
            sha256="pendinghash",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=[],
            candidate_keys=[],
        )

        assert PgKnownHashes(executor).known() == {
            "entryhash": "uthaymin-000421",
            "pendinghash": "submission:pendinghash",
        }


@requires_database
def test_integration_the_index_finds_entries_and_submissions_sharing_a_window() -> None:
    with migrated_schema() as (connection, executor):
        seed_entry(connection, "uthaymin-000421", "entryhash", "e0", "shared", "e2")
        PgSubmissions(executor).record(
            sha256="pendinghash",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=windows("shared", "s1"),
            candidate_keys=[],
        )
        index = PgFingerprintIndex(executor)

        assert index.entries_sharing_a_window([b"shared"]) == {
            "uthaymin-000421",
            "submission:pendinghash",
        }
        assert index.entries_sharing_a_window([b"nothing"]) == set()
        assert list(index.windows_of("uthaymin-000421")) == [b"e0", b"shared", b"e2"]
        assert list(index.windows_of("submission:pendinghash")) == [b"shared", b"s1"]


@requires_database
def test_integration_keeping_stores_the_contributors_claims_once() -> None:
    with migrated_schema() as (connection, executor):
        connection.execute(
            "INSERT INTO scholar (id, name_ar, name_en) VALUES ('ibn-uthaymin', 'ا', 'I')"
        )
        submissions = PgSubmissions(executor)
        submissions.record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=[],
            candidate_keys=["uthaymin-000421"],
        )

        assert submissions.keep("aaa", METADATA) is True
        # A decision is made once; a replayed request must not overwrite it.
        assert submissions.keep("aaa", METADATA) is False

        row = connection.execute(
            "SELECT state, contributor, scholar_id, claimed_attribution, source_note, "
            "candidate_keys FROM submission WHERE sha256 = 'aaa'"
        ).fetchone()
        assert row == (
            "kept",
            "Abdullah",
            "ibn-uthaymin",
            "probably",
            "from the Uthaymin WhatsApp group",
            ["uthaymin-000421"],
        )


@requires_database
def test_integration_dropping_removes_the_submission_and_its_windows() -> None:
    with migrated_schema() as (connection, executor):
        submissions = PgSubmissions(executor)
        submissions.record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=windows("w0", "w1"),
            candidate_keys=[],
        )

        assert submissions.drop("aaa") == Path("/staging/1.mp4")

        assert connection.execute("SELECT count(*) FROM submission").fetchone()[0] == 0
        assert (
            connection.execute("SELECT count(*) FROM submission_fingerprint").fetchone()[0] == 0
        )
        # Nothing left to drop: the caller must not delete a file a second time.
        assert submissions.drop("aaa") is None


@requires_database
def test_integration_a_kept_submission_cannot_be_dropped_by_a_late_request() -> None:
    with migrated_schema() as (connection, executor):
        connection.execute(
            "INSERT INTO scholar (id, name_ar, name_en) VALUES ('ibn-uthaymin', 'ا', 'I')"
        )
        submissions = PgSubmissions(executor)
        submissions.record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=[],
            candidate_keys=[],
        )
        submissions.keep("aaa", METADATA)

        assert submissions.drop("aaa") is None


@requires_database
def test_integration_a_registered_submission_must_name_its_entry() -> None:
    import psycopg

    with migrated_schema() as (connection, executor):
        PgSubmissions(executor).record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=[],
            candidate_keys=[],
        )

        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute("UPDATE submission SET state = 'registered' WHERE sha256 = 'aaa'")


@requires_database
def test_integration_a_kept_submission_must_say_whose_words_these_are() -> None:
    # The form's one required field. A kept upload with neither a known scholar nor a
    # free-text name could never be attributed, so the schema refuses it outright.
    import psycopg

    with migrated_schema() as (connection, executor):
        PgSubmissions(executor).record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=[],
            candidate_keys=[],
        )

        with pytest.raises(psycopg.errors.CheckViolation):
            connection.execute("UPDATE submission SET state = 'kept' WHERE sha256 = 'aaa'")


@requires_database
def test_integration_keeping_with_an_unknown_scholar_is_invalid_metadata() -> None:
    # A foreign-key violation, translated at the boundary: the route turns this into a
    # 422 the page can explain, instead of a 500 it cannot.
    with migrated_schema() as (connection, executor):
        submissions = PgSubmissions(executor)
        submissions.record(
            sha256="aaa",
            original_name="clip.mp4",
            staged_path=Path("/staging/1.mp4"),
            duration_ms=90_000,
            fingerprints=[],
            candidate_keys=[],
        )

        with pytest.raises(InvalidMetadata):
            submissions.keep("aaa", METADATA)  # no scholar 'ibn-uthaymin' in this schema

        state = connection.execute("SELECT state FROM submission WHERE sha256 = 'aaa'")
        assert state.fetchone()[0] == "awaiting_decision"
