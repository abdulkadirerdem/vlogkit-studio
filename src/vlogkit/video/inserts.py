"""Cut-aways: replace the picture for a moment with another clip (music keeps running)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from vlogkit.timecode import fmt


@dataclass(frozen=True)
class Insert:
    """Show `file[src : src+dur]` from timeline time `at`, cropped to fill the frame.

    Put `at` between two frames (see timecode.before_frame) and end the window just before the
    next cut. fx/fy choose the crop centre inside the (scaled) clip, 0..1.
    """

    file: str | Path
    at: float
    dur: float
    src: float = 0.0
    fx: float = 0.5
    fy: float = 0.5
    look: str = "eq=saturation=1.15:contrast=1.05"


def overlay_inserts(
    src: str, inserts: Sequence[Insert], first_input: int, out: str, w: int = 1080, h: int = 1920
) -> str:
    """Graph fragment: [src] + each insert (inputs first_input..) -> [out]."""
    if not inserts:
        return f"[{src}]null[{out}]"
    parts, cur = [], src
    for k, ins in enumerate(inserts):
        # read ~0.3 s past the window: if the clip hits EOF inside the window, overlay passes the
        # original frame through and one stray frame flashes before the next cut
        parts.append(
            f"[{first_input + k}:v]trim=start={fmt(ins.src)}:duration={fmt(ins.dur + 0.3)},"
            "setpts=PTS-STARTPTS,fps=30000/1001,"
            f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,"
            f"crop={w}:{h}:x='(iw-{w})*{fmt(ins.fx)}':y='(ih-{h})*{fmt(ins.fy)}',"
            f"{ins.look},setpts=PTS+{fmt(ins.at)}/TB,setsar=1[ins{k}]"
        )
        nxt = out if k == len(inserts) - 1 else f"{src}_i{k}"
        parts.append(
            f"[{cur}][ins{k}]overlay=0:0:eof_action=pass:"
            f"enable='between(t,{fmt(ins.at)},{fmt(ins.at + ins.dur - 0.001)})'[{nxt}]"
        )
        cur = nxt
    return ";".join(parts)


def insert_inputs(inserts: Sequence[Insert]) -> list[list[str]]:
    return [["-i", str(ins.file)] for ins in inserts]
