"""Timeline elements. Each has draw(canvas, t) and draws nothing outside its time window."""

from __future__ import annotations

import random
from collections.abc import Sequence
from typing import Protocol

from PIL import Image, ImageDraw, ImageFilter

from vlogkit.graphics.easing import clamp, ease_out_back, ease_out_cubic
from vlogkit.graphics.style import (
    ACCENT,
    BLACK,
    CAP_X,
    CAP_Y,
    CAPTION_SIZE,
    TOP_Y,
    VERTICAL,
    WHITE,
    Layout,
    W,
    font,
    is_emoji,
)
from vlogkit.graphics.text import fit, put, render_line, stack
from vlogkit.timecode import FPS_NTSC


class Element(Protocol):
    def draw(self, canvas: Image.Image, t: float) -> None: ...


class Caption:
    """Pops in with overshoot (ease-out-back), fades out."""

    def __init__(
        self,
        img: Image.Image,
        t0: float,
        t1: float,
        cx: float = CAP_X,
        cy: float = CAP_Y,
        pop: float = 0.22,
        fade: float = 0.14,
        s0: float = 0.55,
    ):
        self.img, self.t0, self.t1, self.cx, self.cy = img, t0, t1, cx, cy
        self.pop, self.fade, self.s0 = pop, fade, s0
        self.text = ""  # set by caption(); only used for the emoji check

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = clamp((t - self.t0) / self.pop)
        scale = self.s0 + (1 - self.s0) * ease_out_back(p) if p < 1 else 1.0
        alpha = clamp(p * 3) * clamp((self.t1 - t) / self.fade)
        put(canvas, self.img, self.cx, self.cy, scale, alpha)


def caption(
    text: str,
    t0: float,
    t1: float,
    size: int | None = None,
    layout: Layout = VERTICAL,
    **kw,
) -> Caption:
    """The standard caption: lines split on '\\n', [accent] words, emoji, safe width.

    size = pixels; default CAPTION_SIZE times `layout.scale`.
    """
    size = size or round(CAPTION_SIZE * layout.scale)
    kw.setdefault("cx", layout.cap_x)
    kw.setdefault("cy", layout.cap_y)
    img = fit(stack([render_line(line, size) for line in text.split("\n")]), layout.max_w)
    cap = Caption(img, t0, t1, **kw)
    cap.text = text
    return cap


def count_emoji(text: str) -> int:
    """Visible emoji, roughly: ZWJ sequences, skin tones and flag pairs count once."""
    n, prev, flag_half = 0, "", False
    for ch in text:
        o = ord(ch)
        if 0x1F3FB <= o <= 0x1F3FF or prev == "\u200d":  # skin tone / joined to the previous one
            pass
        elif 0x1F1E6 <= o <= 0x1F1FF:  # regional indicators come in pairs (flags)
            n += not flag_half
            flag_half = not flag_half
        elif is_emoji(ch):
            n += 1
        prev = ch
    return n


def emoji_notes(elements: Sequence[Element], every: int = 3) -> list[str]:
    """House emoji rule, checked before the overlay render (warnings, not errors).

    At most one caption in `every` carries an emoji, one per caption, and only where it adds
    meaning; spoken subtitles (long videos) carry none.
    """
    caps = [e for e in elements if isinstance(e, Caption) and e.text]
    with_emoji = [c for c in caps if count_emoji(c.text)]
    notes = []
    if len(with_emoji) > max(1, len(caps) // every):
        notes.append(
            f"emoji yoğun: {len(with_emoji)}/{len(caps)} altyazıda emoji var "
            f"(kural: en fazla {max(1, len(caps) // every)})"
        )
    notes += [f"birden çok emoji: {c.text!r}" for c in caps if count_emoji(c.text) > 1]
    subs = [e for e in elements if isinstance(e, Subtitle) and count_emoji(e.text)]
    if subs:
        notes.append(f"konuşma altyazısında emoji: {len(subs)} satır (uzun videoda kullanılmaz)")
    return notes


class Subtitle:
    """Spoken words, bottom centre: no pop (it would pull the eye), just a short fade.

    Works for any script: Chinese/Japanese lines are drawn with the CJK font.
    """

    def __init__(
        self,
        text: str,
        t0: float,
        t1: float,
        layout: Layout = VERTICAL,
        size: int | None = None,
        fade: float = 0.08,
    ):
        size = size or round((62 if layout.landscape else 72) * layout.scale)
        self.text = text
        lines = [render_line(line, size, stroke=round(size * 0.12)) for line in text.split("\n")]
        self.img = fit(stack(lines, gap=-int(size * 0.55)), layout.max_w)
        self.t0, self.t1, self.fade = t0, t1, fade
        self.cx, self.cy = layout.w / 2, layout.sub_y

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        a = clamp((t - self.t0) / self.fade) * clamp((self.t1 - t) / self.fade)
        put(canvas, self.img, self.cx, self.cy, alpha=a)


class ChapterCard:
    """Chapter title in the top-left title-safe corner.

    An accent bar grows, then the small tag ('CHAPTER 03') and the title wipe in from the left;
    at the end everything slides back out. Keep it 2-3 s: it labels the section, then gets out
    of the way.
    """

    def __init__(
        self,
        t0: float,
        t1: float,
        title: str,
        tag: str = "",
        layout: Layout = VERTICAL,
        size: int | None = None,
    ):
        size = size or round((72 if layout.landscape else 76) * layout.scale)
        self.t0, self.t1, self.margin = t0, t1, layout.margin
        self.slide = 40 * layout.scale  # px the card slides back out
        self.text = title  # chapter marker name in editor exports
        title_img = render_line(title, size, "BlackItalic")
        tracking = round(6 * layout.scale)
        tag_img = (
            render_line(f"[{tag}]", int(size * 0.42), "ExtraBold", tracking=tracking)
            if tag
            else None
        )
        text = (
            stack([tag_img, title_img], gap=-int(size * 0.2), align="left")
            if tag_img
            else title_img
        )
        bar_w, gap = max(6, size // 10), size // 4
        h = text.height - int(size * 0.5)  # the shadow padding does not need a bar
        self.card = Image.new("RGBA", (bar_w + gap + text.width, text.height), (0, 0, 0, 0))
        self.bar = Image.new("RGBA", (bar_w, h), ACCENT)
        self.bar_y = (text.height - h) // 2
        self.card.alpha_composite(text, (bar_w + gap, 0))

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        grow = ease_out_cubic(clamp((t - self.t0) / 0.18))
        wipe = ease_out_cubic(clamp((t - self.t0 - 0.08) / 0.42))
        out = ease_out_cubic(clamp((t - (self.t1 - 0.32)) / 0.32))
        alpha = 1 - out
        x = self.margin - int(self.slide * out)
        y = self.margin
        bh = max(1, int(self.bar.height * grow))
        bar = self.bar.crop((0, 0, self.bar.width, bh))
        put(canvas, bar, x + bar.width / 2, y + self.bar_y + self.bar.height / 2, alpha=alpha)
        cw = int(self.card.width * wipe)
        if cw > self.bar.width:
            part = self.card.crop((self.bar.width, 0, cw, self.card.height))
            put(canvas, part, x + self.bar.width + part.width / 2, y + part.height / 2, alpha=alpha)


class Karaoke:
    """Words appear as they are spoken; the current word is accent-coloured.

    lines = [[(word, t_start), ...], ...]. Show 1-4 words per chunk and chain several Karaoke
    elements (each with its own t_end) for longer sentences.
    """

    def __init__(
        self,
        lines: Sequence[Sequence[tuple[str, float]]],
        t_end: float,
        size: int = CAPTION_SIZE,
        cx: float = CAP_X,
        cy: float = CAP_Y,
    ):
        self.t_end = t_end
        self.text = "\n".join(" ".join(w for w, _ in line) for line in lines)  # editor exports
        self.cx, self.cy = cx, cy
        self.words: list[tuple[float, Image.Image, Image.Image, float, float]] = []
        f = font("ExtraBold", size)
        space = f.getlength(" ") + size * 0.1
        line_h = int(size * 1.12)
        y = cy - line_h * len(lines) / 2 + line_h / 2
        for line in lines:
            adv = [f.getlength(w) for w, _ in line]
            x = cx - (sum(adv) + space * (len(adv) - 1)) / 2
            for (word, t), a in zip(line, adv, strict=True):
                self.words.append(
                    (
                        t,
                        render_line(word, size, keep_v=True),
                        render_line(f"[{word}]", size, keep_v=True),
                        x + a / 2,
                        y,
                    )
                )
                x += a + space
            y += line_h
        self.words.sort(key=lambda w: w[0])

    def draw(self, canvas: Image.Image, t: float) -> None:
        if t >= self.t_end or t < self.words[0][0]:
            return
        fade = clamp((self.t_end - t) / 0.12)
        visible = [w for w in self.words if w[0] <= t]
        cur = visible[-1]
        for w in visible:
            wt, white, accent, x, y = w
            p = clamp((t - wt) / 0.16)
            scale = 0.6 + 0.4 * ease_out_back(p) if p < 1 else 1.0
            put(canvas, accent if w is cur else white, x, y, scale, clamp(p * 3) * fade)


class Checklist:
    """'✅ item' lines that stack up as each item happens on screen."""

    def __init__(
        self,
        items: Sequence[tuple[str, float]],
        t_end: float,
        cy: float = CAP_Y - 50,
        size: int = 88,
        cx: float = CAP_X,
    ):
        self.imgs = [(render_line(f"✅ {txt}", size), t) for txt, t in items]
        self.t_end, self.cx, self.cy = t_end, cx, cy
        self.w = max(i.width for i, _ in self.imgs)

    def draw(self, canvas: Image.Image, t: float) -> None:
        if t >= self.t_end:
            return
        fade = clamp((self.t_end - t) / 0.14)
        y = self.cy
        for img, t0 in self.imgs:
            if t >= t0:
                p = clamp((t - t0) / 0.2)
                s = 0.55 + 0.45 * ease_out_back(p) if p < 1 else 1.0
                put(canvas, img, self.cx - self.w / 2 + img.width / 2, y, s, clamp(p * 3) * fade)
            y += img.height - 20


def _minutes(hhmm: str) -> int:
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


class Clock:
    """Big HH:MM that rolls from `start` to `end` (either direction), then holds `end` in accent."""

    def __init__(
        self,
        t0: float,
        t_land: float,
        t_end: float,
        start: str = "08:00",
        end: str = "04:05",
        cy: float = TOP_Y,
        size: int = 230,
        ease=ease_out_cubic,  # how the minutes roll; `lambda u: u` = a steady race clock
        pad: bool = True,  # False: "5:07" instead of "05:07" (elapsed time)
    ):
        self.t0, self.t_land, self.t_end, self.cy, self.size = t0, t_land, t_end, cy, size
        self.m0, self.m1 = _minutes(start), _minutes(end)
        self.ease, self.pad = ease, pad
        self.end = self.label(self.m1)
        self.cache: dict[tuple[str, bool], Image.Image] = {}

    def label(self, mins: int) -> str:
        h = f"{mins // 60:02d}" if self.pad else str(mins // 60)
        return f"{h}:{mins % 60:02d}"

    def img(self, label: str, accent: bool) -> Image.Image:
        key = (label, accent)
        if key not in self.cache:
            self.cache[key] = render_line(
                f"[{label}]" if accent else label, self.size, "BlackItalic"
            )
        return self.cache[key]

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t_end):
            return
        if t < self.t_land:
            u = clamp((t - self.t0) / (self.t_land - self.t0))
            mins = round(self.m0 - (self.m0 - self.m1) * self.ease(u))
            put(
                canvas,
                self.img(self.label(mins), False),
                W / 2,
                self.cy,
                1.0,
                clamp(u * 6),
            )
        else:
            p = clamp((t - self.t_land) / 0.25)
            put(
                canvas,
                self.img(self.end, True),
                W / 2,
                self.cy,
                1.18 - 0.18 * ease_out_cubic(p),
                clamp((self.t_end - t) / 0.15),
            )


class Counter:
    """Big number that rolls from `start` to `end` (e.g. 'KM 38.5' -> 'KM 26.5'), then holds `end`
    in accent. The Clock for anything that is not HH:MM: distances, altitudes, counts.

    fmt formats the value ("{:.1f}" -> 26.5, "{:.0f}" -> 27); prefix/suffix stay as they are.
    """

    def __init__(
        self,
        t0: float,
        t_land: float,
        t_end: float,
        start: float,
        end: float,
        fmt: str = "{:.1f}",
        prefix: str = "",
        suffix: str = "",
        cy: float = TOP_Y,
        size: int = 200,
    ):
        self.t0, self.t_land, self.t_end, self.cy, self.size = t0, t_land, t_end, cy, size
        self.start, self.end, self.fmt = start, end, fmt
        self.prefix, self.suffix = prefix, suffix
        self.cache: dict[tuple[str, bool], Image.Image] = {}

    def label(self, value: float) -> str:
        return f"{self.prefix}{self.fmt.format(value)}{self.suffix}"

    def value_at(self, t: float) -> float:
        u = clamp((t - self.t0) / (self.t_land - self.t0))
        return self.start + (self.end - self.start) * ease_out_cubic(u)

    def img(self, label: str, accent: bool) -> Image.Image:
        key = (label, accent)
        if key not in self.cache:
            self.cache[key] = render_line(
                f"[{label}]" if accent else label, self.size, "BlackItalic"
            )
        return self.cache[key]

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t_end):
            return
        if t < self.t_land:
            u = clamp((t - self.t0) / (self.t_land - self.t0))
            img = self.img(self.label(self.value_at(t)), False)
            put(canvas, img, W / 2, self.cy, 1.0, clamp(u * 6))
        else:
            p = clamp((t - self.t_land) / 0.25)
            put(
                canvas,
                self.img(self.label(self.end), True),
                W / 2,
                self.cy,
                1.18 - 0.18 * ease_out_cubic(p),
                clamp((self.t_end - t) / 0.15),
            )


class Flash:
    """Full-frame white flash fading out (cut accents)."""

    def __init__(self, t0: float, dur: float, peak: float):
        self.t0, self.dur, self.peak = t0, dur, peak

    def draw(self, canvas: Image.Image, t: float) -> None:
        if self.t0 <= t < self.t0 + self.dur:
            a = self.peak * (1 - (t - self.t0) / self.dur)
            canvas.alpha_composite(Image.new("RGBA", canvas.size, (255, 255, 255, int(255 * a))))


class RewindFX:
    """VHS rewind: scanlines, drifting tracking-noise bands, flickering RGB-split '◀◀ title'."""

    def __init__(
        self,
        t0: float,
        t1: float,
        title: str = "GERİ SARALIM",
        seed: int = 7,
        fps: float = float(FPS_NTSC),
        layout: Layout = VERTICAL,
    ):
        self.t0, self.t1, self.fps = t0, t1, fps
        W, H = layout.size
        self.w, self.h = W, H
        sl = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(sl)
        for y in range(0, H, 6):
            d.rectangle((0, y, W, y + 2), fill=(0, 0, 0, 70))
        self.scan = sl
        rnd = random.Random(seed)
        self.bands = []
        for _ in range(3):
            bh = rnd.randint(26, 70)
            b = Image.new("RGBA", (W, bh), (0, 0, 0, 0))
            bd = ImageDraw.Draw(b)
            for _ in range(900):
                x, y, ln = rnd.randint(0, W), rnd.randint(0, bh), rnd.randint(8, 90)
                v = rnd.randint(170, 255)
                bd.line((x, y, x + ln, y), fill=(v, v, v, rnd.randint(40, 150)), width=1)
            self.bands.append((b, rnd.random(), 0.9 + rnd.random() * 1.6))
        label = render_line(title, 76, "BlackItalic")
        ic = self.icon(104)
        self.title = Image.new(
            "RGBA", (ic.width + label.width - 10, max(ic.height, label.height)), (0, 0, 0, 0)
        )
        self.title.alpha_composite(ic, (0, (self.title.height - ic.height) // 2))
        self.title.alpha_composite(label, (ic.width - 10, (self.title.height - label.height) // 2))
        self.title_r = self._tint(self.title, (255, 40, 60))
        self.title_c = self._tint(self.title, (40, 230, 255))

    @staticmethod
    def _tint(im: Image.Image, rgb: tuple[int, int, int]) -> Image.Image:
        return Image.merge(
            "RGBA",
            (
                *[Image.new("L", im.size, v) for v in rgb],
                im.getchannel("A").point(lambda a: int(a * 0.7)),
            ),
        )

    @staticmethod
    def icon(size: int) -> Image.Image:
        """◀◀ drawn as polygons (the ▶/⏪ glyphs render as emoji boxes)."""
        h = int(size * 0.8)
        w1 = int(h * 0.8)
        pad = 40
        im = Image.new("RGBA", (2 * w1 + 2 * pad, h + 2 * pad), (0, 0, 0, 0))
        d = ImageDraw.Draw(im)
        for k in range(2):
            x0 = pad + k * w1
            d.polygon(
                [(x0 + w1, pad), (x0 + w1, pad + h), (x0, pad + h / 2)],
                fill=WHITE,
                outline=BLACK,
                width=6,
            )
        sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
        sh.putalpha(im.getchannel("A").point(lambda v: int(v * 0.6)))
        sh = sh.filter(ImageFilter.GaussianBlur(10))
        out = Image.new("RGBA", im.size, (0, 0, 0, 0))
        out.alpha_composite(sh, (0, 6))
        out.alpha_composite(im)
        return out

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        u = (t - self.t0) / (self.t1 - self.t0)
        canvas.alpha_composite(self.scan)
        cx, cy = self.w / 2, self.h / 2
        for b, off, spd in self.bands:
            y = int(((off + u * spd) % 1.0) * (self.h + 100)) - 60
            put(canvas, b, cx, y + b.height / 2)
        n = round((t - self.t0) * self.fps)
        jit = (n * 37 % 7) - 3
        flick = 0.75 + 0.25 * ((n * 13) % 3) / 2
        put(canvas, self.title_r, cx - 7 + jit, cy, alpha=flick)
        put(canvas, self.title_c, cx + 7 + jit, cy, alpha=flick)
        put(canvas, self.title, cx + jit, cy, alpha=flick)


class EndCard:
    """Dimmed band + small accent tag + big title (e.g. 'SIRADAKİ · BÖLÜM 2' / 'Start alanı 🏁')."""

    def __init__(self, t0: float, t1: float, tag: str, title: str, layout: Layout = VERTICAL):
        self.t0, self.t1 = t0, t1
        k = layout.scale
        self.cx, self.cy = layout.w / 2, layout.h / 2
        self.dy_tag, self.dy_title = 110 * k, 15 * k
        self.tag = render_line(f"[{tag}]", round(48 * k), "ExtraBold", tracking=round(5 * k))
        self.title = fit(
            render_line(title, round(110 * k), "BlackItalic"), layout.w - 2 * layout.margin
        )
        grad = Image.new("L", (1, 256))
        for y in range(256):
            grad.putpixel((0, y), int(200 * (1 - abs(y - 128) / 128) ** 0.7))
        band = min(round(700 * k), layout.h * 5 // 8)
        self.dim = Image.new("RGBA", (layout.w, band), (0, 0, 0, 255))
        self.dim.putalpha(grad.resize((layout.w, band)))

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        put(canvas, self.dim, self.cx, self.cy, alpha=clamp((t - self.t0) / 0.3))
        put(
            canvas,
            self.tag,
            self.cx,
            self.cy - self.dy_tag,
            0.8 + 0.2 * ease_out_back(clamp((t - self.t0) / 0.22)),
            clamp((t - self.t0) / 0.1),
        )
        p2 = clamp((t - self.t0 - 0.12) / 0.26)
        if p2 > 0:
            put(
                canvas,
                self.title,
                self.cx,
                self.cy + self.dy_title,
                0.5 + 0.5 * ease_out_back(p2),
                clamp(p2 * 3),
            )


class TitleCard:
    """Centred video title for a long video's cold open: optional small tag, a big title and a
    one-line promise under it. No pop: it fades in while settling from 6 % larger, holds, and
    fades out while drifting 2 % larger (a documentary title, not a meme caption).

    dim  darkness (0-1) of a soft horizontal band behind the text, for bright pictures.
    """

    def __init__(
        self,
        t0: float,
        t1: float,
        title: str,
        sub: str = "",
        tag: str = "",
        layout: Layout = VERTICAL,
        size: int | None = None,
        cy: float | None = None,
        dim: float = 0.35,
        fade_in: float = 0.45,
        fade_out: float = 0.4,
    ):
        k = layout.scale
        size = size or round((150 if layout.landscape else 130) * k)
        self.t0, self.t1, self.fade_in, self.fade_out = t0, t1, fade_in, fade_out
        self.text = "\n".join(x for x in (tag, title, sub) if x)
        self.cx, self.cy = layout.w / 2, layout.h / 2 if cy is None else cy
        img = render_line(title, size, "BlackItalic", tracking=round(size / 30))
        if tag:  # the title's box has room above for accents (Ğ, İ): tuck the tag into it
            t = render_line(f"[{tag}]", round(size * 0.3), "ExtraBold", tracking=round(size / 16))
            img = stack([t, img], gap=-round(size * 0.12))
        if sub:
            img = stack(
                [img, render_line(sub, round(size * 0.4), "ExtraBold")], gap=-round(size * 0.3)
            )
        self.img = fit(img, layout.w - 2 * layout.margin)
        self.dim = None
        if dim > 0:
            band = min(layout.h, round(self.img.height * 1.9))
            grad = Image.new("L", (1, 256))
            for y in range(256):
                grad.putpixel((0, y), int(255 * dim * (1 - abs(y - 128) / 128) ** 0.8))
            self.dim = Image.new("RGBA", (layout.w, band), (0, 0, 0, 255))
            self.dim.putalpha(grad.resize((layout.w, band)))

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p_in = ease_out_cubic(clamp((t - self.t0) / self.fade_in))
        p_out = clamp((t - (self.t1 - self.fade_out)) / self.fade_out)
        alpha = p_in * (1 - p_out)
        if self.dim is not None:
            put(canvas, self.dim, self.cx, self.cy, alpha=alpha)
        scale = 1.06 - 0.06 * p_in + 0.02 * p_out
        put(canvas, self.img, self.cx, self.cy, scale, alpha)
