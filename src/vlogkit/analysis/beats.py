"""Beat / tempo detection with aubio (`brew install aubio`)."""

from __future__ import annotations

import subprocess

from vlogkit.config import require, tools
from vlogkit.ff import PathLike


def beats(path: PathLike) -> list[float]:
    r = subprocess.run(
        [require(tools().aubio, "aubio"), "beat", "-i", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return [float(x) for x in r.stdout.split()]


def tempo(path: PathLike) -> float | None:
    r = subprocess.run(
        [require(tools().aubio, "aubio"), "tempo", "-i", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    lines = [ln for ln in r.stdout.splitlines() if "bpm" in ln]
    return float(lines[-1].split()[0]) if lines else None
