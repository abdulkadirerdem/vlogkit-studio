"""Contact sheets: the fastest way to *see* a video (and to check a render)."""

from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from PIL import Image

from vlogkit.config import FONTS_DIR
from vlogkit.ff import PathLike, ffmpeg
from vlogkit.timecode import FPS_NTSC, frame_at


def contact_sheet(
    src: PathLike,
    out: PathLike,
    *,
    start: float = 0.0,
    duration: float | None = None,
    fps: float = 1.0,
    cols: int = 10,
    size: tuple[int, int] = (180, 320),
    timestamps: bool = True,
) -> Path:
    """Grid of frames sampled `fps` times per second, each stamped with its source time and
    source frame number ('12.345678 #370'), so a cut can be named to the frame."""
    from vlogkit.ff import probe

    info = probe(src)
    if duration is None:
        duration = info.duration - start
    n = max(1, round(duration * fps))
    rows = math.ceil(n / cols)
    w, h = size
    vf = f"fps={fps},scale={w}:{h}"
    if timestamps:
        font = FONTS_DIR / "Montserrat-ExtraBold.ttf"
        rate = info.fps or FPS_NTSC
        frame_no = f" #%{{eif\\:trunc(t*{rate.numerator}/{rate.denominator}+0.5)\\:d}}"
        vf += (
            f",drawtext=fontfile={font}:text='%{{pts\\:flt}}{frame_no}':x=4:y=4:"
            f"fontsize={max(12, h // 18)}:fontcolor=yellow:box=1:boxcolor=black@0.7"
        )
    vf += f",tile={cols}x{rows}"
    ffmpeg(
        [
            "-y",
            "-ss",
            str(start),
            "-t",
            str(duration),
            "-copyts",
            "-i",
            src,
            "-vf",
            vf,
            "-frames:v",
            "1",
            out,
        ]
    )
    return Path(out)


_SHOW_PTS = re.compile(r"\bpts_time:\s*(-?[0-9.]+)")


def _decode_window(
    src: PathLike, start: float, duration: float, size: tuple[int, int | None], near: list[float]
) -> list[tuple[float, Image.Image]]:
    """(source time, frame) for the frames in [start, start + duration] that fall within 0.6 s
    before one of the `near` times, scaled into `size` (letterboxed, never squashed; height None
    = keep the aspect). Real timestamps from showinfo: right on variable frame rate too."""
    from vlogkit.config import require, tools

    w, h = size
    picks = "+".join(
        f"between(t,{max(0.0, t - start - 0.6):.4f},{t - start + 0.02:.4f})" for t in near
    )
    if h is None:
        scale = f"scale={w}:-2"
    else:
        scale = (
            f"scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2"
        )
    cmd = [
        require(tools().ffmpeg, "ffmpeg"), "-hide_banner", "-v", "info", "-nostats",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src), "-an",
        "-vf", f"select='{picks}',{scale},showinfo",
        "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ]  # fmt: skip
    r = subprocess.run(cmd, capture_output=True)
    if r.returncode != 0:
        tail = r.stderr.decode("utf-8", "replace").strip().splitlines()[-5:]
        raise RuntimeError("ffmpeg kare okuyamadı: " + " | ".join(tail))
    stamps = [float(x) for x in _SHOW_PTS.findall(r.stderr.decode("utf-8", "replace"))]
    if not stamps:
        return []
    frame_bytes = len(r.stdout) // len(stamps)
    fw = w
    fh = frame_bytes // (3 * fw) if fw else 0
    out = []
    for k, ts in enumerate(stamps):
        chunk = r.stdout[k * frame_bytes : (k + 1) * frame_bytes]
        if fh and len(chunk) == fw * fh * 3:
            out.append((start + ts, Image.frombytes("RGB", (fw, fh), chunk)))
    return out


def grab_at(
    src: PathLike, times: Sequence[float], size: tuple[int, int | None], gap: float = 3.0
) -> list[tuple[float, Image.Image] | None]:
    """(time of the frame shown, frame) at each time asked: the last frame that started at or
    before it. In the order asked, duplicates allowed. Nearby times share one seek; far apart
    times get their own (two frames a minute apart in a 4K file do not mean decoding the minute
    between them). Rotated clips are letterboxed into `size` instead of squashed."""
    order = sorted(set(times))
    if not order:
        return []
    clusters: list[list[float]] = [[order[0]]]
    for t in order[1:]:
        if t - clusters[-1][-1] <= gap:
            clusters[-1].append(t)
        else:
            clusters.append([t])
    found: dict[float, tuple[float, Image.Image] | None] = {}
    for cl in clusters:
        start = max(0.0, cl[0] - 0.6)
        frames = _decode_window(src, start, cl[-1] - start + 0.1, size, cl)
        for t in cl:
            before = [f for f in frames if f[0] <= t + 1e-3]
            found[t] = before[-1] if before else (frames[0] if frames else None)
    return [found[t] for t in times]


def grab(
    src: PathLike, times: Sequence[float], size: tuple[int, int | None], gap: float = 3.0
) -> list[Image.Image | None]:
    """Just the frames of `grab_at`."""
    return [x[1] if x else None for x in grab_at(src, times, size, gap)]


def frames_sheet(
    src: PathLike,
    times: Sequence[float],
    out: PathLike,
    *,
    cols: int | None = None,
    size: tuple[int, int] = (216, 384),
    fps: Fraction | None = None,
) -> Path:
    """The frames on screen at the given times, in one row/grid (for checking specific moments).
    Missing frames (past the end) stay black tiles in their place."""
    if not times:
        raise ValueError("en az bir zaman ver")
    cols = cols or len(times)
    rows = math.ceil(len(times) / cols)
    sheet = Image.new("RGB", (cols * size[0], rows * size[1]), (0, 0, 0))
    for k, im in enumerate(grab(src, times, size)):
        if im is not None:
            sheet.paste(im, ((k % cols) * size[0], (k // cols) * size[1]))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out


def spectrogram(
    src: PathLike,
    out: PathLike,
    *,
    duration: float | None = None,
    size: tuple[int, int] = (1600, 500),
) -> Path:
    cut = ["-t", str(duration)] if duration else []
    ffmpeg(
        [
            "-y",
            *cut,
            "-i",
            src,
            "-lavfi",
            f"showspectrumpic=s={size[0]}x{size[1]}:legend=1:scale=log:fscale=log",
            out,
        ]
    )
    return Path(out)


def draw_grid(im, step: float = 0.1, labels: bool = True):
    """A coordinate grid over a picture (0-1 on both axes, top-left origin): thin lines every
    `step`, stronger at the thirds and the centre. Positions for crops and graphics can then be
    read off the frame instead of guessed. Returns the same image (RGB)."""
    from PIL import Image, ImageDraw

    from vlogkit.graphics.style import font

    im = im.convert("RGBA")
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    w, h = im.size
    f = font("SemiBold", max(11, min(w, h) // 45))
    n = round(1 / step)
    for i in range(1, n):
        v = i * step
        strong = abs(v - 0.5) < 1e-6
        color = (255, 214, 64, 200) if strong else (255, 255, 255, 110)
        width = 2 if strong else 1
        x, y = round(v * w), round(v * h)
        d.line([(x, 0), (x, h)], fill=color, width=width)
        d.line([(0, y), (w, y)], fill=color, width=width)
        if labels:
            tag = f"{v:.1f}".lstrip("0")
            for pos in ((x + 3, 2), (2, y + 2)):
                box = d.textbbox(pos, tag, font=f)
                d.rectangle(box, fill=(0, 0, 0, 170))
                d.text(pos, tag, font=f, fill=(255, 214, 64, 255))
    for third in (1 / 3, 2 / 3):  # rule of thirds, dashed
        x, y = round(third * w), round(third * h)
        for k in range(0, max(w, h), 18):
            d.line([(x, k), (x, min(k + 8, h))], fill=(64, 200, 255, 150), width=1)
            d.line([(k, y), (min(k + 8, w), y)], fill=(64, 200, 255, 150), width=1)
    im.alpha_composite(layer)
    return im.convert("RGB")


def frame_image(
    src: PathLike,
    t: float,
    out: PathLike,
    *,
    width: int = 1280,
    grid: bool = True,
    fps: Fraction | None = None,
) -> Path:
    """The frame on screen at t, scaled to `width`, with the coordinate grid and a caption line
    (time of that frame, frame number, displayed size): for placing crops, faces and graphics."""
    from PIL import ImageDraw

    from vlogkit.ff import probe
    from vlogkit.graphics.style import font

    info = probe(src)
    rate = fps or info.fps or FPS_NTSC
    if t < 0 or t >= info.duration:
        raise ValueError(f"{t:g} sn videonun dışında (süre {info.duration:.2f} sn)")
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.unlink(missing_ok=True)  # never show an older picture if the grab fails
    got = grab_at(src, [t], (width, None))[0]
    if got is None:
        raise ValueError(f"{t:g} sn'de kare okunamadı")
    shown, im = got
    if grid:
        im = draw_grid(im)
    bar = 30
    canvas = Image.new("RGB", (im.width, im.height + bar), (16, 18, 20))
    canvas.paste(im, (0, 0))
    d = ImageDraw.Draw(canvas)
    dw, dh = info.display_size
    d.text(
        (8, im.height + 7),
        f"{Path(src).name}   t = {shown:.3f} sn   kare #{frame_at(shown, rate)}   kaynak {dw}x{dh}"
        + ("   ızgara: 0-1, sol üst köşe 0,0" if grid else ""),
        font=font("SemiBold", 15),
        fill=(235, 235, 235),
    )
    canvas.save(out)
    return out
