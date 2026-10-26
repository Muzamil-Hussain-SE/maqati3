"""`api.repository.LibraryRepository` over Postgres.

`entry` returns rows whatever their visibility -- the route layer gates them, on purpose
(see api/repository.py). Every *count*, though, is of published entries only: a count
of withheld ones would leak that they exist. "Published" here is the route's
`is_published`, restated as SQL: visibility public, attribution not `not_sure`, and the
Arabic approved.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from maqati3.api.repository import (
    EntryLanguageRow,
    EntryPage,
    EntryRow,
    ScholarRef,
    ScholarRow,
    SegmentRow,
    TopicRow,
)
from maqati3.db.sql import Executor
from maqati3.domain import Attribution, ContentClass, Lang, ReviewState, SpanRole, Visibility

_PUBLISHED = """
    e.visibility = 'public'
    AND e.attribution <> 'not_sure'
    AND EXISTS (SELECT 1 FROM entry_language l
                 WHERE l.entry_id = e.id AND l.lang = 'ar' AND l.state = 'approved')
"""

_ENTRY_COLUMNS = """
    e.id, e.scholar_id, s.name_ar, s.name_en, e.attribution, e.visibility,
    e.title_ar, e.title_en, e.question_ar, e.topic_id, e.hukm, e.generality,
    e.source_url, e.recorded_on, e.duration_sec, e.canonical_id
"""

_ENTRY = f"""
SELECT {_ENTRY_COLUMNS} FROM entry e JOIN scholar s ON s.id = e.scholar_id WHERE e.id = %s
"""

_LANGUAGES = "SELECT entry_id, lang, state FROM entry_language WHERE entry_id = ANY(%s)"

_SEGMENTS = """
SELECT s.idx, s.t_start_ms, s.t_end_ms, s.span_role, s.citable, t.text_raw
  FROM segment s JOIN segment_text t ON t.segment_id = s.id
 WHERE s.entry_id = %s AND t.lang = %s
 ORDER BY s.idx
"""

_TOPICS = f"""
SELECT t.id, t.parent_id, t.name_ar, t.name_en, t.content_class,
       (SELECT count(*) FROM entry e WHERE e.topic_id = t.id AND {_PUBLISHED})
  FROM topic t
 ORDER BY t.id
"""

_SCHOLARS = f"""
SELECT s.id, s.name_ar, s.name_en,
       (SELECT count(*) FROM entry e WHERE e.scholar_id = s.id AND {_PUBLISHED}) AS n
  FROM scholar s
 ORDER BY n DESC, s.name_en
"""

_SCHOLAR_EXISTS = "SELECT 1 FROM scholar WHERE id = %s"

_SCHOLAR_PAGE = f"""
SELECT {_ENTRY_COLUMNS}
  FROM entry e JOIN scholar s ON s.id = e.scholar_id
 WHERE e.scholar_id = %s AND {_PUBLISHED}
 ORDER BY e.recorded_on DESC NULLS LAST, e.id
 LIMIT %s OFFSET %s
"""

_SCHOLAR_TOTAL = f"SELECT count(*) FROM entry e WHERE e.scholar_id = %s AND {_PUBLISHED}"


def _text(value: object) -> str | None:
    return None if value is None else str(value)


class PgLibraryRepository:
    def __init__(self, executor: Executor) -> None:
        self._executor = executor

    def entry(self, entry_id: str) -> EntryRow | None:
        rows = self._executor.fetchall(_ENTRY, (entry_id,))
        if not rows:
            return None
        return self._entries(rows)[0]

    def segments(self, entry_id: str, lang: Lang) -> Sequence[SegmentRow]:
        return [
            SegmentRow(
                idx=int(str(idx)),
                t_start_ms=int(str(start)),
                t_end_ms=None if end is None else int(str(end)),
                span_role=SpanRole(str(role)),
                citable=bool(citable),
                text=str(text),
            )
            for idx, start, end, role, citable, text in self._executor.fetchall(
                _SEGMENTS, (entry_id, lang.value)
            )
        ]

    def topics(self) -> Sequence[TopicRow]:
        return [
            TopicRow(
                id=str(topic_id),
                parent_id=_text(parent_id),
                name_ar=str(name_ar),
                name_en=str(name_en),
                content_class=ContentClass(str(content_class)),
                entry_count=int(str(count)),
            )
            for topic_id, parent_id, name_ar, name_en, content_class, count in (
                self._executor.fetchall(_TOPICS)
            )
        ]

    def scholars(self) -> Sequence[ScholarRow]:
        return [
            ScholarRow(
                id=str(scholar_id),
                name_ar=str(name_ar),
                name_en=str(name_en),
                entry_count=int(str(count)),
            )
            for scholar_id, name_ar, name_en, count in self._executor.fetchall(_SCHOLARS)
        ]

    def entries_by_scholar(self, scholar_id: str, *, limit: int, offset: int) -> EntryPage | None:
        if not self._executor.fetchall(_SCHOLAR_EXISTS, (scholar_id,)):
            return None
        rows = self._executor.fetchall(_SCHOLAR_PAGE, (scholar_id, limit, offset))
        total = self._executor.fetchall(_SCHOLAR_TOTAL, (scholar_id,))[0][0]
        return EntryPage(items=tuple(self._entries(rows)), total=int(str(total)))

    def _entries(self, rows: list[tuple[object, ...]]) -> list[EntryRow]:
        ids = [str(row[0]) for row in rows]
        languages: dict[str, list[EntryLanguageRow]] = {}
        for entry_id, lang, state in self._executor.fetchall(_LANGUAGES, (ids,)):
            languages.setdefault(str(entry_id), []).append(
                EntryLanguageRow(Lang(str(lang)), ReviewState(str(state)))
            )
        entries = []
        for (
            entry_id, scholar_id, name_ar, name_en, attribution, visibility, title_ar,
            title_en, question_ar, topic_id, hukm, generality, source_url, recorded_on,
            duration_sec, canonical_id,
        ) in rows:
            entries.append(
                EntryRow(
                    id=str(entry_id),
                    scholar=ScholarRef(
                        id=str(scholar_id), name_ar=str(name_ar), name_en=str(name_en)
                    ),
                    attribution=Attribution(str(attribution)),
                    visibility=Visibility(str(visibility)),
                    languages=tuple(languages.get(str(entry_id), ())),
                    title_ar=_text(title_ar),
                    title_en=_text(title_en),
                    question_ar=_text(question_ar),
                    topic_id=_text(topic_id),
                    hukm=_text(hukm),
                    generality=str(generality),
                    source_url=_text(source_url),
                    recorded_on=recorded_on if isinstance(recorded_on, date) else None,
                    duration_sec=None if duration_sec is None else int(str(duration_sec)),
                    canonical_id=_text(canonical_id),
                )
            )
        return entries


__all__ = ["PgLibraryRepository"]
