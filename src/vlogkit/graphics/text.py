"""Rich caption text -> RGBA image: stroke, soft shadow, [accent] words and colour emoji."""

from __future__ import annotations

from collections.abc import Sequence

from PIL import Image, ImageDraw, ImageFilter

from vlogkit.graphics.style import (
    ACCENT,
    BLACK,
    MAX_W,
    WHITE,
    cjk_font,
    emoji_img,
    font,
    is_cjk,
    is_emoji,
)

Run = tuple[str, str, bool]  # (kind "t"|"c"|"e", text, accent); "c" = CJK text


def parse_runs(text: str) -> list[Run]:
    """ "Hedef: [04:30]'da ⏱" -> text/emoji runs; [brackets] mark accent-coloured words.

    Chinese/Japanese characters become "c" runs (drawn with the CJK font, Montserrat lacks them).
    """
    runs: list[Run] = []
    acc, buf, kind = False, "", "t"

    def flush() -> None:
        nonlocal buf
        if buf:
            runs.append((kind, buf, acc))
            buf = ""

    for ch in text.replace("️", ""):  # drop emoji variation selectors
        if ch == "[":
            flush()
            acc = True
        elif ch == "]":
            flush()
            acc = False
        elif is_emoji(ch):
            flush()
            runs.append(("e", ch, acc))
        else:
            k = "c" if is_cjk(ch) else "t"
            if k != kind:
                flush()
                kind = k
            buf += ch
    flush()
    return runs


def render_line(
    text: str,
    size: int,
    weight: str = "ExtraBold",
    color=WHITE,
    stroke: int | None = None,
    shadow: bool = True,
    tracking: int = 0,
    keep_v: bool = False,
) -> Image.Image:
    """One line of rich text. keep_v keeps the full line height (baseline-aligned words)."""
    f = font(weight, size)
    fonts = {"t": f, "c": cjk_font(weight, size) if any(is_cjk(c) for c in text) else f}
    stroke = round(size * 0.10) if stroke is None else stroke
    runs = parse_runs(text)
    asc, desc = f.getmetrics()
    cap_h = f.getbbox("H")[3] - f.getbbox("H")[1]
    eh = int(size * 1.0)
    widths = []
    for kind, s, _ in runs:
        if kind != "e":
            widths.append(fonts[kind].getlength(s) + tracking * len(s))
        else:
            e = emoji_img(s)
            widths.append(eh * e.width / e.height + size * 0.12)
    # room for the shadow: its blur (size * 0.16) fades out over ~3x that; never clip it
    pad = max(60, round(size * 0.5))
    txt = Image.new("RGBA", (int(sum(widths)) + 2 * pad, asc + desc + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(txt)
    base_y = pad + asc
    x = pad
    emojis = []
    for (kind, s, a), w in zip(runs, widths, strict=True):
        if kind != "e":
            col = ACCENT if a else color
            rf = fonts[kind]
            if tracking:
                cx = x
                for ch in s:
                    d.text(
                        (cx, base_y),
                        ch,
                        font=rf,
                        fill=col,
                        anchor="ls",
                        stroke_width=stroke,
                        stroke_fill=BLACK,
                    )
                    cx += rf.getlength(ch) + tracking
            else:
                d.text(
                    (x, base_y),
                    s,
                    font=rf,
                    fill=col,
                    anchor="ls",
                    stroke_width=stroke,
                    stroke_fill=BLACK,
                )
        else:
            e = emoji_img(s)
            e = e.resize((int(eh * e.width / e.height), eh), Image.LANCZOS)
            emojis.append((e, int(x + size * 0.06), int(base_y - cap_h / 2 - eh / 2)))
        x += w
    for e, ex, ey in emojis:
        txt.alpha_composite(e, (ex, ey))

    def crop(im: Image.Image) -> Image.Image:
        b = im.getbbox()
        return im.crop((b[0], 0, b[2], im.height) if keep_v else b)

    if not shadow:
        return crop(txt)
    sh = Image.new("RGBA", txt.size, (0, 0, 0, 0))
    sh.putalpha(txt.getchannel("A").point(lambda v: int(v * 0.6)))
    sh = sh.filter(ImageFilter.GaussianBlur(size * 0.16))
    out = Image.new("RGBA", txt.size, (0, 0, 0, 0))
    out.alpha_composite(sh, (0, int(size * 0.08)))
    out.alpha_composite(txt)
    return crop(out)


def stack(images: Sequence[Image.Image], gap: int = -18, align: str = "center") -> Image.Image:
    w = max(i.width for i in images)
    h = sum(i.height for i in images) + gap * (len(images) - 1)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    y = 0
    for i in images:
        x = {"center": (w - i.width) // 2, "right": w - i.width}.get(align, 0)
        out.alpha_composite(i, (x, y))
        y += i.height + gap
    return out


def fit(im: Image.Image, max_w: int = MAX_W) -> Image.Image:
    """Shrink captions wider than the safe width (keeps them clear of the Shorts buttons)."""
    if im.width <= max_w:
        return im
    return im.resize((max_w, int(im.height * max_w / im.width)), Image.LANCZOS)


def with_alpha(im: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return im
    im = im.copy()
    im.putalpha(im.getchannel("A").point(lambda v: int(v * alpha)))
    return im


def put(
    canvas: Image.Image,
    im: Image.Image,
    cx: float,
    cy: float,
    scale: float = 1.0,
    alpha: float = 1.0,
) -> None:
    """Composite `im` centred at (cx, cy), clipped to the canvas."""
    if alpha <= 0.003:
        return
    if abs(scale - 1) > 0.004:
        im = im.resize(
            (max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.BICUBIC
        )
    im = with_alpha(im, alpha)
    cw, ch = canvas.size
    x, y = int(cx - im.width / 2), int(cy - im.height / 2)
    sx, sy = max(0, -x), max(0, -y)
    x, y = max(0, x), max(0, y)
    if sx >= im.width or sy >= im.height or x >= cw or y >= ch:
        return
    canvas.alpha_composite(
        im.crop((sx, sy, min(im.width, sx + cw - x), min(im.height, sy + ch - y))), (x, y)
    )
