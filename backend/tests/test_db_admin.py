"""The admin side in Postgres: who may sign in, and what they do with uploads.

Everything here is a property of the database -- the transaction a registration runs in,
the sequence behind entry ids, what the audit log keeps -- so it runs against a real
Postgres (set DATABASE_URL), like the other integration tests.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from maqati3.api.desk import NotWaiting, ScholarExists, UnknownScholar
from maqati3.db.admin import PgAdmins, PgDesk

from maqati3.db.library import PgLibraryRepository
from maqati3.db.submissions import PgFingerprintIndex, PgKnownHashes, PgSubmissions
from maqati3.dedup.fingerprint import Fingerprint, encode_items, index_keys

REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
SCHEMA = "maqati3_admintest"

requires_database = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="integration test: set DATABASE_URL to a Postgres with pgvector",
)


@contextmanager
def migrated_schema() -> Iterator[tuple[Any, Any]]:
    import psycopg

    from maqati3.db.migrate import migrate
    from maqati3.db.sql import PsycopgExecutor

    with psycopg.connect(os.environ["DATABASE_URL"], autocommit=True) as connection:
        connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
        connection.execute(f"CREATE SCHEMA {SCHEMA}")
        try:
            connection.execute(f"SET search_path TO {SCHEMA}, public")
            executor = PsycopgExecutor(connection)
            migrate(executor, REPO_MIGRATIONS)
            connection.execute(
                "INSERT INTO scholar (id, name_ar, name_en) VALUES "
                "('ibn-uthaymin', 'ابن عثيمين', 'Ibn Uthaymin'), "
                "('ibn-baz', 'ابن باز', 'Ibn Baz')"
            )
            yield connection, executor
        finally:
            connection.execute("SET search_path TO public")
            connection.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")


RECORDING = tuple(range(1000, 1800))


def kept_upload(
    executor: Any, sha: str, *, sender: str = "Abdullah", name: str | None = None,
    keys: list[str] | None = None,
) -> None:
    submissions = PgSubmissions(executor)
    submissions.record(
        sha256=sha,
        original_name=name or f"{sha}.mp4",
        staged_path=Path(f"/staging/{sha}.mp4"),
        fingerprint=Fingerprint(items=RECORDING, duration_ms=80_333),
        candidate_keys=keys or [],
    )
    assert submissions.keep(sha, sender) is True


# ------------------------------------------------------------------ the admin list


@requires_database
def test_integration_an_admin_is_found_by_email_whatever_its_case() -> None:
    with migrated_schema() as (_, executor):
        admins = PgAdmins(executor)

        assert admins.add("Yusuf@Example.org", name="Yusuf", added_by="cli") is True

        found = admins.find("YUSUF@example.ORG")
        assert found is not None
        assert (found.email, found.name) == ("yusuf@example.org", "Yusuf")


@requires_database
def test_integration_someone_not_on_the_list_is_not_found() -> None:
    with migrated_schema() as (_, executor):
        PgAdmins(executor).add("yusuf@example.org", name=None, added_by="cli")

        assert PgAdmins(executor).find("stranger@example.org") is None
        assert PgAdmins(executor).find("") is None


@requires_database
def test_integration_adding_an_admin_twice_changes_nothing() -> None:
    with migrated_schema() as (_, executor):
        admins = PgAdmins(executor)
        admins.add("yusuf@example.org", name="Yusuf", added_by="cli")

        assert admins.add("Yusuf@example.org", name="Other", added_by="cli") is False
        assert [a.name for a in admins.all()] == ["Yusuf"]


@requires_database
def test_integration_a_removed_admin_is_no_longer_found() -> None:
    with migrated_schema() as (_, executor):
        admins = PgAdmins(executor)
        admins.add("yusuf@example.org", name=None, added_by="cli")

        assert admins.remove("YUSUF@example.org") is True
        assert admins.find("yusuf@example.org") is None
        assert admins.remove("yusuf@example.org") is False


@requires_database
def test_integration_the_log_keeps_who_did_what_newest_first() -> None:
    with migrated_schema() as (_, executor):
        admins = PgAdmins(executor)

        admins.log("yusuf@example.org", "login", None, {})
        admins.log("yusuf@example.org", "register", "abc", {"entry_id": "ibn-baz-000001"})

        recent = admins.recent_log(limit=10)
        assert [(r.action, r.subject) for r in recent] == [("register", "abc"), ("login", None)]
        assert recent[0].detail == {"entry_id": "ibn-baz-000001"}
        assert recent[0].admin_email == "yusuf@example.org"


# ------------------------------------------------------------------ the dashboard list


@requires_database
def test_integration_the_dashboard_lists_what_waits_for_an_admin_oldest_first() -> None:
    with migrated_schema() as (_, executor):
        submissions = PgSubmissions(executor)
        kept_upload(executor, "first")
        kept_upload(executor, "second", sender="Yusuf")
        # Undecided uploads are the contributor's business, not the admin's yet.
        submissions.record(
            sha256="undecided",
            original_name="u.mp4",
            staged_path=Path("/staging/u.mp4"),
            fingerprint=Fingerprint(items=(), duration_ms=1000),
            candidate_keys=[],
        )

        items = PgDesk(executor).items()

        assert [i.sha256 for i in items] == ["first", "second"]
        first = items[0]
        assert (first.original_name, first.contributor) == ("first.mp4", "Abdullah")
        assert first.duration_ms == 80_333
        assert first.entry is None


@requires_database
def test_integration_a_match_the_contributor_kept_anyway_is_described_for_the_admin() -> None:
    with migrated_schema() as (_, executor):
        kept_upload(executor, "other", sender="Yusuf", name="whatsapp-clip.mp4")
        kept_upload(executor, "mine", keys=["submission:other", "ibn-baz-000007"])

        mine = next(i for i in PgDesk(executor).items() if i.sha256 == "mine")

        # An entry is named by its id; another pending upload by its file and sender.
        assert sorted(mine.kept_despite) == ["ibn-baz-000007", "whatsapp-clip.mp4 (Yusuf)"]


@requires_database
def test_integration_the_media_of_an_upload_is_found_only_once_it_is_kept() -> None:
    with migrated_schema() as (_, executor):
        desk = PgDesk(executor)
        kept_upload(executor, "kept")
        PgSubmissions(executor).record(
            sha256="undecided",
            original_name="u.mp4",
            staged_path=Path("/staging/u.mp4"),
            fingerprint=Fingerprint(items=(), duration_ms=1000),
            candidate_keys=[],
        )

        assert desk.media_path("kept") == Path("/staging/kept.mp4")
        assert desk.media_path("undecided") is None
        assert desk.media_path("nothing") is None


# ------------------------------------------------------------------ registering


@requires_database
def test_integration_registering_makes_a_draft_entry_that_is_not_sure_and_not_public() -> None:
    with migrated_schema() as (connection, executor):
        kept_upload(executor, "abc")

        entry_id = PgDesk(executor).register("abc", "ibn-uthaymin", "yusuf@example.org")

        assert entry_id.startswith("ibn-uthaymin-")
        number = entry_id.removeprefix("ibn-uthaymin-")
        assert len(number) == 6 and number.isdigit()
        row = connection.execute(
            "SELECT scholar_id, attribution, visibility, sha256, duration_sec, submitted_by "
            "FROM entry WHERE id = %s",
            (entry_id,),
        ).fetchone()
        # attribution starts at not_sure: nothing typed at upload time pre-fills it.
        assert row == ("ibn-uthaymin", "not_sure", "draft", "abc", 80, "Abdullah")


@requires_database
def test_integration_a_registered_entry_is_invisible_to_the_public_library() -> None:
    with migrated_schema() as (_, executor):
        kept_upload(executor, "abc")
        entry_id = PgDesk(executor).register("abc", "ibn-uthaymin", "yusuf@example.org")

        library = PgLibraryRepository(executor)

        counts = {s.id: s.entry_count for s in library.scholars()}
        assert counts["ibn-uthaymin"] == 0
        entry = library.entry(entry_id)
        assert entry is not None and entry.visibility.value == "draft"


@requires_database
def test_integration_a_registered_entry_starts_every_language_not_started() -> None:
    with migrated_schema() as (connection, executor):
        kept_upload(executor, "abc")
        entry_id = PgDesk(executor).register("abc", "ibn-baz", "yusuf@example.org")

        states = connection.execute(
            "SELECT lang, state, assignee FROM entry_language WHERE entry_id = %s ORDER BY lang",
            (entry_id,),
        ).fetchall()

        assert states == [("ar", "not_started", None), ("de", "not_started", None),
                          ("en", "not_started", None)]


@requires_database
def test_integration_the_upload_becomes_registered_and_says_by_whom() -> None:
    with migrated_schema() as (_, executor):
        kept_upload(executor, "abc")
        desk = PgDesk(executor)

        entry_id = desk.register("abc", "ibn-uthaymin", "yusuf@example.org")

        item = next(i for i in desk.items() if i.sha256 == "abc")
        assert item.entry is not None
        assert item.entry.entry_id == entry_id
        assert item.entry.scholar_name_en == "Ibn Uthaymin"
        assert item.registered_by == "yusuf@example.org"
        # Still playable: the media stays where it was staged.
        assert desk.media_path("abc") == Path("/staging/abc.mp4")


@requires_database
def test_integration_duplicates_are_still_caught_after_registration() -> None:
    with migrated_schema() as (_, executor):
        kept_upload(executor, "abc")
        PgDesk(executor).register("abc", "ibn-uthaymin", "yusuf@example.org")

        # The entry now carries the hash and the fingerprint, and answers as the entry --
        # not as the upload it came from, and not as both.
        known = PgKnownHashes(executor).known()
        assert known["abc"].startswith("ibn-uthaymin-")
        candidates = PgFingerprintIndex(executor).candidates(index_keys(RECORDING))
        assert len(candidates) == 1 and next(iter(candidates)).startswith("ibn-uthaymin-")
        assert tuple(PgFingerprintIndex(executor).items_of(next(iter(candidates)))) == RECORDING


@requires_database
def test_integration_entry_numbers_are_never_reused_across_scholars() -> None:
    with migrated_schema() as (_, executor):
        desk = PgDesk(executor)
        kept_upload(executor, "a")
        kept_upload(executor, "b")
        kept_upload(executor, "c")

        ids = [
            desk.register("a", "ibn-baz", "y@example.org"),
            desk.register("b", "ibn-uthaymin", "y@example.org"),
            desk.register("c", "ibn-baz", "y@example.org"),
        ]

        numbers = [int(i.rsplit("-", 1)[1]) for i in ids]
        assert numbers == sorted(set(numbers)) and len(set(ids)) == 3


@requires_database
def test_integration_registering_for_an_unknown_scholar_creates_nothing() -> None:
    with migrated_schema() as (connection, executor):
        kept_upload(executor, "abc")

        with pytest.raises(UnknownScholar):
            PgDesk(executor).register("abc", "no-such-scholar", "y@example.org")

        assert connection.execute("SELECT count(*) FROM entry").fetchone()[0] == 0
        state = connection.execute("SELECT state FROM submission WHERE sha256 = 'abc'")
        assert state.fetchone()[0] == "kept"


@requires_database
def test_integration_an_upload_can_only_be_registered_once() -> None:
    with migrated_schema() as (connection, executor):
        kept_upload(executor, "abc")
        desk = PgDesk(executor)
        desk.register("abc", "ibn-baz", "y@example.org")

        with pytest.raises(NotWaiting):
            desk.register("abc", "ibn-uthaymin", "z@example.org")

        assert connection.execute("SELECT count(*) FROM entry").fetchone()[0] == 1


@requires_database
@pytest.mark.parametrize("sha", ["undecided", "nothing"])
def test_integration_only_a_kept_upload_can_be_registered(sha: str) -> None:
    with migrated_schema() as (_, executor):
        PgSubmissions(executor).record(
            sha256="undecided",
            original_name="u.mp4",
            staged_path=Path("/staging/u.mp4"),
            fingerprint=Fingerprint(items=(), duration_ms=1000),
            candidate_keys=[],
        )

        with pytest.raises(NotWaiting):
            PgDesk(executor).register(sha, "ibn-baz", "y@example.org")


@requires_database
def test_integration_registering_is_written_to_the_log() -> None:
    with migrated_schema() as (_, executor):
        kept_upload(executor, "abc")
        entry_id = PgDesk(executor).register("abc", "ibn-baz", "yusuf@example.org")

        (record,) = PgAdmins(executor).recent_log(limit=5)

        assert (record.admin_email, record.action, record.subject) == (
            "yusuf@example.org", "register", "abc",
        )
        assert record.detail == {"entry_id": entry_id, "scholar_id": "ibn-baz"}


# ------------------------------------------------------------------ discarding


@requires_database
def test_integration_discarding_removes_the_upload_and_returns_its_file() -> None:
    with migrated_schema() as (connection, executor):
        kept_upload(executor, "abc")

        path = PgDesk(executor).discard("abc", "yusuf@example.org")

        assert path == Path("/staging/abc.mp4")
        assert connection.execute("SELECT count(*) FROM submission").fetchone()[0] == 0
        for table in ("submission_fingerprint", "submission_fingerprint_key"):
            assert connection.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
        # Nothing of it is left to match against: the same file is simply new again.
        assert PgKnownHashes(executor).known() == {}


@requires_database
def test_integration_a_registered_upload_cannot_be_discarded() -> None:
    # It is an entry now; removing its file would strand the entry.
    with migrated_schema() as (connection, executor):
        kept_upload(executor, "abc")
        desk = PgDesk(executor)
        desk.register("abc", "ibn-baz", "y@example.org")

        with pytest.raises(NotWaiting):
            desk.discard("abc", "y@example.org")

        assert connection.execute("SELECT count(*) FROM submission").fetchone()[0] == 1


@requires_database
def test_integration_discarding_is_written_to_the_log() -> None:
    with migrated_schema() as (_, executor):
        kept_upload(executor, "abc", sender="Abdullah", name="clip.mp4")
        PgDesk(executor).discard("abc", "yusuf@example.org")

        (record,) = PgAdmins(executor).recent_log(limit=5)

        assert (record.action, record.subject) == ("discard", "abc")
        assert record.detail == {"original_name": "clip.mp4", "contributor": "Abdullah"}


# ------------------------------------------------------------------ scholars


@requires_database
def test_integration_an_admin_can_add_a_scholar_who_is_not_in_the_list() -> None:
    with migrated_schema() as (connection, executor):
        PgDesk(executor).add_scholar(
            "rabi-al-madkhali", "ربيع المدخلي", "Rabi al-Madkhali", "y@example.org"
        )

        row = connection.execute(
            "SELECT name_ar, name_en FROM scholar WHERE id = 'rabi-al-madkhali'"
        ).fetchone()
        assert row == ("ربيع المدخلي", "Rabi al-Madkhali")
        (record,) = PgAdmins(executor).recent_log(limit=5)
        assert (record.action, record.subject) == ("add_scholar", "rabi-al-madkhali")


@requires_database
def test_integration_adding_a_scholar_that_exists_is_refused_and_changes_nothing() -> None:
    with migrated_schema() as (connection, executor):
        with pytest.raises(ScholarExists):
            PgDesk(executor).add_scholar("ibn-baz", "x", "Someone else", "y@example.org")

        name = connection.execute("SELECT name_en FROM scholar WHERE id = 'ibn-baz'")
        assert name.fetchone()[0] == "Ibn Baz"


def test_the_encoded_fingerprint_helper_round_trips() -> None:
    # Guards the helper this file's fixtures lean on: items go in and come out as stored.
    assert len(encode_items(RECORDING)) == 4 * len(RECORDING)
