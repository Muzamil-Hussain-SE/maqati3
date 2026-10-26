"""Behaviour of the Arabic search normalisation."""

from maqati3.text.normalize import normalize_ar


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


# Letterforms that only a Persian, Urdu or Kurdish keyboard produces. They are the
# Arabic letter to the eye and to the reader, and web-copied Arabic is full of them;
# left unfolded they make dedup read one fatwa as two.


def test_normalize_ar_folds_farsi_yeh_and_yeh_barree_to_ya() -> None:
    assert normalize_ar("یےۓ") == "ييي"


def test_normalize_ar_folds_keheh_to_arabic_kaf() -> None:
    assert normalize_ar("ک") == "ك"


def test_normalize_ar_folds_persian_and_urdu_heh_forms_to_ha() -> None:
    assert normalize_ar("ھہۂۀە") == "ههههه"


def test_normalize_ar_folds_noon_ghunna_to_noon() -> None:
    assert normalize_ar("ں") == "ن"


def test_normalize_ar_makes_a_persian_keyboard_line_match_an_arabic_one() -> None:
    assert normalize_ar("ہل یجوز المسح علی الخفین") == normalize_ar("هل يجوز المسح على الخفين")


def test_normalize_ar_is_idempotent_on_persian_letterforms() -> None:
    once = normalize_ar("ہل یجوز المسح علی الخفین")
    assert normalize_ar(once) == once


# Uthmani mushaf orthography carries annotation marks no plainly typed Arabic text
# ever has: honorific signs, small Qur'anic reading marks, and small superscript
# letters (waw/yeh) marking an elided sound. Left unstripped, a Qur'anic quotation in
# mushaf spelling never normalises to the same form as the same words typed plainly --
# which is the single most quoted text in a fatwa corpus.


def test_normalize_ar_removes_small_quranic_annotation_marks() -> None:
    assert normalize_ar("ٖٟ٘") == ""


def test_normalize_ar_removes_honorific_annotation_signs() -> None:
    # U+0610 sallallahu alayhi wa sallam, U+0613 radi allahu anhu
    assert normalize_ar("ؐؓ") == ""


def test_normalize_ar_removes_small_high_quranic_signs() -> None:
    # U+06DF small high rounded zero, U+06E1 small high dotless head of khah
    assert normalize_ar("۟ۡ") == ""


def test_normalize_ar_removes_small_waw_and_yeh_annotation_letters() -> None:
    # U+06E5/U+06E6 are letter-category (Lm) in Unicode, not combining marks, but they
    # are still a Qur'anic annotation and not a letter anyone types.
    assert normalize_ar("ۥۦ") == ""


def test_normalize_ar_matches_a_plainly_typed_verse_to_its_uthmani_spelling() -> None:
    uthmani = "وَأُو۟لَٰٓئِكَ هُمُ ٱلْمُفْلِحُونَ"
    plain = "وأولئك هم المفلحون"
    assert normalize_ar(uthmani) == normalize_ar(plain)


# ۃ (U+06C3, Urdu/Sindhi/Pashto teh marbuta goal) is the ة of those keyboards. The
# Persian/Urdu block already folds the letters around it; without this one every
# feminine-ending word (صلاة، زكاة، جماعة) still fails to match.


def test_normalize_ar_folds_urdu_teh_marbuta_goal_to_ha() -> None:
    assert normalize_ar("ۃ") == "ه"


def test_normalize_ar_matches_an_urdu_keyboard_line_to_its_arabic_spelling() -> None:
    arabic = "ما حكم الصلاة في الجماعة"
    urdu = "ما حکم الصلاۃ فی الجماعۃ"
    assert normalize_ar(arabic) == normalize_ar(urdu)
