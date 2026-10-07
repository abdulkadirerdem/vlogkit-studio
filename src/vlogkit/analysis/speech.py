"""Dead air and filler words: what to cut from talking footage (the first rough cut, "A-cut").

Two sources, used together:
- whisper word timestamps (`transcribe(words=True)`): pauses between words and filler words.
  Whisper usually leaves disfluencies ("ııı", "eee") out of the text, so a filler shows up as a
  *gap* between two words and is caught as a pause.
- ffmpeg `silencedetect`: pauses with nobody talking. Works without speech recognition, but not
  under music (music is never "silent").

Nothing is cut automatically. The result is a list of candidates for the plan; the approved ones
go through `keep_segments` into `video.jumpcut`. Soft candidates are listed but only cut when
explicitly included: fillers that often carry meaning ("yani", "şey") and long stretches without
speech ("quiet", > 2.5 s), which in a vlog are usually action (running, scenery), not dead air.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, replace
from itertools import pairwise

from vlogkit.analysis.transcribe import Segment
from vlogkit.ff import PathLike, ffmpeg

FILLERS = {
    "tr": (
        {"ı", "ıı", "ııı", "ıh", "e", "ee", "eee", "hmm", "hm", "mmm", "aa", "aaa", "ah", "öö"},
        {"şey", "yani", "işte", "hani", "falan", "böyle"},
    ),
    "en": (
        {"um", "umm", "uh", "uhh", "uhm", "erm", "hmm", "hm", "ah", "eh"},
        {"like", "basically", "actually", "literally", "so"},
    ),
}
_SIL_START = re.compile(r"silence_start: (-?[0-9.]+)")
_SIL_END = re.compile(r"silence_end: ([0-9.]+)")


@dataclass(frozen=True)
class Cut:
    start: float
    end: float
    kind: str  # "pause" | "filler" | "quiet" (long stretch without speech)
    text: str = ""
    soft: bool = False  # a filler that may carry meaning: cut only on request

    @property
    def duration(self) -> float:
        return self.end - self.start


def _norm(word: str) -> str:
    w = word.replace("I", "ı").replace("İ", "i").lower()
    return re.sub(r"[^\wçğıöşü]+", "", w)


def word_cuts(
    words: Sequence[Segment], lang: str = "tr", min_pause: float = 0.45, pad: float = 0.12
) -> list[Cut]:
    """Pauses between words (keeping `pad` of breath on both sides) and filler words."""
    hard, soft = FILLERS.get(lang, (set(), set()))
    words = [w for w in words if not w.suspicious and _norm(w.text)]
    cuts = [
        Cut(a.end + pad, b.start - pad, "pause")
        for a, b in pairwise(words)
        if b.start - a.end >= min_pause + 2 * pad
    ]
    for w in words:
        n = _norm(w.text)
        if n in hard or n in soft:
            cuts.append(Cut(w.start, w.end, "filler", w.text.strip(), soft=n in soft))
    return merge(cuts)


def silences(
    path: PathLike, noise_db: float = -35, min_dur: float = 0.5
) -> list[tuple[float, float]]:
    r = ffmpeg(
        ["-i", path, "-vn", "-af", f"silencedetect=n={noise_db}dB:d={min_dur}", "-f", "null", "-"],
        loglevel="info",
        capture=True,
    )
    starts = [max(0.0, float(x)) for x in _SIL_START.findall(r.stderr)]
    ends = [float(x) for x in _SIL_END.findall(r.stderr)]
    return list(zip(starts, ends, strict=False))


def pause_cuts(spans: Sequence[tuple[float, float]], pad: float = 0.12) -> list[Cut]:
    return [Cut(a + pad, b - pad, "pause") for a, b in spans if b - a > 2 * pad + 0.05]


def merge(cuts: Sequence[Cut]) -> list[Cut]:
    """Overlapping candidates become one; the result is soft only if every part was soft."""
    out: list[Cut] = []
    for c in sorted(cuts, key=lambda c: c.start):
        if c.end <= c.start:
            continue
        if out and c.start <= out[-1].end:
            last = out[-1]
            kind = "filler" if "filler" in (last.kind, c.kind) else "pause"
            text = " ".join(t for t in (last.text, c.text) if t)
            out[-1] = replace(
                last, end=max(last.end, c.end), kind=kind, text=text, soft=last.soft and c.soft
            )
        else:
            out.append(c)
    return out


def find_cuts(
    path: PathLike,
    lang: str = "tr",
    *,
    words: Sequence[Segment] | None = None,
    min_pause: float = 0.45,
    pad: float = 0.12,
    silence: bool = True,
    max_pause: float = 2.5,
) -> list[Cut]:
    """All cut candidates of a talking clip (word gaps + fillers + silences)."""
    if words is None:
        from vlogkit.analysis.transcribe import transcribe

        words = transcribe(path, lang, words=True)
    cuts = word_cuts(words, lang, min_pause, pad)
    if silence:
        cuts += pause_cuts(silences(path, min_dur=min_pause + 2 * pad), pad)
    return [
        replace(c, kind="quiet", soft=True) if c.kind == "pause" and c.duration > max_pause else c
        for c in merge(cuts)
    ]


def keep_segments(
    duration: float,
    cuts: Sequence[Cut],
    *,
    include_soft: bool = False,
    min_keep: float = 0.25,
) -> list[tuple[float, float]]:
    """The parts to keep once `cuts` are removed. Slivers shorter than `min_keep` go too."""
    chosen = merge([c for c in cuts if include_soft or not c.soft])
    keep, t = [], 0.0
    for c in chosen:
        if c.start - t >= min_keep:
            keep.append((t, c.start))
        t = max(t, c.end)
    if duration - t >= min_keep:
        keep.append((t, duration))
    return keep


def saved(cuts: Sequence[Cut], include_soft: bool = False) -> float:
    return sum(c.duration for c in merge([c for c in cuts if include_soft or not c.soft]))
