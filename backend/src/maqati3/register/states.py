"""The per-language review state machine."""

from collections.abc import Mapping

from maqati3.domain import ReviewState

__all__ = ["ALLOWED_TRANSITIONS", "InvalidTransition", "ReviewState", "advance"]


class InvalidTransition(Exception):
    """Raised when a review state move is not in the allowed set."""


# The register's "Allowed moves" diagram, as data. Self-transitions are not in it:
# re-setting a state is a no-op the caller should not have to ask for, and treating it as
# legal would hide a caller that lost track of where an entry stands.
ALLOWED_TRANSITIONS: Mapping[ReviewState, frozenset[ReviewState]] = {
    ReviewState.NOT_STARTED: frozenset({ReviewState.DRAFT_READY}),
    ReviewState.DRAFT_READY: frozenset({ReviewState.IN_PROGRESS}),
    ReviewState.IN_PROGRESS: frozenset({ReviewState.AWAITING_REVIEW}),
    ReviewState.AWAITING_REVIEW: frozenset({ReviewState.APPROVED, ReviewState.NEEDS_FIXES}),
    ReviewState.NEEDS_FIXES: frozenset({ReviewState.IN_PROGRESS}),
    ReviewState.APPROVED: frozenset(),
}


def _as_state(state: ReviewState | str, role: str) -> ReviewState:
    """Coerce a value from outside into a member, or refuse the move.

    A state read back from Postgres arrives as a plain string. It compares equal to the
    member but hashes and behaves differently enough that an uncoerced one walked
    straight through the matrix below and came back out as the caller's return value —
    a `str` where everything downstream compares with `is`. Anything that is not a
    state at all becomes `InvalidTransition` too: a caller is told to handle exactly
    one error from this module, so `ValueError` and `KeyError` must not escape it.
    """
    try:
        return ReviewState(state)
    except ValueError as exc:
        raise InvalidTransition(f"{role} state {state!r} is not a review state") from exc


def advance(current: ReviewState | str, target: ReviewState | str) -> ReviewState:
    source = _as_state(current, "current")
    destination = _as_state(target, "target")
    if destination not in ALLOWED_TRANSITIONS[source]:
        raise InvalidTransition(
            f"{source.value} -> {destination.value} is not an allowed move"
        )
    return destination


def can_start_translation(ar_state: ReviewState) -> bool:
    """Whether a translation may leave not_started.

    Register rule 1: it may not until the Arabic is approved, otherwise someone is
    translating a text that is still moving under them.
    """
    return ar_state is ReviewState.APPROVED
