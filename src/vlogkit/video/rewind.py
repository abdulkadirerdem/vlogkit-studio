"""'Rewind' montage: scrub backwards through a clip, decelerating onto a landing frame."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg

# VHS-ish treatment for the rewind frames (RGB split, grain, washed colour).
VHS = "rgbashift=rh=-9:bh=9:gv=2,noise=alls=16:allf=t,eq=contrast=1.12:saturation=0.8"


def ease_out_cubic(u: float) -> float:
    return 1 - (1 - u) ** 3


def reverse_scrub_times(
    valid: Sequence[tuple[float, float]], n: int, ease: Callable[[float], float] = ease_out_cubic
) -> list[float]:
    """n source times going from the end of `valid` back to its start.

    `valid` = usable spans (skip near-black stretches). With ease-out the scrub starts fast and
    lands softly on the first valid frame.
    """
    total = sum(b - a for a, b in valid)
    out = []
    for i in range(n):
        pos = total * (1 - ease(i / (n - 1)))
        for a, b in valid:
            if pos <= b - a:
                out.append(a + pos)
                break
            pos -= b - a
        else:
            out.append(valid[-1][1])
    return out


def extract_frames(
    src: PathLike, times: Sequence[float], out_dir: PathLike, vf: str | None = None
) -> str:
    """Write frames r_00.png.. in the given order. Returns an image2 pattern for ffmpeg."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    for i, t in enumerate(times):
        args: list = ["-y", "-ss", f"{t:.3f}", "-i", src, "-frames:v", "1"]
        if vf:
            args += ["-vf", vf]
        ffmpeg([*args, out / f"r_{i:02d}.png"])
    return str(out / "r_%02d.png")
