"""Does the opening hook? Checked on the rendered video before delivery.

docs/viral-edit.md: a Short has about 1 second to stop the swipe and must state its promise
within 1-3 s. A long video states it within ~10 s and treats the first 30 s like a trailer.
A check is `ok=True/False`, or `None` when there was nothing to check it against.
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageStat

from vlogkit.analysis import pacing
from vlogkit.analysis.transcribe import Segment
from vlogkit.ff import PathLike, extract_frame, ffmpeg, probe

WINDOW = {"short": 3.0, "long": 10.0}  # the promise must be seen or heard by then
_M = re.compile(r"lavfi\.r128\.M=(-?[0-9.]+)")


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool | None
    detail: str

    def line(self) -> str:
        mark = {True: "✓", False: "!", None: "·"}[self.ok]
        return f"{mark} {self.name}: {self.detail}"


def first_sound(path: PathLike, level: float = -35.0, within: float = 15.0) -> float | None:
    """First moment the momentary loudness goes above `level` LUFS."""
    r = ffmpeg(
        [
            "-t",
            f"{within}",
            "-i",
            path,
            "-vn",
            "-af",
            "ebur128=metadata=1,ametadata=print:key=lavfi.r128.M",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
        capture=True,
    )
    for i, v in enumerate(_M.findall(r.stderr)):
        if float(v) > level:
            return i * 0.1  # the 400 ms window ending here: sound is there at this time
    return None


def frame_blank(path: PathLike, t: float = 0.0) -> bool:
    """Black or flat (a fade-in, a title card on a plain background)."""
    with tempfile.TemporaryDirectory() as tmp:
        png = extract_frame(path, t, Path(tmp) / "f.png", vf="scale=160:-2")
        st = ImageStat.Stat(Image.open(png).convert("L"))
    return st.mean[0] < 14 or st.stddev[0] < 6


def _norm(text: str) -> str:
    return re.sub(r"[^\wçğıöşü ]+", " ", text.replace("I", "ı").replace("İ", "i").lower())


def promise_seen(
    promise: Sequence[str],
    window: float,
    words: Sequence[Segment] = (),
    captions: Sequence[tuple[float, str]] = (),
) -> tuple[bool, str]:
    spoken = _norm(" ".join(w.text for w in words if w.start <= window))
    shown = _norm(" ".join(text for t0, text in captions if t0 <= window))
    for p in promise:
        key = _norm(p).strip()
        if key and key in spoken:
            return True, f"“{p}” {window:g} sn içinde söyleniyor"
        if key and key in shown:
            return True, f"“{p}” {window:g} sn içinde ekranda"
    return False, f"vaat ({', '.join(promise)}) ilk {window:g} sn'de ne söyleniyor ne yazıyor"


def _screen_text(path: PathLike, window: float) -> list[tuple[float, str]]:
    from vlogkit.analysis import ocr

    if not ocr.available():
        return []
    try:
        timeline = ocr.text_timeline(path, fps=2.0, duration=window + 0.5)
    except Exception:  # OCR is a bonus: never fail the check because of it
        return []
    return [(t, " ".join(x.text for x in texts)) for t, texts in timeline if ocr.is_caption(texts)]


def check(
    path: PathLike,
    kind: str | None = None,
    *,
    promise: Sequence[str] = (),
    words: Sequence[Segment] | None = None,
    captions: Sequence[tuple[float, str]] = (),
) -> list[Check]:
    """kind: "short" | "long". words: whisper words of (at least) the opening, if available."""
    info = probe(path)
    kind = kind or ("short" if info.vertical else "long")
    window = WINDOW[kind]
    out = []

    blank = frame_blank(path)
    out.append(
        Check(
            "Açılış karesi",
            not blank,
            "siyah ya da düz: ilk kare bir şey göstermeli" if blank else "dolu",
        )
    )

    sound = first_sound(path) if info.has_audio else None
    if sound is None:
        out.append(Check("İlk ses", False, "ilk 15 sn'de ses yok"))
    else:
        out.append(Check("İlk ses", sound <= 0.5, f"{sound:.1f} sn'de başlıyor (hedef <= 0,5 sn)"))

    motion = max((s for _, s in pacing.scores(path, start=0.0, duration=1.0)), default=0.0)
    out.append(
        Check(
            "İlk saniyede hareket",
            motion >= 2.0,
            f"en büyük kare farkı {motion:.1f} (>= 2 bir şey değişiyor demek)",
        )
    )

    if not captions:  # no project: read the text that is on screen (Vision OCR, macOS)
        captions = _screen_text(path, window)
    words = [w for w in (words or []) if not w.suspicious]
    first_word = words[0].start if words else None
    first_caption = min((t0 for t0, _ in captions), default=None)
    first = min((x for x in (first_word, first_caption) if x is not None), default=None)
    if first is None:
        out.append(Check("İlk söz/yazı", None, "konuşma ve altyazı bilgisi yok"))
    else:
        src = "konuşma" if first == first_word else "altyazı"
        out.append(
            Check(
                "İlk söz/yazı",
                first <= window,
                f"ilk {src} {first:.1f} sn'de (hedef <= {window:g} sn)",
            )
        )

    if promise:
        ok, detail = promise_seen(promise, window, words, captions)
        out.append(Check("Vaat", ok, detail))
    else:
        out.append(Check("Vaat", None, 'vaat kelimeleri verilmedi (--promise "zirve,5 saat")'))
    return out
