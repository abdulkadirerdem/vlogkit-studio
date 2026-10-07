"""On-screen text with Apple's Vision framework (macOS, no model download).

A tiny Swift helper (tools/ocr/ocr.swift) is compiled on first use into build/bin/vlogkit-ocr.
Uses: skip frames with burned-in captions when picking montage moments or thumbnails, and read a
promise that is written on screen (hook check) without the project's caption list.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from vlogkit.config import BUILD_DIR, REPO_ROOT
from vlogkit.ff import PathLike, ffmpeg

SOURCE = REPO_ROOT / "tools" / "ocr" / "ocr.swift"
BINARY = BUILD_DIR / "bin" / "vlogkit-ocr"


@dataclass(frozen=True)
class Text:
    text: str
    conf: float
    box: tuple[float, float, float, float]  # x, y, w, h (0-1, top-left origin)

    @property
    def height(self) -> float:
        return self.box[3]


def available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("swiftc")) and SOURCE.exists()


def ensure_built() -> Path:
    """Compile the helper when missing or when its source changed."""
    digest = hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:12]
    stamp = BINARY.with_suffix(".sha")
    if BINARY.exists() and stamp.exists() and stamp.read_text() == digest:
        return BINARY
    if not available():
        raise RuntimeError("OCR için macOS ve Xcode komut satırı araçları (swiftc) gerekli")
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["swiftc", "-O", str(SOURCE), "-o", str(BINARY)], check=True, capture_output=True
    )
    stamp.write_text(digest)
    return BINARY


def read(images: list[Path], accurate: bool = False) -> dict[str, list[Text]]:
    out: dict[str, list[Text]] = {}
    if not images:
        return out
    cmd = [str(ensure_built()), *(["--accurate"] if accurate else [])]
    for i in range(0, len(images), 200):  # keep the argument list short
        r = subprocess.run(
            [*cmd, *map(str, images[i : i + 200])], capture_output=True, text=True, check=True
        )
        for line in r.stdout.splitlines():
            d = json.loads(line)
            out[d["file"]] = [Text(t["text"], t["conf"], tuple(t["box"])) for t in d["texts"]]
    return out


def is_caption(texts: list[Text], min_height: float = 0.02, min_chars: int = 2) -> bool:
    """Readable text of a size that means an overlay (not a tiny logo in the scenery)."""
    return any(len(t.text.strip()) >= min_chars and t.height >= min_height for t in texts)


def _same(a: Text, b: Text, tol: float = 0.025) -> bool:
    ka = "".join(ch for ch in a.text.lower() if ch.isalnum())
    kb = "".join(ch for ch in b.text.lower() if ch.isalnum())
    if not ka or not kb or not (ka in kb or kb in ka):
        return False
    ca = (a.box[0] + a.box[2] / 2, a.box[1] + a.box[3] / 2)
    cb = (b.box[0] + b.box[2] / 2, b.box[1] + b.box[3] / 2)
    return abs(ca[0] - cb[0]) < tol and abs(ca[1] - cb[1]) < tol


def overlay_flags(
    frames: list[list[Text]], min_height: float = 0.012, big: float = 0.03
) -> list[bool]:
    """Burned-in captions in frames sampled ~0.5 s apart.

    Two signs: big text (>= 3 % of the frame height is almost always an overlay), or the same text
    at the same spot in a neighbouring sample. Overlay text stays put while a handheld camera
    moves; text in the scenery (a banner, a logo) moves with the picture.
    """
    hit = []
    for i, texts in enumerate(frames):
        near = [u for j in (i - 1, i + 1) if 0 <= j < len(frames) for u in frames[j]]
        hit.append(
            any(
                len(t.text.strip()) >= 2
                and (t.height >= big or (t.height >= min_height and any(_same(t, u) for u in near)))
                for t in texts
            )
        )
    # captions fade in and out and OCR misses some samples: widen each hit by one sample
    return [any(hit[max(0, i - 1) : i + 2]) for i in range(len(hit))]


def text_timeline(
    path: PathLike, fps: float = 2.0, start: float = 0.0, duration: float | None = None
) -> list[tuple[float, list[Text]]]:
    """(time, texts) sampled at `fps`."""
    with tempfile.TemporaryDirectory() as tmp:
        cut = (["-ss", f"{start:.3f}"] if start else []) + (
            ["-t", f"{duration}"] if duration else []
        )
        ffmpeg(
            [
                "-y",
                *cut,
                "-i",
                path,
                "-an",
                "-vf",
                f"fps={fps},scale=480:-2",
                Path(tmp) / "f%05d.png",
            ]
        )
        frames = sorted(Path(tmp).glob("f*.png"))
        found = read(frames)
        return [(start + (i + 0.5) / fps, found.get(str(f), [])) for i, f in enumerate(frames)]
