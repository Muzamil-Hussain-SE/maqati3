"""Behaviour of the supplier line-format parser."""

from masdar.text.transcript import parse_transcript


def test_parse_transcript_reads_timestamp_and_text_of_a_single_line() -> None:
    parsed = parse_transcript("[00:00:14] الجواب")

    assert len(parsed.segments) == 1
    segment = parsed.segments[0]
    assert segment.idx == 0
    assert segment.t_start_ms == 14_000
    assert segment.text_raw == "الجواب"


def test_parse_transcript_collects_a_line_without_a_timestamp_as_an_error() -> None:
    parsed = parse_transcript("[00:00:00] الحمد لله\nthis line has no timestamp")

    assert len(parsed.segments) == 1
    assert len(parsed.errors) == 1
    assert parsed.errors[0].line_no == 2
    assert parsed.errors[0].raw == "this line has no timestamp"
    assert "[HH:MM:SS]" in parsed.errors[0].reason


def test_parse_transcript_rejects_a_single_digit_hour_timestamp() -> None:
    parsed = parse_transcript("[0:14] الجواب")

    assert parsed.segments == ()
    assert len(parsed.errors) == 1
    assert parsed.errors[0].line_no == 1


def test_parse_transcript_rejects_a_timestamp_with_sixty_seconds() -> None:
    parsed = parse_transcript("[00:00:60] الجواب")

    assert parsed.segments == ()
    assert len(parsed.errors) == 1
    assert "second" in parsed.errors[0].reason


def test_parse_transcript_rejects_a_timestamp_with_sixty_minutes() -> None:
    parsed = parse_transcript("[00:60:00] الجواب")

    assert parsed.segments == ()
    assert "minute" in parsed.errors[0].reason


def test_parse_transcript_keeps_a_timestamped_line_without_text_as_a_segment() -> None:
    # Two Arabic rows covered by one translated sentence. Correct, never an error.
    parsed = parse_transcript("[00:00:10] الاول\n[00:00:14]")

    assert len(parsed.segments) == 2
    assert parsed.segments[1].text_raw == ""
    assert parsed.errors == ()


def test_parse_transcript_ignores_blank_separator_lines() -> None:
    parsed = parse_transcript("[00:00:10] الاول\n\n   \n[00:00:14] الثاني")

    assert len(parsed.segments) == 2
    assert parsed.errors == ()


def test_parse_transcript_numbers_segments_consecutively_across_a_bad_line() -> None:
    parsed = parse_transcript("[00:00:10] الاول\nbroken\n[00:00:14] الثاني")

    assert [s.idx for s in parsed.segments] == [0, 1]
    assert parsed.errors[0].line_no == 2


def test_parse_transcript_records_the_source_line_number_on_each_segment() -> None:
    parsed = parse_transcript("\n[00:00:10] الاول")

    assert parsed.segments[0].line_no == 2


def test_parse_transcript_flags_an_unintelligible_marker() -> None:
    segment = parse_transcript("[00:00:30] وقد روى [...] عن المغيرة").segments[0]

    assert segment.has_unclear is True
    assert segment.has_uncertain_reading is False


def test_parse_transcript_flags_an_ellipsis_character_as_unintelligible() -> None:
    # Contributors typing on macOS get the single ellipsis character automatically.
    assert parse_transcript("[00:00:30] وقد روى […] عن المغيرة").segments[0].has_unclear is True


def test_parse_transcript_flags_an_uncertain_reading_marker() -> None:
    segment = parse_transcript("[00:00:30] عن المغيرة [?]").segments[0]

    assert segment.has_uncertain_reading is True
    assert segment.has_unclear is False


def test_parse_transcript_leaves_both_marker_flags_false_on_a_clean_line() -> None:
    segment = parse_transcript("[00:00:30] الحمد لله").segments[0]

    assert segment.has_unclear is False
    assert segment.has_uncertain_reading is False
    assert segment.notes == ()
    assert segment.quran_spans == ()


def test_parse_transcript_collects_a_reviewer_note() -> None:
    segment = parse_transcript("[00:00:30] الحمد لله [note: check the name]").segments[0]

    assert segment.notes == ("check the name",)


def test_parse_transcript_removes_a_reviewer_note_from_the_display_text() -> None:
    # text_raw is what the site displays. A note must be structurally unpublishable.
    segment = parse_transcript("[00:00:30] الحمد لله [note: check the name]").segments[0]

    assert segment.text_raw == "الحمد لله"


def test_parse_transcript_collects_several_reviewer_notes_in_order() -> None:
    segment = parse_transcript("[00:00:30] [note: first] متن [note: second]").segments[0]

    assert segment.notes == ("first", "second")
    assert segment.text_raw == "متن"


def test_parse_transcript_marks_a_quran_span_by_character_position_in_text_raw() -> None:
    segment = parse_transcript("[00:00:23] قال تعالى ﴿ وأرجلكم ﴾ انتهى").segments[0]

    assert len(segment.quran_spans) == 1
    start, end = segment.quran_spans[0]
    assert segment.text_raw[start:end] == "﴿ وأرجلكم ﴾"


def test_parse_transcript_marks_two_quran_spans_in_one_line() -> None:
    segment = parse_transcript("[00:00:23] ﴿ الاول ﴾ و ﴿ الثاني ﴾").segments[0]

    assert len(segment.quran_spans) == 2
    assert segment.text_raw[slice(*segment.quran_spans[1])] == "﴿ الثاني ﴾"


def test_parse_transcript_computes_quran_spans_after_removing_a_note() -> None:
    segment = parse_transcript("[00:00:23] [note: verify] ﴿ وأرجلكم ﴾").segments[0]

    assert segment.text_raw[slice(*segment.quran_spans[0])] == "﴿ وأرجلكم ﴾"


# The validator tells contributors to mark an uncertain reading with [?], and the guide
# tells them to put remarks in [note: ...]. Following both at once — a note that mentions
# a [?] — used to cut the note at the first closing bracket, leaving its tail in the
# displayed line and swallowing the marker, so the validator went quiet about it too.


def test_a_note_containing_brackets_is_removed_whole() -> None:
    parsed = parse_transcript(
        "[00:01:02] قال الشيخ [note: unsure whether he said X or Y [?]] والله أعلم"
    )
    segment = parsed.segments[0]
    assert segment.notes == ("unsure whether he said X or Y [?]",)
    assert segment.text_raw == "قال الشيخ والله أعلم"
    assert "]" not in segment.text_raw


def test_an_uncertain_marker_inside_a_note_does_not_flag_the_line() -> None:
    """The [?] belongs to the reviewer's remark, not to the transcript text."""
    parsed = parse_transcript("[00:01:02] قال الشيخ [note: he may mean X [?]] تمام")
    assert parsed.segments[0].has_uncertain_reading is False


def test_an_uncertain_marker_outside_a_note_still_flags_the_line() -> None:
    parsed = parse_transcript("[00:01:02] قال الشيخ [?] [note: see [Bukhari 1]] تمام")
    segment = parsed.segments[0]
    assert segment.has_uncertain_reading is True
    assert segment.notes == ("see [Bukhari 1]",)
    assert segment.text_raw == "قال الشيخ [?] تمام"


def test_an_unclosed_note_is_an_error_not_a_silent_truncation() -> None:
    parsed = parse_transcript("[00:01:02] قال الشيخ [note: he may mean X")
    assert parsed.segments == ()
    assert len(parsed.errors) == 1
    assert "note" in parsed.errors[0].reason.lower()
