"""Publication and citation gates.

These mirror db/migrations/0001_init.sql: the `public_requires_attribution` constraint on
`entry` and the `WHERE` clause of the `segment_citable` view. The duplication is on
purpose. The database is the last line; this is the one that can say *why*.
"""

from dataclasses import dataclass

from masdar.domain import Attribution, ContentClass, SpanRole, Visibility
from masdar.register.states import ReviewState


@dataclass(frozen=True, slots=True)
class GateResult:
    """The answer of a gate, with the concrete ground when it refuses.

    `reason` is empty when allowed. It is written for a log line and for an admin, not
    for a visitor.
    """

    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        # So that `if gate(...)` refuses instead of passing on a non-empty object.
        return self.allowed


def can_publish(attribution: Attribution, arabic_state: ReviewState) -> GateResult:
    """Whether an entry may be set to visibility=public.

    Register rule 2. Unapproved translations simply do not show; the entry stays
    Arabic-only until they are approved. That is the normal case, not a defect.
    """
    blockers: list[str] = []
    if attribution is Attribution.NOT_SURE:
        blockers.append("attribution is not_sure")
    if arabic_state is not ReviewState.APPROVED:
        blockers.append(f"arabic review state is {arabic_state.value}, not approved")
    if blockers:
        return GateResult(allowed=False, reason="; ".join(blockers))
    return GateResult(allowed=True, reason="")


def is_citable(
    *,
    span_role: SpanRole,
    citable: bool,
    visibility: Visibility,
    attribution: Attribution,
    language_state: ReviewState,
    content_class: ContentClass,
    canonical_id: str | None,
) -> GateResult:
    """Whether this segment may be quoted as the scholar's position in this language.

    The Python side of the `segment_citable` view. Arguments are keyword-only on purpose:
    four of the seven are interchangeable at a call site, and a silently transposed pair
    here publishes the wrong text under a scholar's name.
    """
    blockers: list[str] = []
    if span_role is not SpanRole.SCHOLAR_OWN:
        blockers.append(f"span role is {span_role.value}, not scholar_own")
    if not citable:
        blockers.append("timestamp is not human-confirmed")
    if visibility is not Visibility.PUBLIC:
        blockers.append(f"entry visibility is {visibility.value}, not public")
    if attribution is Attribution.NOT_SURE:
        blockers.append("attribution is not_sure")
    if language_state is not ReviewState.APPROVED:
        blockers.append(f"review state for this language is {language_state.value}, not approved")
    if content_class is ContentClass.EXCLUDED:
        blockers.append("topic is excluded from the index")
    if canonical_id is not None:
        blockers.append(f"entry is a variant of {canonical_id}; only the canonical one is cited")
    if blockers:
        return GateResult(allowed=False, reason="; ".join(blockers))
    return GateResult(allowed=True, reason="")


def may_synthesise(content_class: ContentClass) -> bool:
    """Whether the answer path may write a summarising answer over this topic at all.

    Only `open` may. For `sources_only` the path returns findings — citations the reader
    opens for himself — and nothing in our own words.
    """
    return content_class is ContentClass.OPEN
