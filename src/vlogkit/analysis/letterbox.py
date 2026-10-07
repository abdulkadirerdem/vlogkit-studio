"""Letterboxed / pillarboxed video: find the picture inside the black bars.

Common with re-exported phone edits (a 16:9 vlog placed on a 9:16 canvas). Everything that looks
at the whole frame is then wrong: the bars pull the mean luma down (every shot looks "dim"), and
crops/zooms work on the bars. Measure and reframe on the active area instead.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from vlogkit.ff import PathLike, ffmpeg

_CROP = re.compile(r"crop=(\d+):(\d+):(\d+):(\d+)")


@dataclass(frozen=True)
class Box:
    w: int
    h: int
    x: int
    y: int

    def crop(self) -> str:
        return f"crop={self.w}:{self.h}:{self.x}:{self.y}"

    def inset(self, px: int) -> Box:
        """Shave `px` from each edge (bar edges are blended with the picture by the scaler)."""
        return Box(self.w - 2 * px, self.h - 2 * px, self.x + px, self.y + px)

    def shave(self, top: int = 0, bottom: int = 0, left: int = 0, right: int = 0) -> Box:
        return Box(self.w - left - right, self.h - top - bottom, self.x + left, self.y + top)


def boxes(path: PathLike, fps: float = 2.0, limit: int = 24) -> list[tuple[float, Box]]:
    """(time, active area) per sampled frame, from ffmpeg's cropdetect."""
    r = ffmpeg(
        [
            "-i",
            path,
            "-vf",
            f"fps={fps},cropdetect=limit={limit}:round=2:reset=1",
            "-an",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
        capture=True,
    )
    found = [Box(*map(int, m)) for m in _CROP.findall(r.stderr)]
    return [(i / fps, b) for i, b in enumerate(found)]


def active_area(path: PathLike, fps: float = 2.0) -> Box:
    """The most common active area. Dark frames give smaller boxes; the mode ignores them."""
    found = boxes(path, fps)
    if not found:
        raise RuntimeError(f"cropdetect sonuç vermedi: {path}")
    return Counter(b for _, b in found).most_common(1)[0][0]
