"""The read surface the public library API needs, and nothing more.

This module defines a Protocol plus the plain row types that cross it. No database
driver is imported here on purpose: the Postgres implementation lives elsewhere, and
the routes are tested against an in-memory fake through a FastAPI dependency override.

The rows mirror `db/migrations/0001_init.sql`. They carry `visibility` and
`attribution` even though the Postgres implementation is expected to return public
rows only -- the route layer re-checks the publication gate, because a filter that
exists in exactly one place is a filter that gets forgotten once.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Protocol

from masdar.domain import (
    Attribution,
    ContentClass,
    Lang,
    ReviewState,
    SpanRole,
    Visibility,
)


@dataclass(frozen=True, slots=True)
class ScholarRef:
    id: str
    name_ar: str
    name_en: str


@dataclass(frozen=True, slots=True)
class ScholarRow:
    id: str
    name_ar: str
    name_en: str
    entry_count: int


@dataclass(frozen=True, slots=True)
class TopicRow:
    id: str
    parent_id: str | None
    name_ar: str
    name_en: str
    content_class: ContentClass
    entry_count: int


@dataclass(frozen=True, slots=True)
class EntryLanguageRow:
    lang: Lang
    state: ReviewState


@dataclass(frozen=True, slots=True)
class EntryRow:
    id: str
    scholar: ScholarRef
    attribution: Attribution
    visibility: Visibility
    languages: tuple[EntryLanguageRow, ...] = ()
    title_ar: str | None = None
    title_en: str | None = None
    question_ar: str | None = None
    topic_id: str | None = None
    hukm: str | None = None
    generality: str = "unclear"
    source_url: str | None = None
    recorded_on: date | None = None
    duration_sec: int | None = None
    canonical_id: str | None = None


@dataclass(frozen=True, slots=True)
class SegmentRow:
    idx: int
    t_start_ms: int
    t_end_ms: int | None
    span_role: SpanRole
    citable: bool
    text: str


@dataclass(frozen=True, slots=True)
class EntryPage:
    items: tuple[EntryRow, ...]
    total: int


class LibraryRepository(Protocol):
    """Read-only operations behind the public library routes."""

    def entry(self, entry_id: str) -> EntryRow | None:
        """One entry by id, or None. May return non-public rows; the route gates."""
        ...

    def segments(self, entry_id: str, lang: Lang) -> Sequence[SegmentRow]:
        """Transcript lines of one entry in one language, ordered by `idx`."""
        ...

    def topics(self) -> Sequence[TopicRow]:
        """Every topic, flat, with the count of its own public entries."""
        ...

    def scholars(self) -> Sequence[ScholarRow]:
        """Every scholar with at least the count of his public entries."""
        ...

    def entries_by_scholar(
        self, scholar_id: str, *, limit: int, offset: int
    ) -> EntryPage | None:
        """One page of a scholar's entries, or None if the scholar does not exist.

        `EntryPage.total` counts public entries only; an implementation that counted
        withheld ones would leak their number through the page count.
        """
        ...
