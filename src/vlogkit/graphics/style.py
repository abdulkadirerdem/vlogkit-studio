"""Design tokens and layouts.

Vertical (Shorts / Reels, 1080x1920): the top ~150 px holds the search/camera icons, the bottom
~25-30% the title/channel/description, the right edge (x > ~960, y 1000-1700) the like/comment/share
buttons. Captions therefore sit at y≈1180, slightly left of centre, at most 840 px wide.

Landscape (YouTube long video, 1920x1080): keep text inside the 90% title-safe area (96 px / 54 px
inset). The player's progress bar and controls cover the bottom ~10% while hovering, so spoken-word
subtitles sit at y≈955 and chapter cards in the top-left corner. `LANDSCAPE_4K` is the same layout
on a 3840x2160 canvas (`Layout.scaled`): elements that take a layout scale their default sizes.

The module-level constants (W, H, CAP_X, ...) are the vertical layout, kept for existing projects.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vlogkit.config import FONTS_DIR


@dataclass(frozen=True)
class Layout:
    """Canvas size + where each kind of text goes."""

    name: str
    w: int
    h: int
    cap_x: float  # pop caption centre
    cap_y: float
    max_w: int  # widest a caption / subtitle may get
    sub_y: float  # spoken-word subtitle centre
    top_y: float  # big numbers / meme "top text"
    tag_y: float  # small letter-spaced tags
    margin: int  # title-safe inset (chapter cards)
    scale: float = 1.0  # default text sizes of the elements are multiplied by this

    @property
    def size(self) -> tuple[int, int]:
        return (self.w, self.h)

    @property
    def landscape(self) -> bool:
        return self.w > self.h

    def scaled(self, k: float, name: str | None = None) -> Layout:
        """The same design on a k-times bigger canvas (e.g. 4K): every position, width and default
        text size grows by k, so the graphics look like the 1080p ones, drawn at full resolution."""
        return Layout(
            name or f"{self.name}-x{k:g}",
            round(self.w * k),
            round(self.h * k),
            cap_x=self.cap_x * k,
            cap_y=self.cap_y * k,
            max_w=round(self.max_w * k),
            sub_y=self.sub_y * k,
            top_y=self.top_y * k,
            tag_y=self.tag_y * k,
            margin=round(self.margin * k),
            scale=self.scale * k,
        )


VERTICAL = Layout(
    "vertical",
    1080,
    1920,
    cap_x=525,
    cap_y=1180,
    max_w=840,
    sub_y=1180,
    top_y=330,
    tag_y=250,
    margin=60,
)
LANDSCAPE = Layout(
    "landscape",
    1920,
    1080,
    cap_x=960,
    cap_y=790,
    max_w=1600,
    sub_y=955,
    top_y=200,
    tag_y=150,
    margin=96,
)
# 4K UHD long video (3840x2160): keep a 4K source at 4K, graphics drawn natively (not upscaled).
LANDSCAPE_4K = LANDSCAPE.scaled(2, "landscape-4k")

W, H = VERTICAL.w, VERTICAL.h

WHITE = (255, 255, 255, 255)
ACCENT = (255, 207, 64, 255)  # warm yellow, marks [highlighted] words
BLACK = (0, 0, 0, 255)

CAP_X = VERTICAL.cap_x  # caption centre x (nudged left of the action buttons)
CAP_Y = VERTICAL.cap_y  # caption centre y
TOP_Y = VERTICAL.top_y  # big numbers / "top text" of meme cut-aways
TAG_Y = VERTICAL.tag_y  # small letter-spaced tags
MAX_W = VERTICAL.max_w  # widest a caption may get

CAPTION_SIZE = 84  # Montserrat ExtraBold px
EMOJI_FONT = "/System/Library/Fonts/Apple Color Emoji.ttc"  # macOS; renders at 160 px only
_EMOJI_CHARS = "⏪⏱▶⭐"  # below U+1F000 but missing from Montserrat -> draw as emoji
_EMOJI_RANGES = ((0x2600, 0x27BF),)  # misc symbols + dingbats: ☀ ☕ ⛰ ✅ ✈ ✨ ...

# Montserrat has no Chinese/Japanese glyphs. Hiragino Sans GB (macOS) covers simplified Chinese;
# index 2 = W6 (bold), 0 = W3. STHeiti is the fallback on older systems.
CJK_FONTS = (
    ("/System/Library/Fonts/Hiragino Sans GB.ttc", {"bold": 2, "regular": 0}),
    ("/System/Library/Fonts/STHeiti Medium.ttc", {"bold": 0, "regular": 0}),
)
_CJK_RANGES = (
    (0x3000, 0x303F),  # CJK punctuation
    (0x3040, 0x30FF),  # kana
    (0x3400, 0x4DBF),  # ext. A
    (0x4E00, 0x9FFF),  # unified ideographs
    (0xF900, 0xFAFF),  # compatibility ideographs
    (0xFF00, 0xFFEF),  # full-width forms (，！？)
)


@cache
def font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """Montserrat-<weight>.ttf from assets/fonts (ExtraBold, Black, BlackItalic, SemiBold...)."""
    return ImageFont.truetype(str(FONTS_DIR / f"Montserrat-{weight}.ttf"), size)


@cache
def cjk_font(weight: str, size: int) -> ImageFont.FreeTypeFont:
    """The CJK counterpart of a Montserrat weight (SemiBold -> regular, everything else bold)."""
    kind = "regular" if weight in ("SemiBold", "Regular", "Medium") else "bold"
    for path, index in CJK_FONTS:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=index[kind])
    raise RuntimeError("CJK fontu bulunamadı (Hiragino Sans GB / STHeiti)")


@cache
def emoji_img(ch: str) -> Image.Image:
    f = ImageFont.truetype(EMOJI_FONT, 160)
    im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
    ImageDraw.Draw(im).text((0, 0), ch, font=f, embedded_color=True)
    box = im.getbbox()  # None: the emoji font has no glyph for ch
    return im.crop(box) if box else im


def is_emoji(ch: str) -> bool:
    o = ord(ch)
    return o >= 0x1F000 or ch in _EMOJI_CHARS or any(a <= o <= b for a, b in _EMOJI_RANGES)


def is_cjk(ch: str) -> bool:
    o = ord(ch)
    return any(a <= o <= b for a, b in _CJK_RANGES)


def tr_upper(text: str) -> str:
    """Upper case the Turkish way (i -> İ, ı -> I); str.upper() writes 'I' for 'i'."""
    return text.replace("i", "İ").replace("ı", "I").upper()


def unsafe_zones(size: tuple[int, int]) -> list[tuple[str, tuple[int, int, int, int]]]:
    """Where the platform draws over the picture, as (name, (x0, y0, x1, y1)) boxes.

    Vertical (YouTube Shorts and Instagram Reels, the stricter of the two): the top icons, the
    title / channel / description block at the bottom ~25 %, the like/comment/share column at the
    right. Landscape: outside the 90 % title-safe area."""
    w, h = size
    if h > w:
        k = w / 1080
        return [
            ("üst simgeler", (0, 0, w, round(180 * k))),
            ("alttaki başlık ve kanal adı", (0, round(1440 * k), w, h)),
            ("sağdaki butonlar", (round(960 * k), round(1000 * k), w, round(1700 * k))),
        ]
    k = w / 1920
    mx, my = round(96 * k), round(54 * k)
    return [
        ("üst kenar", (0, 0, w, my)),
        ("alt kenar", (0, h - my, w, h)),
        ("sol kenar", (0, 0, mx, h)),
        ("sağ kenar", (w - mx, 0, w, h)),
    ]
