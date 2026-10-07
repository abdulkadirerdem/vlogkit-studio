"""Third-party media library: assets/manifest.toml (in git) -> assets/library/ (fetched, ignored).

Why not commit the files: the Pixabay license forbids redistributing files "on a standalone basis"
(a public repo would do exactly that), and binaries bloat git history. The manifest keeps the
source, license and author of everything we use, so every Short stays auditable.
"""

from __future__ import annotations

import tomllib
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path

from vlogkit.config import LIBRARY_DIR, MANIFEST, MANIFEST_LOCAL

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) vlogkit/0.1"


@dataclass(frozen=True)
class Asset:
    id: str
    kind: str  # sfx | stock | music
    file: str  # path inside the library dir
    url: str  # direct download
    page: str  # human page (license proof)
    license: str
    author: str
    attribution: bool
    description: str = ""
    note: str = ""
    checked: str = ""  # date its page showed no Content ID registration (music from Pixabay)

    @property
    def path(self) -> Path:
        return LIBRARY_DIR / self.file


@cache
def manifest() -> dict[str, Asset]:
    """The shipped manifest plus `manifest.local.toml` (media this install added; an installed
    copy keeps it out of git so updates never touch it; the same id there wins)."""
    out = {}
    for path in (MANIFEST, MANIFEST_LOCAL):
        if path.exists():
            out |= {a["id"]: Asset(**a) for a in tomllib.loads(path.read_text()).get("asset", [])}
    return out


_used: set[str] | None = None  # ids resolved while `recording()` is on


@contextmanager
def recording() -> Iterator[set[str]]:
    """Collect the ids `path()` resolves meanwhile (a build step: which library files it used)."""
    global _used
    outer, _used = _used, set()
    try:
        yield _used
    finally:
        inner = _used
        _used = outer
        if outer is not None:  # a nested recording also counts for the outer one
            outer |= inner


def path(asset_id: str) -> Path:
    """Local path of an asset; raises with a hint if it has not been fetched yet."""
    a = manifest()[asset_id]
    if _used is not None:
        _used.add(asset_id)
    if not a.path.exists():
        raise FileNotFoundError(f"{a.file} yok. Önce: vlogkit assets fetch {asset_id}")
    return a.path


def fetch(ids: list[str] | None = None, force: bool = False) -> list[tuple[str, str]]:
    from vlogkit.ff import probe  # local import: keep `vlogkit assets list` ffmpeg-free

    results = []
    for a in manifest().values():
        if ids and a.id not in ids:
            continue
        if a.path.exists() and not force:
            results.append((a.id, "var"))
            continue
        a.path.parent.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(a.url, headers={"User-Agent": _UA})
        tmp = a.path.with_suffix(a.path.suffix + ".part")
        with urllib.request.urlopen(req, timeout=60) as r:
            tmp.write_bytes(r.read())
        try:
            probe(tmp)  # rejects HTML error pages saved as .mp3/.mp4
        except Exception:
            tmp.unlink(missing_ok=True)
            results.append((a.id, "HATA: geçerli medya değil"))
            continue
        tmp.rename(a.path)
        results.append((a.id, "indirildi"))
    return results
