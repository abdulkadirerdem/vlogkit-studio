"""Average brightness over time -> find dim shots that need an exposure lift."""

from __future__ import annotations

import re

from vlogkit.ff import PathLike, ffmpeg

_VAL = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")


def luma_curve(
    path: PathLike, fps: float = 4.0, crop: str | None = None
) -> list[tuple[float, float]]:
    """(time, mean luma 0-255) sampled `fps` times per second.

    The analysis stream is converted to 8-bit YUV before signalstats so 10/12/16-bit
    sources use the same code-value scale and dark threshold as 8-bit sources. This
    is measurement-only (not an exposure correction or HDR-to-SDR tone mapping).

    crop: "crop=w:h:x:y" to measure only the picture of a letterboxed video
    (`analysis.letterbox.active_area(...).crop()`); black bars make every shot look dim.
    """
    pre = f"{crop}," if crop else ""
    r = ffmpeg(
        [
            "-i",
            path,
            "-vf",
            f"fps={fps},{pre}format=yuv444p,signalstats,metadata=print:key=lavfi.signalstats.YAVG",
            "-an",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
        capture=True,
    )
    vals = [float(v) for v in _VAL.findall(r.stderr)]
    return [(i / fps, v) for i, v in enumerate(vals)]


def dark_spans(
    curve: list[tuple[float, float]], threshold: float = 45.0, min_len: float = 0.5
) -> list[tuple[float, float]]:
    """Merge consecutive samples below `threshold` into (start, end) spans of at least min_len s."""
    if not curve:
        return []
    step = curve[1][0] - curve[0][0] if len(curve) > 1 else 0.25
    spans: list[tuple[float, float]] = []
    start = None
    for t, y in curve:
        if y < threshold and start is None:
            start = t
        elif y >= threshold and start is not None:
            spans.append((start, t))
            start = None
    if start is not None:
        spans.append((start, curve[-1][0] + step))
    return [(a, b) for a, b in spans if b - a >= min_len]
