"""The validator that gives contributors their feedback.

It is the cheapest quality mechanism in the project: it runs before a human reviewer
spends a minute on the entry, and every message names the line and the fix. The rules it
enforces are what lets the pipeline do without forced alignment — timestamps come out of
the ASR run and survive human correction only because rows are never added, removed or
reordered. See CLAUDE.md, "Why there is no forced alignment in phase 1".
"""

from dataclasses import dataclass
from typing import Literal

from masdar.text.transcript import ParsedTranscript, Segment

Severity = Literal["error", "warning"]

_FORMAT_HINT = "Expected format: [HH:MM:SS] text, one row per line."


@dataclass(frozen=True, slots=True)
class Problem:
    """One finding, phrased so a contributor can act on it without asking."""

    severity: Severity
    line: int | None
    lang: str
    message: str


def validate_transcripts(
    ar: ParsedTranscript,
    translations: dict[str, ParsedTranscript],
    duration_sec: int | None,
) -> list[Problem]:
    """Check an Arabic transcript and its translations against each other.

    Returns every problem found, Arabic first and then each translation in the order
    given, so a contributor fixes the source before the translations that follow it.
    An empty list means the set is ready for review.

    Errors block; warnings are for a human to judge. A row-count mismatch suppresses the
    per-row timestamp comparison for that language, because one inserted row shifts every
    later row and would bury the one message that matters under a hundred that do not.
    """
    problems: list[Problem] = []
    problems += _check_one(ar, "ar", duration_sec)
    for lang, translation in translations.items():
        problems += _check_one(translation, lang, duration_sec)
        problems += _check_against_arabic(ar, translation, lang)
    return problems


def _check_one(
    transcript: ParsedTranscript, lang: str, duration_sec: int | None
) -> list[Problem]:
    """Checks that need only this one file."""
    problems: list[Problem] = []

    for error in transcript.errors:
        problems.append(
            Problem(
                severity="error",
                line=error.line_no,
                lang=lang,
                message=(
                    f"Line {error.line_no}: cannot read this line in {lang}.txt "
                    f"({error.reason}). {_FORMAT_HINT}"
                ),
            )
        )

    previous: Segment | None = None
    for segment in transcript.segments:
        if previous is not None and segment.t_start_ms <= previous.t_start_ms:
            problems.append(
                Problem(
                    severity="error",
                    line=segment.line_no,
                    lang=lang,
                    message=(
                        f"Line {segment.line_no}: timestamp {_hms(segment.t_start_ms)} in "
                        f"{lang}.txt is not later than {_hms(previous.t_start_ms)} on the "
                        "previous row. Timestamps must increase strictly from row to row."
                    ),
                )
            )
        if duration_sec is not None and segment.t_start_ms > duration_sec * 1000:
            problems.append(
                Problem(
                    severity="error",
                    line=segment.line_no,
                    lang=lang,
                    message=(
                        f"Line {segment.line_no}: timestamp {_hms(segment.t_start_ms)} in "
                        f"{lang}.txt is past the end of the recording "
                        f"({_hms(duration_sec * 1000)}). Correct the timestamp."
                    ),
                )
            )
        if segment.has_uncertain_reading:
            problems.append(
                Problem(
                    severity="warning",
                    line=segment.line_no,
                    lang=lang,
                    message=(
                        f"Line {segment.line_no}: {lang}.txt still carries an uncertain "
                        "reading marker [?]. Resolve the reading, or replace it with "
                        "[note: ...] so the reviewer sees the question."
                    ),
                )
            )
        previous = segment

    return problems


def _check_against_arabic(
    ar: ParsedTranscript, translation: ParsedTranscript, lang: str
) -> list[Problem]:
    """Checks that tie a translation to the Arabic timeline row by row."""
    if len(translation.segments) != len(ar.segments):
        return [
            Problem(
                severity="error",
                line=_divergence_line(ar, translation),
                lang=lang,
                message=(
                    f"{lang}.txt has {len(translation.segments)} rows, "
                    f"ar.txt has {len(ar.segments)} rows. "
                    "Rows must never be added or removed. If one sentence covers two "
                    "Arabic rows, write it in the first and leave the second empty."
                ),
            )
        ]

    return [
        Problem(
            severity="error",
            line=theirs.line_no,
            lang=lang,
            message=(
                f"Line {theirs.line_no}: {lang}.txt row {theirs.idx} has timestamp "
                f"{_hms(theirs.t_start_ms)}, ar.txt has {_hms(ours.t_start_ms)}. "
                "Copy the Arabic timestamps unchanged — they anchor the row to the audio."
            ),
        )
        for ours, theirs in zip(ar.segments, translation.segments, strict=True)
        if ours.t_start_ms != theirs.t_start_ms
    ]


def _divergence_line(ar: ParsedTranscript, translation: ParsedTranscript) -> int | None:
    """The source line in the translation where it first stops matching the Arabic."""
    for ours, theirs in zip(ar.segments, translation.segments, strict=False):
        if ours.t_start_ms != theirs.t_start_ms:
            return theirs.line_no
    if len(translation.segments) > len(ar.segments):
        return translation.segments[len(ar.segments)].line_no
    return translation.segments[-1].line_no if translation.segments else None


def _hms(ms: int) -> str:
    seconds = ms // 1000
    return f"{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
