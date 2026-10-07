"""Picture-in-picture: a second video in a rounded window over the picture (a narrator in the
corner while the story plays), with a soft drop shadow and alpha fades in and out.

    mask, shadow = pip_assets(work, w=1152, h=648)
    inputs += [["-i", talk], *pip_inputs(mask, shadow, duration)]
    graph += pip_graph(base="cat", out="v", video=k, mask=k + 1, shadow=k + 2, ...)

The window is cut from the source with `crop` (w, h, x, y in source pixels), scaled to the window
size, given the rounded alpha of `mask` and placed at (x, y) on the canvas from timeline `t0` on.
Frames outside the window time are untouched (overlay `eof_action=pass`).
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from vlogkit.timecode import FPS_NTSC, fmt


@dataclass(frozen=True)
class Pip:
    t0: float  # timeline seconds the window appears
    duration: float  # seconds it stays
    x: int  # window position on the canvas (top-left, px)
    y: int
    w: int  # window size (px)
    h: int
    crop: tuple[int, int, int, int]  # source region: w, h, x, y
    src_start_frame: int = 0  # first source frame shown
    fade: float = 0.3  # alpha fade in (and out, unless fade_out is set), s; 0 = hard
    fade_out: float | None = None  # e.g. 0 where the next window continues seamlessly
    radius: int = 36  # corner radius (px)
    shadow: int = 40  # shadow blur (px); 0 = none
    vf: str = ""  # filters on the source before the crop (grade, denoise...)


def pip_assets(work: Path, p: Pip) -> tuple[Path, Path]:
    """The rounded alpha mask (window size) and a blurred shadow (window + margin) as PNGs."""
    work.mkdir(parents=True, exist_ok=True)
    mask = work / f"pip_mask_{p.w}x{p.h}_{p.radius}.png"
    if not mask.exists():
        m = Image.new("L", (p.w, p.h), 0)
        ImageDraw.Draw(m).rounded_rectangle((0, 0, p.w - 1, p.h - 1), radius=p.radius, fill=255)
        m.save(mask)
    shadow = work / f"pip_shadow_{p.w}x{p.h}_{p.radius}_{p.shadow}.png"
    if not shadow.exists():
        pad = 2 * p.shadow
        s = Image.new("RGBA", (p.w + 2 * pad, p.h + 2 * pad), (0, 0, 0, 0))
        a = Image.new("L", s.size, 0)
        ImageDraw.Draw(a).rounded_rectangle(
            (pad, pad + p.shadow // 3, pad + p.w, pad + p.h + p.shadow // 3),
            radius=p.radius,
            fill=150,
        )
        s.putalpha(a.filter(ImageFilter.GaussianBlur(max(1, p.shadow))) if p.shadow else a)
        s.save(shadow)
    return mask, shadow


def pip_inputs(mask: Path, shadow: Path, p: Pip, fps: Fraction = FPS_NTSC) -> list[list]:
    """ffmpeg input groups for the mask and the shadow (still images looped for the duration)."""
    rate = f"{fps.numerator}/{fps.denominator}"
    d = f"{p.duration + 0.5:.3f}"
    return [
        ["-loop", "1", "-framerate", rate, "-t", d, "-i", mask],
        ["-loop", "1", "-framerate", rate, "-t", d, "-i", shadow],
    ]


def pip_graph(
    p: Pip, base: str, out: str, video: int, mask: int, shadow: int, tag: str = "pip",
    fps: Fraction = FPS_NTSC,
) -> str:  # fmt: skip
    """Filter graph fragment: [base] + the window -> [out]."""
    n = round(p.duration * fps)
    tb = f"{fps.denominator}/{fps.numerator}"
    cw, ch, cx, cy = p.crop
    out_d = p.fade if p.fade_out is None else p.fade_out
    fades = []
    if p.fade > 0:
        fades.append(f"fade=t=in:st=0:d={fmt(p.fade)}:alpha=1")
    if out_d > 0:
        fades.append(f"fade=t=out:st={fmt(p.duration - out_d)}:d={fmt(out_d)}:alpha=1")
    fade = ",".join(fades) or "null"
    vf = f"{p.vf}," if p.vf else ""
    pad = 2 * p.shadow
    return ";".join(
        [
            f"[{video}:v]trim=start_frame={p.src_start_frame}:end_frame={p.src_start_frame + n},"
            f"setpts=PTS-STARTPTS,{vf}crop={cw}:{ch}:{cx}:{cy},scale={p.w}:{p.h}:flags=lanczos,"
            f"format=yuva444p10le[{tag}_v]",
            f"[{mask}:v]format=gray,scale={p.w}:{p.h},trim=end_frame={n}[{tag}_m]",
            f"[{tag}_v][{tag}_m]alphamerge,{fade},settb=expr={tb},"
            f"setpts=PTS-STARTPTS+{fmt(p.t0)}/TB[{tag}_w]",
            f"[{shadow}:v]format=yuva444p10le,trim=end_frame={n},{fade},settb=expr={tb},"
            f"setpts=PTS-STARTPTS+{fmt(p.t0)}/TB[{tag}_s]",
            f"[{base}][{tag}_s]overlay={p.x - pad}:{p.y - pad}:eof_action=pass:format=auto[{tag}_b]",
            f"[{tag}_b][{tag}_w]overlay={p.x}:{p.y}:eof_action=pass:format=auto[{out}]",
        ]
    )
