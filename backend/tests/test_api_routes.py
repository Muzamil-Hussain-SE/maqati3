"""Route-level tests for the public library API.

The API is tested against a dumb in-memory repository: it returns exactly the rows it
was given and enforces nothing. Every publication gate therefore has to be enforced by
the route layer for these tests to pass, which is the point.
"""

from __future__ import annotations

from collections.abc import Sequence

from fastapi.testclient import TestClient

from masdar.api.app import create_app
from masdar.api.repository import (
    Attribution,
    ContentClass,
    EntryLanguageRow,
    EntryPage,
    EntryRow,
    Lang,
    ReviewState,
    ScholarRef,
    ScholarRow,
    SegmentRow,
    SpanRole,
    TopicRow,
    Visibility,
)

UTHAYMIN = ScholarRef(id="ibn-uthaymin", name_ar="ابن عثيمين", name_en="Ibn ʿUthaymīn")


class FakeRepository:
    """Returns what it was given and enforces nothing.

    Deliberately dumb: if a gate is missing from the route layer, a test that feeds this
    fake a held-back entry will see that entry come out of the API.
    """

    def __init__(
        self,
        *,
        entries: Sequence[EntryRow] = (),
        segments: dict[tuple[str, Lang], Sequence[SegmentRow]] | None = None,
        scholars: Sequence[ScholarRow] = (),
        topics: Sequence[TopicRow] = (),
        pages: dict[str, EntryPage] | None = None,
    ) -> None:
        self._entries = {entry.id: entry for entry in entries}
        self._segments = segments or {}
        self._scholars = list(scholars)
        self._topics = list(topics)
        self._pages = pages or {}
        self.page_calls: list[tuple[str, int, int]] = []

    def entry(self, entry_id: str) -> EntryRow | None:
        return self._entries.get(entry_id)

    def segments(self, entry_id: str, lang: Lang) -> Sequence[SegmentRow]:
        return self._segments.get((entry_id, lang), ())

    def scholars(self) -> Sequence[ScholarRow]:
        return self._scholars

    def topics(self) -> Sequence[TopicRow]:
        return self._topics

    def entries_by_scholar(
        self, scholar_id: str, *, limit: int, offset: int
    ) -> EntryPage | None:
        self.page_calls.append((scholar_id, limit, offset))
        return self._pages.get(scholar_id)


def make_entry(
    entry_id: str = "uthaymin-000421",
    *,
    visibility: Visibility = Visibility.PUBLIC,
    attribution: Attribution = Attribution.CONFIRMED,
    languages: tuple[EntryLanguageRow, ...] = (
        EntryLanguageRow(Lang.AR, ReviewState.APPROVED),
    ),
    **kwargs: object,
) -> EntryRow:
    return EntryRow(
        id=entry_id,
        scholar=UTHAYMIN,
        attribution=attribution,
        visibility=visibility,
        languages=languages,
        **kwargs,  # type: ignore[arg-type]
    )


def client_for(**kwargs: object) -> TestClient:
    return TestClient(create_app(FakeRepository(**kwargs)))  # type: ignore[arg-type]


def test_health_returns_ok() -> None:
    client = TestClient(create_app(None))  # type: ignore[arg-type]

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# --------------------------------------------------------------- entry: the gate


def test_entry_held_back_is_not_reachable() -> None:
    held_back = make_entry("uthaymin-000421", visibility=Visibility.HELD_BACK)

    response = client_for(entries=[held_back]).get("/api/v1/entries/uthaymin-000421")

    assert response.status_code == 404
    assert response.json() == {"detail": "entry_not_found"}


def test_entry_draft_is_not_reachable() -> None:
    draft = make_entry("uthaymin-000421", visibility=Visibility.DRAFT)

    response = client_for(entries=[draft]).get("/api/v1/entries/uthaymin-000421")

    assert response.status_code == 404


def test_entry_withheld_is_indistinguishable_from_entry_that_never_existed() -> None:
    held_back = make_entry("uthaymin-000421", visibility=Visibility.HELD_BACK)
    client = client_for(entries=[held_back])

    withheld = client.get("/api/v1/entries/uthaymin-000421")
    unknown = client.get("/api/v1/entries/uthaymin-999999")

    assert (withheld.status_code, withheld.json()) == (unknown.status_code, unknown.json())


def test_entry_public_returns_its_metadata() -> None:
    entry = make_entry("uthaymin-000421", title_ar="حكم الصلاة", duration_sec=184)

    body = client_for(entries=[entry]).get("/api/v1/entries/uthaymin-000421").json()

    assert body["id"] == "uthaymin-000421"
    assert body["title_ar"] == "حكم الصلاة"
    assert body["duration_sec"] == 184


def test_entry_response_always_carries_scholar_and_attribution() -> None:
    entry = make_entry(attribution=Attribution.PROBABLY)

    body = client_for(entries=[entry]).get("/api/v1/entries/uthaymin-000421").json()

    assert body["attribution"] == "probably"
    assert body["scholar"] == {
        "id": "ibn-uthaymin",
        "name_ar": "ابن عثيمين",
        "name_en": "Ibn ʿUthaymīn",
    }


def test_entry_lists_only_approved_languages_as_available() -> None:
    entry = make_entry(
        languages=(
            EntryLanguageRow(Lang.AR, ReviewState.APPROVED),
            EntryLanguageRow(Lang.DE, ReviewState.AWAITING_REVIEW),
            EntryLanguageRow(Lang.EN, ReviewState.NOT_STARTED),
        )
    )

    body = client_for(entries=[entry]).get("/api/v1/entries/uthaymin-000421").json()

    assert body["available_languages"] == ["ar"]


# --------------------------------------------------------------- transcript: the gate


def test_transcript_in_unapproved_language_is_not_served() -> None:
    entry = make_entry(
        languages=(
            EntryLanguageRow(Lang.AR, ReviewState.APPROVED),
            EntryLanguageRow(Lang.DE, ReviewState.AWAITING_REVIEW),
        )
    )
    draft = SegmentRow(0, 0, 4000, SpanRole.SCHOLAR_OWN, True, "Unreviewed German draft")
    client = client_for(
        entries=[entry], segments={("uthaymin-000421", Lang.DE): [draft]}
    )

    response = client.get("/api/v1/entries/uthaymin-000421/transcript", params={"lang": "de"})

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "transcript_not_available"
    assert "Unreviewed German draft" not in response.text


def test_transcript_refusal_names_the_languages_that_are_available() -> None:
    entry = make_entry(
        languages=(
            EntryLanguageRow(Lang.AR, ReviewState.APPROVED),
            EntryLanguageRow(Lang.EN, ReviewState.APPROVED),
            EntryLanguageRow(Lang.DE, ReviewState.NEEDS_FIXES),
        )
    )

    body = (
        client_for(entries=[entry])
        .get("/api/v1/entries/uthaymin-000421/transcript", params={"lang": "de"})
        .json()
    )

    assert body["detail"]["requested_lang"] == "de"
    assert body["detail"]["available_languages"] == ["ar", "en"]


def test_transcript_of_a_withheld_entry_is_not_served() -> None:
    entry = make_entry(visibility=Visibility.HELD_BACK)
    segment = SegmentRow(0, 0, 4000, SpanRole.SCHOLAR_OWN, True, "withheld text")
    client = client_for(
        entries=[entry], segments={("uthaymin-000421", Lang.AR): [segment]}
    )

    response = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "ar"}
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "entry_not_found"}


def test_transcript_with_an_unknown_language_is_rejected() -> None:
    client = client_for(entries=[make_entry()])

    response = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "fr"}
    )

    assert response.status_code == 422


def test_transcript_returns_the_segments_of_the_approved_language() -> None:
    entry = make_entry()
    segments = [
        SegmentRow(0, 0, 3200, SpanRole.QUESTIONER, False, "ما حكم كذا؟"),
        SegmentRow(1, 3200, 9100, SpanRole.SCHOLAR_OWN, True, "هذا جائز"),
    ]
    client = client_for(
        entries=[entry], segments={("uthaymin-000421", Lang.AR): segments}
    )

    body = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "ar"}
    ).json()

    assert [segment["text"] for segment in body["segments"]] == ["ما حكم كذا؟", "هذا جائز"]


def test_every_transcript_segment_carries_its_start_time() -> None:
    segments = [
        SegmentRow(0, 0, 3200, SpanRole.QUESTIONER, False, "ما حكم كذا؟"),
        SegmentRow(1, 3200, 9100, SpanRole.SCHOLAR_OWN, True, "هذا جائز"),
    ]
    client = client_for(
        entries=[make_entry()], segments={("uthaymin-000421", Lang.AR): segments}
    )

    body = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "ar"}
    ).json()

    assert [segment["t_start_ms"] for segment in body["segments"]] == [0, 3200]


def test_every_transcript_segment_carries_its_span_role() -> None:
    segments = [
        SegmentRow(0, 0, 3200, SpanRole.QUESTIONER, False, "ما حكم كذا؟"),
        SegmentRow(1, 3200, 9100, SpanRole.SCHOLAR_OWN, True, "هذا جائز"),
    ]
    client = client_for(
        entries=[make_entry()], segments={("uthaymin-000421", Lang.AR): segments}
    )

    body = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "ar"}
    ).json()

    assert [segment["span_role"] for segment in body["segments"]] == [
        "questioner",
        "scholar_own",
    ]


def test_transcript_response_carries_scholar_and_attribution() -> None:
    client = client_for(entries=[make_entry(attribution=Attribution.PROBABLY)])

    body = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "ar"}
    ).json()

    assert body["attribution"] == "probably"
    assert body["scholar"]["id"] == "ibn-uthaymin"


# --------------------------------------------------------------- webvtt export

CUE_SEGMENTS = [
    SegmentRow(0, 0, 3200, SpanRole.QUESTIONER, False, "ما حكم كذا؟"),
    SegmentRow(1, 3200, 3_725_400, SpanRole.SCHOLAR_OWN, True, "هذا جائز"),
]


def vtt_client(**kwargs: object) -> TestClient:
    kwargs.setdefault("segments", {("uthaymin-000421", Lang.AR): CUE_SEGMENTS})
    return client_for(**kwargs)


def test_vtt_of_an_unapproved_language_is_not_served() -> None:
    entry = make_entry(languages=(EntryLanguageRow(Lang.AR, ReviewState.APPROVED),))
    client = vtt_client(
        entries=[entry],
        segments={("uthaymin-000421", Lang.DE): [
            SegmentRow(0, 0, 3200, SpanRole.SCHOLAR_OWN, True, "Unreviewed German draft")
        ]},
    )

    response = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "de"}
    )

    assert response.status_code == 404
    assert response.json()["detail"]["error"] == "transcript_not_available"
    assert "Unreviewed German draft" not in response.text


def test_vtt_starts_with_the_webvtt_header() -> None:
    client = vtt_client(entries=[make_entry()])

    response = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    )

    assert response.status_code == 200
    assert response.text.startswith("WEBVTT\n\n")


def test_vtt_writes_timestamps_as_hours_minutes_seconds_millis() -> None:
    client = vtt_client(entries=[make_entry()])

    text = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    ).text

    assert "00:00:00.000 --> 00:00:03.200" in text
    assert "00:00:03.200 --> 01:02:05.400" in text


def test_vtt_separates_cues_by_a_blank_line() -> None:
    client = vtt_client(entries=[make_entry()])

    text = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    ).text

    assert text == (
        "WEBVTT\n"
        "\n"
        "00:00:00.000 --> 00:00:03.200\n"
        "ما حكم كذا؟\n"
        "\n"
        "00:00:03.200 --> 01:02:05.400\n"
        "هذا جائز\n"
        "\n"
    )


def test_vtt_cue_without_end_time_runs_until_the_next_cue() -> None:
    segments = [
        SegmentRow(0, 0, None, SpanRole.SCHOLAR_OWN, True, "first"),
        SegmentRow(1, 4500, 9000, SpanRole.SCHOLAR_OWN, True, "second"),
    ]
    client = client_for(
        entries=[make_entry()], segments={("uthaymin-000421", Lang.AR): segments}
    )

    text = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    ).text

    assert "00:00:00.000 --> 00:00:04.500" in text


def test_vtt_last_cue_without_end_time_gets_a_fixed_tail() -> None:
    segments = [SegmentRow(0, 60_000, None, SpanRole.SCHOLAR_OWN, True, "last")]
    client = client_for(
        entries=[make_entry()], segments={("uthaymin-000421", Lang.AR): segments}
    )

    text = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    ).text

    assert "00:01:00.000 --> 00:01:03.000" in text


def test_vtt_cue_sharing_a_start_with_the_next_one_still_has_a_duration() -> None:
    # A cue whose end is not after its start is discarded by the browser without any
    # error, so the line vanishes from the player while GET /transcript still has it.
    segments = [
        SegmentRow(0, 5000, None, SpanRole.SCHOLAR_OWN, True, "first"),
        SegmentRow(1, 5000, 9000, SpanRole.SCHOLAR_OWN, True, "second"),
    ]
    client = client_for(
        entries=[make_entry()], segments={("uthaymin-000421", Lang.AR): segments}
    )

    text = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    ).text

    assert "00:00:05.000 --> 00:00:05.001" in text


def test_vtt_cue_with_a_stored_end_before_its_start_still_has_a_duration() -> None:
    segments = [SegmentRow(0, 9000, 4000, SpanRole.SCHOLAR_OWN, True, "reversed")]
    client = client_for(
        entries=[make_entry()], segments={("uthaymin-000421", Lang.AR): segments}
    )

    text = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    ).text

    assert "00:00:09.000 --> 00:00:09.001" in text


def test_vtt_is_served_as_text_vtt() -> None:
    client = vtt_client(entries=[make_entry()])

    response = client.get(
        "/api/v1/entries/uthaymin-000421/transcript.vtt", params={"lang": "ar"}
    )

    assert response.headers["content-type"] == "text/vtt; charset=utf-8"


# --------------------------------------------------------------- scholars


def test_entries_of_an_unknown_scholar_are_not_found() -> None:
    client = client_for(pages={})

    response = client.get("/api/v1/scholars/nobody/entries")

    assert response.status_code == 404
    assert response.json() == {"detail": "scholar_not_found"}


def test_entry_list_rejects_a_limit_above_the_maximum() -> None:
    page = EntryPage(items=(), total=0)
    client = client_for(pages={"ibn-uthaymin": page})

    response = client.get(
        "/api/v1/scholars/ibn-uthaymin/entries", params={"limit": 1000}
    )

    assert response.status_code == 422


def test_entry_list_drops_an_entry_that_is_not_public() -> None:
    page = EntryPage(
        items=(
            make_entry("uthaymin-000421"),
            make_entry("uthaymin-000422", visibility=Visibility.HELD_BACK),
        ),
        total=2,
    )
    client = client_for(pages={"ibn-uthaymin": page})

    body = client.get("/api/v1/scholars/ibn-uthaymin/entries").json()

    assert [item["id"] for item in body["items"]] == ["uthaymin-000421"]


def test_entry_list_passes_limit_and_offset_to_the_repository() -> None:
    repository = FakeRepository(pages={"ibn-uthaymin": EntryPage(items=(), total=0)})
    client = TestClient(create_app(repository))  # type: ignore[arg-type]

    client.get(
        "/api/v1/scholars/ibn-uthaymin/entries", params={"limit": 25, "offset": 50}
    )

    assert repository.page_calls == [("ibn-uthaymin", 25, 50)]


def test_entry_list_keeps_the_repository_total_when_it_drops_an_entry() -> None:
    page = EntryPage(
        items=(make_entry("uthaymin-000421"),),
        total=7,
    )
    client = client_for(pages={"ibn-uthaymin": page})

    body = client.get("/api/v1/scholars/ibn-uthaymin/entries").json()

    assert (body["total"], body["limit"], body["offset"]) == (7, 50, 0)


def test_scholars_are_listed_with_their_entry_count() -> None:
    scholars = [
        ScholarRow("ibn-uthaymin", "ابن عثيمين", "Ibn ʿUthaymīn", 412),
        ScholarRow("ibn-baz", "ابن باز", "Ibn Bāz", 87),
    ]

    body = client_for(scholars=scholars).get("/api/v1/scholars").json()

    assert body == [
        {"id": "ibn-uthaymin", "name_ar": "ابن عثيمين", "name_en": "Ibn ʿUthaymīn",
         "entry_count": 412},
        {"id": "ibn-baz", "name_ar": "ابن باز", "name_en": "Ibn Bāz", "entry_count": 87},
    ]


# --------------------------------------------------------------- topics


def test_topic_with_an_unknown_parent_is_kept_as_a_root() -> None:
    # Dropping it would make a whole branch of the library invisible without any error.
    topics = [
        TopicRow("fiqh", None, "فقه", "Fiqh", ContentClass.OPEN, 2),
        TopicRow("fiqh.hajj", "missing", "حج", "Hajj", ContentClass.OPEN, 5),
    ]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert [node["id"] for node in body] == ["fiqh", "fiqh.hajj"]


def test_topics_are_returned_as_a_two_level_tree() -> None:
    topics = [
        TopicRow("fiqh", None, "فقه", "Fiqh", ContentClass.OPEN, 2),
        TopicRow("fiqh.taharah", "fiqh", "طهارة", "Purification", ContentClass.OPEN, 9),
        TopicRow("aqidah", None, "عقيدة", "ʿAqīdah", ContentClass.OPEN, 4),
    ]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert [node["id"] for node in body] == ["fiqh", "aqidah"]
    assert [child["id"] for child in body[0]["children"]] == ["fiqh.taharah"]


def test_topic_carries_its_own_count_and_the_count_including_children() -> None:
    topics = [
        TopicRow("fiqh", None, "فقه", "Fiqh", ContentClass.OPEN, 2),
        TopicRow("fiqh.taharah", "fiqh", "طهارة", "Purification", ContentClass.OPEN, 9),
        TopicRow("fiqh.salah", "fiqh", "صلاة", "Prayer", ContentClass.OPEN, 20),
    ]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert body[0]["entry_count"] == 2
    assert body[0]["total_entry_count"] == 31


def test_topics_nest_to_a_third_level() -> None:
    # topics.yml is two-level today, but topic.parent_id is not: a tree builder that
    # only knows two levels drops a grandchild silently, with no error anywhere.
    topics = [
        TopicRow("fiqh", None, "فقه", "Fiqh", ContentClass.OPEN, 1),
        TopicRow("fiqh.ibadat", "fiqh", "عبادات", "Worship", ContentClass.OPEN, 2),
        TopicRow("fiqh.ibadat.salah", "fiqh.ibadat", "صلاة", "Prayer", ContentClass.OPEN, 4),
    ]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert [node["id"] for node in body] == ["fiqh"]
    assert [child["id"] for child in body[0]["children"]] == ["fiqh.ibadat"]
    assert [
        grandchild["id"] for grandchild in body[0]["children"][0]["children"]
    ] == ["fiqh.ibadat.salah"]


def test_total_entry_count_sums_through_every_level() -> None:
    topics = [
        TopicRow("fiqh", None, "فقه", "Fiqh", ContentClass.OPEN, 1),
        TopicRow("fiqh.ibadat", "fiqh", "عبادات", "Worship", ContentClass.OPEN, 2),
        TopicRow("fiqh.ibadat.salah", "fiqh.ibadat", "صلاة", "Prayer", ContentClass.OPEN, 4),
    ]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert body[0]["total_entry_count"] == 7


def test_a_parent_cycle_degrades_to_flat_roots_rather_than_an_empty_tree() -> None:
    # Two rows naming each other have no root, so a root-first builder returns nothing
    # and the whole library looks empty. Showing them flat loses the nesting only.
    topics = [
        TopicRow("a", "b", "أ", "A", ContentClass.OPEN, 1),
        TopicRow("b", "a", "ب", "B", ContentClass.OPEN, 2),
    ]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert sorted(node["id"] for node in body) == ["a", "b"]


def test_topic_reports_its_content_class() -> None:
    topics = [TopicRow("private", None, "خاص", "Private", ContentClass.EXCLUDED, 3)]

    body = client_for(topics=topics).get("/api/v1/topics").json()

    assert body[0]["content_class"] == "excluded"


# --------------------------------------------------------------- attribution gate


def test_entry_with_unsure_attribution_is_not_reachable() -> None:
    # The schema's CHECK already forbids public + not_sure. The route repeats it so a
    # row that arrived by any other path still cannot be read out of the archive.
    entry = make_entry(visibility=Visibility.PUBLIC, attribution=Attribution.NOT_SURE)

    response = client_for(entries=[entry]).get("/api/v1/entries/uthaymin-000421")

    assert response.status_code == 404
    assert response.json() == {"detail": "entry_not_found"}


def test_transcript_of_an_entry_with_unsure_attribution_is_not_served() -> None:
    entry = make_entry(attribution=Attribution.NOT_SURE)
    segment = SegmentRow(0, 0, 3200, SpanRole.SCHOLAR_OWN, True, "unattributed text")
    client = client_for(
        entries=[entry], segments={("uthaymin-000421", Lang.AR): [segment]}
    )

    response = client.get(
        "/api/v1/entries/uthaymin-000421/transcript", params={"lang": "ar"}
    )

    assert response.status_code == 404
    assert "unattributed text" not in response.text


def test_entry_list_drops_an_entry_with_unsure_attribution() -> None:
    page = EntryPage(
        items=(
            make_entry("uthaymin-000421"),
            make_entry("uthaymin-000422", attribution=Attribution.NOT_SURE),
        ),
        total=2,
    )
    client = client_for(pages={"ibn-uthaymin": page})

    body = client.get("/api/v1/scholars/ibn-uthaymin/entries").json()

    assert [item["id"] for item in body["items"]] == ["uthaymin-000421"]


def test_entry_names_its_canonical_entry_when_it_is_a_variant() -> None:
    # Variants stay reachable -- their URLs are in circulation -- but a client must be
    # able to see that this recording is a duplicate of another and link to it.
    entry = make_entry("uthaymin-000422", canonical_id="uthaymin-000421")

    body = client_for(entries=[entry]).get("/api/v1/entries/uthaymin-000422").json()

    assert body["canonical_id"] == "uthaymin-000421"


# Register rule 2 has two halves. The attribution half was enforced from the start; the
# Arabic-approval half lived only in register.gates.can_publish, which nothing called.
# Title, question and hukm are produced by a model in ingest step 7 — before Arabic
# approval no human has read them, so serving them is serving unreviewed machine output
# under a scholar's name.


def test_entry_is_not_served_while_its_arabic_is_still_awaiting_review() -> None:
    client = client_for(
        entries=[
            make_entry(
                languages=(EntryLanguageRow(Lang.AR, ReviewState.AWAITING_REVIEW),),
                title_ar="عنوان من الآلة",
                hukm="haram",
            )
        ]
    )
    response = client.get("/api/v1/entries/uthaymin-000421")
    assert response.status_code == 404


def test_entry_is_not_served_when_it_has_no_arabic_row_at_all() -> None:
    """Missing is not approved. The gate fails closed."""
    client = client_for(entries=[make_entry(languages=())])
    assert client.get("/api/v1/entries/uthaymin-000421").status_code == 404


def test_scholar_listing_omits_an_entry_whose_arabic_is_not_approved() -> None:
    client = client_for(
        pages={
            "ibn-uthaymin": EntryPage(
                items=(
                    make_entry("uthaymin-000001"),
                    make_entry(
                        "uthaymin-000002",
                        languages=(EntryLanguageRow(Lang.AR, ReviewState.IN_PROGRESS),),
                    ),
                ),
                total=2,
            )
        }
    )
    body = client.get("/api/v1/scholars/ibn-uthaymin/entries").json()
    assert [item["id"] for item in body["items"]] == ["uthaymin-000001"]
