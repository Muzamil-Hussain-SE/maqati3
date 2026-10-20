"""Dedup layer 4: the same content in a different recording.

The fixtures below are already normalised the way ``segment_text.text_norm`` is: no
tashkeel, unified alef/hamza, no punctuation. SimHash never normalises anything itself.
"""

import subprocess
import sys

import pytest

from masdar.dedup.simhash import (
    from_signed_64,
    hamming,
    is_near_duplicate,
    simhash,
    to_signed_64,
)

# Fatwa A: wiping over socks.
FATWA_A = (
    "السوال يقول هل يجوز المسح علي الجوربين اذا كانا خفيفين فالجواب ان المسح علي "
    "الجوربين جايز عند جمهور اهل العلم بشرط ان يكونا ساترين لمحل الفرض وان يكون "
    "لبسهما علي طهاره فاذا توضا الانسان ولبس الجوربين وهو علي طهاره فانه يمسح عليهما "
    "يوما وليله ان كان مقيما وثلاثه ايام بلياليها ان كان مسافرا واما اذا كان الجورب "
    "خفيفا يصف البشره بحيث يري لون الجلد من ورايه فان الصحيح انه لا يجزي المسح عليه "
    "لانه ليس بساتر والمسح انما شرع علي ما يستر القدم ومن مسح علي جورب مخرق خرقا "
    "يسيرا فان بعض اهل العلم رخص في ذلك والاحوط ان يكون الجورب سليما والله اعلم"
)

# Fatwa B: a different question from the same scholar in the same chapter of fiqh, so it
# shares the stock phrases. These two must never be collapsed into one entry.
FATWA_B = (
    "السوال يقول هل ينتقض الوضوء بمس الزوجه فالجواب ان العلماء اختلفوا في هذه "
    "المساله علي اقوال والراجح ان مس الزوجه لا ينقض الوضوء الا اذا خرج منه شيء لان "
    "النبي صلي الله عليه وسلم كان يقبل بعض نسايه ثم يخرج الي الصلاه ولا يتوضا واما "
    "قوله تعالي او لامستم النساء فالمراد به الجماع علي الصحيح من اقوال اهل العلم وهو "
    "قول ابن عباس رضي الله عنهما فمن مس زوجته بشهوه او بغير شهوه فوضوءه صحيح ما لم "
    "يخرج منه مذي او غيره فان خرج منه مذي وجب عليه الوضوء وغسل ما اصاب بدنه او ثوبه "
    "والله اعلم"
)


def test_two_different_fatawa_on_the_same_topic_are_not_near_duplicates() -> None:
    assert is_near_duplicate(simhash(FATWA_A), simhash(FATWA_B)) is False


# The same recording of Fatwa A run through a worse ASR pass: roughly one word in ten
# differs. This is the case layer 4 exists for.
FATWA_A_ASR = (
    "السوال يقول هل يجوز المسح علي الجوارب اذا كانا خفيفتين فالجواب ان المسح علي "
    "الجوربين جايز عند الجمهور اهل العلم بشرط ان يكونا ثابتين لمحل الفرض وان يكون "
    "لبسهما علي طهاره فاذا تواضا الانسان ولبس الجوربين وهو علي طهاره فانه يمسح عليهما "
    "يوما وليله ان كان مقيما وثلاثه ايام بلياليهن ان كان مسافرا واما اذا كان الجورب "
    "خفيفا يكشف البشره بحيث يري لون الجلد من وراءها فان الصحيح انه لا يجزي المسح عليه "
    "لانه ليس بساتر والمسح انما شرع علي ما يستر القدم ومن مسح علي جورب محرق خرقا "
    "يسير فان بعض اهل العلم رخص في ذلك فالاحوط ان يكون الجورب سليما والله اعلم"
)


def test_asr_noise_of_about_ten_percent_still_reads_as_a_near_duplicate() -> None:
    assert is_near_duplicate(simhash(FATWA_A), simhash(FATWA_A_ASR)) is True


def test_identical_text_has_distance_zero() -> None:
    assert hamming(simhash(FATWA_A), simhash(FATWA_A)) == 0


def test_a_single_changed_word_moves_the_hash_only_a_little() -> None:
    changed = FATWA_A.replace("مقيما", "مقيم")
    assert changed != FATWA_A
    assert hamming(simhash(FATWA_A), simhash(changed)) <= 3


def test_completely_different_text_is_far_apart() -> None:
    assert hamming(simhash(FATWA_A), simhash(FATWA_B)) > 6


def test_empty_text_hashes_to_zero() -> None:
    assert simhash("") == 0


def test_text_shorter_than_the_shingle_size_still_hashes() -> None:
    short = "نعم"
    assert len(short) < 4
    assert simhash(short, shingle_size=4) == simhash(short, shingle_size=4)
    assert simhash(short, shingle_size=4) != 0


def test_two_different_short_texts_do_not_collide() -> None:
    assert simhash("نعم", shingle_size=4) != simhash("لا", shingle_size=4)


def test_the_hash_fits_in_64_bits() -> None:
    assert 0 <= simhash(FATWA_A) < 2**64


def test_a_shingle_size_below_one_is_rejected() -> None:
    with pytest.raises(ValueError, match="shingle_size"):
        simhash(FATWA_A, shingle_size=0)


def test_hamming_counts_differing_bits() -> None:
    assert hamming(0b1011, 0b1001) == 1
    assert hamming(0, 0) == 0


def test_distance_exactly_at_the_threshold_still_counts_as_a_duplicate() -> None:
    six_bits = 0b111111
    assert hamming(0, six_bits) == 6
    assert is_near_duplicate(0, six_bits, threshold=6) is True


def test_distance_one_above_the_threshold_does_not_count() -> None:
    seven_bits = 0b1111111
    assert hamming(0, seven_bits) == 7
    assert is_near_duplicate(0, seven_bits, threshold=6) is False


def test_the_hash_is_stable_across_interpreter_runs() -> None:
    # simhash_ar is stored in the database and compared against hashes computed months
    # later by another process. The builtin hash() is salted per run and would quietly
    # stop matching after a restart, so this guards the choice of blake2b.
    script = (
        "import sys; sys.path.insert(0, 'src');"
        "from masdar.dedup.simhash import simhash;"
        "print(simhash(sys.argv[1]))"
    )
    runs = {
        subprocess.run(  # noqa: S603
            [sys.executable, "-I", "-c", script, FATWA_A],
            cwd=".",
            capture_output=True,
            text=True,
            check=True,
            env={"PYTHONHASHSEED": seed, "PATH": "/usr/bin:/bin"},
        ).stdout.strip()
        for seed in ("0", "1", "random")
    }
    assert runs == {str(simhash(FATWA_A))}


PG_BIGINT_MIN = -(2**63)
PG_BIGINT_MAX = 2**63 - 1


def test_a_hash_with_the_top_bit_set_does_not_fit_a_postgres_bigint_unconverted() -> None:
    # Guards the reason to_signed_64 exists at all.
    top_bit_set = 2**63 + 12345
    assert top_bit_set > PG_BIGINT_MAX


def test_every_hash_converts_into_the_range_of_a_postgres_bigint() -> None:
    texts = [FATWA_A, FATWA_A_ASR, FATWA_B, "نعم", "لا", "x" * 200]
    for text in texts:
        stored = to_signed_64(simhash(text))
        assert PG_BIGINT_MIN <= stored <= PG_BIGINT_MAX


def test_the_conversion_round_trips() -> None:
    for value in (0, 1, 2**62, 2**63, 2**63 + 7, 2**64 - 1):
        assert from_signed_64(to_signed_64(value)) == value


def test_hamming_is_unaffected_by_the_signed_representation() -> None:
    a, b = simhash(FATWA_A), simhash(FATWA_A_ASR)
    assert hamming(to_signed_64(a), to_signed_64(b)) == hamming(a, b)
