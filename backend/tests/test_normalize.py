"""Behaviour of the Arabic search normalisation."""

from masdar.text.normalize import normalize_ar


def test_normalize_ar_removes_tashkeel_marks() -> None:
    assert normalize_ar("مُحَمَّدٌ") == "محمد"


def test_normalize_ar_removes_tatweel() -> None:
    assert normalize_ar("الرحمـــن") == "الرحمن"


def test_normalize_ar_folds_alef_variants_to_bare_alef() -> None:
    assert normalize_ar("أإآٱا") == "ااااا"


def test_normalize_ar_folds_alef_maqsura_to_ya() -> None:
    assert normalize_ar("على") == "علي"


def test_normalize_ar_folds_ta_marbuta_to_ha() -> None:
    assert normalize_ar("صلاة") == "صلاه"


def test_normalize_ar_folds_hamza_on_waw_to_waw() -> None:
    assert normalize_ar("مؤمن") == "مومن"


def test_normalize_ar_folds_hamza_on_ya_to_ya() -> None:
    assert normalize_ar("مسئلة") == "مسيله"


def test_normalize_ar_maps_arabic_indic_digits_to_ascii() -> None:
    assert normalize_ar("٠١٢٣٤٥٦٧٨٩") == "0123456789"


def test_normalize_ar_maps_extended_arabic_indic_digits_to_ascii() -> None:
    assert normalize_ar("۰۱۲۳۴۵۶۷۸۹") == "0123456789"


def test_normalize_ar_collapses_runs_of_whitespace_to_one_space() -> None:
    assert normalize_ar("باب\t\tالطهارة\n\nوالصلاة") == "باب الطهاره والصلاه"


def test_normalize_ar_trims_surrounding_whitespace() -> None:
    assert normalize_ar("  كتاب  ") == "كتاب"


def test_normalize_ar_returns_empty_string_for_empty_input() -> None:
    assert normalize_ar("") == ""


def test_normalize_ar_returns_empty_string_for_whitespace_only_input() -> None:
    assert normalize_ar("   \n\t ") == ""


def test_normalize_ar_leaves_already_normalised_text_unchanged() -> None:
    already = "باب المسح علي الخفين"
    assert normalize_ar(already) == already


def test_normalize_ar_is_idempotent_on_a_fully_vocalised_quran_verse() -> None:
    verse = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
    once = normalize_ar(verse)
    assert normalize_ar(once) == once


def test_normalize_ar_strips_a_fully_vocalised_quran_verse_to_bare_letters() -> None:
    verse = "بِسْمِ ٱللَّهِ ٱلرَّحْمَٰنِ ٱلرَّحِيمِ"
    assert normalize_ar(verse) == "بسم الله الرحمن الرحيم"


def test_normalize_ar_keeps_latin_text_in_a_mixed_line() -> None:
    assert normalize_ar("الشيخ ibn Uthaymin ١٤٢١") == "الشيخ ibn Uthaymin 1421"
