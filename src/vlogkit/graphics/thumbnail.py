"""Thumbnail from a frame: vivid picture + a few huge words in the caption style.

docs/viral-edit.md: bright and simple, readable in 1.5 s, 3-5 words at most, and the promise
must match the video's opening. The text goes on the calmer half of the picture so it does not
cover the subject.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageStat

from vlogkit.graphics.style import ACCENT, BLACK
from vlogkit.graphics.style import font as style_font
from vlogkit.graphics.text import fit, render_line, stack

LANDSCAPE = (1280, 720)
PORTRAIT = (1080, 1920)


def _cover(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    w, h = size
    s = max(w / im.width, h / im.height)
    im = im.resize((round(im.width * s), round(im.height * s)), Image.Resampling.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def calmer_side(im: Image.Image) -> str:
    """'left' or 'right': the half with less detail (edge energy)."""
    edges = im.convert("L").filter(ImageFilter.FIND_EDGES)
    w, h = edges.size
    left = ImageStat.Stat(edges.crop((0, 0, w // 2, h))).mean[0]
    right = ImageStat.Stat(edges.crop((w // 2, 0, w, h))).mean[0]
    return "left" if left <= right else "right"


def compose(
    frame: str | Path,
    text: str,
    out: str | Path,
    size: tuple[int, int] | None = None,
    vivid: float = 1.25,
) -> Path:
    """text: 1-2 lines ('\\n'), [accent] words allowed; keep it to 3-5 words."""
    src = Image.open(frame).convert("RGB")
    size = size or (PORTRAIT if src.height > src.width else LANDSCAPE)
    im = _cover(src, size)
    im = ImageEnhance.Color(im).enhance(vivid)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=3)).convert("RGBA")
    if text.strip():
        w, h = size
        portrait = h > w
        line_size = int((w if portrait else h) * (0.13 if portrait else 0.17))
        lines = [
            render_line(t, line_size, "Black", stroke=round(line_size * 0.12))
            for t in text.split("\n")
        ]
        block = fit(
            stack(lines, gap=-int(line_size * 0.35), align="center" if portrait else "left"),
            int(w * (0.9 if portrait else 0.56)),
        )
        if portrait:
            x, y = (w - block.width) // 2, int(h * 0.12)
        else:
            side = calmer_side(im)
            x = int(w * 0.04) if side == "left" else w - block.width - int(w * 0.04)
            y = (h - block.height) // 2
        im.alpha_composite(block, (x, y))
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    im.convert("RGB").save(out, quality=92)
    return out


def sheet(paths: list[Path], out: str | Path, height: int = 360) -> Path:
    """The finished thumbnails side by side, to compare them at a glance."""
    ims = [Image.open(p).convert("RGB") for p in paths]
    ims = [im.resize((round(im.width * height / im.height), height)) for im in ims]
    gap = 12
    canvas = Image.new("RGB", (sum(i.width for i in ims) + gap * (len(ims) - 1), height), "white")
    x = 0
    for im in ims:
        canvas.paste(im, (x, 0))
        x += im.width + gap
    canvas.save(out, quality=90)
    return Path(out)


# --------------------------------------------------------------------------- designed thumbnails
# `compose` is the one-liner. `design` builds a thumbnail from explicit choices: which part of the
# frame (focus + zoom from a 4K still keeps it sharp), a light on the face, a vignette, where each
# text block sits, and small badges. `check_sheet` shows the result at the sizes people actually
# see (home feed, search, suggested on a phone) with YouTube's duration stamp drawn in.


@dataclass(frozen=True)
class Words:
    """A text block. x, y: where the block's anchor sits (0-1 of the canvas); anchor: 'lt', 'mt',
    'rt', 'lm', 'mm', 'rm', 'lb', 'mb', 'rb' (left/middle/right + top/middle/bottom)."""

    text: str  # lines split on '\n', [accent] words in the accent colour
    x: float
    y: float
    size: float = 0.17  # line height, share of the canvas height
    anchor: str = "lm"
    weight: str = "Black"
    max_w: float = 0.62  # widest the block may get, share of the canvas width
    tilt: float = 0.0  # degrees, a slight tilt reads as energy; keep it under ~4
    color: tuple[int, int, int, int] | None = None  # plain (non-[accent]) words; default white


@dataclass(frozen=True)
class Badge:
    """Small pill label (e.g. '2800 m'): dark text on the accent colour."""

    text: str
    x: float
    y: float
    size: float = 0.07
    anchor: str = "lt"


@dataclass(frozen=True)
class Subject:
    """A cut-out person/object (RGBA, e.g. `cutout` -> `bloat` -> cropped) placed over the
    background: `height` = its height as a share of the canvas height, anchored like `Words`."""

    image: Image.Image
    x: float
    y: float
    height: float = 1.0
    anchor: str = "lb"
    rim: float = 0.006  # white outline width, share of the canvas height (0 = none)
    brightness: float = 1.08
    contrast: float = 1.05
    vivid: float = 1.08
    gamma: float = 1.0  # > 1 opens up a shadowed face


def _anchor_xy(
    w: int, h: int, bw: int, bh: int, x: float, y: float, anchor: str
) -> tuple[int, int]:
    ax = {"l": 0.0, "m": 0.5, "r": 1.0}[anchor[0]]
    ay = {"t": 0.0, "m": 0.5, "b": 1.0}[anchor[1]]
    return round(x * w - ax * bw), round(y * h - ay * bh)


def crop_focus(
    im: Image.Image,
    size: tuple[int, int],
    focus: tuple[float, float] = (0.5, 0.5),
    zoom: float = 1.0,
) -> Image.Image:
    """Cover-crop to `size`, `zoom` x tighter, centred on `focus` (0-1 of the source) as far as
    the edges allow. From a 4K still a 2x zoom still has more pixels than a 1280x720 thumbnail."""
    w, h = size
    s = max(w / im.width, h / im.height) * zoom
    cw, ch = w / s, h / s  # crop box in source pixels
    cx = min(max(focus[0] * im.width, cw / 2), im.width - cw / 2)
    cy = min(max(focus[1] * im.height, ch / 2), im.height - ch / 2)
    box = (round(cx - cw / 2), round(cy - ch / 2), round(cx + cw / 2), round(cy + ch / 2))
    return im.crop(box).resize(size, Image.Resampling.LANCZOS)


def light(
    im: Image.Image,
    center: tuple[float, float] | None = None,
    radius: float = 0.35,
    lift: float = 0.18,
    vignette: float = 0.25,
) -> Image.Image:
    """Brighten a soft disc (the face, `lift` = +18 %) and darken the corners (`vignette`): the eye
    lands on the subject first, even at 168 px wide."""
    w, h = im.size
    out = im.convert("RGB")
    if center and lift:
        mask = Image.new("L", (w, h), 0)
        cx, cy, r = center[0] * w, center[1] * h, radius * h
        ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
        mask = mask.filter(ImageFilter.GaussianBlur(r * 0.45))
        out = Image.composite(ImageEnhance.Brightness(out).enhance(1 + lift), out, mask)
    if vignette:
        small = Image.new("L", (64, 36), 0)
        d = ImageDraw.Draw(small)
        d.ellipse((-14, -10, 78, 46), fill=255)
        mask = small.filter(ImageFilter.GaussianBlur(7)).resize((w, h), Image.Resampling.BICUBIC)
        dark = ImageEnhance.Brightness(out).enhance(1 - vignette)
        out = Image.composite(out, dark, mask)
    return out


def _bbox(im: Image.Image, threshold: int) -> tuple[int, int, int, int]:
    box = im.getchannel("A").point(lambda v: 255 if v > threshold else 0).getbbox()
    return box or (0, 0, im.width, im.height)


def text_block(t: Words, w: int, h: int) -> tuple[Image.Image, tuple[int, int], tuple[int, int]]:
    """(image, hard size, hard offset): the words are placed and fitted by their letters and
    stroke (alpha > 96), the soft shadow around them may spill over the anchor."""
    px = round(h * t.size)
    colour = {"color": t.color} if t.color else {}
    lines = [
        render_line(s, px, t.weight, stroke=round(px * 0.11), **colour) for s in t.text.split("\n")
    ]
    align = {"l": "left", "m": "center", "r": "right"}[t.anchor[0]]
    block = stack(lines, gap=-round(px * 0.36), align=align)
    block = block.crop(_bbox(block, 4))
    hard = _bbox(block, 96)
    scale = min(1.0, w * t.max_w / (hard[2] - hard[0]))
    if scale < 1:
        size = (round(block.width * scale), round(block.height * scale))
        block = block.resize(size, Image.Resampling.LANCZOS)
    if t.tilt:
        block = block.rotate(t.tilt, resample=Image.Resampling.BICUBIC, expand=True)
    hard = _bbox(block, 96)
    return block, (hard[2] - hard[0], hard[3] - hard[1]), (hard[0], hard[1])


def badge_image(text: str, height: int) -> Image.Image:
    font = style_font("Black", round(height * 0.62))
    tw = font.getlength(text)
    pad = round(height * 0.42)
    im = Image.new("RGBA", (round(tw + 2 * pad), height), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, im.width - 1, height - 1), radius=height // 2, fill=ACCENT)
    d.text((pad, height / 2), text, font=font, fill=BLACK, anchor="lm")
    return im


def design(frame: str | Path | Image.Image, out: str | Path, *, quality: int = 92, **kw) -> Path:
    """`render` and save as JPEG."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    render(frame, **kw).convert("RGB").save(out, quality=quality, optimize=True)
    return out


def render(
    frame: str | Path | Image.Image,
    *,
    size: tuple[int, int] = LANDSCAPE,
    focus: tuple[float, float] = (0.5, 0.5),
    zoom: float = 1.0,
    vivid: float = 1.2,
    contrast: float = 1.08,
    brightness: float = 1.0,
    gamma: float = 1.0,
    face: tuple[float, float] | None = None,
    face_radius: float = 0.3,
    face_lift: float = 0.15,
    vignette: float = 0.22,
    words: tuple[Words, ...] = (),
    badges: tuple[Badge, ...] = (),
    subject: Subject | tuple[Subject, ...] | None = None,
    blur: float = 0.0,
    marks: tuple[Arrow | Ring, ...] = (),
    frost_fx: dict | None = None,
    stickers: tuple[Sticker, ...] = (),
) -> Image.Image:
    """A finished thumbnail (RGBA). `face` is in *thumbnail* coordinates (0-1), after the crop.
    `subject` goes over the background (softened by `blur`, share of the height: depth)."""
    src = frame if isinstance(frame, Image.Image) else Image.open(frame)
    im = crop_focus(src.convert("RGB"), size, focus, zoom)
    im = lift_shadows(ImageEnhance.Brightness(im).enhance(brightness), gamma)
    im = ImageEnhance.Color(im).enhance(vivid)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    im = im.filter(ImageFilter.UnsharpMask(radius=2, percent=70, threshold=3))
    im = light(im, face, face_radius, face_lift, vignette).convert("RGBA")
    w, h = size
    if blur:
        im = im.filter(ImageFilter.GaussianBlur(blur * h))
    for sub in (subject,) if isinstance(subject, Subject) else subject or ():
        place_subject(im, sub)
    if frost_fx is not None:  # over the picture and the person, under stickers and text
        im = frost(im, **frost_fx).convert("RGBA")
    for st in stickers:
        im = place_sticker(im, st)
    for mark in marks:
        im.alpha_composite(mark.render(size))
    for t in words:
        block, (bw, bh), (ox, oy) = text_block(t, w, h)
        x, y = _anchor_xy(w, h, bw, bh, t.x, t.y, t.anchor)
        layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
        layer.paste(block, (x - ox, y - oy))  # may start left of / above the canvas: clipped
        im.alpha_composite(layer)
    for b in badges:
        pill = badge_image(b.text, round(h * b.size))
        im.alpha_composite(pill, _anchor_xy(w, h, pill.width, pill.height, b.x, b.y, b.anchor))
    return im


def duration_stamp(im: Image.Image, label: str = "3:09") -> Image.Image:
    """YouTube's duration pill in the bottom-right corner (it covers that corner in every feed)."""
    im = im.convert("RGBA")
    w, h = im.size
    ph = max(10, round(h * 0.085))
    font = style_font("ExtraBold", round(ph * 0.62))
    pw = round(font.getlength(label) + ph * 0.7)
    x, y = w - pw - round(w * 0.02), h - ph - round(h * 0.035)
    layer = Image.new("RGBA", im.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x, y, x + pw, y + ph), radius=round(ph * 0.2), fill=(0, 0, 0, 200))
    d.text((x + pw / 2, y + ph / 2), label, font=font, fill=(255, 255, 255, 255), anchor="mm")
    im.alpha_composite(layer)
    return im


def check_sheet(
    paths: list[Path],
    out: str | Path,
    widths: tuple[int, ...] = (640, 360, 168),
    label: str = "3:09",
) -> Path:
    """Every thumbnail (rows) at the sizes it is seen at (columns): 640 ≈ desktop home, 360 ≈
    phone home feed, 168 ≈ suggested / search on a phone. The duration stamp is drawn in."""
    rows = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        cells = [
            duration_stamp(
                im.resize((wd, round(wd * im.height / im.width)), Image.Resampling.LANCZOS), label
            )
            for wd in widths
        ]
        rows.append(cells)
    gap = 16
    width = sum(widths) + gap * (len(widths) + 1)
    heights = [max(c.height for c in r) for r in rows]
    canvas = Image.new("RGB", (width, sum(heights) + gap * (len(rows) + 1)), (18, 18, 18))
    y = gap
    for r, rh in zip(rows, heights, strict=True):
        x = gap
        for c in r:
            canvas.paste(c.convert("RGB"), (x, y))
            x += c.width + gap
        y += rh + gap
    canvas.save(out, quality=90)
    return Path(out)


# --------------------------------------------------------------------------- cut-out subject
# The creator cut out of one frame (`analysis.segment.mask`) over the place from another: the
# classic "me in front of where I was" thumbnail. `bloat` enlarges the head the way a liquify
# brush does: full scale in the middle, easing to none at `r_out`, so a hand on the head or an arm
# next to it bends smoothly instead of breaking at a cut line.


def cutout(frame: str | Path | Image.Image, mask: Image.Image, feather: float = 1.2) -> Image.Image:
    """RGBA: the frame with the mask as alpha (edge softened by `feather` px)."""
    im = frame if isinstance(frame, Image.Image) else Image.open(frame)
    alpha = mask.convert("L").resize(im.size)
    if feather:
        alpha = alpha.filter(ImageFilter.GaussianBlur(feather))
    out = im.convert("RGBA")
    out.putalpha(alpha)
    return out


def lift_shadows(im: Image.Image, gamma: float) -> Image.Image:
    """gamma > 1 opens up the shadows and mids (a dusk face, a dark lake) without clipping the
    highlights the way a plain brightness multiply does."""
    if abs(gamma - 1) < 1e-3:
        return im
    lut = [round(255 * (v / 255) ** (1 / gamma)) for v in range(256)]
    if im.mode == "RGBA":
        rgb, a = im.convert("RGB"), im.getchannel("A")
        out = rgb.point(lut * 3).convert("RGBA")
        out.putalpha(a)
        return out
    return im.point(lut * len(im.getbands()))


def _smooth(u: float) -> float:
    u = min(max(u, 0.0), 1.0)
    return u * u * (3 - 2 * u)


def bloat_source(
    p: tuple[float, float], center: tuple[float, float], r_in: float, r_out: float, scale: float
) -> tuple[float, float]:
    """Where the output pixel p reads from (inverse of the bloat, by fixed-point iteration)."""
    cx, cy = center
    dx, dy = p[0] - cx, p[1] - cy
    qx, qy = dx / scale, dy / scale
    for _ in range(12):
        r = (qx * qx + qy * qy) ** 0.5
        s = 1 + (scale - 1) * (1 - _smooth((r - r_in) / max(1e-6, r_out - r_in)))
        qx, qy = dx / s, dy / s
    return cx + qx, cy + qy


def bloat(
    im: Image.Image,
    center: tuple[float, float],
    r_in: float,
    r_out: float,
    scale: float = 1.2,
    grid: int = 64,
) -> Image.Image:
    """Enlarge the disc of radius r_in around `center` (pixels) by `scale`, easing back to 1x at
    r_out. r_out >= 2 * r_in keeps the warp smooth (no fold) for scale <= 1.3."""
    w, h = im.size
    xs = [round(w * i / grid) for i in range(grid + 1)]
    ys = [round(h * j / grid) for j in range(grid + 1)]
    src = {(x, y): bloat_source((x, y), center, r_in, r_out, scale) for x in xs for y in ys}
    mesh = []
    for x0, x1 in pairwise(xs):
        for y0, y1 in pairwise(ys):
            quad = (*src[(x0, y0)], *src[(x0, y1)], *src[(x1, y1)], *src[(x1, y0)])
            mesh.append(((x0, y0, x1, y1), quad))
    return im.transform((w, h), Image.Transform.MESH, mesh, resample=Image.Resampling.BICUBIC)


def rim(
    subject: Image.Image, width: float, color=(255, 255, 255), alpha: float = 0.9
) -> Image.Image:
    """A soft outline around a cut-out (put it under the subject): separates it from a busy
    background at phone size."""
    a = subject.getchannel("A")
    grown = a.filter(ImageFilter.MaxFilter(max(3, round(width) | 1)))
    grown = grown.filter(ImageFilter.GaussianBlur(width * 0.35))
    layer = Image.new("RGBA", subject.size, (*color, 0))
    layer.putalpha(grown.point(lambda v: round(v * alpha)))
    return layer


def place_subject(canvas: Image.Image, s: Subject) -> None:
    """Grade, scale and composite a cut-out (with its rim) onto the canvas in place."""
    w, h = canvas.size
    img = s.image
    rgb, alpha = img.convert("RGB"), img.getchannel("A")
    rgb = lift_shadows(ImageEnhance.Brightness(rgb).enhance(s.brightness), s.gamma)
    rgb = ImageEnhance.Contrast(rgb).enhance(s.contrast)
    rgb = ImageEnhance.Color(rgb).enhance(s.vivid)
    img = rgb.convert("RGBA")
    img.putalpha(alpha)
    k = s.height * h / img.height
    img = img.resize((round(img.width * k), round(img.height * k)), Image.Resampling.LANCZOS)
    x, y = _anchor_xy(w, h, img.width, img.height, s.x, s.y, s.anchor)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    if s.rim:
        pad = round(s.rim * h * 2)
        padded = Image.new("RGBA", (img.width + 2 * pad, img.height + 2 * pad), (0, 0, 0, 0))
        padded.paste(img, (pad, pad))
        layer.paste(rim(padded, s.rim * h), (x - pad, y - pad))
    top = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    top.paste(img, (x, y))
    layer.alpha_composite(top)
    canvas.alpha_composite(layer)


# --------------------------------------------------------------------------- arrows, rings, split
@dataclass(frozen=True)
class Arrow:
    """A thick curved arrow with a dark outline (the hand-drawn look), tail -> head in canvas
    fractions. bend: sideways bulge as a share of the length (+ = to the left of the direction).
    One per thumbnail at most: arrows everywhere read as amateur."""

    tail: tuple[float, float]
    head: tuple[float, float]
    bend: float = 0.15
    width: float = 0.022  # share of the canvas height
    color: tuple[int, int, int] = (255, 48, 48)

    def points(self, w: int, h: int, n: int = 40) -> list[tuple[float, float]]:
        (x0, y0), (x1, y1) = (
            (self.tail[0] * w, self.tail[1] * h),
            (self.head[0] * w, self.head[1] * h),
        )
        dx, dy = x1 - x0, y1 - y0
        mx, my = (x0 + x1) / 2 - dy * self.bend, (y0 + y1) / 2 + dx * self.bend  # control point
        return [
            ((1 - u) ** 2 * x0 + 2 * (1 - u) * u * mx + u * u * x1,
             (1 - u) ** 2 * y0 + 2 * (1 - u) * u * my + u * u * y1)
            for u in (i / n for i in range(n + 1))
        ]  # fmt: skip

    def render(self, size: tuple[int, int]) -> Image.Image:
        w, h = size
        lw = max(3, round(self.width * h))
        pts = self.points(w, h)
        (ax, ay), (bx, by) = pts[-4], pts[-1]
        vx, vy = bx - ax, by - ay
        n = max(1e-6, (vx * vx + vy * vy) ** 0.5)
        vx, vy = vx / n, vy / n
        hl, hw = lw * 3.2, lw * 2.4  # head length / half width
        base = (bx - vx * hl, by - vy * hl)
        head = [
            (bx, by),
            (base[0] - vy * hw, base[1] + vx * hw),
            (base[0] + vy * hw, base[1] - vx * hw),
        ]
        shaft = [p for p in pts if (p[0] - bx) * vx + (p[1] - by) * vy < -hl * 0.8]
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        outline = max(2, round(lw * 0.35))
        for colour, grow in ((BLACK, outline), ((*self.color, 255), 0)):
            d.line(shaft, fill=colour, width=lw + 2 * grow, joint="curve")
            r = (lw + 2 * grow) / 2
            x, y = shaft[0]
            d.ellipse((x - r, y - r, x + r, y + r), fill=colour)
            if grow:
                cx = sum(p[0] for p in head) / 3
                cy = sum(p[1] for p in head) / 3
                big = [(cx + (px - cx) * 1.25, cy + (py - cy) * 1.25) for px, py in head]
                d.polygon(big, fill=colour)
            else:
                d.polygon(head, fill=colour)
        shadow = layer.getchannel("A").filter(ImageFilter.GaussianBlur(lw * 0.6))
        out = Image.new("RGBA", size, (0, 0, 0, 0))
        out.putalpha(shadow.point(lambda v: v * 0.5))
        out.alpha_composite(layer)
        return out


@dataclass(frozen=True)
class Ring:
    """A hand-drawn-style circle around something small (the tiny swimmers)."""

    center: tuple[float, float]
    radius: float  # share of the canvas height
    width: float = 0.014
    color: tuple[int, int, int] = (255, 48, 48)

    def render(self, size: tuple[int, int]) -> Image.Image:
        w, h = size
        cx, cy, r = self.center[0] * w, self.center[1] * h, self.radius * h
        lw = max(3, round(self.width * h))
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        box = (cx - r * 1.25, cy - r, cx + r * 1.25, cy + r)
        d.ellipse(box, outline=BLACK, width=lw + 2 * max(2, round(lw * 0.35)))
        d.ellipse(
            (box[0] + lw * 0.35, box[1] + lw * 0.35, box[2] - lw * 0.35, box[3] - lw * 0.35),
            outline=(*self.color, 255),
            width=lw,
        )
        return layer


def split(
    left: Image.Image,
    right: Image.Image,
    size: tuple[int, int] = LANDSCAPE,
    slant: float = 0.06,
    line: float = 0.008,
) -> Image.Image:
    """Two pictures side by side with a slanted white divider (the "before / after" layout).
    Each side is cover-cropped to the full canvas first, so crop them (focus, zoom) beforehand."""
    w, h = size
    a = _cover(left.convert("RGB"), size)
    b = _cover(right.convert("RGB"), size)
    m = Image.new("L", size, 0)
    top, bottom = w * (0.5 + slant / 2), w * (0.5 - slant / 2)
    ImageDraw.Draw(m).polygon([(top, 0), (w, 0), (w, h), (bottom, h)], fill=255)
    out = Image.composite(b, a, m)
    if line:
        ImageDraw.Draw(out).line(
            [(top, 0), (bottom, h)], fill=(255, 255, 255), width=round(line * h)
        )
    return out


def clone_fill(
    im: Image.Image,
    mask: Image.Image,
    offset: tuple[int, int],
    grow: int = 24,
    feather: float = 18.0,
) -> Image.Image:
    """Clone stamp: paint over the masked area (people to remove) with the picture shifted by
    `offset` pixels (where similar texture is: the same slope, the same shore). The mask is grown
    by `grow` px so no outline stays, and its edge softened by `feather`. Meant for areas a
    cut-out will mostly cover; a large bare area needs real inpainting."""
    dx, dy = offset
    src = im.convert("RGB")
    shifted = Image.new("RGB", src.size)
    shifted.paste(src, (-dx, -dy))  # shifted(x, y) = src(x + dx, y + dy)
    m = mask.convert("L").resize(src.size)
    if grow:
        m = m.filter(ImageFilter.MaxFilter(grow * 2 + 1 if grow < 50 else 101))
    if feather:
        m = m.filter(ImageFilter.GaussianBlur(feather))
    return Image.composite(shifted, src, m)


# --------------------------------------------------------------------------- frost
def _edge_falloff(size: tuple[int, int], reach: float) -> Image.Image:
    """L mask: 255 at the frame edges, fading to 0 at `reach` (share of the short side) inside."""
    w, h = size
    sw, sh = 192, max(2, round(192 * h / w))
    m = Image.new("L", (sw, sh))
    r = reach * min(sw, sh)
    for y in range(sh):
        for x in range(sw):
            d = min(x, y, sw - 1 - x, sh - 1 - y)
            u = max(0.0, 1 - d / max(1e-6, r))
            m.putpixel((x, y), round(255 * u * u * (3 - 2 * u)))
    return m.filter(ImageFilter.GaussianBlur(2)).resize(size, Image.Resampling.BICUBIC)


def _corner_falloff(
    size: tuple[int, int], weights: tuple[float, float, float, float], radius: float
) -> Image.Image:
    """L mask: weights[i] * 255 at corner i (tl, tr, br, bl), fading out over `radius` (share of
    the short side); the brightest corner wins where they overlap."""
    w, h = size
    sw, sh = 192, max(2, round(192 * h / w))
    r = radius * min(sw, sh)
    pts = ((0, 0), (sw - 1, 0), (sw - 1, sh - 1), (0, sh - 1))
    m = Image.new("L", (sw, sh))
    for y in range(sh):
        for x in range(sw):
            best = 0.0
            for (cx, cy), wt in zip(pts, weights, strict=True):
                u = max(0.0, 1 - ((x - cx) ** 2 + (y - cy) ** 2) ** 0.5 / max(1e-6, r))
                best = max(best, wt * u * u * (3 - 2 * u))
            m.putpixel((x, y), round(255 * min(1.0, best)))
    return m.filter(ImageFilter.GaussianBlur(3)).resize(size, Image.Resampling.BICUBIC)


def frost(
    im: Image.Image,
    reach: float = 0.22,
    strength: float = 0.9,
    density: float = 1.0,
    tint: tuple[int, int, int] = (228, 242, 255),
    cold: float = 0.15,
    seed: int = 7,
    corners: tuple[float, float, float, float] | None = None,
    haze: float = 0.5,
) -> Image.Image:
    """haze: opacity of the frosty white-blue fog along the edges (0-1).
    corners: weights (top-left, top-right, bottom-right, bottom-left) to pile the frost into
    corners instead of all four edges, e.g. (0.5, 0, 0, 1) for a heavy bottom-left.

    Frozen-window edges: feathery frost (fern-like dendrites) grows in from the borders over a
    frosty haze and a sprinkle of crystals, and the whole picture turns a little colder (`cold`,
    0-1). Procedural: no stock image, no licence. reach = how far in (share of the short side)."""
    rnd = random.Random(seed)
    w, h = im.size
    k = 0.5  # draw at half size, then soften on the way up
    cw, ch = round(w * k), round(h * k)
    lines = Image.new("L", (cw, ch), 0)
    d = ImageDraw.Draw(lines)
    short = min(cw, ch)

    def fern(x: float, y: float, ang: float, length: float, width: float, depth: int) -> None:
        """A dendrite: a slightly wandering spine with short side barbs at ~60°, recursively."""
        steps = max(3, round(length / 4))
        seg = length / steps
        for i in range(steps):
            ang += rnd.uniform(-0.12, 0.12)
            x2, y2 = x + math.cos(ang) * seg, y + math.sin(ang) * seg
            u = i / steps
            d.line(
                (x, y, x2, y2),
                fill=round(255 * (1 - 0.5 * u)),
                width=max(1, round(width * (1 - 0.6 * u))),
            )
            if depth > 0 and i % 2 == 0 and rnd.random() < 0.8:
                for side in (-1, 1):
                    if rnd.random() < 0.85:
                        fern(x2, y2, ang + side * rnd.uniform(0.8, 1.2), length * (1 - u) * 0.4,
                             width * 0.6, depth - 1)  # fmt: skip
            x, y = x2, y2

    n = round(70 * density * (cw + ch) / 1000)
    for _ in range(n):
        side = rnd.randrange(4)
        t = rnd.random()
        x, y, ang = {
            0: (t * cw, 0, math.pi / 2),
            1: (cw, t * ch, math.pi),
            2: (t * cw, ch, -math.pi / 2),
            3: (0, t * ch, 0.0),
        }[side]
        fern(x, y, ang + rnd.uniform(-0.7, 0.7), short * reach * rnd.uniform(0.35, 0.8),
             short * 0.0055, 2)  # fmt: skip
    speckle = Image.effect_noise((cw, ch), 64).point(lambda v: 255 if v > 214 else 0)
    glow = lines.filter(ImageFilter.GaussianBlur(2)).point(lambda v: min(255, round(v * 1.2)))
    crystals = ImageChops.lighter(lines.filter(ImageFilter.GaussianBlur(0.5)), glow)
    crystals = ImageChops.lighter(crystals, speckle.point(lambda v: v // 2))
    crystals = crystals.resize((w, h), Image.Resampling.BICUBIC)
    edge = _edge_falloff((w, h), reach)
    fog = edge.point(lambda v: round(v * haze))
    alpha = ImageChops.lighter(
        ImageChops.multiply(crystals, _edge_falloff((w, h), reach * 1.4)), fog
    )
    alpha = alpha.point(lambda v: round(v * strength))
    if corners:
        alpha = ImageChops.multiply(alpha, _corner_falloff((w, h), corners, reach * 4.0))
    base = im.convert("RGB")
    if cold:
        r, g, b = base.split()
        base = Image.merge("RGB", (r.point(lambda v: round(v * (1 - cold * 0.5))), g,
                                   b.point(lambda v: min(255, round(v * (1 + cold * 0.35))))))  # fmt: skip
    return Image.composite(Image.new("RGB", (w, h), tint), base, alpha)


@dataclass(frozen=True)
class Sticker:
    """A picture laid over the thumbnail (an ice cube, an emoji-like prop). blend="screen" puts a
    subject shot on black (light, ice, fire, sparks) without a mask: black disappears."""

    image: Image.Image
    x: float
    y: float
    height: float = 0.25  # share of the canvas height
    anchor: str = "lb"
    blend: str = "screen"  # "screen" | "normal" (uses the image's alpha)
    angle: float = 0.0
    opacity: float = 1.0


def place_sticker(canvas: Image.Image, st: Sticker) -> Image.Image:
    w, h = canvas.size
    img = st.image.convert("RGBA")
    k = st.height * h / img.height
    img = img.resize(
        (max(1, round(img.width * k)), max(1, round(img.height * k))), Image.Resampling.LANCZOS
    )
    if st.angle:
        img = img.rotate(st.angle, resample=Image.Resampling.BICUBIC, expand=True)
    x, y = _anchor_xy(w, h, img.width, img.height, st.x, st.y, st.anchor)
    layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    layer.paste(img, (x, y), img)
    if st.blend == "screen":
        rgb = layer.convert("RGB")
        if st.opacity < 1:
            rgb = rgb.point(lambda v: round(v * st.opacity))
        out = ImageChops.screen(canvas.convert("RGB"), rgb).convert("RGBA")
        out.putalpha(canvas.getchannel("A") if canvas.mode == "RGBA" else 255)
        return out
    if st.opacity < 1:
        layer.putalpha(layer.getchannel("A").point(lambda v: round(v * st.opacity)))
    out = canvas.convert("RGBA")
    out.alpha_composite(layer)
    return out


ICE_BLUE = (185, 232, 255, 255)  # icy text colour (Words(color=ICE_BLUE))


def icy(im: Image.Image, dark=(0, 0, 0), light=(215, 245, 255)) -> Image.Image:
    """Recolour a photo (e.g. an ice cube lit orange) to cold blues, keeping its light and detail."""
    rgb = im.convert("RGB")
    out = ImageOps.colorize(ImageOps.autocontrast(rgb.convert("L"), cutoff=1), dark, light)
    if im.mode == "RGBA":
        out = out.convert("RGBA")
        out.putalpha(im.getchannel("A"))
    return out
