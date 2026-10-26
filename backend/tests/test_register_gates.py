"""The publication gates.

Deliberate redundancy with the database: the same rules live in the
`public_requires_attribution` constraint and the `segment_citable` view in
db/migrations/0001_init.sql. Defence in depth — code that never reaches those objects
must still refuse.
"""

import pytest

from maqati3.register.gates import (
    Attribution,
    ContentClass,
    GateResult,
    SpanRole,
    Visibility,
    can_publish,
    is_citable,
    may_synthesise,
)
from maqati3.register.states import ReviewState


def test_publication_is_blocked_when_attribution_is_not_sure() -> None:
    result = can_publish(Attribution.NOT_SURE, ReviewState.APPROVED)
    assert result.allowed is False


@pytest.mark.parametrize(
    "arabic_state", [state for state in ReviewState if state is not ReviewState.APPROVED]
)
def test_publication_is_blocked_while_the_arabic_is_not_approved(
    arabic_state: ReviewState,
) -> None:
    result = can_publish(Attribution.CONFIRMED, arabic_state)
    assert result.allowed is False


def test_blocked_publication_names_the_unapproved_arabic_as_the_reason() -> None:
    result = can_publish(Attribution.CONFIRMED, ReviewState.AWAITING_REVIEW)
    assert "awaiting_review" in result.reason


def test_blocked_publication_names_every_failing_condition_at_once() -> None:
    result = can_publish(Attribution.NOT_SURE, ReviewState.IN_PROGRESS)
    assert "not_sure" in result.reason
    assert "in_progress" in result.reason


def test_publication_is_allowed_when_attribution_is_established_and_the_arabic_is_approved() -> (
    None
):
    assert can_publish(Attribution.CONFIRMED, ReviewState.APPROVED).allowed is True


def test_publication_is_allowed_on_probably_because_only_not_sure_blocks() -> None:
    assert can_publish(Attribution.PROBABLY, ReviewState.APPROVED).allowed is True


# ------------------------------------------------------------------ is_citable

# One set of inputs that satisfies every condition. Each test below flips exactly one of
# them, so a dropped condition in the implementation fails exactly one test.
CITABLE_INPUTS: dict[str, object] = {
    "span_role": SpanRole.SCHOLAR_OWN,
    "citable": True,
    "visibility": Visibility.PUBLIC,
    "attribution": Attribution.CONFIRMED,
    "language_state": ReviewState.APPROVED,
    "content_class": ContentClass.OPEN,
    "canonical_id": None,
}


def citable_with(**overrides: object) -> GateResult:
    return is_citable(**(CITABLE_INPUTS | overrides))  # type: ignore[arg-type]


def test_a_view_the_scholar_quotes_only_to_refute_is_never_citable_as_his_own_position() -> None:
    """The failure this whole module exists to prevent.

    The scholar says "some claim this is permitted — but that is wrong". The first half
    carries span_role=quoted_other. Quoted and attributed to him, it reverses his ruling:
    the single worst error this system can make, and a public one is socially
    irreversible. Diarisation cannot catch it — he is speaking in both halves.
    """
    result = citable_with(span_role=SpanRole.QUOTED_OTHER)
    assert result.allowed is False
    assert "quoted_other" in result.reason


@pytest.mark.parametrize(
    "span_role", [role for role in SpanRole if role is not SpanRole.SCHOLAR_OWN]
)
def test_only_the_scholars_own_speech_is_citable(span_role: SpanRole) -> None:
    assert citable_with(span_role=span_role).allowed is False


def test_a_segment_with_an_unconfirmed_timestamp_is_not_citable() -> None:
    assert citable_with(citable=False).allowed is False


@pytest.mark.parametrize(
    "visibility", [v for v in Visibility if v is not Visibility.PUBLIC]
)
def test_a_segment_of_a_non_public_entry_is_not_citable(visibility: Visibility) -> None:
    assert citable_with(visibility=visibility).allowed is False


def test_a_segment_is_not_citable_when_attribution_is_not_sure() -> None:
    assert citable_with(attribution=Attribution.NOT_SURE).allowed is False


@pytest.mark.parametrize(
    "language_state", [s for s in ReviewState if s is not ReviewState.APPROVED]
)
def test_a_segment_is_not_citable_in_a_language_that_is_not_approved(
    language_state: ReviewState,
) -> None:
    assert citable_with(language_state=language_state).allowed is False


def test_a_segment_of_an_excluded_topic_is_not_citable() -> None:
    assert citable_with(content_class=ContentClass.EXCLUDED).allowed is False


def test_a_segment_of_a_variant_entry_is_not_citable_because_only_the_canonical_is_indexed() -> (
    None
):
    assert citable_with(canonical_id="uthaymin-000421").allowed is False


def test_a_blocked_citation_names_every_failing_condition_at_once() -> None:
    result = citable_with(span_role=SpanRole.QUESTIONER, citable=False)
    assert "questioner" in result.reason
    assert "timestamp" in result.reason


def test_a_segment_is_citable_when_every_condition_is_met() -> None:
    assert citable_with().allowed is True


def test_a_segment_of_a_sources_only_topic_stays_citable_because_only_excluded_blocks() -> None:
    assert citable_with(content_class=ContentClass.SOURCES_ONLY).allowed is True


# ------------------------------------------------------------------ may_synthesise


def test_a_sources_only_topic_may_not_be_synthesised_over() -> None:
    """Sources-only means the answer path returns findings and nothing else.

    No summarising sentence of our own: a summary of a fatwa is a new ruling.
    """
    assert may_synthesise(ContentClass.SOURCES_ONLY) is False


def test_an_excluded_topic_may_not_be_synthesised_over() -> None:
    assert may_synthesise(ContentClass.EXCLUDED) is False


def test_an_open_topic_may_be_synthesised_over() -> None:
    assert may_synthesise(ContentClass.OPEN) is True


# ------------------------------------------------------------------ GateResult


def test_a_blocked_gate_result_is_falsy_so_a_forgotten_allowed_still_refuses() -> None:
    """`if can_publish(...)` must not pass just because an object was returned."""
    assert not can_publish(Attribution.NOT_SURE, ReviewState.APPROVED)


def test_an_allowed_gate_result_is_truthy() -> None:
    assert can_publish(Attribution.CONFIRMED, ReviewState.APPROVED)
