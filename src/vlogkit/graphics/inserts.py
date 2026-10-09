"""Full-frame and inset graphics for long videos: an old-film countdown leader, a photo in a rounded
window (with a ring on the detail to look at), falling rain over a shot and a soft line of text.

All follow the overlay Element protocol: `draw(canvas, t)` composites onto the RGBA frame.
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

from vlogkit.graphics.easing import clamp, ease_out_back, ease_out_cubic
from vlogkit.graphics.style import Layout, font
from vlogkit.graphics.text import put, render_line, stack


class FilmLeader:
    """Old-film countdown (3-2-1...): a sweep around the circle each second, flicker, grain,
    scratches and gate jitter. Opaque: it covers the frame. Drawn at a quarter of the canvas size
    and scaled up (the softness is part of the look)."""

    BG = (196, 188, 172)
    SWEEP = (150, 143, 130)
    INK = (38, 36, 33)
    LINE = (242, 238, 230)

    def __init__(
        self, t0: float, layout: Layout, numbers: int = 3, per: float = 1.0, seed: int = 11
    ):
        self.t0, self.numbers, self.per = t0, numbers, per
        self.t1 = t0 + numbers * per
        self.size = layout.size
        self.w, self.h = max(320, layout.w // 4), max(180, layout.h // 4)
        self.rnd = random.Random(seed)
        rnd = random.Random(seed)
        self.grain = []
        for _ in range(6):
            g = Image.effect_noise((self.w, self.h), 64).point(lambda v: max(0, min(255, v)))
            self.grain.append(g)
        vig = Image.new("L", (self.w, self.h), 0)
        d = ImageDraw.Draw(vig)
        for i in range(40):  # dark corners
            k = i / 40
            d.ellipse((-self.w * (0.25 - 0.2 * k), -self.h * (0.35 - 0.3 * k),
                       self.w * (1.25 - 0.2 * k), self.h * (1.35 - 0.3 * k)), fill=int(255 * k))  # fmt: skip
        self.vignette = vig.filter(ImageFilter.GaussianBlur(self.h / 12))
        self.digits = {}
        f = font("Black", int(self.h * 0.55))
        for n in range(1, numbers + 1):
            im = Image.new("L", (self.w, self.h), 0)
            ImageDraw.Draw(im).text((self.w / 2, self.h / 2), str(n), font=f, fill=255, anchor="mm")
            self.digits[n] = im
        self.scratch_seed = rnd.randint(0, 10**6)

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        local = t - self.t0
        idx = min(self.numbers - 1, int(local / self.per))
        n = self.numbers - idx
        frac = (local - idx * self.per) / self.per
        frame = round(t * 30)
        rnd = random.Random(self.scratch_seed + frame)
        w, h = self.w, self.h
        flick = 1.0 + (rnd.random() - 0.5) * 0.1
        bg = tuple(int(c * flick) for c in self.BG)
        img = Image.new("RGB", (w, h), bg)
        d = ImageDraw.Draw(img)
        r = h * 0.42
        box = (w / 2 - r, h / 2 - r, w / 2 + r, h / 2 + r)
        if frac > 0.001:
            sweep = tuple(int(c * flick) for c in self.SWEEP)
            d.pieslice(box, -90, -90 + 360 * frac, fill=sweep)
        lw = max(2, h // 120)
        d.line((0, h / 2, w, h / 2), fill=self.INK, width=lw)
        d.line((w / 2, 0, w / 2, h), fill=self.INK, width=lw)
        for k in (1.0, 0.86):
            rr = r * k
            d.ellipse((w / 2 - rr, h / 2 - rr, w / 2 + rr, h / 2 + rr), outline=self.LINE,
                      width=lw + 1)  # fmt: skip
        img.paste(self.INK, (0, 0), self.digits[n])
        for _ in range(rnd.randint(1, 3)):  # scratches
            x = rnd.uniform(0.05, 0.95) * w
            shade = rnd.choice([(245, 242, 235), (60, 56, 50)])
            d.line((x, 0, x + rnd.uniform(-3, 3), h), fill=shade, width=1)
        for _ in range(rnd.randint(2, 7)):  # dust
            x, y, s = rnd.uniform(0, w), rnd.uniform(0, h), rnd.uniform(1, 3.5)
            d.ellipse((x, y, x + s, y + s * rnd.uniform(0.6, 1.4)), fill=(30, 28, 25))
        dark = Image.new("RGB", (w, h), (20, 18, 15))
        img = Image.composite(img, dark, self.vignette)
        g = self.grain[frame % len(self.grain)]
        img = Image.blend(img, Image.merge("RGB", (g, g, g)), 0.12)
        dx, dy = rnd.randint(-2, 2), rnd.randint(-2, 2)  # gate jitter
        img = img.transform(img.size, Image.Transform.AFFINE, (1, 0, dx, 0, 1, dy),
                            fillcolor=(20, 18, 15))  # fmt: skip
        big = img.resize(self.size, Image.Resampling.BICUBIC).convert("RGBA")
        canvas.alpha_composite(big)


class PhotoInset:
    """A photo in a rounded window with a soft shadow: pops in, holds, fades out. `ring` =
    (x, y, radius) as fractions of the shown photo: a circle drawn around a detail (a tiny animal
    in a big landscape) shortly after the pop."""

    def __init__(
        self,
        photo: Image.Image,
        t0: float,
        t1: float,
        cx: float,
        cy: float,
        width: int,
        radius: int = 40,
        shadow: int = 36,
        ring: tuple[float, float, float] | None = None,
        ring_color: tuple[int, int, int] = (255, 214, 64),
    ):
        self.t0, self.t1, self.cx, self.cy = t0, t1, cx, cy
        ph = photo.convert("RGB")
        hgt = round(width * ph.height / ph.width)
        ph = ph.resize((width, hgt), Image.Resampling.LANCZOS)
        mask = Image.new("L", (width, hgt), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, hgt - 1), radius, fill=255)
        pad = shadow * 2
        card = Image.new("RGBA", (width + 2 * pad, hgt + 2 * pad), (0, 0, 0, 0))
        sh = Image.new("L", card.size, 0)
        ImageDraw.Draw(sh).rounded_rectangle(
            (pad, pad + shadow // 3, pad + width, pad + hgt + shadow // 3), radius, fill=150
        )
        card.putalpha(sh.filter(ImageFilter.GaussianBlur(max(1, shadow))))
        body = ph.convert("RGBA")
        body.putalpha(mask)
        card.alpha_composite(body, (pad, pad))
        self.card, self.pad, self.pw, self.ph = card, pad, width, hgt
        self.ring, self.ring_color = ring, ring_color

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = clamp((t - self.t0) / 0.32)
        scale = 0.82 + 0.18 * ease_out_back(p) if p < 1 else 1.0
        alpha = clamp(p * 2.5) * clamp((self.t1 - t) / 0.3)
        img = self.card
        if self.ring:
            q = ease_out_cubic(clamp((t - self.t0 - 0.45) / 0.45))
            if q > 0:
                img = img.copy()
                x, y, r = self.ring
                cx, cy = self.pad + x * self.pw, self.pad + y * self.ph
                rr = r * self.pw
                lw = max(4, round(self.pw / 150))
                ImageDraw.Draw(img).arc((cx - rr, cy - rr, cx + rr, cy + rr), -90,
                                        -90 + 360 * q, fill=self.ring_color, width=lw)  # fmt: skip
        put(canvas, img, self.cx, self.cy, scale, alpha)


class Rain:
    """Falling rain streaks over the frame (a gloomy filter: darken the picture underneath)."""

    def __init__(
        self,
        t0: float,
        t1: float,
        layout: Layout,
        drops: int = 420,
        angle: float = 12.0,
        alpha: int = 95,
        seed: int = 5,
        fade: float = 0.25,
    ):
        self.t0, self.t1, self.fade = t0, t1, fade
        self.w, self.h = layout.size
        k = layout.h / 1080
        rnd = random.Random(seed)
        self.slope = math.tan(math.radians(angle))
        self.drops = [
            (rnd.uniform(-0.2, 1.0) * self.w, rnd.uniform(0, 1), rnd.uniform(70, 170) * k,
             rnd.uniform(1600, 2600) * k, max(1, round(rnd.uniform(1.0, 2.2) * k)),
             int(alpha * rnd.uniform(0.5, 1.0)))
            for _ in range(drops)
        ]  # fmt: skip

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        a = clamp((t - self.t0) / self.fade) * clamp((self.t1 - t) / self.fade)
        layer = Image.new("RGBA", (self.w, self.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        span = self.h * 1.3
        for x0, phase, length, speed, width, al in self.drops:
            y = (phase * span + speed * t) % span - self.h * 0.15
            x = x0 + y * self.slope
            dx = length * self.slope
            d.line((x, y, x + dx, y + length), fill=(205, 215, 230, int(al * a)), width=width)
        canvas.alpha_composite(layer)


class SoftText:
    """One quiet line (an end note on black): fades in while rising a little (`rise` px at 1x,
    0 = a plain fade in place), fades out."""

    def __init__(
        self,
        text: str,
        t0: float,
        t1: float,
        layout: Layout,
        size: int = 58,
        y: float = 0.5,
        weight: str = "SemiBold",
        alpha: float = 0.9,
        fade_in: float = 1.2,
        fade_out: float = 0.6,
        rise: float = 24.0,
    ):
        self.text, self.t0, self.t1, self.rise = text, t0, t1, rise
        s = round(size * layout.scale)
        lines = [render_line(x, s, weight, stroke=0, shadow=False, tracking=round(2 * layout.scale))
                 for x in text.split("\n")]  # fmt: skip
        self.img = stack(lines, gap=round(s * 0.3)) if len(lines) > 1 else lines[0]  # no shadow pad
        self.cx, self.cy, self.scale = layout.w / 2, layout.h * y, layout.scale
        self.alpha, self.fade_in, self.fade_out = alpha, fade_in, fade_out

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = clamp((t - self.t0) / self.fade_in)
        a = p * clamp((self.t1 - t) / self.fade_out) * self.alpha
        rise = (1 - ease_out_cubic(p)) * self.rise * self.scale
        put(canvas, self.img, self.cx, self.cy + rise, alpha=a)


class RingMark:
    """A red ring drawn around something (an animal far away, a tiny person): the stroke grows
    around the ellipse in `draw_s`, holds, fades out. Same look as the thumbnail ring (red with a
    dark outline)."""

    def __init__(
        self,
        t0: float,
        t1: float,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        width: int = 12,
        color: tuple[int, int, int] = (255, 48, 48),
        draw_s: float = 0.4,
    ):
        self.t0, self.t1, self.box = t0, t1, (cx - rx, cy - ry, cx + rx, cy + ry)
        self.width, self.color, self.draw_s = width, color, draw_s

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = ease_out_cubic(clamp((t - self.t0) / self.draw_s))
        a = clamp((self.t1 - t) / 0.2)
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        end = -90 + 360 * p
        outline = self.width + 2 * max(2, round(self.width * 0.35))
        d.arc(self.box, -90, end, fill=(0, 0, 0, round(255 * a)), width=outline)
        d.arc(self.box, -90, end, fill=(*self.color, round(255 * a)), width=self.width)
        canvas.alpha_composite(layer)
