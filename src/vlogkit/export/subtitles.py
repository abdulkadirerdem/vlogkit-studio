"""Subtitle cues -> SubRip (.srt), the format YouTube accepts for closed captions.

Keep one list of cues per video and use it twice: burned into the picture (`Subtitle` elements)
and as an .srt next to the delivery file, so both always say and time the same thing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from itertools import pairwise
from pathlib import Path

_TIME = re.compile(
    r"(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})\s*-->\s*(\d+):(\d{1,2}):(\d{1,2})[,.](\d{1,3})"
)


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str  # "\n" = line break; [accent] brackets are stripped in the .srt

    def shifted(self, offset: float) -> Cue:
        return replace(self, start=self.start + offset, end=self.end + offset)


def srt_time(t: float) -> str:
    """Seconds -> 'HH:MM:SS,mmm'."""
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def plain(text: str) -> str:
    """Caption markup -> subtitle text: accent brackets removed."""
    return text.replace("[", "").replace("]", "")


def to_srt(cues: Iterable[Cue]) -> str:
    cues = sorted(cues, key=lambda c: c.start)
    blocks = []
    for i, c in enumerate(cues, 1):
        if c.end <= c.start:
            raise ValueError(f"altyazı süresi yok: {c}")
        blocks.append(f"{i}\n{srt_time(c.start)} --> {srt_time(c.end)}\n{plain(c.text)}\n")
    for a, b in pairwise(cues):
        if b.start < a.end:
            raise ValueError(f"altyazılar çakışıyor: {a.text!r} / {b.text!r}")
    return "\n".join(blocks)


def write_srt(cues: Iterable[Cue], path: str | Path) -> Path:
    path = Path(path)
    path.write_text(to_srt(cues), encoding="utf-8")
    return path


def _secs(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse_srt(text: str) -> list[Cue]:
    """SubRip text -> cues (the user's corrected subtitles). Tolerates a BOM, Windows line ends,
    '.' instead of ',' before the milliseconds, missing index lines and extra blank lines.
    Multi-line cues keep their line break ("\n")."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    cues: list[Cue] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [ln for ln in block.split("\n") if ln.strip()]
        for i, line in enumerate(lines):
            m = _TIME.search(line)
            if m:
                body = "\n".join(ln.strip() for ln in lines[i + 1 :])
                if body:
                    cues.append(Cue(_secs(*m.group(1, 2, 3, 4)), _secs(*m.group(5, 6, 7, 8)), body))
                break
    return sorted(cues, key=lambda c: c.start)


def read_srt(path: str | Path) -> list[Cue]:
    return parse_srt(Path(path).read_text(encoding="utf-8-sig"))
