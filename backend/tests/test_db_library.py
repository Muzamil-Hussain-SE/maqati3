"""The Postgres side of the public library, the reference seed, and the pooled executor.

Parsing the reference files is unit-tested; everything that is a property of Postgres
runs only against a real database (set DATABASE_URL).
"""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from masdar.api.repository import EntryLanguageRow
from masdar.db.library import PgLibraryRepository
from masdar.db.seed import load_scholars, load_topics, seed_reference
from masdar.domain import Attribution, ContentClass, Lang, ReviewState, SpanRole, Visibility

REFERENCE = Path(__file__).resolve().parents[2] / "reference"


# --------------------------------------------------------------- reference parsing


def test_the_real_scholar_list_parses_and_skips_its_comment_line() -> None:
    scholars = load_scholars(REFERENCE / "scholars.csv")
    ids = [s.id for s in scholars]
    assert "ibn-uthaymin" in ids
    assert all(not i.startswith("#") for i in ids)
    assert len(ids) == len(set(ids))


def test_a_scholar_marked_as_a_body_is_not_a_person(tmp_path: Path) -> None:
    csv = tmp_path / "scholars.csv"
    csv.write_text(
        "id,name_ar,name_en,type,died_h,died_ce,note\n"
        "lajna,اللجنة الدائمة,The Permanent Committee,body,,,\n"
        "ibn-baz,ابن باز,Ibn Bāz,person,1420,1999,\n",
        encoding="utf-8",
    )
    lajna, baz = load_scholars(csv)
    assert (lajna.is_person, baz.is_person) == (False, True)
    assert (baz.died_h, baz.died_ce, lajna.died_h) == (1420, 1999, None)


def test_the_real_topic_list_parses_into_parents_and_children() -> None:
    topics = {t.id: t for t in load_topics(REFERENCE / "topics.yml")}
    assert topics["fiqh"].parent_id is None
    assert topics["fiqh.salah"].parent_id == "fiqh"
    assert topics["fiqh.salah"].name_en == "Prayer"
    assert all(t.parent_id is None or t.parent_id in topics for t in topics.values())


# --------------------------------------------------------------- against Postgres

REPO_MIGRATIONS = Path(__file__).resolve().parents[2] / "db" / "migrations"
SCHEMA = "masdar_libtest"

requires_database = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL"),
    reason="integration test: set DATABASE_URL to a Postgres with pgvector",
)


@contextmanager
def migrated_schema() -> Iterator[tuple[Any, Any]]:
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


def seed_all(executor: Any) -> None:
    seed_reference(
        executor, load_scholars(REFERENCE / "scholars.csv"), load_topics(REFERENCE / "topics.yml")
    )


def add_entry(
    connection: Any,
    entry_id: str,
    *,
    visibility: str = "public",
    attribution: str = "confirmed",
    ar_state: str | None = "approved",
    topic_id: str | None = "fiqh.salah",
) -> None:
    connection.execute(
        "INSERT INTO entry (id, scholar_id, attribution, visibility, topic_id, title_ar) "
        "VALUES (%s, 'ibn-uthaymin', %s, %s, %s, 'عنوان')",
        (entry_id, attribution, visibility, topic_id),
    )
    if ar_state is not None:
        connection.execute(
            "INSERT INTO entry_language (entry_id, lang, state) VALUES (%s, 'ar', %s)",
            (entry_id, ar_state),
        )


@requires_database
def test_integration_seeding_twice_changes_nothing_the_second_time() -> None:
    with migrated_schema() as (connection, executor):
        scholars = load_scholars(REFERENCE / "scholars.csv")
        topics = load_topics(REFERENCE / "topics.yml")

        seed_reference(executor, scholars, topics)
        seed_reference(executor, scholars, topics)

        assert connection.execute("SELECT count(*) FROM scholar").fetchone()[0] == len(scholars)
        assert connection.execute("SELECT count(*) FROM topic").fetchone()[0] == len(topics)


@requires_database
def test_integration_seeding_never_overwrites_a_content_class_set_in_the_database() -> None:
    # Which topics stay out of the index is a human decision; a re-seed from a file that
    # does not carry the field yet must not silently reopen an excluded topic.
    with migrated_schema() as (connection, executor):
        topics = load_topics(REFERENCE / "topics.yml")
        seed_reference(executor, [], topics)
        connection.execute("UPDATE topic SET content_class = 'excluded' WHERE id = 'manhaj.takfir'")

        seed_reference(executor, [], topics)

        row = connection.execute("SELECT content_class FROM topic WHERE id = 'manhaj.takfir'")
        assert row.fetchone()[0] == "excluded"


@requires_database
def test_integration_an_entry_comes_back_with_its_scholar_and_languages() -> None:
    with migrated_schema() as (connection, executor):
        seed_all(executor)
        add_entry(connection, "uthaymin-000421", ar_state="approved")
        connection.execute(
            "INSERT INTO entry_language (entry_id, lang, state) VALUES ('uthaymin-000421', 'de', "
            "'awaiting_review')"
        )

        entry = PgLibraryRepository(executor).entry("uthaymin-000421")

        assert entry is not None
        assert entry.scholar.id == "ibn-uthaymin"
        assert entry.scholar.name_en == "Ibn ʿUthaymīn"
        assert entry.attribution is Attribution.CONFIRMED
        assert entry.visibility is Visibility.PUBLIC
        assert entry.topic_id == "fiqh.salah"
        assert set(entry.languages) == {
            EntryLanguageRow(Lang.AR, ReviewState.APPROVED),
            EntryLanguageRow(Lang.DE, ReviewState.AWAITING_REVIEW),
        }
        assert PgLibraryRepository(executor).entry("nope-000000") is None


@requires_database
def test_integration_every_scholar_is_listed_even_without_entries() -> None:
    # The upload page offers this list as a dropdown: a scholar nobody has uploaded yet
    # is exactly the one that has to be selectable.
    with migrated_schema() as (connection, executor):
        scholars = load_scholars(REFERENCE / "scholars.csv")
        seed_reference(executor, scholars, load_topics(REFERENCE / "topics.yml"))
        add_entry(connection, "uthaymin-000421")
        add_entry(connection, "uthaymin-000422", visibility="held_back")

        listed = {s.id: s.entry_count for s in PgLibraryRepository(executor).scholars()}

        assert set(listed) == {s.id for s in scholars}
        # A withheld entry is not counted: the count would leak that it exists.
        assert listed["ibn-uthaymin"] == 1
        assert listed["ibn-baz"] == 0


@requires_database
def test_integration_topics_count_only_published_entries() -> None:
    with migrated_schema() as (connection, executor):
        seed_all(executor)
        add_entry(connection, "uthaymin-000001")
        add_entry(connection, "uthaymin-000002", attribution="not_sure", visibility="draft")
        add_entry(connection, "uthaymin-000003", ar_state="in_progress")
        add_entry(connection, "uthaymin-000004", visibility="held_back")

        topics = {t.id: t for t in PgLibraryRepository(executor).topics()}

        assert topics["fiqh.salah"].entry_count == 1
        assert topics["fiqh.salah"].parent_id == "fiqh"
        assert topics["fiqh"].content_class is ContentClass.OPEN


@requires_database
def test_integration_segments_come_back_in_order_in_one_language() -> None:
    with migrated_schema() as (connection, executor):
        seed_all(executor)
        add_entry(connection, "uthaymin-000421")
        for idx, start, role, ar, de in [
            (1, 3200, "scholar_own", "هذا جائز", "Das ist erlaubt"),
            (0, 0, "questioner", "ما حكم كذا؟", "Was ist das Urteil?"),
        ]:
            seg = connection.execute(
                "INSERT INTO segment (entry_id, idx, t_start_ms, span_role, citable) "
                "VALUES ('uthaymin-000421', %s, %s, %s, true) RETURNING id",
                (idx, start, role),
            ).fetchone()[0]
            for lang, text in (("ar", ar), ("de", de)):
                connection.execute(
                    "INSERT INTO segment_text (segment_id, lang, text_raw, provenance) "
                    "VALUES (%s, %s, %s, 'human')",
                    (seg, lang, text),
                )

        segments = PgLibraryRepository(executor).segments("uthaymin-000421", Lang.AR)

        assert [(s.idx, s.text, s.span_role) for s in segments] == [
            (0, "ما حكم كذا؟", SpanRole.QUESTIONER),
            (1, "هذا جائز", SpanRole.SCHOLAR_OWN),
        ]


@requires_database
def test_integration_a_page_of_a_scholars_entries_counts_published_only() -> None:
    with migrated_schema() as (connection, executor):
        seed_all(executor)
        for n in range(1, 4):
            add_entry(connection, f"uthaymin-00000{n}")
        add_entry(connection, "uthaymin-000009", visibility="held_back")
        repository = PgLibraryRepository(executor)

        page = repository.entries_by_scholar("ibn-uthaymin", limit=2, offset=0)

        assert page is not None
        assert page.total == 3
        assert len(page.items) == 2
        assert repository.entries_by_scholar("no-such-scholar", limit=2, offset=0) is None


@requires_database
def test_integration_the_pooled_executor_lets_only_one_of_two_racing_uploads_win() -> None:
    # The race the submission primary key exists for, run the way the server runs it:
    # two request threads, each with its own pooled connection and transaction.
    from psycopg_pool import ConnectionPool

    from masdar.db.sql import PooledExecutor
    from masdar.db.submissions import PgSubmissions
    from masdar.dedup.fingerprint import Fingerprint

    with migrated_schema():
        url = os.environ["DATABASE_URL"]
        pool = ConnectionPool(
            url, open=True, min_size=2, max_size=4, kwargs={"options": f"-c search_path={SCHEMA},public"}
        )
        try:
            submissions = PgSubmissions(PooledExecutor(pool))
            barrier = threading.Barrier(2)
            results: list[bool] = []

            def upload(n: int) -> None:
                barrier.wait()
                results.append(
                    submissions.record(
                        sha256="samebytes",
                        original_name=f"copy{n}.mp4",
                        staged_path=Path(f"/staging/{n}.mp4"),
                        fingerprint=Fingerprint(items=tuple(range(100)), duration_ms=12_000),
                        candidate_keys=[],
                    )
                )

            threads = [threading.Thread(target=upload, args=(n,)) for n in (1, 2)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            assert sorted(results) == [False, True]
        finally:
            pool.close()
