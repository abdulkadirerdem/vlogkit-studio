"""Brand images for the public README: the app icon and the logo (icon + wordmark).

    uv run python scripts/brand.py   ->  assets/brand/icon.png, assets/brand/logo.png

Made from the shipped Montserrat font and the studio's colours (the desktop app's icon, the
sidebar wordmark), so the README looks like the app. Transparent background: it reads on GitHub's
light and dark themes alike.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vlogkit.config import FONTS_DIR, REPO_ROOT
from vlogkit.ui.launcher import _icon_png

OUT = REPO_ROOT / "assets" / "brand"
YELLOW, INK = (255, 207, 64, 255), (27, 29, 31, 255)


def logo(height: int = 200) -> Image.Image:
    with tempfile.TemporaryDirectory() as tmp:
        _icon_png(Path(tmp) / "icon.png", 1024)
        icon = Image.open(Path(tmp) / "icon.png").convert("RGBA").resize((height, height))
    font = ImageFont.truetype(str(FONTS_DIR / "Montserrat-Black.ttf"), int(height * 0.62))
    stroke = max(2, height // 22)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    x0, t, r, b = probe.textbbox((0, 0), "vlogkit", font=font, stroke_width=stroke)
    gap = height // 6
    im = Image.new("RGBA", (height + gap + (r - x0), height), (0, 0, 0, 0))
    im.alpha_composite(icon, (0, 0))
    d = ImageDraw.Draw(im)
    y = (height - (b - t)) // 2 - t
    d.text((height + gap - x0, y), "vlogkit", font=font, fill=YELLOW, stroke_width=stroke,
           stroke_fill=INK)  # fmt: skip
    return im


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _icon_png(OUT / "icon.png", 512)
    logo().save(OUT / "logo.png", optimize=True)
    for p in sorted(OUT.glob("*.png")):
        print(p, Image.open(p).size)


if __name__ == "__main__":
    main()
