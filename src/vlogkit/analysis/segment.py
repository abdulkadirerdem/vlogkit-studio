"""Subject / person masks with Apple's Vision framework (macOS, no model download).

A tiny Swift helper (tools/segment/segment.swift) is compiled on first use into
build/bin/vlogkit-segment. Default mode is the foreground-subject mask Photos uses for "lift
subject" (macOS 14+): full resolution, hair, fingers and a held object stay in. `person=True`
uses the person segmentation request instead (people only, lower resolution, upscaled).

Use: cut the creator out of a frame for a thumbnail (`graphics.thumbnail.cutout`).
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image

from vlogkit.config import BUILD_DIR, REPO_ROOT
from vlogkit.ff import PathLike

SOURCE = REPO_ROOT / "tools" / "segment" / "segment.swift"
BINARY = BUILD_DIR / "bin" / "vlogkit-segment"


def available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("swiftc")) and SOURCE.exists()


def ensure_built() -> Path:
    """Compile the helper when missing or when its source changed."""
    digest = hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:12]
    stamp = BINARY.with_suffix(".sha")
    if BINARY.exists() and stamp.exists() and stamp.read_text() == digest:
        return BINARY
    if not available():
        raise RuntimeError("Maske için macOS ve Xcode komut satırı araçları (swiftc) gerekli")
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["swiftc", "-O", str(SOURCE), "-o", str(BINARY)], check=True, capture_output=True
    )
    stamp.write_text(digest)
    return BINARY


def mask(
    image: PathLike, out: PathLike | None = None, person: bool = False, largest: bool = False
) -> Image.Image:
    """8-bit mask the size of `image` (255 = subject). Written to `out` if given.
    largest: only the biggest subject (the creator in front, not the friends behind)."""
    image = Path(image)
    out = Path(out) if out else image.with_name(f"{image.stem}_mask.png")
    flags = [*(["--person"] if person else []), *(["--largest"] if largest else [])]
    cmd = [str(ensure_built()), str(image), str(out), *flags]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"vlogkit-segment: {r.stderr.strip()}")
    return Image.open(out).convert("L")
