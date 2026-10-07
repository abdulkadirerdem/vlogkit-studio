"""Thin wrappers around ffmpeg / ffprobe.

Always build commands as argument lists (never shell strings): filter graphs are full of quotes,
commas and brackets that shells mangle.
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from vlogkit.config import require, tools

PathLike = str | Path


class FFmpegError(RuntimeError):
    pass


def ffmpeg(
    args: Sequence[str | Path], *, loglevel: str = "error", capture: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run ffmpeg. With capture=True stderr is returned (ffmpeg logs/analysis go to stderr)."""
    cmd = [require(tools().ffmpeg, "ffmpeg"), "-hide_banner", "-v", loglevel, *map(str, args)]
    r = subprocess.run(cmd, capture_output=capture, text=True)
    if r.returncode != 0:
        tail = "\n".join((r.stderr or "").strip().splitlines()[-15:])
        raise FFmpegError(f"ffmpeg failed ({r.returncode})\n{tail}")
    return r


def ffprobe_json(path: PathLike, *extra: str) -> dict:
    cmd = [
        require(tools().ffprobe, "ffprobe"),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        *extra,
        str(path),
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path}: {r.stderr.strip()}")
    return json.loads(r.stdout)


@dataclass(frozen=True)
class MediaInfo:
    path: Path
    duration: float
    width: int | None
    height: int | None
    fps: Fraction | None
    frames: int | None
    has_audio: bool
    sample_rate: int | None
    rotation: int = 0  # degrees ffmpeg turns the picture when it decodes (display matrix / tag)

    @property
    def display_size(self) -> tuple[int | None, int | None]:
        """Width and height as decoded and shown (a 90/270 rotation swaps the stored size)."""
        if self.rotation % 180:
            return self.height, self.width
        return self.width, self.height

    @property
    def vertical(self) -> bool:
        w, h = self.display_size
        return bool(w and h and h > w)


def probe(path: PathLike, *, count_frames: bool = False) -> MediaInfo:
    extra = ("-count_frames",) if count_frames else ()
    j = ffprobe_json(path, *extra)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    fps = frames = None
    if v:
        num, den = (int(x) for x in v.get("r_frame_rate", "0/1").split("/"))
        fps = Fraction(num, den) if den and num else None
        n = v.get("nb_read_frames") or v.get("nb_frames")
        frames = int(n) if n else None
    rotation = 0
    if v:
        rots = [int(d["rotation"]) for d in v.get("side_data_list", []) if "rotation" in d]
        rots += [int(v.get("tags", {}).get("rotate", 0) or 0)]
        rotation = next((r % 360 for r in rots if r % 360), 0)
    return MediaInfo(
        rotation=rotation,
        path=Path(path),
        duration=float(j["format"].get("duration", 0.0)),
        width=v and v.get("width"),
        height=v and v.get("height"),
        fps=fps,
        frames=frames,
        has_audio=a is not None,
        sample_rate=int(a["sample_rate"]) if a else None,
    )


def extract_frame(src: PathLike, t: float, out: PathLike, vf: str | None = None) -> Path:
    """Grab one frame. Note: with -ss before -i, `t` inside filters restarts at 0."""
    args: list[str | Path] = ["-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1"]
    if vf:
        args += ["-vf", vf]
    ffmpeg([*args, out])
    return Path(out)
