"""Caption styles by name, the hook headline, and the safe-area check.

Styles (pick one per video, show the gallery to choose: `vlogkit captions`):

    pop       the house caption: ExtraBold, pops in, [accent] words yellow
    kutu      the same on a soft dark box: reads on bright, busy pictures (snow, sky, crowds)
    sade      small, no pop, a short fade: calm vlog narration, lots of text
    karaoke   words light up as they are spoken (needs word times)
    büyük     big, upper case (Turkish İ/I), for a punch line or a number

`HookTitle` is the promise as one headline at the top in the first seconds (OpusClip's "auto
headline"): one style for the whole channel, under the platform's top icons.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from vlogkit.graphics.easing import clamp, ease_out_cubic
from vlogkit.graphics.elements import Caption, Karaoke, Subtitle, caption
from vlogkit.graphics.style import (
    CAPTION_SIZE,
    VERTICAL,
    Layout,
    font,
    tr_upper,
    unsafe_zones,
)
from vlogkit.graphics.text import fit, put, render_line, stack


def boxed(img: Image.Image, size: int, alpha: float = 0.62) -> Image.Image:
    """`img` (rendered text) on a rounded dark box with some room around the letters."""
    pad_x, pad_y = round(size * 0.34), round(size * 0.22)
    out = Image.new("RGBA", (img.width + 2 * pad_x, img.height + 2 * pad_y), (0, 0, 0, 0))
    solid = img.getchannel("A").point(lambda v: 255 if v > 110 else 0).getbbox()
    x0, y0, x1, y1 = solid or (0, 0, img.width, img.height)
    ImageDraw.Draw(out).rounded_rectangle(
        (x0, y0, x1 + 2 * pad_x, y1 + 2 * pad_y),
        radius=round(size * 0.28),
        fill=(0, 0, 0, round(255 * alpha)),
    )
    out.alpha_composite(img, (pad_x, pad_y))
    return out


def _boxed_caption(text: str, t0: float, t1: float, layout: Layout) -> Caption:
    size = round(CAPTION_SIZE * 0.9 * layout.scale)
    lines = [render_line(line, size, stroke=0, shadow=False) for line in text.split("\n")]
    img = boxed(fit(stack(lines, gap=-round(size * 0.55)), layout.max_w), size)
    cap = Caption(img, t0, t1, cx=layout.cap_x, cy=layout.cap_y)
    cap.text = text
    return cap


def _plain(text: str, t0: float, t1: float, layout: Layout) -> Subtitle:
    sub = Subtitle(
        text, t0, t1, layout=layout, size=round((58 if layout.landscape else 64) * layout.scale)
    )
    sub.cy = layout.cap_y if not layout.landscape else layout.sub_y
    return sub


def wrap_words(
    words: Sequence[tuple[str, float]], size: int, max_w: int, max_lines: int = 3
) -> list[list[tuple[str, float]]]:
    """Karaoke words in lines that fit max_w (Karaoke itself never wraps or shrinks)."""
    f = font("ExtraBold", size)
    space = f.getlength(" ") + size * 0.1
    lines: list[list[tuple[str, float]]] = [[]]
    width = 0.0
    for w, t in words:
        wl = f.getlength(w)
        if lines[-1] and width + space + wl > max_w and len(lines) < max_lines:
            lines.append([])
            width = 0.0
        width += (space if lines[-1] else 0) + wl
        lines[-1].append((w, t))
    return [ln for ln in lines if ln]


def _karaoke(
    text: str, t0: float, t1: float, layout: Layout, words: Sequence[tuple[str, float]] | None
) -> Karaoke:
    if words is None:  # no word times: spread them evenly (gallery, rough previews)
        ws = text.replace("[", "").replace("]", "").split()  # the spoken word is the accent
        step = (t1 - t0) / max(1, len(ws))
        words = [(w, t0 + i * step) for i, w in enumerate(ws)]
    size = round(CAPTION_SIZE * layout.scale)
    lines = wrap_words(list(words), size, layout.max_w)
    while size > 40 and any(  # still too long in max_lines: shrink a little
        font("ExtraBold", size).getlength(" ".join(w for w, _ in ln)) > layout.max_w for ln in lines
    ):
        size = round(size * 0.9)
        lines = wrap_words(list(words), size, layout.max_w)
    return Karaoke(lines, t1, size=size, cx=layout.cap_x, cy=layout.cap_y)


def _big(text: str, t0: float, t1: float, layout: Layout) -> Caption:
    return caption(tr_upper(text), t0, t1, size=round(118 * layout.scale), layout=layout)


STYLES: dict[str, tuple[str, Callable]] = {
    "pop": (
        "Ev stili: kalın, zıplayarak gelir, [vurgu] sarı",
        lambda x, a, b, lay, w: caption(x, a, b, layout=lay),
    ),
    "kutu": (
        "Koyu kutu üstünde: parlak ve kalabalık görüntüde okunur",
        lambda x, a, b, lay, w: _boxed_caption(x, a, b, lay),
    ),
    "sade": (
        "Küçük, zıplamaz: sakin anlatım, çok yazı",
        lambda x, a, b, lay, w: _plain(x, a, b, lay),
    ),
    "karaoke": (
        "Kelimeler söylendikçe yanar (kelime zamanı ister)",
        lambda x, a, b, lay, w: _karaoke(x, a, b, lay, w),
    ),
    "büyük": (
        "Büyük ve BÜYÜK HARF: espri, sayı, vurucu cümle",
        lambda x, a, b, lay, w: _big(x, a, b, lay),
    ),
}


def styled(
    style: str,
    text: str,
    t0: float,
    t1: float,
    layout: Layout = VERTICAL,
    words: Sequence[tuple[str, float]] | None = None,
):
    """One caption element in a named style (see module doc). words: karaoke word times."""
    if style not in STYLES:
        raise ValueError(f"altyazı stili: {' | '.join(STYLES)}")
    return STYLES[style][1](text, t0, t1, layout, words)


class HookTitle:
    """The promise as a headline at the top for the first seconds: ExtraBold on a soft dark box,
    slides down a little while it fades in, holds, fades out. [accent] words are yellow; keep it
    to 3-7 words. Sits under the platform's top icons (vertical) or in the title-safe top
    (landscape)."""

    def __init__(
        self,
        text: str,
        t0: float = 0.0,
        t1: float = 3.0,
        layout: Layout = VERTICAL,
        size: int | None = None,
        cy: float | None = None,
        box: float = 0.55,
    ):
        k = layout.scale
        size = size or round((72 if layout.landscape else 78) * k)
        self.text, self.t0, self.t1 = text, t0, t1
        lines = [render_line(line, size, stroke=round(size * 0.06)) for line in text.split("\n")]
        img = fit(
            stack(lines, gap=-round(size * 0.5)),
            layout.max_w if not layout.landscape else round(layout.w * 0.7),
        )
        self.img = boxed(img, size, box) if box > 0 else img
        self.cx = layout.w / 2
        top = 300 * k if not layout.landscape else layout.margin + 70 * k
        self.cy = cy if cy is not None else top
        self.slide = round(18 * k)

    def draw(self, canvas: Image.Image, t: float) -> None:
        if not (self.t0 <= t < self.t1):
            return
        p = ease_out_cubic(clamp((t - self.t0) / 0.3))
        alpha = p * clamp((self.t1 - t) / 0.3)
        put(canvas, self.img, self.cx, self.cy - self.slide * (1 - p), alpha=alpha)


# --------------------------------------------------------------------------- safe area
def drawn_box(element, t: float, size: tuple[int, int]) -> tuple[int, int, int, int] | None:
    """Where the element's solid pixels are at time t (shadows and soft edges left out)."""
    from vlogkit.graphics.render import compose_frame

    a = compose_frame([element], t, size).getchannel("A")
    return a.point(lambda v: 255 if v > 96 else 0).getbbox()


def _overlap(a, b) -> int:
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def safe_notes(elements: Sequence, size: tuple[int, int]) -> list[tuple[bool | None, str]]:
    """Text elements drawn where the platform covers the picture: (fix?, note). More than 10 %
    of the text inside a zone is a fix; a sliver is information."""
    from vlogkit.export.resolve import time_window

    zones = unsafe_zones(size)
    out = []
    for e in elements:
        text = " ".join(str(getattr(e, "text", "") or "").replace("[", "").replace("]", "").split())
        w = time_window(e)
        if not text or w is None:
            continue
        t = w[0] + 0.6 * (w[1] - w[0])  # past the pop-in, before the fade
        box = drawn_box(e, t, size)
        if not box:
            continue
        area = (box[2] - box[0]) * (box[3] - box[1])
        name, worst = max(((n, _overlap(box, z)) for n, z in zones), key=lambda x: x[1])
        share = worst / area if area else 0
        if share > 0.01:
            out.append(
                (
                    False if share > 0.1 else None,
                    f'{w[0]:.1f} sn "{text[:40]}": %{share * 100:.0f}\'i {name} bölgesinde '
                    "(platform arayüzünün altında kalır)",
                )
            )
    return out


# --------------------------------------------------------------------------- gallery
def gallery(
    out: Path,
    background: Image.Image | None = None,
    text: str = "Göle [5 saat] kaldı",
    layout: Layout = VERTICAL,
    zones: bool = True,
) -> Path:
    """Every style on the same frame, side by side, labelled; unsafe zones tinted red."""
    from vlogkit.graphics.render import compose_frame

    w, h = layout.size
    tile_w = 360 if h > w else 640
    tile_h = round(tile_w * h / w)
    names = list(STYLES)
    sheet = Image.new("RGB", (tile_w * len(names), tile_h + 54), (18, 20, 23))
    d = ImageDraw.Draw(sheet)
    bg = (background or Image.new("RGB", (w, h), (92, 104, 116))).convert("RGBA").resize((w, h))
    for i, name in enumerate(names):
        el = styled(name, text, 0.0, 2.0, layout)
        frame = bg.copy()
        if zones:
            tint = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            td = ImageDraw.Draw(tint)
            for _, z in unsafe_zones((w, h)):
                td.rectangle(z, fill=(255, 60, 60, 60))
            frame.alpha_composite(tint)
        frame.alpha_composite(compose_frame([el], 1.9, (w, h)))  # every karaoke word is up
        sheet.paste(frame.convert("RGB").resize((tile_w, tile_h), Image.LANCZOS), (i * tile_w, 54))
        d.text((i * tile_w + 10, 6), name, font=font("ExtraBold", 20), fill=(255, 207, 64))
        d.text(
            (i * tile_w + 10, 31),
            STYLES[name][0][:58],
            font=font("SemiBold", 12),
            fill=(210, 210, 210),
        )
    sheet = sheet.filter(ImageFilter.SHARPEN) if tile_w < 400 else sheet
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out, quality=90)
    return out
