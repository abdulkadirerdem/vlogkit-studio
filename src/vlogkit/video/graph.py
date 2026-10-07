"""Assembling segments into a frame-accurate picture and writing the ProRes intermediate."""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from vlogkit.ff import ffmpeg
from vlogkit.timecode import FPS_NTSC

# 10-bit 4:2:2 ProRes HQ: fast to decode, survives the grade + overlay without banding.
PRORES_HQ = [
    "-c:v",
    "prores_ks",
    "-profile:v",
    "3",
    "-pix_fmt",
    "yuv422p10le",
    "-color_primaries",
    "bt709",
    "-color_trc",
    "bt709",
    "-colorspace",
    "bt709",
]

SEGMENT_TAIL = "setsar=1,format=yuv422p10le"


def concat(
    labels: Sequence[str], fps: Fraction = FPS_NTSC, tail_black: int = 0, out: str = "v"
) -> str:
    """Concatenate video segments and force uniform timestamps.

    Do NOT put an `fps` filter after concat: at segment boundaries it can drop a frame and shift
    everything after it (1 frame off the music). `settb + setpts=N` renumbers frames instead.
    """
    ins = "".join(f"[{x}]" for x in labels)
    chain = (
        f"{ins}concat=n={len(labels)}:v=1:a=0,settb=expr={fps.denominator}/{fps.numerator},setpts=N"
    )
    if tail_black:
        chain += f",tpad=stop_mode=add:stop={tail_black}:color=black"
    return f"{chain}[{out}]"


def render_intermediate(
    inputs: Sequence[Sequence[str | Path]],
    filter_complex: str,
    out: str | Path,
    map_label: str = "[v]",
) -> Path:
    """inputs = groups of input args, e.g. [["-i", a], ["-framerate", "30000/1001", "-i", pat]]."""
    args: list = ["-y"]
    for group in inputs:
        args += list(group)
    args += ["-filter_complex", filter_complex, "-map", map_label, *PRORES_HQ, out]
    ffmpeg(args)  # "error": the PNG->yuv swscaler warnings are harmless noise
    return Path(out)
