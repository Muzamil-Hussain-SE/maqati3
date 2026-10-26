"""Parser for the supplier line format ``[HH:MM:SS] text``."""

import re
from dataclasses import dataclass

_FORMAT = "[HH:MM:SS] text"

# Hours may exceed two digits; minutes and seconds are always two and are range-checked
# below rather than in the pattern, so a wrong value gets a message that names the field.
_LINE = re.compile(r"^\[(\d{2,}):(\d{2}):(\d{2})\](?:[ \t](.*))?$")

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
        notes, text_raw, note_error = _split_notes(body or "")
        if note_error is not None:
            errors.append(LineError(line_no=line_no, raw=line, reason=note_error))
            continue
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


#: Case-folded, because contributors capitalise: "[Note:" and "[NOTE:" mean the same.
_NOTE_OPEN = "[note:"


def _split_notes(body: str) -> tuple[tuple[str, ...], str, str | None]:
    """Return the reviewer notes of ``body``, the body without them, and any error.

    Notes are removed rather than flagged, so that nothing downstream can publish one by
    forgetting to filter: the display text never contains them in the first place.

    Brackets are matched by depth rather than by a non-greedy pattern, because notes
    routinely contain them. The guide asks contributors to mark an uncertain reading
    `[?]` and to address the reviewer in `[note: ...]`; doing both at once produces
    `[note: ... [?]]`, and stopping at the first `]` would leave the tail of the note in
    the displayed line and swallow the marker along with it.
    """
    notes: list[str] = []
    out: list[str] = []
    i = 0
    while i < len(body):
        if body[i : i + len(_NOTE_OPEN)].lower() != _NOTE_OPEN:
            out.append(body[i])
            i += 1
            continue
        depth = 1
        j = i + len(_NOTE_OPEN)
        while j < len(body) and depth:
            if body[j] == "[":
                depth += 1
            elif body[j] == "]":
                depth -= 1
                if not depth:
                    break
            j += 1
        if depth:
            # Truncating here would publish part of a remark as the scholar's words.
            return (), "", "unclosed [note: ...] -- every note must end with ]"
        notes.append(body[i + len(_NOTE_OPEN) : j].strip())
        out.append(" ")
        i = j + 1
    return tuple(notes), _SPACES.sub(" ", "".join(out)).strip(), None
