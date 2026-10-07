"""Hard-cut detection with ffmpeg's `scdet`."""

from __future__ import annotations

import re

from vlogkit.ff import PathLike, ffmpeg

_SCD = re.compile(r"lavfi\.scd\.time: ([0-9.]+)")


def detect_cuts(path: PathLike, threshold: float = 8.0) -> list[float]:
    """Timestamps (s) of the first frame after each cut.

    threshold 8 works well for handheld phone/GoPro footage; lower it for subtle cuts. Also use it
    to *verify* a render: an edit that keeps the music must reproduce the source cut times exactly.
    """
    r = ffmpeg(
        ["-i", path, "-vf", f"scdet=threshold={threshold}", "-an", "-f", "null", "-"],
        loglevel="info",
        capture=True,
    )
    return [float(x) for x in _SCD.findall(r.stderr)]
