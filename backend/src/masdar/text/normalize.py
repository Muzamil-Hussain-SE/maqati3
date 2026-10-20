"""Search normalisation for Arabic.

One function, one contract, because the same transformation has to be reproduced
exactly in SQL later. Any change here is a corpus-wide reindex.
"""

import re
import unicodedata

# Tashkeel (U+064B-U+0652), superscript alef (U+0670), the hamza/madda marks
# (U+0653-U+0655), and tatweel (U+0640). All deleted outright.
_REMOVE = dict.fromkeys([*range(0x064B, 0x0656), 0x0670, 0x0640], None)

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
    and step 4 then folds it to a bare alef):

    1. NFKC
    2. remove tashkeel U+064B-U+0652, superscript alef U+0670, marks U+0653-U+0655
    3. remove tatweel U+0640
    4. alef variants أ إ آ ٱ -> ا
    5. alef maqsura ى -> ي
    6. ta marbuta ة -> ه
    7. hamza carriers ؤ -> و, ئ -> ي
    8. arabic-indic digits ٠-٩ and ۰-۹ -> 0-9
    9. collapse whitespace runs to a single space, then trim

    Deterministic and idempotent: ``normalize_ar(normalize_ar(x)) == normalize_ar(x)``.

    This is the SEARCH form and nothing else. ``text_raw`` is what the site displays;
    ``text_norm`` is what it searches. Never apply ``normalize_ar`` to display text —
    it destroys vocalisation, which for a Qur'anic quotation is a corruption of the
    text, not a formatting detail.
    """
    folded = unicodedata.normalize("NFKC", s).translate(_REMOVE).translate(_FOLD)
    return _WHITESPACE.sub(" ", folded).strip()
