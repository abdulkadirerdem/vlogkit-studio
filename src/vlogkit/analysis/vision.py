"""What is in a frame, with Apple's Vision framework (macOS, no model download).

A small Swift helper (tools/vision/vision.swift) is compiled on first use into
build/bin/vlogkit-vision. Per image: faces, human bodies, scene labels (VNClassifyImageRequest)
and, on macOS 15+, an aesthetics score. The footage log uses it to tell a real moment from camera
handling (a face filling the frame) and to give Claude words for what is on screen.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from vlogkit.config import BUILD_DIR, REPO_ROOT

SOURCE = REPO_ROOT / "tools" / "vision" / "vision.swift"
BINARY = BUILD_DIR / "bin" / "vlogkit-vision"

Box = tuple[float, float, float, float]  # x, y, w, h (0-1, top-left origin)


@dataclass
class Seen:
    faces: list[Box] = field(default_factory=list)
    humans: list[Box] = field(default_factory=list)
    labels: list[tuple[str, float]] = field(default_factory=list)
    aesthetics: float | None = None  # -1..1 (macOS 15+)
    utility: bool = False  # screenshot / document-like picture

    @property
    def face_height(self) -> float:
        return max((b[3] for b in self.faces), default=0.0)

    def to_json(self) -> dict:
        return {
            "faces": [list(b) for b in self.faces],
            "humans": [list(b) for b in self.humans],
            "labels": [list(x) for x in self.labels],
            "aesthetics": self.aesthetics,
            "utility": self.utility,
        }

    @staticmethod
    def from_json(d: dict) -> Seen:
        return Seen(
            [tuple(b) for b in d.get("faces", [])],
            [tuple(b) for b in d.get("humans", [])],
            [(str(a), float(b)) for a, b in d.get("labels", [])],
            d.get("aesthetics"),
            bool(d.get("utility", False)),
        )


def available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("swiftc")) and SOURCE.exists()


def ensure_built() -> Path:
    """Compile the helper when missing or when its source changed."""
    digest = hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:12]
    stamp = BINARY.with_suffix(".sha")
    if BINARY.exists() and stamp.exists() and stamp.read_text() == digest:
        return BINARY
    if not available():
        raise RuntimeError("Vision için macOS ve Xcode komut satırı araçları (swiftc) gerekli")
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["swiftc", "-O", "-parse-as-library", str(SOURCE), "-o", str(BINARY)],
        check=True,
        capture_output=True,
    )
    stamp.write_text(digest)
    return BINARY


def _parse(d: dict) -> Seen:
    return Seen(
        [tuple(f["box"]) for f in d.get("faces", [])],
        [tuple(h["box"]) for h in d.get("humans", [])],
        [(x["id"], float(x["conf"])) for x in d.get("labels", [])],
        (d.get("aesthetics") or {}).get("overall"),
        bool((d.get("aesthetics") or {}).get("utility", False)),
    )


def read(images: list[Path], aesthetics: bool = True) -> dict[str, Seen]:
    """{image path: Seen}. Images missing from the output (unreadable) are absent."""
    out: dict[str, Seen] = {}
    if not images:
        return out
    cmd = [str(ensure_built()), *([] if aesthetics else ["--no-aesthetics"])]
    for i in range(0, len(images), 200):  # keep the argument list short
        r = subprocess.run(
            [*cmd, *map(str, images[i : i + 200])], capture_output=True, text=True, check=True
        )
        for line in r.stdout.splitlines():
            d = json.loads(line)
            if "error" not in d:
                out[d["file"]] = _parse(d)
    return out
