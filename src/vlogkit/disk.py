"""Disk space: what the build folder holds, freeing what a build can make again, and a check
before a build that would not fit.

A build writes big intermediates into build/<project>/<variant>/ (and `reel` into
build/reels/<name>/): base.mov is ProRes 422 HQ, ~27 GB for 4 minutes of 4K. They make a revision
fast (`build -s overlay` reuses base.mov) but they are not the delivery: the mp4 sits next to the
footage. A variant nobody touched for N days is a finished video or an old experiment: its heavy
media can go, and a later build makes them again (Edit.run adds the missing steps).

Only those work folders are cleaned, only rebuildable media in them (mov, wav, mkv, ...; never
mp4, images, json, logs), never the tool folders (log, analysis, cache, ui, timelines, bin). A file
hardlinked from somewhere else (a Resolve folder next to the video, another variant still in use)
is left alone: deleting it would free nothing.
"""

from __future__ import annotations

import os
import re
import shutil
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vlogkit.config import BUILD_DIR, PROJECTS_DIR

HEAVY = {".mov", ".mxf", ".mkv", ".avi", ".y4m", ".wav", ".aif", ".aiff", ".flac", ".m4a"}
MIN_SIZE = 1 << 20  # smaller files are not worth a rebuild
DAY = 86400.0
LOW = 30e9  # below this the studio says so after a job
RESERVE = 5e9  # a build never leaves less than this free
CLEAN_DAYS = (0, 7, 14, 30)  # studio setting: delete after N days untouched (0 = by hand)


@dataclass
class Unit:
    """One work folder: a project variant or a reel."""

    path: Path
    newest: float  # mtime of the newest file inside: when someone last built here
    heavy: list[Path] = field(default_factory=list)
    size: int = 0  # bytes of its heavy files (a hardlink inside it counted once)

    @property
    def age_days(self) -> float:
        return (time.time() - self.newest) / DAY


def free_bytes(path: Path = BUILD_DIR) -> int:
    p = Path(path)
    while not p.exists():
        p = p.parent
    return shutil.disk_usage(p).free


# build/<name> folders that belong to tools, never to a project (a project with such a name
# would otherwise expose them)
TOOL_DIRS = {"analysis", "bin", "cache", "captions", "find", "log", "matte", "music", "prompts",
             "redact", "review", "separate", "sheets", "strips", "thumbs", "timelines", "ui"}  # fmt: skip
_READS = re.compile(
    r"""BUILD_DIR\s*/\s*["']([^"']+)["']\s*/\s*["']([^"']+)["']|build/([\w.-]+)/([\w.-]+)"""
)


def borrowed(projects: Path) -> set[tuple[str, str]]:
    """(project, variant) work folders a project's code reads from: one project can reuse
    another's expensive files (a denoised voice, an upscaled pan), which only that other project
    makes again, so they stay."""
    found = set()
    for src in projects.glob("*/*.py"):
        try:
            text = src.read_text(encoding="utf-8")
        except OSError:
            continue
        for m in _READS.finditer(text):
            name, variant = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
            if name != src.parent.name:
                found.add((name, variant))
    return found


def work_dirs(build: Path, projects: Path) -> list[Path]:
    """Variant folders of real projects (a folder with edit.py) and reel work folders, minus the
    ones another project reads from."""
    names = {
        p.name
        for p in projects.iterdir()
        if (p / "edit.py").is_file() and not p.name.startswith("_") and p.name not in TOOL_DIRS
    }
    keep = borrowed(projects)
    out = []
    for top in [build / n for n in sorted(names)] + [build / "reels"]:
        if top.is_dir():
            out += sorted(
                d
                for d in top.iterdir()
                if d.is_dir() and not d.is_symlink() and (top.name, d.name) not in keep
            )
    return out


def scan(folder: Path) -> Unit:
    newest, heavy, size, seen = 0.0, [], 0, set()
    for root, dirs, files in os.walk(folder):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for name in files:
            p = Path(root, name)
            try:
                st = p.lstat()
            except OSError:
                continue
            newest = max(newest, st.st_mtime)
            if p.suffix.lower() in HEAVY and st.st_size >= MIN_SIZE and not p.is_symlink():
                heavy.append(p)
                if (st.st_dev, st.st_ino) not in seen:
                    seen.add((st.st_dev, st.st_ino))
                    size += st.st_size
    return Unit(folder, newest or folder.stat().st_mtime, heavy, size)


def scan_all(build: Path, projects: Path) -> list[Unit]:
    return [scan(d) for d in work_dirs(build, projects)]


def units() -> list[Unit]:
    return scan_all(BUILD_DIR, PROJECTS_DIR)


def plan(days: float, all_units: Sequence[Unit], now: float | None = None) -> list[Unit]:
    """Work folders untouched for `days` days that hold heavy media."""
    now = time.time() if now is None else now
    return [u for u in all_units if u.heavy and now - u.newest >= days * DAY]


def removable(chosen: Iterable[Unit]) -> tuple[list[Path], int]:
    """The files of `chosen` whose every hardlink is among them, and the bytes that frees."""
    links: dict[tuple[int, int], list[Path]] = {}
    sizes: dict[tuple[int, int], tuple[int, int]] = {}
    for u in chosen:
        for p in u.heavy:
            try:
                st = Path(p).lstat()
            except OSError:
                continue
            key = (st.st_dev, st.st_ino)
            if p not in links.setdefault(key, []):
                links[key].append(Path(p))
            sizes[key] = (st.st_size, st.st_nlink)
    files, freed = [], 0
    for key, paths in links.items():
        size, nlink = sizes[key]
        if len(paths) >= nlink:  # nothing outside keeps it alive
            files += paths
            freed += size
    return files, freed


def total(all_units: Iterable[Unit]) -> int:
    """Bytes of heavy media, a file hardlinked into several variants counted once."""
    seen, n = set(), 0
    for u in all_units:
        for p in u.heavy:
            try:
                st = Path(p).lstat()
            except OSError:
                continue
            if (st.st_dev, st.st_ino) not in seen:
                seen.add((st.st_dev, st.st_ino))
                n += st.st_size
    return n


def clean(chosen: Iterable[Unit]) -> int:
    files, freed = removable(chosen)
    for p in files:
        p.unlink(missing_ok=True)
    return freed


def gb(n: float) -> str:
    return f"{n / 1e9:.1f} GB"


# --------------------------------------------------------------------------- before a build
def prores_bytes(width: int, height: int, fps: float, seconds: float) -> float:
    """ProRes 422 HQ size: ~220 Mb/s at 1080p29.97, scaling with pixels and frame rate (Apple)."""
    rate = 220e6 * (width * height) / (1920 * 1080) * (fps / 29.97)
    return rate * seconds / 8


def build_need(width: int, height: int, fps: float, seconds: float, steps: Sequence[str]) -> float:
    """Bytes a build writes: base.mov (and a third more for parts an edit renders first),
    overlay.mov (mostly transparent ProRes 4444) and audio.wav. The caller subtracts the files
    the steps overwrite (ffmpeg truncates them, so their space comes back)."""
    base = prores_bytes(width, height, fps, seconds)
    need = 0.0
    if "base" in steps:
        need += base * 1.3
    if "overlay" in steps:
        need += base * 0.15
    if "audio" in steps:
        need += seconds * 48000 * 2 * 3 * 4  # 24-bit stereo + stems
    if "compose" in steps:
        need += seconds * 2.5e6  # the delivery mp4, generously
    return need


class NoSpace(RuntimeError):
    pass


def ensure(need: float, where: Path = BUILD_DIR) -> str | None:
    """Raise if `need` bytes do not fit (keeping RESERVE free); a warning if it is tight."""
    free = free_bytes(where)
    hint = "`uv run vlogkit disk` ile bak, `vlogkit disk --clean` eski ara dosyaları siler"
    if free - need < RESERVE:
        raise NoSpace(f"disk yetmiyor: bu derleme ~{gb(need)} yazar, boş {gb(free)}. {hint}")
    if free - need < LOW:
        return f"disk az: derlemeden sonra ~{gb(free - need)} kalacak. {hint}"
    return None
