"""YouTube chapters: the '0:00 Title' lines that go into the video description.

YouTube only turns them into chapters if the list starts at 0:00, has at least 3 entries and
every chapter is at least 10 s long; otherwise it silently shows plain timestamps.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

MIN_CHAPTERS = 3
MIN_LENGTH = 10.0  # seconds


@dataclass(frozen=True)
class Chapter:
    start: float  # seconds on the delivered timeline
    title: str


def stamp(seconds: int) -> str:
    """75 -> '1:15', 3725 -> '1:02:05'."""
    h, rest = divmod(int(seconds), 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def chapter_seconds(chapters: Sequence[Chapter]) -> list[int]:
    """Whole-second stamps, rounded *up*: a click never lands on the previous chapter's tail."""
    return [0 if i == 0 else math.ceil(c.start - 1e-6) for i, c in enumerate(chapters)]


def youtube_chapters(chapters: Sequence[Chapter], duration: float) -> str:
    """Validated description block. Raises ValueError with the broken rule."""
    if len(chapters) < MIN_CHAPTERS:
        raise ValueError(f"en az {MIN_CHAPTERS} bölüm gerekli")
    if chapters[0].start > 0.5:
        raise ValueError("ilk bölüm 0:00'da başlamalı")
    secs = chapter_seconds(chapters)
    ends = [*secs[1:], math.floor(duration)]
    for c, a, b in zip(chapters, secs, ends, strict=True):
        if b - a < MIN_LENGTH:
            raise ValueError(f"'{c.title}' {b - a} sn; YouTube en az {MIN_LENGTH:g} sn istiyor")
    return "\n".join(f"{stamp(s)} {c.title}" for s, c in zip(secs, chapters, strict=True))
