"""Looks: how a shot is shown, drawn over its rendered frames (security camera, live news, a phone
video, old film, night vision). The story devices of the genre: the same scene "caught on camera",
"on the news", "gone viral" reads as a new event without a new set.

    "look": "security"                                   (a name)
    "look": {"kind": "news", "text": "...", "ticker": "...", "channel": "PEKİ YA TV"}

Everything stays clear of the platform overlays (top icons, the bottom title block, the right
button column) and of the counter (top left) and the captions (middle).
"""

from __future__ import annotations

import math
import random

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageOps

from vlogkit.graphics.style import font, tr_upper

RED = (215, 38, 30)


def _spec(look) -> dict:
    return {"kind": look} if isinstance(look, str) else dict(look or {})


def _noise(size: tuple[int, int], amount: int, seed: int) -> Image.Image:
    random.seed(seed)
    small = Image.effect_noise((max(1, size[0] // 2), max(1, size[1] // 2)), amount)
    return small.resize(size, Image.NEAREST)


def _vignette(img: Image.Image, strength: float = 0.55) -> Image.Image:
    w, h = img.size
    mask = Image.new("L", (w // 8, h // 8), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse((-w // 40, -h // 60, w // 8 + w // 40, h // 8 + h // 60), fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(w // 50)).resize((w, h), Image.BILINEAR)
    dark = Image.new("RGB", (w, h), (0, 0, 0))
    return Image.composite(img, Image.blend(img, dark, strength), mask)


def _clock(t_abs: float, base: str = "03:14") -> str:
    hh, mm = (int(x) for x in base.split(":"))
    s = int(t_abs) + 17
    return f"{hh:02d}:{(mm + s // 60) % 60:02d}:{s % 60:02d}"


def _text(d, xy, text, size, fill, weight="Black", anchor="la"):
    d.text(xy, text, font=font(weight, size), fill=fill, anchor=anchor)


def security(img: Image.Image, s: dict, t: float, t_abs: float, k: float, seed: int) -> Image.Image:
    w, h = img.size
    g = ImageOps.grayscale(img).filter(ImageFilter.GaussianBlur(0.8 * k))
    g = ImageEnhance.Contrast(g).enhance(1.25)
    g = ImageChops.add(g, _noise((w, h), 38, seed), scale=1.0, offset=-60)
    out = Image.merge("RGB", (g, g.point(lambda v: min(255, v + 6)), g))
    lines = Image.new("L", (w, h), 0)
    ld = ImageDraw.Draw(lines)
    for y in range(0, h, max(2, round(4 * k))):
        ld.line((0, y, w, y), fill=28)
    out = ImageChops.subtract(out, Image.merge("RGB", (lines, lines, lines)))
    out = _vignette(out, 0.5)
    d = ImageDraw.Draw(out)
    m = round(40 * k)
    if int(t * 2) % 2 == 0:
        d.ellipse(
            (w - round(250 * k), round(215 * k), w - round(222 * k), round(243 * k)), fill=RED
        )
    _text(
        d, (w - round(210 * k), round(229 * k)), "REC", round(34 * k), (255, 255, 255), anchor="lm"
    )
    _text(d, (w - m, round(285 * k)), tr_upper(s.get("text", "KAMERA 03")), round(30 * k), (235, 235, 235),
          "ExtraBold", anchor="ra")  # fmt: skip
    _text(d, (m, round(1385 * k)), _clock(t_abs, s.get("time", "03:14")), round(40 * k), (240, 240, 240),
          "ExtraBold", anchor="ls")  # fmt: skip
    c, L = round(26 * k), round(70 * k)  # corner brackets
    for x, y, sx, sy in ((c, c + round(180 * k), 1, 1), (w - c, c + round(180 * k), -1, 1),
                         (c, round(1420 * k), 1, -1), (w - c, round(1420 * k), -1, -1)):  # fmt: skip
        d.line((x, y, x + sx * L, y), fill=(230, 230, 230), width=max(2, round(4 * k)))
        d.line((x, y, x, y + sy * L), fill=(230, 230, 230), width=max(2, round(4 * k)))
    return out


def news(img: Image.Image, s: dict, t: float, t_abs: float, k: float, seed: int) -> Image.Image:
    w = img.size[0]
    out = img.copy()
    d = ImageDraw.Draw(out, "RGBA")
    # CANLI badge and channel, top right below the platform icons
    bx = w - round(40 * k)
    _text(d, (bx, round(215 * k)), tr_upper(s.get("channel", "PEKİ YA TV")), round(30 * k),
          (255, 255, 255), "Black", anchor="ra")  # fmt: skip
    live_w = round(130 * k)
    d.rounded_rectangle((bx - live_w, round(258 * k), bx, round(304 * k)), round(8 * k), fill=RED)
    _text(
        d, (bx - live_w // 2, round(281 * k)), "CANLI", round(28 * k), (255, 255, 255), anchor="mm"
    )
    # lower third: tag, headline, ticker (above the bottom title block)
    y0 = round(1160 * k)
    tag = tr_upper(s.get("tag", "SON DAKİKA"))
    f_tag = font("Black", round(40 * k))
    tw = d.textlength(tag, font=f_tag) + round(44 * k)
    slide = min(1.0, t / 0.35)  # the banner slides in
    x_off = round((1 - (1 - (1 - slide) ** 3)) * -w)
    d.rectangle((x_off, y0, x_off + tw, y0 + round(66 * k)), fill=RED)
    d.text(
        (x_off + round(22 * k), y0 + round(33 * k)),
        tag,
        font=f_tag,
        fill=(255, 255, 255),
        anchor="lm",
    )
    head = tr_upper(s.get("text", ""))
    f_head = font("Black", round(50 * k))
    while d.textlength(head, font=f_head) > w - round(80 * k) and f_head.size > 24:
        f_head = font("Black", f_head.size - 2)
    d.rectangle(
        (x_off, y0 + round(66 * k), x_off + w, y0 + round(156 * k)), fill=(255, 255, 255, 240)
    )
    d.text(
        (x_off + round(30 * k), y0 + round(111 * k)),
        head,
        font=f_head,
        fill=(20, 20, 20),
        anchor="lm",
    )
    ty = y0 + round(156 * k)
    d.rectangle((0, ty, w, ty + round(52 * k)), fill=(16, 28, 58, 235))
    ticker = tr_upper(s.get("ticker", "")) or head
    f_t = font("ExtraBold", round(30 * k))
    tl = d.textlength(ticker + "   •   ", font=f_t)
    x = w - (t * 260 * k) % (tl + w)
    while x < w:
        d.text(
            (x, ty + round(26 * k)), ticker + "   •   ", font=f_t, fill=(255, 210, 63), anchor="lm"
        )
        x += tl
    return out


def phone(img: Image.Image, s: dict, t: float, t_abs: float, k: float, seed: int) -> Image.Image:
    """The shot plays on a phone held up to the viewer: a viral post with a climbing like count."""
    w = img.size[0]
    bg = img.filter(ImageFilter.GaussianBlur(28 * k))
    bg = ImageEnhance.Brightness(bg).enhance(0.45)
    pw, ph = round(720 * k), round(1280 * k)
    x0, y0 = (w - pw) // 2, round(205 * k)
    bez = round(22 * k)
    d = ImageDraw.Draw(bg, "RGBA")
    d.rounded_rectangle(
        (x0 - bez, y0 - bez, x0 + pw + bez, y0 + ph + bez), round(70 * k), fill=(14, 14, 18)
    )
    screen = ImageOps.fit(img, (pw, ph), Image.LANCZOS)
    mask = Image.new("L", (pw, ph), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, pw, ph), round(52 * k), fill=255)
    bg.paste(screen, (x0, y0), mask)
    d = ImageDraw.Draw(bg, "RGBA")
    # the post: user, follow, the climbing like counter, the hashtag line
    ux, uy = x0 + round(36 * k), y0 + round(150 * k)  # below the counter
    d.ellipse((ux, uy - round(26 * k), ux + round(52 * k), uy + round(26 * k)), fill=(255, 122, 89))
    _text(
        d,
        (ux + round(68 * k), uy),
        s.get("user", "@pekiya"),
        round(30 * k),
        (255, 255, 255),
        "ExtraBold",
        "lm",
    )
    rx, ry = x0 + pw - round(70 * k), y0 + round(760 * k)
    likes = float(s.get("likes", 2_400_000)) * min(1.0, 0.15 + t / 2.5)
    for i, (icon, val) in enumerate(
        (("heart", _short(likes)), ("bubble", _short(likes / 37)), ("share", _short(likes / 90)))
    ):
        y = ry + i * round(120 * k)
        _icon(d, icon, rx, y, round(30 * k))
        _text(d, (rx, y + round(54 * k)), val, round(24 * k), (255, 255, 255), "ExtraBold", "mm")
    _text(d, (x0 + round(36 * k), y0 + ph - round(110 * k)), s.get("text", "#pekiya"), round(34 * k),
          (255, 255, 255), "Black", "ls")  # fmt: skip
    return bg


def _icon(d, kind: str, cx: int, cy: int, r: int) -> None:
    """The post's buttons, drawn (the font has no symbols)."""
    if kind == "heart":
        q = r * 0.55
        red = (255, 48, 84)
        d.ellipse((cx - r, cy - q - r * 0.5, cx, cy + q - r * 0.5), fill=red)
        d.ellipse((cx, cy - q - r * 0.5, cx + r, cy + q - r * 0.5), fill=red)
        d.polygon(
            [(cx - r * 0.97, cy - r * 0.3), (cx + r * 0.97, cy - r * 0.3), (cx, cy + r)], fill=red
        )
    elif kind == "bubble":
        d.ellipse((cx - r, cy - r * 0.85, cx + r, cy + r * 0.75), fill=(255, 255, 255))
        d.polygon([(cx - r * 0.6, cy + r * 0.4), (cx - r * 0.9, cy + r), (cx - r * 0.1, cy + r * 0.65)],
                  fill=(255, 255, 255))  # fmt: skip
    else:
        d.polygon([(cx - r, cy + r * 0.6), (cx - r * 0.2, cy - r * 0.35), (cx - r * 0.2, cy - r * 0.9),
                   (cx + r, cy), (cx - r * 0.2, cy + r * 0.9), (cx - r * 0.2, cy + r * 0.35)],
                  fill=(255, 255, 255))  # fmt: skip


def _short(n: float) -> str:
    if n >= 1e6:
        return f"{n / 1e6:.1f} M".replace(".", ",")
    if n >= 1e3:
        return f"{n / 1e3:.0f} B"
    return str(int(n))


def old(img: Image.Image, s: dict, t: float, t_abs: float, k: float, seed: int) -> Image.Image:
    w, h = img.size
    g = ImageOps.grayscale(img)
    sep = ImageOps.colorize(g, (38, 26, 14), (240, 222, 186))
    flick = 0.92 + 0.08 * math.sin(t_abs * 37.0 + seed)
    sep = ImageEnhance.Brightness(sep).enhance(flick)
    grain = _noise((w, h), 50, seed)
    sep = Image.blend(sep, Image.merge("RGB", (grain, grain, grain)), 0.08)
    d = ImageDraw.Draw(sep)
    rng = random.Random(seed)
    for _ in range(rng.randint(0, 2)):
        x = rng.randint(0, w)
        d.line((x, 0, x + rng.randint(-20, 20), h), fill=(250, 240, 220), width=1)
    return _vignette(sep, 0.65)


def nightvision(
    img: Image.Image, s: dict, t: float, t_abs: float, k: float, seed: int
) -> Image.Image:
    w, h = img.size
    g = ImageEnhance.Brightness(ImageOps.grayscale(img)).enhance(1.6)
    g = ImageChops.add(g, _noise((w, h), 40, seed), offset=-50)
    out = ImageOps.colorize(g, (0, 18, 0), (170, 255, 150))
    return _vignette(out, 0.75)


LOOKS = {"security": security, "news": news, "phone": phone, "old": old, "nightvision": nightvision}


def apply(img: Image.Image, look, t: float, t_abs: float, seed: int = 0) -> Image.Image:
    """Draw the look over one frame; `t` = seconds into the shot, `t_abs` = into the video."""
    s = _spec(look)
    fn = LOOKS.get(s.get("kind", ""))
    if fn is None:
        return img
    k = img.size[0] / 1080
    return fn(img.convert("RGB"), s, t, t_abs, k, seed)
