"""Beat / tempo detection with aubio (`brew install aubio`).

aubio reads some files badly: a silent track, a screen recording's AAC track or a container it
cannot seek segfaults the CLI (exit -11). That must not take the caller down with it, so both
helpers raise `BeatsUnavailable` and `analyze` skips the beat list instead of crashing.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from vlogkit.config import require, tools
from vlogkit.ff import PathLike


class BeatsUnavailable(RuntimeError):
    """aubio could not read this file (missing tool, unreadable audio, or a crash)."""


def _aubio(mode: str, path: PathLike) -> str:
    r = subprocess.run(
        [require(tools().aubio, "aubio"), mode, "-i", str(path)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        why = f"sinyal {-r.returncode} ile çöktü" if r.returncode < 0 else f"çıkış {r.returncode}"
        detail = (r.stderr or "").strip().splitlines()
        tail = f": {detail[-1]}" if detail else ""
        raise BeatsUnavailable(
            f"aubio {mode} '{Path(path).name}' dosyasını okuyamadı ({why}){tail}"
        )
    return r.stdout


def beats(path: PathLike) -> list[float]:
    return [float(x) for x in _aubio("beat", path).split()]


def tempo(path: PathLike) -> float | None:
    lines = [ln for ln in _aubio("tempo", path).splitlines() if "bpm" in ln]
    return float(lines[-1].split()[0]) if lines else None
