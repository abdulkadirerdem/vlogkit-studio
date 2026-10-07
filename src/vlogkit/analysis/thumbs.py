"""Thumbnail candidates: the sharpest, most colourful, well-exposed frames of a video.

Run it on the *source* footage. Frames right at a cut (transition blur) and frames with
burned-in text (Vision OCR, macOS) are skipped. Faces are not detected; the picks are shown as a sheet so the user (or
Claude, looking at the sheet) chooses. Packaging advice: docs/viral-edit.md.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageFilter, ImageMath, ImageStat

from vlogkit.analysis.scenes import detect_cuts
from vlogkit.ff import PathLike, extract_frame, ffmpeg

_LAPLACE = ImageFilter.Kernel((3, 3), [0, 1, 0, 1, -4, 1, 0, 1, 0], scale=1, offset=128)


@dataclass(frozen=True)
class Frame:
    t: float
    sharp: float
    color: float
    exposure: float
    score: float = 0.0


def measure(im: Image.Image) -> tuple[float, float, float]:
    """(sharpness, colourfulness, exposure 0-1) of one frame."""
    gray = im.convert("L")
    sharp = ImageStat.Stat(gray.filter(_LAPLACE)).stddev[0]
    r, g, b = im.convert("RGB").split()
    rg = ImageMath.lambda_eval(lambda a: a["r"] - a["g"], r=r.convert("F"), g=g.convert("F"))
    yb = ImageMath.lambda_eval(
        lambda a: (a["r"] + a["g"]) * 0.5 - a["b"],
        r=r.convert("F"),
        g=g.convert("F"),
        b=b.convert("F"),
    )
    srg, syb = ImageStat.Stat(rg), ImageStat.Stat(yb)
    color = (srg.stddev[0] ** 2 + syb.stddev[0] ** 2) ** 0.5 + 0.3 * (
        srg.mean[0] ** 2 + syb.mean[0] ** 2
    ) ** 0.5  # Hasler & Süsstrunk colourfulness
    hist = gray.histogram()
    clipped = (sum(hist[:8]) + sum(hist[248:])) / max(1, sum(hist))
    mean = ImageStat.Stat(gray).mean[0]
    exposure = max(0.0, 1 - abs(mean - 125) / 125 - 2 * clipped)
    return sharp, color, exposure


def _rank(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    out = [0.0] * len(values)
    for r, i in enumerate(order):
        out[i] = r / max(1, len(values) - 1)
    return out


def _captioned(files: list[Path]) -> list[bool]:
    """Frames with burned-in text (Vision OCR on macOS): not thumbnail material."""
    from vlogkit.analysis import ocr

    if not ocr.available():
        return [False] * len(files)
    try:
        found = ocr.read(files)
    except Exception:
        return [False] * len(files)
    return ocr.overlay_flags([found.get(str(f), []) for f in files])


def score(path: PathLike, fps: float = 2.0, skip_near_cut: float = 0.3) -> list[Frame]:
    cuts = detect_cuts(path)
    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg(["-y", "-i", path, "-an", "-vf", f"fps={fps},scale=320:-2", Path(tmp) / "f%05d.jpg"])
        files = sorted(Path(tmp).glob("f*.jpg"))
        captioned = _captioned(files)
        raw = []
        for i, f in enumerate(files):
            t = (i + 0.5) / fps
            if captioned[i] or any(abs(t - c) < skip_near_cut for c in cuts):
                continue
            with Image.open(f) as im:
                raw.append((t, *measure(im)))
    if not raw:
        return []
    rs, rc = _rank([x[1] for x in raw]), _rank([x[2] for x in raw])
    return [
        Frame(t, s, c, e, 0.45 * rs[i] + 0.3 * rc[i] + 0.25 * e)
        for i, (t, s, c, e) in enumerate(raw)
    ]


def pick(frames: list[Frame], n: int = 3, min_gap: float = 2.0) -> list[Frame]:
    """The best `n` frames, at least `min_gap` s apart (different moments, not one moment 3x)."""
    chosen: list[Frame] = []
    for f in sorted(frames, key=lambda f: -f.score):
        if all(abs(f.t - c.t) >= min_gap for c in chosen):
            chosen.append(f)
        if len(chosen) == n:
            break
    return sorted(chosen, key=lambda f: f.t)


def extract(path: PathLike, frames: list[Frame], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    return [extract_frame(path, f.t, out_dir / f"kare_{f.t:07.2f}.png") for f in frames]
