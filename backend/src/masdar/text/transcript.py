"""Parser for the supplier line format ``[HH:MM:SS] text``."""

import re
from dataclasses import dataclass

_FORMAT = "[HH:MM:SS] text"

# Hours may exceed two digits; minutes and seconds are always two and are range-checked
# below rather than in the pattern, so a wrong value gets a message that names the field.
_LINE = re.compile(r"^\[(\d{2,}):(\d{2}):(\d{2})\](?:[ \t](.*))?$")

_NOTE = re.compile(r"\[note:(.*?)\]", re.IGNORECASE)
_UNCLEAR = re.compile(r"\[(?:\.\.\.|…)\]")
_UNCERTAIN = "[?]"
_QURAN = re.compile("﴿(.*?)﴾", re.DOTALL)  # ﴿ … ﴾
_SPACES = re.compile(r"[ \t]{2,}")


@dataclass(frozen=True, slots=True)
class Segment:
    """One line of a transcript: one moment in the recording.

    ``text_raw`` is the display text with reviewer notes already stripped out;
    ``quran_spans`` are half-open character positions into that same string.
    """

    idx: int
    line_no: int
    t_start_ms: int
    text_raw: str
    has_unclear: bool = False
    has_uncertain_reading: bool = False
    notes: tuple[str, ...] = ()
    quran_spans: tuple[tuple[int, int], ...] = ()


@dataclass(frozen=True, slots=True)
class LineError:
    """A line that could not be parsed. Never dropped silently."""

    line_no: int
    raw: str
    reason: str


@dataclass(frozen=True, slots=True)
class ParsedTranscript:
    """The segments of one language file, plus every line that failed to parse."""

    segments: tuple[Segment, ...] = ()
    errors: tuple[LineError, ...] = ()


def parse_transcript(text: str) -> ParsedTranscript:
    """Parse ``text`` into one segment per line.

    Blank lines are separators and are skipped. A line with a timestamp and no text is
    valid and means the translator covered two rows with one sentence — rows are never
    added or removed, so the empty row has to survive. Every other unparsable line is
    collected in ``errors`` with its 1-based source line number and a reason.
    """
    segments: list[Segment] = []
    errors: list[LineError] = []

    for line_no, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        match = _LINE.match(line.rstrip())
        if match is None:
            errors.append(
                LineError(line_no=line_no, raw=line, reason=f"line does not match {_FORMAT}")
            )
            continue
        hours, minutes, seconds, body = match.groups()
        if int(minutes) > 59:
            errors.append(
                LineError(line_no=line_no, raw=line, reason=f"minute {minutes} is out of range")
            )
            continue
        if int(seconds) > 59:
            errors.append(
                LineError(line_no=line_no, raw=line, reason=f"second {seconds} is out of range")
            )
            continue
        t_start_ms = (int(hours) * 3600 + int(minutes) * 60 + int(seconds)) * 1000
        notes, text_raw = _split_notes(body or "")
        segments.append(
            Segment(
                idx=len(segments),
                line_no=line_no,
                t_start_ms=t_start_ms,
                text_raw=text_raw,
                has_unclear=_UNCLEAR.search(text_raw) is not None,
                has_uncertain_reading=_UNCERTAIN in text_raw,
                notes=notes,
                quran_spans=tuple(m.span() for m in _QURAN.finditer(text_raw)),
            )
        )

    return ParsedTranscript(segments=tuple(segments), errors=tuple(errors))


def _split_notes(body: str) -> tuple[tuple[str, ...], str]:
    """Return the reviewer notes of ``body`` and the body without them.

    Notes are removed rather than flagged, so that nothing downstream can publish one by
    forgetting to filter: the display text never contains them in the first place.
    """
    notes = tuple(m.group(1).strip() for m in _NOTE.finditer(body))
    stripped = _NOTE.sub(" ", body) if notes else body
    return notes, _SPACES.sub(" ", stripped).strip()
