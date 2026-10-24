"""Response models, and the shaping that turns repository rows into them.

Nothing here reaches outside; everything takes rows from `repository` and returns
plain data. The one rule the models enforce by construction: an entry can never be
serialised without its scholar and its attribution.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date

from pydantic import BaseModel, Field

from masdar.api.repository import (
    EntryRow,
    ScholarRef,
    ScholarRow,
    SegmentRow,
    TopicRow,
)
from masdar.domain import (
    Attribution,
    ContentClass,
    Lang,
    ReviewState,
    SpanRole,
)


class ScholarOut(BaseModel):
    id: str
    name_ar: str
    name_en: str

    @classmethod
    def of(cls, scholar: ScholarRef) -> ScholarOut:
        return cls(id=scholar.id, name_ar=scholar.name_ar, name_en=scholar.name_en)


class EntryOut(BaseModel):
    """Metadata of one entry.

    `scholar` and `attribution` are required fields, not optional ones: a client must
    never be handed a text it could display without saying whose words it is and how
    sure we are of that.
    """

    id: str
    scholar: ScholarOut
    attribution: Attribution
    available_languages: list[Lang] = Field(default_factory=list)
    title_ar: str | None = None
    title_en: str | None = None
    question_ar: str | None = None
    topic_id: str | None = None
    hukm: str | None = None
    generality: str = "unclear"
    source_url: str | None = None
    recorded_on: date | None = None
    duration_sec: int | None = None
    #: Set when this recording is a near-duplicate of another entry. Variants are
    #: linked, never deleted, so the client can point at the canonical one.
    canonical_id: str | None = None

    @classmethod
    def of(cls, entry: EntryRow) -> EntryOut:
        return cls(
            id=entry.id,
            scholar=ScholarOut.of(entry.scholar),
            attribution=entry.attribution,
            available_languages=approved_languages(entry),
            title_ar=entry.title_ar,
            title_en=entry.title_en,
            question_ar=entry.question_ar,
            topic_id=entry.topic_id,
            hukm=entry.hukm,
            generality=entry.generality,
            source_url=entry.source_url,
            recorded_on=entry.recorded_on,
            duration_sec=entry.duration_sec,
            canonical_id=entry.canonical_id,
        )


def approved_languages(entry: EntryRow) -> list[Lang]:
    """The languages whose transcript has been through review and may be shown."""
    return [
        language.lang
        for language in entry.languages
        if language.state is ReviewState.APPROVED
    ]


class SegmentOut(BaseModel):
    """One line of the transcript.

    `t_start_ms` is always present, never optional: the deep link to the second is the
    product, and a segment that cannot say where it starts cannot be linked to.
    `span_role` travels with the text so a client can mark a line that is the
    questioner's or a position the scholar is about to reject.
    """

    idx: int
    t_start_ms: int
    t_end_ms: int | None = None
    span_role: SpanRole
    citable: bool
    text: str

    @classmethod
    def of(cls, segment: SegmentRow) -> SegmentOut:
        return cls(
            idx=segment.idx,
            t_start_ms=segment.t_start_ms,
            t_end_ms=segment.t_end_ms,
            span_role=segment.span_role,
            citable=segment.citable,
            text=segment.text,
        )


class TranscriptOut(BaseModel):
    """A transcript never travels without whose words it is."""

    entry_id: str
    scholar: ScholarOut
    attribution: Attribution
    lang: Lang
    segments: list[SegmentOut]

    @classmethod
    def of(
        cls, entry: EntryRow, lang: Lang, segments: Iterable[SegmentRow]
    ) -> TranscriptOut:
        return cls(
            entry_id=entry.id,
            scholar=ScholarOut.of(entry.scholar),
            attribution=entry.attribution,
            lang=lang,
            segments=[SegmentOut.of(segment) for segment in segments],
        )


class TopicNode(BaseModel):
    """A topic in the browse tree.

    `entry_count` is the topic's own entries, `total_entry_count` includes its
    children -- a parent whose own count is zero still has to show how much sits
    beneath it, or the tree looks empty at the level people start from.
    """

    id: str
    parent_id: str | None
    name_ar: str
    name_en: str
    content_class: ContentClass
    entry_count: int
    total_entry_count: int
    children: list[TopicNode] = Field(default_factory=list)

    @classmethod
    def of(cls, topic: TopicRow, children: list[TopicNode]) -> TopicNode:
        return cls(
            id=topic.id,
            parent_id=topic.parent_id,
            name_ar=topic.name_ar,
            name_en=topic.name_en,
            content_class=topic.content_class,
            entry_count=topic.entry_count,
            total_entry_count=topic.entry_count
            + sum(child.total_entry_count for child in children),
            children=children,
        )


class ScholarListItem(BaseModel):
    """A scholar as the index page shows him: name plus how much is on file."""

    id: str
    name_ar: str
    name_en: str
    entry_count: int

    @classmethod
    def of(cls, scholar: ScholarRow) -> ScholarListItem:
        return cls(
            id=scholar.id,
            name_ar=scholar.name_ar,
            name_en=scholar.name_en,
            entry_count=scholar.entry_count,
        )


class EntryPageOut(BaseModel):
    """One page of a scholar's entries.

    `total` is the repository's count, not `len(items)`: the route drops anything that
    is not public as a backstop, and a page that silently renumbered itself would make
    paging through a scholar's work inconsistent.
    """

    items: list[EntryOut]
    total: int
    limit: int
    offset: int


#: Length given to a final cue whose segment has no end time. The timeline comes from
#: the ASR run, which occasionally leaves the last `t_end_ms` empty; a cue without an
#: end is not valid WebVTT, so the last line gets a short fixed tail rather than being
#: dropped from the player.
DEFAULT_FINAL_CUE_MS = 3000

#: Shortest end-minus-start a cue may have. WebVTT requires the end to be strictly
#: after the start and browsers drop a cue that is not, silently: the line disappears
#: from the player while `GET /transcript` still returns it. Two segments can share a
#: `t_start_ms` after a human correction, and a stored `t_end_ms` can sit before its
#: start, so the renderer clamps instead of trusting the row.
MIN_CUE_MS = 1


def format_vtt_timestamp(milliseconds: int) -> str:
    """`HH:MM:SS.mmm`, the only timestamp form WebVTT accepts with hours."""
    seconds, millis = divmod(milliseconds, 1000)
    minutes, secs = divmod(seconds, 60)
    hours, mins = divmod(minutes, 60)
    return f"{hours:02d}:{mins:02d}:{secs:02d}.{millis:03d}"


def render_webvtt(segments: Sequence[SegmentRow]) -> str:
    """Serialise transcript lines as WebVTT for the player's track element."""
    cues: list[str] = []
    for position, segment in enumerate(segments):
        following = segments[position + 1] if position + 1 < len(segments) else None
        end_ms = segment.t_end_ms
        if end_ms is None:
            end_ms = (
                following.t_start_ms
                if following is not None
                else segment.t_start_ms + DEFAULT_FINAL_CUE_MS
            )
        end_ms = max(end_ms, segment.t_start_ms + MIN_CUE_MS)
        text = "\n".join(line.strip() for line in segment.text.splitlines() if line.strip())
        start = format_vtt_timestamp(segment.t_start_ms)
        stop = format_vtt_timestamp(end_ms)
        cues.append(f"{start} --> {stop}\n{text}")
    return "WEBVTT\n\n" + "".join(f"{cue}\n\n" for cue in cues)


def build_topic_tree(topics: Sequence[TopicRow]) -> list[TopicNode]:
    """Nest the flat topic rows into the browse tree, however deep they nest.

    `reference/topics.yml` is two levels today, but `topic.parent_id` is an
    unconstrained self-reference, so the shape is decided by the data and not by this
    function. Two rules keep a malformed parent chain visible instead of silent:

    * A topic whose `parent_id` names a topic that is not in the result is kept as a
      root. A missing branch is far worse than a flat one, because nothing about it
      is visible.
    * A cycle degrades to flat roots. Its members are reachable from no root at all,
      so a root-first walk alone would return an empty tree and the library would
      look empty; they are appended without children rather than dropped.
    """
    known = {topic.id for topic in topics}
    children_of: dict[str, list[TopicRow]] = {}
    roots: list[TopicRow] = []
    for topic in topics:
        parent_id = topic.parent_id
        if parent_id is not None and parent_id != topic.id and parent_id in known:
            children_of.setdefault(parent_id, []).append(topic)
        else:
            roots.append(topic)

    nested: set[str] = set()

    def node(topic: TopicRow, ancestors: frozenset[str]) -> TopicNode:
        nested.add(topic.id)
        trail = ancestors | {topic.id}
        return TopicNode.of(
            topic,
            [
                node(child, trail)
                for child in children_of.get(topic.id, [])
                if child.id not in trail
            ],
        )

    tree = [node(topic, frozenset()) for topic in roots]
    tree.extend(TopicNode.of(topic, []) for topic in topics if topic.id not in nested)
    return tree
