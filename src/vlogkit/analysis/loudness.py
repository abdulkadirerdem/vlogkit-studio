"""EBU R128 loudness measurement (YouTube normalises playback to about -14 LUFS)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from vlogkit.ff import PathLike, ffmpeg

_JSON = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}")
_MOMENTARY = re.compile(r"lavfi\.r128\.M=([-0-9.]+)")


@dataclass(frozen=True)
class Loudness:
    integrated: float  # LUFS
    true_peak: float  # dBTP
    lra: float  # LU
    threshold: float

    def __str__(self) -> str:
        return f"{self.integrated:.1f} LUFS, {self.true_peak:.1f} dBTP, LRA {self.lra:.1f}"


def parse_loudnorm(stderr: str) -> Loudness:
    m = json.loads(_JSON.search(stderr).group(0))
    return Loudness(
        float(m["input_i"]), float(m["input_tp"]), float(m["input_lra"]), float(m["input_thresh"])
    )


def measure(path: PathLike) -> Loudness:
    r = ffmpeg(
        ["-i", path, "-vn", "-af", "loudnorm=I=-14:TP=-1.5:print_format=json", "-f", "null", "-"],
        loglevel="info",
        capture=True,
    )
    return parse_loudnorm(r.stderr)


def momentary(path: PathLike) -> list[tuple[float, float]]:
    """(time, momentary loudness LUFS) every 100 ms: use it to balance SFX against the music."""
    r = ffmpeg(
        [
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
    return [((i + 1) * 0.1, float(v)) for i, v in enumerate(_MOMENTARY.findall(r.stderr))]
