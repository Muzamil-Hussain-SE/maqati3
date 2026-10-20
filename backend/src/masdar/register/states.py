"""The per-language review state machine."""

from collections.abc import Mapping
from enum import StrEnum


class ReviewState(StrEnum):
    NOT_STARTED = "not_started"
    DRAFT_READY = "draft_ready"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_FIXES = "needs_fixes"
    APPROVED = "approved"


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


def advance(current: ReviewState, target: ReviewState) -> ReviewState:
    if target not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(f"{current.value} -> {target.value} is not an allowed move")
    return target


def can_start_translation(ar_state: ReviewState) -> bool:
    """Whether a translation may leave not_started.

    Register rule 1: it may not until the Arabic is approved, otherwise someone is
    translating a text that is still moving under them.
    """
    return ar_state is ReviewState.APPROVED
