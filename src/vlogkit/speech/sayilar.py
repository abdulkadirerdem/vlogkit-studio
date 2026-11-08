"""Numbers to Turkish words before speech: the voice models read digits badly ("1.250" ->
"bin iki yüz elli", "%38" -> "yüzde otuz sekiz", "2,5" -> "iki virgül beş").

Turkish writes thousands with "." and decimals with ","; "1.250" is one thousand two hundred and
fifty, "2,5" two and a half. A number glued to a unit keeps the unit ("600 ton").
"""

from __future__ import annotations

import re

ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]
SCALES = [
    (10**18, "kentilyon"),
    (10**15, "katrilyon"),
    (10**12, "trilyon"),
    (10**9, "milyar"),
    (10**6, "milyon"),
    (10**3, "bin"),
]


def _under_thousand(n: int) -> str:
    h, rest = divmod(n, 100)
    t, o = divmod(rest, 10)
    out = []
    if h:
        out.append("yüz" if h == 1 else f"{ONES[h]} yüz")
    if t:
        out.append(TENS[t])
    if o:
        out.append(ONES[o])
    return " ".join(out)


def integer(n: int) -> str:
    if n == 0:
        return "sıfır"
    if n < 0:
        return "eksi " + integer(-n)
    out = []
    for value, name in SCALES:
        if n >= value:
            k, n = divmod(n, value)
            out.append(name if (value == 1000 and k == 1) else f"{integer(k)} {name}")
    if n:
        out.append(_under_thousand(n))
    return " ".join(out)


def _number(text: str) -> str:
    """'1.250' / '2,5' / '1.250,75' -> words."""
    whole, _, frac = text.partition(",")
    n = int(whole.replace(".", "") or 0)
    words = integer(n)
    if frac:
        words += " virgül " + (
            integer(int(frac))
            if not frac.startswith("0")
            else " ".join(ONES[int(d)] or "sıfır" for d in frac)
        )
    return words


_VOWELS = "aıeioöuü"


def ordinal(n: int) -> str:
    """5 -> 'beşinci', 4 -> 'dördüncü', 29 -> 'yirmi dokuzuncu' (the suffix follows the last
    word's last vowel; a word ending in a vowel drops the suffix's own)."""
    words = integer(n).split()
    last = words[-1]
    if last == "dört":
        last = "dörd"  # the t softens before a vowel
    v = next(c for c in reversed(last) if c in _VOWELS)
    harmony = {"a": "ı", "ı": "ı", "e": "i", "i": "i", "o": "u", "u": "u", "ö": "ü", "ü": "ü"}[v]
    suffix = f"{harmony}nc{harmony}"
    words[-1] = last + (suffix[1:] if last[-1] in _VOWELS else suffix)
    return " ".join(words)


# "5. gün", "29. gün": a number with a dot followed by a lower-case word is an ordinal; at the end
# of a sentence ("Seviye 8. Hazır mısın?") it is not
_ORD = re.compile(r"(?<![\w.,])(\d+)\.(?=\s+[a-zçğıöşü])")
_NUM = re.compile(r"(?<![\w])(%\s?)?(\d{1,3}(?:\.\d{3})+|\d+)(,\d+)?(?![\d])")


def spell(text: str) -> str:
    """Every number in `text` written out; percent signs read as 'yüzde'; "5. gün" as an
    ordinal ("beşinci gün")."""

    def sub(m: re.Match) -> str:
        pct = "yüzde " if m.group(1) else ""
        return pct + _number(m.group(2) + (m.group(3) or ""))

    text = _ORD.sub(lambda m: ordinal(int(m.group(1))), text)
    return re.sub(r"\s+", " ", _NUM.sub(sub, text)).strip()
