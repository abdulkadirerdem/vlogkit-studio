"""Match a shot's colour to a reference frame ("make this shot look like that one").

1. `stats(images)`: robust colour statistics of a few frames in Oklab.
2. `transfer(ref, target)`: how to move the target's statistics towards the reference.
3. `transfer_lut(ref, target)`: that move baked into a 3D LUT (.cube text).
4. `match(video, ref, out_cube)`: sample, measure, write the .cube + a before/after image.
5. `lut_filter(cube)`: the ffmpeg filter that applies it inside a grade chain.

Why it is built this way:
- **Oklab, not CIELAB.** Both are perceptual Lab spaces, but CIELAB's hue bends in the blues: on a
  DJI sky a 0.71 chroma gain in CIELAB turned the sky 4 degrees towards violet (visible). Oklab
  keeps the hue. Values are x100: L 0-100, a/b about -30..30. The sRGB curve decodes Rec.709
  code values (same primaries and white); decode and encode are exact inverses, so the LUT is
  identity wherever the transfer is.
- **Percentiles, not mean/std.** A blown sky or a black jacket drags a mean around. Lightness uses
  p10/p50/p90 and pixels with a clipped channel (>= 250) or crushed to black (<= 8) are skipped:
  they carry no colour information.
- **Neutral axis, not the average colour.** A forest is green and a sky is blue: shifting the
  average a/b to the reference's would paint one onto the other (the classic failure of plain
  Reinhard transfer). The white balance is read from the least colourful quarter of the pixels
  and moved onto the reference's; colours keep their hue and get a saturation gain around that
  axis.
- **Chroma relative to lightness** (a / L, quoted at mid grey, L 60): in Oklab a white-balance
  cast on a neutral grows exactly with L. A grey maps to a grey at every level, black stays black
  and brightening a shot does not wash it out.
- **Lightness as a curve, not a line.** Reinhard's median shift + spread gain, split at the
  median (p10-p50 and p50-p90 get their own gain), is evaluated at the target's p10/p50/p90 and
  joined to 0 -> 0 and 100 -> 100 by a monotone cubic: blacks stay black, whites stay white,
  nothing clips.
- **Safety.** Contrast and saturation gains stay in 0.6-1.6, the lightness shift within 15 L
  (about one stop at mid grey: a night shot stays a night shot), the white-balance shift within
  3.5 a/b (about 12 in CIELAB units). The colour change fades out above L 94: clipped whites stay
  white instead of turning yellow or cyan.
- **10-bit.** lut3d has no YUV input. On yuv422p10le ffmpeg auto-converts to gbrp10le (measured:
  not 8-bit, +-1 code on a 10-bit ramp); `lut_filter` asks for gbrp16le, which makes an identity
  LUT bit-exact and keeps the LUT 16-bit even after an 8-bit filter. Out-of-gamut YUV (super
  whites, extreme chroma) is clipped by the RGB round trip; on DJI 4K the mean change is 0.003
  codes.
"""

from __future__ import annotations

import math
import tempfile
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError

from vlogkit.ff import PathLike, extract_frame, ffmpeg, probe

SAMPLE_WIDTH = 160  # px: enough for percentiles, fast in pure Python
CLIP_HI = 250  # 8-bit: a channel at or above this is clipped (blown sky)
CLIP_LO = 8  # 8-bit: every channel at or below this is crushed black
NEUTRAL_SHARE = 0.25  # the least colourful quarter defines the neutral axis
GAIN = (0.6, 1.6)  # contrast and saturation gain limits
MAX_SHIFT = 15.0  # lightness shift limit (Oklab L x100; about one stop at mid grey)
MAX_CAST = 3.5  # white-balance shift limit (a/b x100 at mid grey)
FADE = 94.0  # the colour change fades out between this lightness and 100
MID = 60.0  # Oklab L of mid grey (sRGB 0.5 = 59.8): chroma is quoted as it would be there
SAMPLES = 5  # frames measured when no times are given
PANEL = 640  # preview panel long side (px)
INTERPS = ("nearest", "trilinear", "tetrahedral", "pyramid", "prism")

# --------------------------------------------------------------------------- sRGB / Rec.709 <-> Oklab
_M1 = (  # linear sRGB -> LMS (Ottosson 2021)
    (0.4122214708, 0.5363325363, 0.0514459929),
    (0.2119034982, 0.6806995451, 0.1073969566),
    (0.0883024619, 0.2817188376, 0.6299787005),
)
_M2 = (  # LMS^(1/3) -> Lab
    (0.2104542553, 0.7936177850, -0.0040720468),
    (1.9779984951, -2.4285922050, 0.4505937099),
    (0.0259040371, 0.7827717662, -0.8086757660),
)


def _inverse(m: tuple[tuple[float, ...], ...]) -> tuple[tuple[float, ...], ...]:
    """3x3 inverse (computed, not copied: the round trip is exact to float precision)."""
    (a, b, c), (d, e, f), (g, h, i) = m
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return (
        ((e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det),
        ((f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det),
        ((d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det),
    )


_M1I, _M2I = _inverse(_M1), _inverse(_M2)


def _decode(v: float) -> float:
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def _encode(v: float) -> float:
    v = min(max(v, 0.0), 1.0)
    return v * 12.92 if v <= 0.0031308 else 1.055 * v ** (1 / 2.4) - 0.055


_LIN8 = [_decode(i / 255) for i in range(256)]


def _mul(m: tuple[tuple[float, ...], ...], x: float, y: float, z: float) -> tuple[float, ...]:
    return tuple(r0 * x + r1 * y + r2 * z for r0, r1, r2 in m)


def _lab_linear(r: float, g: float, b: float) -> tuple[float, float, float]:
    lms = (math.cbrt(v) for v in _mul(_M1, r, g, b))
    lab_l, a, bb = _mul(_M2, *lms)
    return 100 * lab_l, 100 * a, 100 * bb


def rgb_to_oklab(r: float, g: float, b: float) -> tuple[float, float, float]:
    """sRGB / Rec.709 code values (0-1) -> Oklab x100: L 0-100, a/b about -30..30."""
    return _lab_linear(_decode(r), _decode(g), _decode(b))


def oklab_to_rgb(lab_l: float, a: float, b: float) -> tuple[float, float, float]:
    """Oklab x100 -> sRGB / Rec.709 code values, clipped to 0-1 per channel (out of gamut)."""
    lms = (v**3 for v in _mul(_M2I, lab_l / 100, a / 100, b / 100))
    return tuple(_encode(v) for v in _mul(_M1I, *lms))  # type: ignore[return-value]


# --------------------------------------------------------------------------- 1. statistics
@dataclass(frozen=True)
class Stats:
    """Robust colour statistics in Oklab x100; chroma is quoted at mid grey (module docstring)."""

    l10: float  # lightness percentiles (0-100)
    l50: float
    l90: float
    cast_a: float  # neutral axis: median a / b of the least colourful quarter
    cast_b: float  # (b > 0 warm/yellow, b < 0 cool/blue; a > 0 magenta, a < 0 green)
    sat: float  # p75 chroma distance from the neutral axis
    n: int  # pixels measured

    @property
    def spread(self) -> float:
        return self.l90 - self.l10


def _pct(xs: Sequence[float], q: float) -> float:
    """Percentile of an already sorted list (linear interpolation)."""
    pos = q * (len(xs) - 1)
    i = int(pos)
    if i + 1 >= len(xs):
        return xs[-1]
    return xs[i] + (xs[i + 1] - xs[i]) * (pos - i)


def _small(im: Image.Image | PathLike) -> Image.Image:
    if not isinstance(im, Image.Image):
        with Image.open(im) as f:
            im = ImageOps.exif_transpose(f).convert("RGB")
    im = im.convert("RGB")
    if im.width > SAMPLE_WIDTH:
        h = max(1, round(im.height * SAMPLE_WIDTH / im.width))
        im = im.resize((SAMPLE_WIDTH, h), Image.Resampling.BOX)  # area average: less noise
    return im


def _neutral(rel: Sequence[tuple[float, float]]) -> tuple[float, float]:
    """The neutral axis: median a/b of the least colourful quarter. It under-reads a strong cast
    (a synthetic -3.4 reads -2.65), which fails safe. Re-centring the quarter on the estimate
    removed that bias but walked into the nearest big colour cluster on real frames (the warm
    hat/skin/dust side of a sky-and-grass DJI frame): a tint instead of a correction."""
    n = max(1, round(len(rel) * NEUTRAL_SHARE))
    near = sorted(rel, key=lambda p: p[0] * p[0] + p[1] * p[1])[:n]
    return _pct(sorted(p[0] for p in near), 0.5), _pct(sorted(p[1] for p in near), 0.5)


def stats(images: Iterable[Image.Image | PathLike]) -> Stats:
    """Colour statistics of one or more frames (PIL images or image paths), each downscaled to
    160 px wide. Clipped and crushed pixels are skipped; raises ValueError if nothing is left."""
    lights: list[float] = []
    rel: list[tuple[float, float]] = []
    cache: dict[bytes, tuple[float, float, float]] = {}
    for item in images:
        data = _small(item).tobytes()
        for i in range(0, len(data), 3):
            px = data[i : i + 3]
            hit = cache.get(px)
            if hit is None:
                r, g, b = px
                top = max(r, g, b)
                if top >= CLIP_HI or top <= CLIP_LO:
                    hit = (-1.0, 0.0, 0.0)
                else:
                    lab_l, a, bb = _lab_linear(_LIN8[r], _LIN8[g], _LIN8[b])
                    k = MID / lab_l  # > 0: crushed pixels are skipped above
                    hit = (lab_l, a * k, bb * k)
                cache[px] = hit
            if hit[0] >= 0:
                lights.append(hit[0])
                rel.append((hit[1], hit[2]))
    if not lights:
        raise ValueError("ölçülecek piksel yok: kare tamamen siyah ya da patlamış")
    lights.sort()
    cast_a, cast_b = _neutral(rel)
    dist = sorted(math.hypot(a - cast_a, b - cast_b) for a, b in rel)
    return Stats(
        l10=_pct(lights, 0.1),
        l50=_pct(lights, 0.5),
        l90=_pct(lights, 0.9),
        cast_a=cast_a,
        cast_b=cast_b,
        sat=_pct(dist, 0.75),
        n=len(lights),
    )


# --------------------------------------------------------------------------- 2. the transfer
def _clamp(v: float, lo: float, hi: float) -> float:
    return min(max(v, lo), hi)


def _monotone(knots: Sequence[tuple[float, float]]) -> Callable[[float], float]:
    """Monotone cubic (PCHIP-style tangents) through increasing knots: no overshoot, so a tone
    curve never folds back. Collinear knots give exactly the straight line."""
    xs = [k[0] for k in knots]
    ys = [k[1] for k in knots]
    h = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(len(h))]
    m = [d[0]]
    for i in range(1, len(d)):
        if d[i - 1] * d[i] <= 0:
            m.append(0.0)
        else:  # weighted harmonic mean (Fritsch-Butland): never steeper than 3x a secant
            m.append(3 * (h[i - 1] + h[i]) / ((2 * h[i] + h[i - 1]) / d[i - 1]
                                              + (h[i] + 2 * h[i - 1]) / d[i]))  # fmt: skip
    m.append(d[-1])

    def curve(x: float) -> float:
        x = _clamp(x, xs[0], xs[-1])
        i = 0
        while i < len(h) - 1 and x > xs[i + 1]:
            i += 1
        t = (x - xs[i]) / h[i]
        t2, t3 = t * t, t * t * t
        return ((2 * t3 - 3 * t2 + 1) * ys[i] + (t3 - 2 * t2 + t) * h[i] * m[i]
                + (-2 * t3 + 3 * t2) * ys[i + 1] + (t3 - t2) * h[i] * m[i + 1])  # fmt: skip

    return curve


def _smooth(x: float) -> float:
    x = _clamp(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


def _fade(lab_l: float) -> float:
    """Weight of the colour change: 1, falling to 0 at pure white (clipped whites stay white)."""
    return 1 - _smooth((lab_l - FADE) / (100 - FADE))


@dataclass(frozen=True)
class Transfer:
    """What the LUT does, in numbers (strength already applied)."""

    knots: tuple[tuple[float, float], ...]  # lightness curve: target L -> new L (0, 100 fixed)
    cast_from: tuple[float, float]  # the target's neutral axis (a, b at mid grey) ...
    cast_to: tuple[float, float]  # ... moves here (towards the reference's)
    sat_gain: float  # chroma gain around the neutral axis
    l_shift: float  # median lightness shift (L units)
    l_gain: float  # p10-p90 spread (contrast) gain

    @cached_property
    def _curve(self) -> Callable[[float], float]:
        return _monotone(self.knots)

    def lab(self, lab_l: float, a: float, b: float) -> tuple[float, float, float]:
        new_l = self._curve(lab_l)
        k = MID / max(lab_l, 1e-9)
        ra, rb = a * k, b * k
        ta = self.cast_to[0] + self.sat_gain * (ra - self.cast_from[0])
        tb = self.cast_to[1] + self.sat_gain * (rb - self.cast_from[1])
        w = _fade(lab_l)
        k2 = new_l / MID
        return new_l, (ra + w * (ta - ra)) * k2, (rb + w * (tb - rb)) * k2

    def rgb(self, r: float, g: float, b: float) -> tuple[float, float, float]:
        """One code value (0-1) through the transfer, clipped to 0-1."""
        return oklab_to_rgb(*self.lab(*rgb_to_oklab(r, g, b)))


def transfer(ref: Stats, target: Stats, strength: float = 0.8) -> Transfer:
    """Move `target` towards `ref`: strength 0 = identity, 1 = full (within the safety limits)."""
    s = _clamp(strength, 0.0, 1.0)
    shift = _clamp(ref.l50 - target.l50, -MAX_SHIFT, MAX_SHIFT)
    # Reinhard's shift + gain, split at the median: shadows (p10-p50) and highlights (p50-p90)
    # get their own gain. One gain over p10-p90 lifted the blacks of a skewed DJI frame about 5 L
    # past the reference's.
    lo = _clamp(max(ref.l50 - ref.l10, 0.5) / max(target.l50 - target.l10, 0.5), *GAIN)
    hi = _clamp(max(ref.l90 - ref.l50, 0.5) / max(target.l90 - target.l50, 0.5), *GAIN)
    knots = [(0.0, 0.0)]
    for x in (target.l10, target.l50, target.l90):
        if x - knots[-1][0] >= 1.0 and x <= 99.0:  # drop degenerate knots (flat frames)
            full = target.l50 + shift + (lo if x < target.l50 else hi) * (x - target.l50)
            knots.append((x, x + s * (full - x)))
    knots.append((100.0, 100.0))
    span = target.spread
    gain = (lo * (target.l50 - target.l10) + hi * (target.l90 - target.l50)) / span if span else 1
    for i in range(1, len(knots) - 1):  # strictly increasing and inside (0, 100)
        x, y = knots[i]
        px, py = knots[i - 1]
        y = _clamp(y, py + 0.2 * (x - px), 100 - 0.2 * (100 - x))
        knots[i] = (x, y)
    da, db = ref.cast_a - target.cast_a, ref.cast_b - target.cast_b
    k = s * min(1.0, MAX_CAST / max(math.hypot(da, db), 1e-9))
    sat = _clamp(max(ref.sat, 0.15) / max(target.sat, 0.15), *GAIN)
    return Transfer(
        knots=tuple(knots),
        cast_from=(target.cast_a, target.cast_b),
        cast_to=(target.cast_a + k * da, target.cast_b + k * db),
        sat_gain=1 + s * (sat - 1),
        l_shift=s * shift,
        l_gain=1 + s * (gain - 1),
    )


# --------------------------------------------------------------------------- 3. the LUT
def cube_text(fn: Callable[[float, float, float], tuple[float, float, float]], size: int = 33,
              comments: Sequence[str] = ()) -> str:  # fmt: skip
    """A function on 0-1 RGB as .cube text (Adobe/Resolve format; red runs fastest)."""
    if size < 2:
        raise ValueError("LUT boyutu en az 2 olmalı")
    grid = [i / (size - 1) for i in range(size)]
    lines = ['TITLE "vlogkit colormatch"', *(f"# {c}" for c in comments),
             f"LUT_3D_SIZE {size}", "DOMAIN_MIN 0.0 0.0 0.0", "DOMAIN_MAX 1.0 1.0 1.0"]  # fmt: skip
    for b in grid:
        for g in grid:
            for r in grid:
                lines.append("{:.6f} {:.6f} {:.6f}".format(*fn(r, g, b)))
    return "\n".join(lines) + "\n"


def _describe(s: Stats) -> str:
    return (f"L {s.l10:.1f}/{s.l50:.1f}/{s.l90:.1f}  a {s.cast_a:+.2f}  b {s.cast_b:+.2f}  "
            f"sat {s.sat:.2f}  n {s.n}")  # fmt: skip


def transfer_lut(ref: Stats, target: Stats, size: int = 33, strength: float = 0.8) -> str:
    """The transfer target -> ref as a size^3 .cube (values clipped to 0-1). The statistics and
    the applied numbers are written as comments, so the file explains itself later."""
    t = transfer(ref, target, strength)
    notes = [
        f"ref    {_describe(ref)}",
        f"target {_describe(target)}",
        f"strength {strength:g}  L shift {t.l_shift:+.2f}  contrast x{t.l_gain:.3f}  "
        f"cast {t.cast_from[0]:+.2f},{t.cast_from[1]:+.2f} -> {t.cast_to[0]:+.2f},"
        f"{t.cast_to[1]:+.2f}  sat x{t.sat_gain:.3f}",
    ]
    return cube_text(t.rgb, size, notes)


def _escape(path: PathLike) -> str:
    """A path as a filter option value: escaped for the option parser (\\ : '), then once more
    for the graph parser (\\ ' [ ] , ;). No quotes, so any path survives -vf and filter_complex."""
    opt = str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
    return "".join("\\" + c if c in "\\'[],;" else c for c in opt)


def lut_filter(cube: PathLike, interp: str = "tetrahedral") -> str:
    """ffmpeg filter applying a .cube in a grade chain, e.g. before `Grade.filter()`.

    Converts to 16-bit planar RGB first: lut3d has no YUV input and would otherwise take whatever
    the previous filter negotiates (gbrp10le on a 10-bit source, rgb24 after an 8-bit one)."""
    if interp not in INTERPS:
        raise ValueError(f"interp: {' | '.join(INTERPS)}")
    return f"format=gbrp16le,lut3d=file={_escape(Path(cube).absolute())}:interp={interp}"


# --------------------------------------------------------------------------- 4. match a shot
def _even(duration: float, n: int = SAMPLES) -> list[float]:
    return [round(duration * (i + 0.5) / n, 3) for i in range(n)]


def _panel(w: int, h: int) -> tuple[int, int]:
    k = PANEL / max(w, h)
    return max(2, round(w * k / 2) * 2), max(2, round(h * k / 2) * 2)


def _grab(src: Path, times: Sequence[float], tmp: Path, tag: str) -> list[Path]:
    """Frames at `times`, scaled to the preview panel size (area average), as PNG paths."""
    info = probe(src)
    if not info.width or not info.height:
        raise ValueError(f"görüntü akışı yok: {src}")
    for t in times:  # duration 0: a still only ffmpeg decodes (HEIC without a Pillow plugin)
        if t < 0 or (info.duration > 0 and t >= info.duration):
            raise ValueError(f"{t:g} sn {src.name} içinde değil (süre {info.duration:.1f} sn)")
    w, h = _panel(info.width, info.height)
    paths = []
    for i, t in enumerate(times):
        out = tmp / f"{tag}{i:02d}.png"
        extract_frame(src, t, out, vf=f"scale={w}:{h}:flags=area")
        if not out.exists():
            raise ValueError(f"{src.name}: {t:g} sn'de kare okunamadı")
        paths.append(out)
    return paths


def _still(path: Path) -> Image.Image | None:
    try:
        with Image.open(path) as im:
            return ImageOps.exif_transpose(im).convert("RGB")
    except (UnidentifiedImageError, OSError):
        return None


def _load(paths: Sequence[Path]) -> list[Image.Image]:
    ims = []
    for p in paths:
        with Image.open(p) as im:
            ims.append(im.convert("RGB"))
    return ims


def _gap(s: Stats, ref: Stats) -> dict[str, float]:
    """How far `s` is from the reference (s - ref; `cast` is the a/b distance)."""
    return {
        "lightness": s.l50 - ref.l50,
        "contrast": s.spread - ref.spread,
        "cast_a": s.cast_a - ref.cast_a,
        "cast_b": s.cast_b - ref.cast_b,
        "cast": math.hypot(s.cast_a - ref.cast_a, s.cast_b - ref.cast_b),
        "saturation": s.sat - ref.sat,
    }


def _signed(x: float, digits: int = 1) -> str:
    return f"{round(x, digits) + 0.0:+.{digits}f}"  # + 0.0: no "-0.0"


def _summary(t: Transfer, before: dict[str, float], after: dict[str, float]) -> str:
    da, db = t.cast_to[0] - t.cast_from[0], t.cast_to[1] - t.cast_from[1]
    warm = " (daha sıcak)" if db > 0.2 else " (daha soğuk)" if db < -0.2 else ""
    return (
        f"ışık {_signed(t.l_shift)} L, kontrast x{t.l_gain:.2f}, beyaz dengesi a "
        f"{_signed(da, 2)} / b {_signed(db, 2)}{warm}, doygunluk x{t.sat_gain:.2f}. Referansa "
        f"fark: ışık {abs(before['lightness']):.1f} -> {abs(after['lightness']):.1f}, renk "
        f"{before['cast']:.2f} -> {after['cast']:.2f}, doygunluk "
        f"{abs(before['saturation']):.1f} -> {abs(after['saturation']):.1f}"
    )


def _fit(im: Image.Image, size: tuple[int, int]) -> Image.Image:
    """`im` inside `size` (letterboxed on the sheet colour): the reference may be a photo."""
    canvas = Image.new("RGB", size, (16, 18, 20))
    fitted = ImageOps.contain(im, size, Image.Resampling.LANCZOS)
    canvas.paste(fitted, ((size[0] - fitted.width) // 2, (size[1] - fitted.height) // 2))
    return canvas


def _preview(befores: list[Image.Image], afters: list[Image.Image], ref: Image.Image,
             out: Path, strength: float, summary: str) -> Path:  # fmt: skip
    """Rows of before | after | reference (up to 3 sampled frames: first, middle, last)."""
    from vlogkit.graphics.style import font

    picks = sorted({0, len(befores) // 2, len(befores) - 1})
    w, h = befores[0].size
    gap, head, foot = 6, 34, 34
    sheet = Image.new("RGB", (3 * w + 2 * gap, head + len(picks) * (h + gap) + foot), (16, 18, 20))
    d = ImageDraw.Draw(sheet)
    f = font("SemiBold", 18)
    for col, label in enumerate(("önce", f"sonra (güç {strength:g})", "referans")):
        d.text((col * (w + gap) + 8, 8), label, font=f, fill=(235, 235, 235))
    for row, i in enumerate(picks):
        y = head + row * (h + gap)
        sheet.paste(befores[i], (0, y))
        sheet.paste(afters[i], (w + gap, y))
        sheet.paste(_fit(ref, (w, h)), (2 * (w + gap), y))
    d.text((8, sheet.height - foot + 8), summary, font=font("SemiBold", 14), fill=(200, 200, 200))
    sheet.save(out, quality=92)
    return out


def match(
    target_video: PathLike,
    ref: PathLike,
    out_cube: PathLike,
    *,
    at: Sequence[float] | None = None,
    ref_at: float | None = None,
    strength: float = 0.8,
    preview: bool = True,
) -> dict:
    """Make `target_video` look like `ref` (an image, or a video frame at `ref_at` s; without it
    5 frames of the video are averaged). The target is measured at `at` (s) or 5 even frames.

    Writes the .cube and, with `preview`, `<cube>_once-sonra.jpg` next to it. The "after" frames
    go through `lut_filter` in ffmpeg, so their statistics measure what the LUT really does.
    Returns {cube, preview, times, ref, before, after (Stats), transfer, delta {before, after},
    summary}.
    """
    target_video, ref, out_cube = Path(target_video), Path(ref), Path(out_cube)
    for p in (target_video, ref):
        if not p.exists():
            raise FileNotFoundError(p)
    out_cube.parent.mkdir(parents=True, exist_ok=True)
    times = list(at) if at else _even(probe(target_video).duration)
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        before_png = _grab(target_video, times, tmpd, "t")
        befores = _load(before_png)
        ref_im = _still(ref)
        if ref_im is not None:
            refs = [ref_im]
        else:
            duration = probe(ref).duration
            ref_times = [ref_at] if ref_at is not None else _even(duration) if duration else [0.0]
            refs = _load(_grab(ref, ref_times, tmpd, "r"))
            ref_im = refs[len(refs) // 2]
        st_ref, st_before = stats(refs), stats(befores)
        t = transfer(st_ref, st_before, strength)
        out_cube.write_text(transfer_lut(st_ref, st_before, strength=strength))
        # the same filter the grade chain will use, on the sampled frames (PNG sequence in/out)
        ffmpeg(["-y", "-i", tmpd / "t%02d.png", "-vf", lut_filter(out_cube), "-pix_fmt",
                "rgb24", "-start_number", "0", tmpd / "a%02d.png"])  # fmt: skip
        afters = _load([tmpd / f"a{i:02d}.png" for i in range(len(times))])
    st_after = stats(afters)
    delta = {"before": _gap(st_before, st_ref), "after": _gap(st_after, st_ref)}
    summary = _summary(t, delta["before"], delta["after"])
    prev = None
    if preview:
        prev = out_cube.with_name(f"{out_cube.stem}_once-sonra.jpg")
        _preview(befores, afters, ref_im, prev, strength, summary)
    return {
        "cube": out_cube,
        "preview": prev,
        "times": times,
        "ref": st_ref,
        "before": st_before,
        "after": st_after,
        "transfer": t,
        "delta": delta,
        "summary": summary,
    }
