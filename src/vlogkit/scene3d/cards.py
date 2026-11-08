"""On-screen devices of the build-up formats, drawn over the rendered picture.

- `wipe_frame`: a before/after slider between two shots. The previous shot's last frame stays,
  the new shot slides in from the right to the middle, both states hold side by side with their
  labels, then the new one takes the frame. One look tells what changed.
- `Term`: the word the video teaches ("Buna ___ denir"): a big yellow card with the term under a
  small "BUNA … DENİR" tag, readable at a glance (a sign in the 3D scene is small and flat).
- `Counter`: a number running up as something happens (the depth while a well is dug).
- `Stamp`: a verdict slammed onto the frame (YANLIŞ in red, DOĞRU in green), the game-ad beat.
- `Choices`: the closing question with numbered answers ("1 TAŞ DUVAR  2 POMPA  3 BORU") popping
  in one by one, and a line asking for the number in the comments: a comment costs one key.
"""

from __future__ import annotations

from PIL import Image, ImageDraw

from vlogkit.graphics.easing import clamp, ease_out_cubic
from vlogkit.graphics.style import VERTICAL, Layout, font, tr_upper
from vlogkit.graphics.text import put, render_line

SLIDE = 0.32  # s: each half of the wipe
YELLOW = (255, 210, 63)
INK = (17, 17, 17)


def wipe_spec(w) -> dict:
    """The shot's `wipe` (true or {labels, hold}) with its defaults."""
    w = w if isinstance(w, dict) else {}
    labels = list(w.get("labels") or ["ÖNCE", "SONRA"])[:2]
    return {"labels": [tr_upper(str(x)) for x in labels], "hold": float(w.get("hold", 1.1))}


def wipe_frames(w, fps: float) -> int:
    return round((2 * SLIDE + wipe_spec(w)["hold"]) * fps)


def wipe_split(t: float, hold: float) -> float:
    """How much of the frame (from the right) the new state covers at t: 0 -> 0.5 -> 1."""
    if t < SLIDE:
        return 0.5 * ease_out_cubic(clamp(t / SLIDE))
    if t < SLIDE + hold:
        return 0.5
    return 0.5 + 0.5 * ease_out_cubic(clamp((t - SLIDE - hold) / SLIDE))


def _label(text: str, size: int, fill, color) -> Image.Image:
    f = font("ExtraBold", size)
    x0, y0, x1, y1 = f.getbbox(text)
    pad_x, pad_y = round(size * 0.5), round(size * 0.28)
    w, h = x1 - x0 + 2 * pad_x, y1 - y0 + 2 * pad_y
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2, fill=fill)
    d.text((pad_x - x0, pad_y - y0), text, font=f, fill=color)
    return im


def wipe_frame(before: Image.Image, after: Image.Image, t: float, w) -> Image.Image:
    """Frame t (s from the new shot's start) of the slider between the two pictures."""
    spec = wipe_spec(w)
    after = after.convert("RGB")
    W, H = after.size
    k = W / 1080
    p = wipe_split(t, spec["hold"])
    x = round(W * (1 - p))
    out = before.convert("RGB").resize(after.size)
    if x < W:
        out.paste(after.crop((x, 0, W, H)), (x, 0))
    d = ImageDraw.Draw(out, "RGBA")
    if 0 < x < W:  # the divider: a white bar with a soft shadow and a round handle
        lw = max(2, round(7 * k))
        d.rectangle((x - lw - round(4 * k), 0, x + lw + round(4 * k), H), fill=(0, 0, 0, 60))
        d.rectangle((x - lw // 2, 0, x + lw // 2, H), fill=(255, 255, 255, 255))
        r, cy = round(40 * k), round(H * 0.5)
        d.ellipse((x - r, cy - r, x + r, cy + r), fill=(255, 255, 255, 255))
        a = round(15 * k)
        d.polygon([(x - a * 0.4, cy - a), (x - a * 0.4, cy + a), (x - a * 1.5, cy)], fill=INK)
        d.polygon([(x + a * 0.4, cy - a), (x + a * 0.4, cy + a), (x + a * 1.5, cy)], fill=INK)
    size = max(12, round(50 * k))
    y = round(H * 0.7)
    left, right = spec["labels"]
    # each label sits in the middle of its side while that side is big enough to hold it
    if x > W * 0.22:
        im = _label(left, size, (17, 17, 17, 215), (255, 255, 255))
        out.paste(im, (round(x / 2 - im.width / 2), y), im)
    if W - x > W * 0.22:
        im = _label(right, size, (*YELLOW, 255), INK)
        out.paste(im, (round((x + W) / 2 - im.width / 2), y), im)
    return out


class Choices:
    """The closing question as numbered answers. `title` at the top, `items` as rows (2-4) that
    pop in one after another, `ask` under them; holds until t1."""

    def __init__(
        self,
        title: str,
        items: list[str],
        t0: float,
        t1: float,
        layout: Layout = VERTICAL,
        ask: str = "CEVABINI YORUMA YAZ",
        pick: dict | None = None,
    ):
        """`pick`: {"n": 1-based row, "t": time, "ok": bool}: that row is tapped at t and turns
        green (right) or red (wrong) – the game-ad answer."""
        k = layout.scale
        self.k = k
        self.pick = pick
        self.text = " ".join([title, *items, ask])
        self.t0, self.t1 = t0, t1
        self.cx = layout.w / 2
        self.title = render_line(tr_upper(title), round(76 * k), stroke=round(8 * k))
        if self.title.width > layout.max_w:
            s = layout.max_w / self.title.width
            self.title = self.title.resize((layout.max_w, round(self.title.height * s)))
        self.rows = [self._row(i + 1, tr_upper(str(x)), k, layout) for i, x in enumerate(items)]
        self.ask = render_line(tr_upper(ask), round(48 * k), color=YELLOW, stroke=round(6 * k))
        top = 520 * k
        gap = 34 * k
        rows_h = sum(r.height for r in self.rows) + gap * (len(self.rows) - 1)
        self.title_y = top
        y = top + self.title.height / 2 + 60 * k
        self.row_y = []
        for r in self.rows:
            self.row_y.append(y + r.height / 2)
            y += r.height + gap
        self.ask_y = top + self.title.height / 2 + 60 * k + rows_h + 70 * k

    @staticmethod
    def _row(n: int, text: str, k: float, layout: Layout) -> Image.Image:
        h = round(124 * k)
        w = min(layout.max_w, round(820 * k))
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=round(26 * k), fill=(17, 17, 17, 225))
        r = round(44 * k)
        cx, cy = round(24 * k) + r, h // 2
        d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=YELLOW)
        fn = font("Black", round(58 * k))
        x0, y0, x1, y1 = fn.getbbox(str(n))
        d.text((cx - (x0 + x1) / 2, cy - (y0 + y1) / 2), str(n), font=fn, fill=INK)
        ft = font("ExtraBold", round(56 * k))
        x0, y0, x1, y1 = ft.getbbox(text)
        if x1 - x0 > w - (cx + r + 60 * k):  # a long answer: smaller, never cut
            ft = font("ExtraBold", round(56 * k * (w - cx - r - 60 * k) / (x1 - x0)))
            x0, y0, x1, y1 = ft.getbbox(text)
        d.text((cx + r + round(30 * k) - x0, cy - (y0 + y1) / 2), text, font=ft, fill="white")
        return im

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        out = clamp((self.t1 - t) / 0.25)
        p = ease_out_cubic(clamp((t - self.t0) / 0.3))
        put(canvas, self.title, self.cx, self.title_y - 20 * (1 - p), alpha=p * out)
        for i, (r, y) in enumerate(zip(self.rows, self.row_y, strict=True)):
            # a question asked again to answer it: the rows are already there
            delay = 0.0 if self.pick else 0.25 + 0.22 * i
            q = ease_out_cubic(clamp((t - self.t0 - delay) / 0.25))
            if q > 0:
                put(canvas, r, self.cx + 120 * (1 - q), y, alpha=q * out)
        pk = self.pick
        if pk and 1 <= int(pk["n"]) <= len(self.rows) and t >= float(pk["t"]):
            i = int(pk["n"]) - 1
            r, y = self.rows[i], self.row_y[i]
            dt = t - float(pk["t"])
            d = ImageDraw.Draw(canvas)
            x0, y0 = self.cx - r.width / 2, y - r.height / 2
            col = (46, 204, 113) if pk.get("ok") else (255, 59, 48)
            w = max(3, round(9 * self.k))
            d.rounded_rectangle((x0 - w, y0 - w, x0 + r.width + w, y0 + r.height + w),
                                radius=round(30 * self.k), outline=(*col, round(255 * out)), width=w)  # fmt: skip
            if dt < 0.45:  # the tap: a ring opening out from the finger
                rr = (20 + 120 * dt / 0.45) * self.k
                a = round(220 * (1 - dt / 0.45) * out)
                cx = x0 + r.width * 0.78
                d.ellipse((cx - rr, y - rr, cx + rr, y + rr), outline=(255, 255, 255, a), width=w)
        q = ease_out_cubic(clamp((t - self.t0 - 0.35 - 0.22 * len(self.rows)) / 0.3))
        if q > 0:
            put(canvas, self.ask, self.cx, self.ask_y, alpha=q * out)


class Term:
    """The term of a "Buna ___ denir" line, popped up big under the captions for ~2 s."""

    def __init__(
        self, text: str, t0: float, t1: float, layout: Layout = VERTICAL, tag: str = "BUNA DENİR"
    ):
        k = layout.scale
        self.text, self.t0, self.t1 = text, t0, t1
        self.cx = layout.w / 2
        self.tag = _label(tr_upper(tag), round(36 * k), (17, 17, 17, 225), (255, 255, 255))
        card = _label(tr_upper(text), round(84 * k), (*YELLOW, 255), INK)
        if card.width > layout.max_w:
            s = layout.max_w / card.width
            card = card.resize((layout.max_w, round(card.height * s)))
        self.card = card
        self.y = 1290 * k
        self.tag_y = self.y - card.height / 2 - self.tag.height / 2 - 14 * k

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = clamp((t - self.t0) / 0.18)
        out = clamp((self.t1 - t) / 0.2)
        # a quick pop: a little over-size, then settles
        s = 0.7 + 0.3 * ease_out_cubic(p) + 0.06 * (1 - abs(2 * p - 1)) * (p < 1)
        card = self.card.resize(
            (max(1, round(self.card.width * s)), max(1, round(self.card.height * s)))
        )
        put(canvas, card, self.cx, self.y, alpha=out * min(1.0, p * 2))
        put(canvas, self.tag, self.cx, self.tag_y, alpha=out * clamp((t - self.t0 - 0.12) / 0.2))


class Counter:
    """A number running from `a` to `b` (a depth as it is dug, a cost as it adds up): a small tag
    over a big yellow figure, under the captions; holds a moment at the end."""

    def __init__(
        self,
        a: float,
        b: float,
        t0: float,
        dur: float,
        t1: float,
        layout: Layout = VERTICAL,
        unit: str = "",
        label: str = "",
    ):
        k = layout.scale
        self.a, self.b, self.t0, self.dur, self.t1 = a, b, t0, max(0.2, dur), t1
        self.unit, self.k = tr_upper(unit), k
        self.text = f"{label} {b:g} {unit}"
        self.cx = layout.w / 2
        self.y = 1290 * k
        self.size = round(110 * k)
        self.tag = (
            _label(tr_upper(label), round(36 * k), (17, 17, 17, 225), (255, 255, 255))
            if label
            else None
        )
        self.decimals = 1 if (b - a) < 3 and (a % 1 or b % 1) else 0

    def value(self, t: float) -> float:
        p = clamp((t - self.t0) / self.dur)
        return self.a + (self.b - self.a) * (1 - (1 - p) ** 2)  # fast, then settles

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        from vlogkit.scene3d.hud import tr_number

        v = self.value(t)
        num = tr_number(round(v, self.decimals)) if self.decimals else tr_number(round(v))
        img = render_line(
            f"{num} {self.unit}".strip(), self.size, color=YELLOW, stroke=round(10 * self.k)
        )
        alpha = clamp((t - self.t0) / 0.12) * clamp((self.t1 - t) / 0.2)
        put(canvas, img, self.cx, self.y, alpha=alpha)
        if self.tag is not None:
            put(
                canvas,
                self.tag,
                self.cx,
                self.y - img.height / 2 - self.tag.height / 2 - 8 * self.k,
                alpha=alpha,
            )


class Stamp:
    """A big tilted word in a frame, slammed down (from large to its size), held, faded."""

    def __init__(
        self, text: str, t0: float, t1: float, layout: Layout = VERTICAL, color: str = "#ff3b30"
    ):
        k = layout.scale
        self.text, self.t0, self.t1 = text, t0, t1
        self.cx, self.cy = layout.w / 2, 1180 * k
        col = tuple(int(color.lstrip("#")[i : i + 2], 16) for i in (0, 2, 4))
        f = font("Black", round(150 * k))
        x0, y0, x1, y1 = f.getbbox(tr_upper(text))
        pad = round(36 * k)
        w, h = x1 - x0 + 2 * pad, y1 - y0 + 2 * pad
        im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=round(24 * k), fill=(*col, 235))
        d.rounded_rectangle((8 * k, 8 * k, w - 1 - 8 * k, h - 1 - 8 * k), radius=round(18 * k),
                            outline=(255, 255, 255, 255), width=max(2, round(7 * k)))  # fmt: skip
        d.text((pad - x0, pad - y0), tr_upper(text), font=f, fill="white")
        self.img = im.rotate(-8, resample=Image.BICUBIC, expand=True)

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = clamp((t - self.t0) / 0.16)
        s = 1.7 - 0.7 * ease_out_cubic(p)  # slammed down from above the frame
        img = self.img.resize(
            (max(1, round(self.img.width * s)), max(1, round(self.img.height * s)))
        )
        put(canvas, img, self.cx, self.cy, alpha=min(1.0, p * 1.5) * clamp((self.t1 - t) / 0.2))
