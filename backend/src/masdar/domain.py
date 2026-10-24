"""The vocabulary of the archive.

These six enums name the states and classifications the whole system turns on, so they
are defined exactly once. They were briefly declared in two places — `api.repository`
and `register` — with identical members, which type-checks fine in isolation and then
refuses to compose: a `ReviewState` read by the API was not the `ReviewState` the
publication gate expected, so the gate simply could not be called from the route that
needed it.

Values mirror the enum types in `db/migrations/0001_init.sql` one for one. Changing a
member here without changing the migration splits the Python view of a row from what
Postgres will accept.
"""

from enum import StrEnum


class Lang(StrEnum):
    AR = "ar"
    EN = "en"
    DE = "de"


class Visibility(StrEnum):
    DRAFT = "draft"
    PUBLIC = "public"
    HELD_BACK = "held_back"


class Attribution(StrEnum):
    """How firmly a recording is tied to the scholar it names.

    `NOT_SURE` is never published, however good the transcript is.
    """

    CONFIRMED = "confirmed"
    PROBABLY = "probably"
    NOT_SURE = "not_sure"


class ReviewState(StrEnum):
    """Per language, not per entry: material arrives unevenly."""

    NOT_STARTED = "not_started"
    DRAFT_READY = "draft_ready"
    IN_PROGRESS = "in_progress"
    AWAITING_REVIEW = "awaiting_review"
    NEEDS_FIXES = "needs_fixes"
    APPROVED = "approved"


class SpanRole(StrEnum):
    """Who the words on a line belong to.

    Only `SCHOLAR_OWN` may be quoted as the scholar's position. The rest stay in the
    index for context: a line where he reports a view in order to reject it is still
    part of the answer, but attributing it to him inverts what he said.
    """

    SCHOLAR_OWN = "scholar_own"
    QUESTIONER = "questioner"
    QUOTED_OTHER = "quoted_other"
    RECITED_TEXT = "recited_text"
    UNCLEAR = "unclear"


class ContentClass(StrEnum):
    """What may be done with a topic: answered over, cited only, or neither."""

    OPEN = "open"
    SOURCES_ONLY = "sources_only"
    EXCLUDED = "excluded"
