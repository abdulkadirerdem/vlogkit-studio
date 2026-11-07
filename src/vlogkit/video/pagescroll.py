"""A scrolled screen recording -> one tall page image -> a slow, smooth camera move over it.

A recording of someone scrolling a page (a profile, a chat, a document) holds the whole page, but
its own scroll is fast and jerky: a 10 s edit cannot be cut out of 4 s of flicking. So:

1. `stitch` matches consecutive frames by their row-brightness signature (the scroll is a pure
   vertical translation of a static page) and pastes them into one tall still. Crop the recording
   to the content column first (`Column`), so browser chrome, sticky headers and side rails -- the
   parts that do *not* scroll -- stay out of the stitch.
2. `move` flies a window over that still: `Key` frames give the window's centre and width in page
   pixels, and the frames in between are resampled with sub-pixel accuracy (Pillow's float `box`),
   so the move is as slow as the edit wants and never stair-steps the way ffmpeg's `zoompan` does.

Every pixel still comes from the recording; nothing is redrawn.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from PIL import Image

from vlogkit.config import require, tools
from vlogkit.ff import PathLike, ffmpeg
from vlogkit.timecode import FPS_NTSC
from vlogkit.video.graph import PRORES_HQ


@dataclass(frozen=True)
class Column:
    """The scrolling content area of the recording, in source pixels (`vlogkit frame` grid)."""

    x: int
    y: int
    w: int
    h: int

    def crop(self) -> str:
        return f"crop={self.w}:{self.h}:{self.x}:{self.y}"


@dataclass(frozen=True)
class Page:
    """The stitched still: `offsets[i]` is where frame i sits on the page (px from the top)."""

    path: Path
    width: int
    height: int
    offsets: list[int]
    worst_match: float  # largest per-row brightness error of a match (0 = identical rows)


def _signature(im: Image.Image) -> list[float]:
    """One value per row: that row's mean brightness (the width collapsed to a single pixel)."""
    return list(im.convert("L").resize((1, im.height), Image.BOX).tobytes())  # satır başına 1 bayt


def _min_overlap(height: int) -> int:
    """Rows two frames must share before their match means anything (a quarter of the column)."""
    return max(60, height // 4)


def _shifts(
    a: Sequence[float], b: Sequence[float], max_shift: int, row_step: int, keep: int = 6
) -> list[tuple[int, float]]:
    """Candidate shifts s >= 0 with b[y] ~= a[y + s]: how far the page moved up between two frames.

    One best match is not enough. In the fastest part of a flick only a few hundred rows overlap
    and most of them are blank card background, so several shifts score almost the same (on a
    LinkedIn profile: 262, 294, 342 and 433 within 0.5 of each other). The caller picks between
    them with the page's longer context. Candidates are kept 8 px apart, best first.
    """
    n = len(a)
    scored: list[tuple[float, int]] = []
    for s in range(0, max_shift + 1):
        if n - s < _min_overlap(n):  # çok az örtüşme: rastgele eşleşme
            break
        rows = range(0, n - s, row_step)
        scored.append((sum(abs(a[y + s] - b[y]) for y in rows) / len(rows), s))
    scored.sort()
    picks: list[tuple[int, float]] = []
    for cost, s in scored:
        if all(abs(s - p) > 8 for p, _ in picks):
            picks.append((s, cost))
        if len(picks) == keep:
            break
    return picks or [(0, 0.0)]


def _page_cost(page_sig: Sequence[float], frame_sig: Sequence[float], off: int) -> float:
    """How well the frame sits at `off` on the page built so far (mean per-row error)."""
    rows = range(0, min(len(frame_sig), len(page_sig) - off))
    if off < 0 or len(rows) < _min_overlap(len(frame_sig)):  # örtüşme az: karşılaştırma anlamsız
        return float("inf")
    return sum(abs(page_sig[off + y] - frame_sig[y]) for y in rows) / len(rows)


def _place(
    page_sig: Sequence[float], frame_sig: Sequence[float], guesses: Sequence[int], radius: int
) -> int:
    """Pick where the frame goes: the candidate (nudged ±radius) that fits the page best.

    The page carries a much longer context than the previous frame alone, so it both settles the
    ambiguity between candidate shifts and takes out the few px of drift a half-scrolled frame
    adds. Without this a single bad match pushes *everything* below it down and leaves a seam --
    a line of text cut in half by the card above it.
    """
    best, best_cost = guesses[0], float("inf")
    for guess in guesses:
        for off in range(max(0, guess - radius), guess + radius + 1):
            cost = _page_cost(page_sig, frame_sig, off)
            if cost < best_cost:
                best, best_cost = off, cost
    return best


def stitch(
    video: PathLike,
    out: PathLike,
    column: Column,
    *,
    max_shift: int = 260,
    row_step: int = 3,
    refine: int = 15,
) -> Page:
    """Paste the recording's frames into one tall page image. `max_shift`: the largest scroll
    between two frames in px -- raise it for a faster flick, but keep it well under the column
    height or a repeating UI pattern can match itself. `refine`: how far (px) a frame may be nudged
    off its candidate shift to fit the page built so far (0 = pair matching only)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg(
            ["-y", "-i", str(video), "-vf", column.crop(), "-start_number", "0", f"{tmp}/%05d.png"]
        )
        files = sorted(Path(tmp).glob("*.png"))
        if not files:
            raise ValueError(f"kareler çıkarılamadı: {video}")
        frames = [Image.open(p).convert("RGB") for p in files]
        sigs = [_signature(im) for im in frames]
        offsets, worst = [0], 0.0
        page_sig = list(sigs[0])
        for i in range(1, len(frames)):
            picks = _shifts(sigs[i - 1], sigs[i], max_shift, row_step)
            if refine:
                off = _place(page_sig, sigs[i], [offsets[-1] + s for s, _ in picks], refine)
            else:
                off = offsets[-1] + picks[0][0]
            offsets.append(off)
            worst = max(worst, _page_cost(page_sig, sigs[i], off))
            page_sig[off:] = sigs[i]  # yeni kare üstte: yapıştırma sırasıyla aynı
        page = Image.new("RGB", (column.w, offsets[-1] + column.h), "white")
        for off, im in zip(offsets, frames, strict=True):
            page.paste(im, (0, off))  # yeni kare üstte: sayfa en son görülen hâlini taşır
        page.save(out)
    return Page(out, page.width, page.height, offsets, worst)


# --------------------------------------------------------------------------- camera move
EASES: dict[str, Callable[[float], float]] = {
    "linear": lambda u: u,
    "smooth": lambda u: u * u * (3 - 2 * u),  # ease in and out
    "in": lambda u: u * u,  # slow start
    "out": lambda u: 1 - (1 - u) ** 2,  # slow landing
}


@dataclass(frozen=True)
class Key:
    """Where the camera is at time `t`: window centre (cx, cy) and window width, in page pixels.

    `ease` shapes the move that *ends* here. Two keys with the same values are a hold; a short
    segment with a small width drop is a push ("punch") on a beat.
    """

    t: float
    cx: float
    cy: float
    w: float
    ease: str = "smooth"


def window(keys: Sequence[Key], t: float) -> tuple[float, float, float]:
    """The interpolated (cx, cy, w) at time t. Width is interpolated geometrically, so a push
    from 400 to 200 px feels even all the way through."""
    if t <= keys[0].t:
        k = keys[0]
        return k.cx, k.cy, k.w
    for a, b in pairwise(keys):
        if t <= b.t:
            u = (t - a.t) / (b.t - a.t) if b.t > a.t else 1.0
            e = EASES[b.ease](max(0.0, min(1.0, u)))
            w = a.w * (b.w / a.w) ** e
            return a.cx + (b.cx - a.cx) * e, a.cy + (b.cy - a.cy) * e, w
    k = keys[-1]
    return k.cx, k.cy, k.w


def frame(page: Image.Image, cx: float, cy: float, w: float, size: tuple[int, int]) -> Image.Image:
    """One output frame: the window around (cx, cy), clamped to the page, resampled to `size`."""
    h = w * size[1] / size[0]
    x0 = min(max(cx - w / 2, 0.0), max(0.0, page.width - w))
    y0 = min(max(cy - h / 2, 0.0), max(0.0, page.height - h))
    return page.resize(size, Image.LANCZOS, box=(x0, y0, x0 + w, y0 + h))


def move(
    page_image: PathLike,
    keys: Sequence[Key],
    out: PathLike,
    *,
    size: tuple[int, int] = (1080, 1920),
    fps: Fraction = FPS_NTSC,
    nframes: int | None = None,
    filters: str = "",
) -> Path:
    """Render the camera move to a ProRes intermediate. `filters`: an ffmpeg chain applied on the
    way out (grade, vignette, fades) -- one encode, so the frames are only resampled once."""
    keys = sorted(keys, key=lambda k: k.t)
    if len(keys) < 2:
        raise ValueError("en az iki anahtar kare gerekli")
    n = nframes if nframes is not None else round(keys[-1].t * float(fps))
    page = Image.open(page_image).convert("RGB")
    chain = f"{filters},setsar=1,format=yuv422p10le" if filters else "setsar=1,format=yuv422p10le"
    cmd = [
        require(tools().ffmpeg, "ffmpeg"),
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{size[0]}x{size[1]}",
        "-framerate",
        str(fps),
        "-i",
        "-",
        "-vf",
        chain,
        *PRORES_HQ,
        str(out),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE, text=False)
    assert proc.stdin
    try:
        for i in range(n):
            cx, cy, w = window(keys, i / float(fps))
            proc.stdin.write(frame(page, cx, cy, w, size).tobytes())
    finally:
        proc.stdin.close()
        err = proc.stderr.read().decode() if proc.stderr else ""
        if proc.wait() != 0:
            raise RuntimeError("kamera hareketi yazılamadı:\n" + err)
    return Path(out)
