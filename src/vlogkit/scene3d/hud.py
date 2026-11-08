"""The counter in the top-left corner of a "what if" video: a small letter-spaced label, a big
number that rolls to each new value, and a short red tag under it ("TEHLİKE", "TCK 151").

    Hud("TIKANAN TUVALET", [(0.0, 12, None, None), (4.2, 250, None, "ARIZALI"), ...])

Each key is (time s, value, text or None, tag or None). With `text` the number is shown as that
text ("2,1 MİLYON"); otherwise the value is formatted the Turkish way (1.250.000).
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from vlogkit.graphics.easing import clamp, ease_out_back, ease_out_cubic
from vlogkit.graphics.style import ACCENT, VERTICAL, Layout, font, tr_upper
from vlogkit.graphics.text import put, render_line

RED = (214, 52, 43, 255)


def tr_number(v: float) -> str:
    """1250000 -> '1.250.000', 2.5 -> '2,5'."""
    if abs(v - round(v)) < 1e-9:
        return f"{round(v):,}".replace(",", ".")
    s = f"{v:,.1f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


class Hud:
    def __init__(
        self,
        label: str,
        keys: list[tuple[float, float, str | None, str | None]],
        t_end: float,
        layout: Layout = VERTICAL,
        roll: float = 0.7,
    ):
        self.keys = sorted(keys)
        self.t0 = self.keys[0][0] if self.keys else 0.0
        self.t_end, self.roll = t_end, roll
        k = layout.scale
        self.x = round(70 * k)  # left edge (inside the 60 px Reels margin)
        self.y = round(250 * k)  # under the platform's top icons
        self.k = k
        self.label = (
            render_line(
                tr_upper(label),
                round(34 * k),
                "ExtraBold",
                stroke=round(3 * k),
                tracking=round(4 * k),
            )
            if label
            else None
        )
        self.cache: dict[tuple, Image.Image] = {}
        self.text = label  # emoji check reads .text of captions only; harmless here

    def _num(self, s: str, size: int) -> Image.Image:
        key = ("n", s, size)
        if key not in self.cache:
            self.cache[key] = render_line(s, size, "Black", stroke=round(size * 0.07))
        return self.cache[key]

    def _tag(self, s: str) -> Image.Image:
        key = ("t", s)
        if key not in self.cache:
            f = font("ExtraBold", round(30 * self.k))
            w = round(f.getlength(s)) + round(28 * self.k)
            h = round(48 * self.k)
            im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            d = ImageDraw.Draw(im)
            d.rounded_rectangle((0, 0, w - 1, h - 1), radius=round(10 * self.k), fill=RED)
            d.text((w / 2, h / 2), s, font=f, fill=(255, 255, 255, 255), anchor="mm")
            self.cache[key] = im
        return self.cache[key]

    def _state(self, t: float):
        cur = prev = None
        for key in self.keys:
            if key[0] <= t:
                prev, cur = cur, key
        return prev, cur

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not self.keys or not (self.t0 <= t < self.t_end):
            return
        prev, cur = self._state(t)
        if cur is None:
            return
        fade = clamp((t - self.t0) / 0.25) * clamp((self.t_end - t) / 0.2)
        y = self.y
        if self.label:
            canvas.alpha_composite(_alpha(self.label, fade), (self.x, y))
            y += self.label.height - round(6 * self.k)
        u = clamp((t - cur[0]) / self.roll)
        if prev is not None and u < 1 and cur[2] is None and prev[2] is None:
            v = prev[1] + (cur[1] - prev[1]) * ease_out_cubic(u)
            # whole numbers run through whole numbers (a day counter never shows "7,5")
            whole = float(cur[1]).is_integer() and float(prev[1]).is_integer()
            s = tr_number(round(v) if whole or abs(cur[1]) >= 10 else round(v, 1))
        else:
            s = cur[2] or tr_number(cur[1])
        size = round(118 * self.k)
        num = self._num(s, size)
        pop = (
            1.0 + 0.12 * (1 - ease_out_back(clamp((t - cur[0]) / 0.3))) if prev is not None else 1.0
        )
        put(canvas, num, self.x + num.width * pop / 2, y + num.height / 2, pop, fade)
        y += num.height - round(10 * self.k)
        tag = cur[3]
        if tag:
            tg = self._tag(tr_upper(tag))
            p = clamp((t - cur[0] - 0.1) / 0.2)
            put(
                canvas,
                tg,
                self.x + tg.width / 2 + round(6 * self.k),
                y + tg.height / 2,
                0.7 + 0.3 * ease_out_back(p),
                p * fade,
            )


def _alpha(im: Image.Image, a: float) -> Image.Image:
    if a >= 1:
        return im
    out = im.copy()
    out.putalpha(out.getchannel("A").point(lambda v: round(v * a)))
    return out


ACCENT_COLOR = ACCENT  # re-exported for projects that colour their own extras
