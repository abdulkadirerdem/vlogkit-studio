"""Frame <-> time helpers. All edits are frame-accurate: think in frames, express in seconds."""

from __future__ import annotations

from fractions import Fraction

FPS_NTSC = Fraction(30000, 1001)  # 29.97, what phones/GoPros record as "30 fps"


def frame_at(t: float, fps: Fraction = FPS_NTSC) -> int:
    """Index of the frame displayed at time t."""
    return round(t * fps)


def time_of(frame: int, fps: Fraction = FPS_NTSC) -> float:
    return float(frame / fps)


def before_frame(frame: int, fps: Fraction = FPS_NTSC) -> float:
    """A time halfway between frame-1 and frame.

    Use it for `enable=between(t,...)` window edges so it is unambiguous which frame is the first
    one affected (a window starting exactly on a frame timestamp is at the mercy of float error).
    """
    return float((Fraction(frame) - Fraction(1, 2)) / fps)


def fmt(x: float) -> str:
    """Compact number for ffmpeg expressions (39.138 -> '39.138', 32.730000000000004 -> '32.73')."""
    return format(x, ".6g")
