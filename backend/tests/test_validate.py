"""Behaviour of the contributor-facing transcript validator."""

from maqati3.text.transcript import parse_transcript
from maqati3.text.validate import validate_transcripts


def test_validate_transcripts_reports_a_translation_with_fewer_rows() -> None:
    ar = parse_transcript("[00:00:00] الاول\n[00:00:05] الثاني\n[00:00:09] الثالث")
    de = parse_transcript("[00:00:00] Erstens\n[00:00:05] Zweitens")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].lang == "de"
    assert "de.txt has 2 rows, ar.txt has 3 rows" in problems[0].message
    assert "never be added or removed" in problems[0].message


def test_validate_transcripts_points_at_the_line_where_a_short_translation_stops() -> None:
    ar = parse_transcript("[00:00:00] الاول\n[00:00:05] الثاني\n[00:00:09] الثالث")
    de = parse_transcript("[00:00:00] Erstens\n[00:00:05] Zweitens")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert problems[0].line == 2


def test_validate_transcripts_points_at_the_first_extra_row_of_a_long_translation() -> None:
    ar = parse_transcript("[00:00:00] الاول")
    de = parse_transcript("[00:00:00] Erstens\n[00:00:05] Zweitens")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert problems[0].line == 2
    assert "de.txt has 2 rows, ar.txt has 1 rows" in problems[0].message


def test_validate_transcripts_reports_a_row_count_mismatch_without_timestamp_noise() -> None:
    # A row inserted at the top shifts every later timestamp. Fix the count first;
    # reporting every shifted row on top of it buries the one actionable message.
    ar = parse_transcript("[00:00:05] الاول\n[00:00:09] الثاني")
    de = parse_transcript("[00:00:00] Null\n[00:00:05] Erstens\n[00:00:09] Zweitens")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert len(problems) == 1


def test_validate_transcripts_reports_a_timestamp_that_differs_from_the_arabic() -> None:
    ar = parse_transcript("[00:00:00] الاول\n[00:01:02] الثاني")
    de = parse_transcript("[00:00:00] Erstens\n[00:01:05] Zweitens")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].line == 2
    assert "row 1" in problems[0].message
    assert "00:01:05" in problems[0].message
    assert "00:01:02" in problems[0].message


def test_validate_transcripts_reports_a_timestamp_that_does_not_increase() -> None:
    ar = parse_transcript("[00:00:09] الاول\n[00:00:05] الثاني")

    problems = validate_transcripts(ar, {}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].lang == "ar"
    assert problems[0].line == 2
    assert "00:00:05" in problems[0].message


def test_validate_transcripts_reports_two_identical_consecutive_timestamps() -> None:
    ar = parse_transcript("[00:00:05] الاول\n[00:00:05] الثاني")

    problems = validate_transcripts(ar, {}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].line == 2


def test_validate_transcripts_reports_a_timestamp_past_the_recording_duration() -> None:
    ar = parse_transcript("[00:00:05] الاول\n[00:10:30] الثاني")

    problems = validate_transcripts(ar, {}, duration_sec=600)

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].line == 2
    assert "00:10:30" in problems[0].message
    assert "00:10:00" in problems[0].message


def test_validate_transcripts_accepts_a_timestamp_exactly_at_the_duration() -> None:
    ar = parse_transcript("[00:10:00] الاول")

    assert validate_transcripts(ar, {}, duration_sec=600) == []


def test_validate_transcripts_reports_an_unparsable_line() -> None:
    ar = parse_transcript("[00:00:05] الاول\n0:09 الثاني")

    problems = validate_transcripts(ar, {}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].severity == "error"
    assert problems[0].line == 2
    assert "[HH:MM:SS]" in problems[0].message


def test_validate_transcripts_reports_an_unparsable_line_in_a_translation() -> None:
    ar = parse_transcript("[00:00:05] الاول")
    de = parse_transcript("broken line")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert [p.lang for p in problems] == ["de", "de"]
    assert problems[0].line == 1


def test_validate_transcripts_warns_about_a_remaining_uncertain_reading_marker() -> None:
    ar = parse_transcript("[00:00:05] المغيرة [?]")

    problems = validate_transcripts(ar, {}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].severity == "warning"
    assert problems[0].line == 1
    assert "[?]" in problems[0].message


def test_validate_transcripts_warns_about_an_uncertain_reading_in_a_translation() -> None:
    ar = parse_transcript("[00:00:05] المغيرة")
    de = parse_transcript("[00:00:05] al-Mughira [?]")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert len(problems) == 1
    assert problems[0].lang == "de"


def test_validate_transcripts_does_not_warn_about_an_unintelligible_marker() -> None:
    # [...] is a faithful record of what the audio does not contain. Nothing to fix.
    ar = parse_transcript("[00:00:05] وقد روى [...] عن المغيرة")

    assert validate_transcripts(ar, {}, duration_sec=None) == []


def test_validate_transcripts_returns_no_problems_for_a_clean_set() -> None:
    ar = parse_transcript("[00:00:00] الحمد لله\n[00:00:08] الجواب")
    en = parse_transcript("[00:00:00] All praise\n[00:00:08] The answer")
    de = parse_transcript("[00:00:00] Alles Lob\n[00:00:08] Die Antwort")

    assert validate_transcripts(ar, {"en": en, "de": de}, duration_sec=600) == []


def test_validate_transcripts_reports_arabic_problems_before_translation_problems() -> None:
    ar = parse_transcript("[00:00:09] الاول\n[00:00:05] الثاني")
    de = parse_transcript("[00:00:09] Erstens\n[00:00:05] Zweitens [?]")

    problems = validate_transcripts(ar, {"de": de}, duration_sec=None)

    assert [p.lang for p in problems] == ["ar", "de", "de"]


def test_validate_transcripts_keeps_an_empty_translation_row_matched_to_the_arabic() -> None:
    # One German sentence covering two Arabic rows. The empty row is correct.
    ar = parse_transcript("[00:00:00] الاول\n[00:00:05] الثاني")
    de = parse_transcript("[00:00:00] Erstens und zweitens\n[00:00:05]")

    assert validate_transcripts(ar, {"de": de}, duration_sec=None) == []


def test_validate_transcripts_returns_no_problems_for_empty_input() -> None:
    assert validate_transcripts(parse_transcript(""), {}, duration_sec=None) == []


def test_validate_transcripts_does_not_treat_a_reviewer_note_as_a_problem() -> None:
    # A note is a message to the reviewer, not a defect. It is already out of text_raw.
    ar = parse_transcript("[00:00:05] المغيرة [note: spelling of the name]")

    assert validate_transcripts(ar, {}, duration_sec=None) == []
