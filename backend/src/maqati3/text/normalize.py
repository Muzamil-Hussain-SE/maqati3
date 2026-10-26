"""Search normalisation for Arabic.

One function, one contract, because the same transformation has to be reproduced
exactly in SQL later. Any change here is a corpus-wide reindex.
"""

import re
import unicodedata

# Tashkeel (U+064B-U+0652), superscript alef (U+0670), the hamza/madda marks
# (U+0653-U+0655), and tatweel (U+0640). All deleted outright.
#
# U+0656-U+065F, U+0610-U+061A and U+06D6-U+06ED are Qur'anic annotation: small
# reading marks, honorific signs (sallallahu alayhi wa sallam, radi allahu anhu), and
# the small waw/yeh that mark a letter as silent in recitation. None of them is ever
# typed in plain Arabic, so a verse in mushaf spelling only normalises to the same
# form as the same words typed plainly if these are stripped too -- and a quoted verse
# is the single most common text a fatwa corpus has to match. U+06E5/U+06E6 fall in
# that same Qur'anic-annotation range but are letters (category Lm) rather than
# combining marks, so they need listing by hand rather than by Unicode category.
_REMOVE = dict.fromkeys(
    [
        *range(0x064B, 0x0656),
        0x0670,
        0x0640,
        *range(0x0656, 0x0660),
        *range(0x0610, 0x061B),
        *range(0x06D6, 0x06EE),
    ],
    None,
)

_FOLD = str.maketrans(
    {
        "أ": "ا",  # alef with hamza above
        "إ": "ا",  # alef with hamza below
        "آ": "ا",  # alef with madda above
        "ٱ": "ا",  # alef wasla
        "ى": "ي",  # alef maqsura -> ya
        "ة": "ه",  # ta marbuta -> ha
        "ؤ": "و",  # hamza on waw -> waw
        "ئ": "ي",  # hamza on ya -> ya
        # Letterforms no Arabic keyboard produces, but Persian, Urdu and Kurdish ones
        # do. In text that is meant to be Arabic they are the Arabic letter -- same
        # shape, same reading, different codepoint -- and text copied off the web is
        # full of them. Persian consonants with no Arabic counterpart (پ چ ژ گ) are
        # deliberately left alone: those are not variants of anything.
        "ی": "ي",  # farsi yeh
        "ے": "ي",  # yeh barree
        "ۓ": "ي",  # yeh barree with hamza above
        "ک": "ك",  # keheh
        "ھ": "ه",  # heh doachashmee
        "ہ": "ه",  # heh goal
        "ۂ": "ه",  # heh goal with hamza above
        "ۀ": "ه",  # heh with yeh above
        "ە": "ه",  # ae
        "ۃ": "ه",  # teh marbuta goal (urdu/sindhi/pashto ta marbuta)
        "ں": "ن",  # noon ghunna
        **{chr(0x0660 + d): str(d) for d in range(10)},  # arabic-indic digits
        **{chr(0x06F0 + d): str(d) for d in range(10)},  # extended arabic-indic digits
    }
)

_WHITESPACE = re.compile(r"\s+")


def normalize_ar(s: str) -> str:
    """Return the search form of ``s``.

    The steps, in exactly the order they are applied — SQL must reproduce this order,
    because the folding steps are not commutative with the removal steps (NFKC first
    composes a bare alef plus U+0654 into U+0623, which step 2 therefore cannot strip,
    and step 4 then folds it to a bare alef; the same holds for ۀ and ۓ in step 8):

    1. NFKC
    2. remove tashkeel U+064B-U+0652, superscript alef U+0670, marks U+0653-U+0655
    3. remove Qur'anic annotation: small reading marks U+0656-U+065F, honorific signs
       U+0610-U+061A, small high/low signs and the small waw/yeh U+06D6-U+06ED
    4. remove tatweel U+0640
    5. alef variants أ إ آ ٱ -> ا
    6. alef maqsura ى -> ي
    7. ta marbuta ة -> ه
    8. hamza carriers ؤ -> و, ئ -> ي
    9. Persian, Urdu and Kurdish letterforms: ی ے ۓ -> ي, ک -> ك,
       ھ ہ ۂ ۀ ە ۃ -> ه, ں -> ن
    10. arabic-indic digits ٠-٩ and ۰-۹ -> 0-9
    11. collapse whitespace runs to a single space, then trim

    Deterministic and idempotent: ``normalize_ar(normalize_ar(x)) == normalize_ar(x)``.

    This is the SEARCH form and nothing else. ``text_raw`` is what the site displays;
    ``text_norm`` is what it searches. Never apply ``normalize_ar`` to display text —
    it destroys vocalisation, which for a Qur'anic quotation is a corruption of the
    text, not a formatting detail.
    """
    folded = unicodedata.normalize("NFKC", s).translate(_REMOVE).translate(_FOLD)
    return _WHITESPACE.sub(" ", folded).strip()
