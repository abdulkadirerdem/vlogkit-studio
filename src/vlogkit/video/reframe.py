"""Low-res / letterboxed sources onto a bigger delivery canvas.

A 16:9 vlog re-exported onto a 464x832 vertical canvas holds a 464x262 picture. Delivered as a
1920x1080 YouTube video that is a 4x upscale, which exposes the source's macroblocks. Clean at the
source size (spp deblock + light temporal denoise: cheap there), scale with lanczos, then sharpen
with contrast-adaptive sharpening (no halos like a strong unsharp).
"""

from __future__ import annotations

from fractions import Fraction

from vlogkit.analysis.letterbox import Box

CLEAN = "spp=4:3,hqdn3d=2:1.5:3:3"
SHARPEN = "cas=strength=0.6"


def cfr(fps: Fraction) -> str:
    """Constant frame rate. Phone re-exports are often variable (60 fps parts in a 30 fps edit);
    put this first so every later `t` / frame count is on a fixed grid."""
    return f"fps={fps.numerator}/{fps.denominator}"


def crop(box: Box, y: str | None = None, x: str | None = None) -> str:
    """Crop to `box`; x / y may be per-frame expressions (e.g. a different framing for one shot)."""
    return f"crop={box.w}:{box.h}:x='{x or box.x}':y='{y or box.y}'"


def upscale(w: int, h: int, clean: str | None = CLEAN, sharpen: str | None = SHARPEN) -> str:
    parts = [clean, f"scale={w}:{h}:flags=lanczos", sharpen]
    return ",".join(p for p in parts if p)
