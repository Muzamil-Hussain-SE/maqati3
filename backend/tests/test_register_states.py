"""The per-language review state machine (reference/REGISTER.md, "Allowed moves")."""

import pytest

from masdar.register.states import (
    InvalidTransition,
    ReviewState,
    advance,
    can_start_translation,
)


def test_advance_rejects_a_move_that_is_not_in_the_allowed_set() -> None:
    with pytest.raises(InvalidTransition):
        advance(ReviewState.NOT_STARTED, ReviewState.APPROVED)


def test_advance_returns_the_target_for_an_allowed_move() -> None:
    assert advance(ReviewState.NOT_STARTED, ReviewState.DRAFT_READY) is ReviewState.DRAFT_READY


# Written out literally rather than imported from the module under test: the point of the
# matrix is to state the register's rules a second time, not to echo the implementation.
VALID_MOVES: frozenset[tuple[ReviewState, ReviewState]] = frozenset(
    {
        (ReviewState.NOT_STARTED, ReviewState.DRAFT_READY),
        (ReviewState.DRAFT_READY, ReviewState.IN_PROGRESS),
        (ReviewState.IN_PROGRESS, ReviewState.AWAITING_REVIEW),
        (ReviewState.AWAITING_REVIEW, ReviewState.APPROVED),
        (ReviewState.AWAITING_REVIEW, ReviewState.NEEDS_FIXES),
        (ReviewState.NEEDS_FIXES, ReviewState.IN_PROGRESS),
    }
)

ALL_PAIRS: list[tuple[ReviewState, ReviewState]] = [
    (current, target) for current in ReviewState for target in ReviewState
]
INVALID_MOVES = [pair for pair in ALL_PAIRS if pair not in VALID_MOVES]


@pytest.mark.parametrize(("current", "target"), sorted(INVALID_MOVES))
def test_advance_raises_for_every_move_outside_the_allowed_matrix(
    current: ReviewState, target: ReviewState
) -> None:
    with pytest.raises(InvalidTransition):
        advance(current, target)


@pytest.mark.parametrize(("current", "target"), sorted(VALID_MOVES))
def test_advance_returns_the_target_for_every_move_in_the_allowed_matrix(
    current: ReviewState, target: ReviewState
) -> None:
    assert advance(current, target) is target


def test_invalid_transition_message_names_both_states() -> None:
    with pytest.raises(InvalidTransition) as excinfo:
        advance(ReviewState.APPROVED, ReviewState.IN_PROGRESS)
    message = str(excinfo.value)
    assert "approved" in message
    assert "in_progress" in message


@pytest.mark.parametrize(
    "ar_state", [state for state in ReviewState if state is not ReviewState.APPROVED]
)
def test_translation_may_not_start_while_the_arabic_is_not_approved(
    ar_state: ReviewState,
) -> None:
    assert can_start_translation(ar_state) is False


def test_translation_may_start_once_the_arabic_is_approved() -> None:
    assert can_start_translation(ReviewState.APPROVED) is True


# A state read back from Postgres arrives as a plain string, not as an enum member.
# The machine has to meet it at the boundary: InvalidTransition is the one error a
# caller is told to handle, so nothing else may escape.


def test_advance_accepts_a_stored_string_and_returns_an_enum_member() -> None:
    assert advance("not_started", "draft_ready") is ReviewState.DRAFT_READY


def test_advance_raises_invalid_transition_for_a_stored_string_outside_the_matrix() -> None:
    with pytest.raises(InvalidTransition):
        advance("approved", "in_progress")


def test_advance_raises_invalid_transition_for_a_current_state_that_is_not_a_state() -> None:
    with pytest.raises(InvalidTransition):
        advance("gibberish", "draft_ready")


def test_advance_raises_invalid_transition_for_a_target_that_is_not_a_state() -> None:
    with pytest.raises(InvalidTransition):
        advance("not_started", "gibberish")
