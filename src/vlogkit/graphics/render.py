"""Render elements -> RGBA frames -> ProRes 4444 (alpha) via an ffmpeg pipe."""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from PIL import Image

from vlogkit.config import require, tools
from vlogkit.ff import extract_frame
from vlogkit.graphics.elements import Element
from vlogkit.graphics.style import H, W
from vlogkit.timecode import FPS_NTSC


def compose_frame(
    elements: Sequence[Element], t: float, size: tuple[int, int] = (W, H)
) -> Image.Image:
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    for e in elements:
        e.draw(canvas, t)
    return canvas


def render_overlay(
    elements: Sequence[Element],
    nframes: int,
    out: str | Path,
    fps: Fraction = FPS_NTSC,
    size: tuple[int, int] = (W, H),
    progress: bool = True,
    start: int = 0,
) -> Path:
    """Frames start..start+nframes-1 of the timeline (t = frame / fps). With `start` a single
    element can become its own clip that matches the full overlay frame for frame."""
    w, h = size
    cmd = [
        require(tools().ffmpeg, "ffmpeg"),
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgba",
        "-s",
        f"{w}x{h}",
        "-r",
        f"{fps.numerator}/{fps.denominator}",
        "-i",
        "-",
        "-c:v",
        "prores_ks",
        "-profile:v",
        "4444",
        "-pix_fmt",
        "yuva444p10le",
        str(out),
    ]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert p.stdin
    for n in range(nframes):
        p.stdin.write(compose_frame(elements, float((start + n) / fps), size).tobytes())
        if progress and n % 150 == 0:
            print(f"  overlay {n}/{nframes}", flush=True)
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("overlay encode failed")
    return Path(out)


def preview(
    elements: Sequence[Element],
    times: Sequence[float],
    out_dir: str | Path,
    background: str | Path | None = None,
    size: tuple[int, int] = (W, H),
    grid: bool = False,
) -> list[Path]:
    """PNG per time: the graphics over the real picture (if `background` video given) or grey.
    grid=True draws the 0-1 coordinate grid on top (for placing graphics)."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for t in times:
        if background:
            bg_path = out / f"_bg_{t:.2f}.png"
            extract_frame(background, t, bg_path)
            bg = Image.open(bg_path).convert("RGBA").resize(size)
            bg_path.unlink()
        else:
            bg = Image.new("RGBA", size, (90, 100, 110, 255))
        bg.alpha_composite(compose_frame(elements, t, size))
        path = out / f"preview_{t:.2f}.png"
        im = bg.convert("RGB")
        if grid:
            from vlogkit.analysis.sheets import draw_grid

            im = draw_grid(im)
        im.save(path)
        paths.append(path)
    return paths
