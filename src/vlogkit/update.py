"""Updates for an installed copy: the public release repo, one tag per version.

install.sh clones the release repo; its root holds `.release` (written by scripts/release.py), so
the copy knows it is an installed one and where its updates come from. A developer checkout has no
`.release` and never updates itself.

The studio asks the repo for its version tags now and then (`git ls-remote`, anonymous https),
shows "Güncelleme var" when a newer one exists, with that version's notes from CHANGELOG.md, and
on a click moves the clone to the tag, syncs the environment, fetches new library media and
restarts itself. The user's projects, builds, library and settings are untracked (ignored by the
release repo's .gitignore), so an update never touches them. Tracked files changed by hand (or by
an agent that should not have) are stashed first, never lost.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

from vlogkit import __version__
from vlogkit.config import BUILD_DIR, REPO_ROOT

RELEASE_FILE = REPO_ROOT / ".release"
STATE = BUILD_DIR / "ui" / "update.json"
CHECK_EVERY = 3600.0  # an open studio sees a new version within the hour
_VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


REFRESH_SHORTCUT = (
    "from vlogkit.ui.launcher import APP_NAME, DESKTOP, create_shortcut\n"
    "if (DESKTOP / f'{APP_NAME}.app').exists(): create_shortcut(DESKTOP)"
)


class UpdateError(RuntimeError):
    pass


def channel() -> dict | None:
    """{"repo": url, "version": ...} for an installed copy, None for a developer checkout."""
    try:
        data = json.loads(RELEASE_FILE.read_text())
        return data if data.get("repo") else None
    except (OSError, ValueError):
        return None


def parse(version: str) -> tuple[int, int, int] | None:
    m = _VERSION.match(version.strip())
    return tuple(int(x) for x in m.groups()) if m else None  # type: ignore[return-value]


def newest(tags: list[str]) -> str | None:
    found = [(v, t.lstrip("v")) for t in tags if (v := parse(t))]
    return max(found)[1] if found else None


GIT_ENV = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}  # never wait for a password prompt


def _git(*args: str, timeout: float = 60) -> str:
    r = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        env=GIT_ENV,
    )
    if r.returncode != 0:
        raise UpdateError(
            (r.stderr or r.stdout).strip().splitlines()[-1] if (r.stderr or r.stdout) else "git"
        )
    return r.stdout


def has_git() -> bool:
    """Apple's developer tools are installed. Without them /usr/bin/git is only a stub that pops
    up an install dialog, so it is never called before this says yes."""
    try:
        return subprocess.run(["xcode-select", "-p"], capture_output=True).returncode == 0
    except OSError:
        return False


def remote_tags(repo: str) -> list[str]:
    if has_git():
        out = subprocess.run(
            ["git", "ls-remote", "--tags", "--refs", repo],
            capture_output=True,
            text=True,
            timeout=30,
            env=GIT_ENV,
        )
        if out.returncode != 0:
            raise UpdateError("güncelleme sunucusuna ulaşılamadı")
        return [
            ln.rsplit("refs/tags/", 1)[-1] for ln in out.stdout.splitlines() if "refs/tags/" in ln
        ]
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo)
    if not m:
        raise UpdateError("güncellemeyi görmek için Apple geliştirici araçları gerekli")
    try:  # no git yet (installed before the developer tools): GitHub's public API
        with urllib.request.urlopen(
            f"https://api.github.com/repos/{m.group(1)}/tags", timeout=20
        ) as r:
            return [t["name"] for t in json.load(r)]
    except (OSError, ValueError, KeyError) as e:
        raise UpdateError("güncelleme sunucusuna ulaşılamadı") from e


def adopt() -> bool:
    """A copy unpacked from a tarball (install.sh ran before the developer tools were there)
    becomes a git clone of its own version once git works, so updates can move it. The files are
    not touched: the index is set to the tag the copy was made from. True when it is a clone."""
    ch = channel()
    if (REPO_ROOT / ".git").exists():
        return True
    if not ch or not has_git():
        return False
    _git("init", "--quiet", "-b", "main")
    _git("remote", "add", "origin", ch["repo"])
    _git("fetch", "--quiet", "--tags", "origin", timeout=300)
    _git("reset", "--quiet", f"v{ch.get('version') or __version__}")
    return True


def notes(changelog: str, current: str, target: str) -> str:
    """The CHANGELOG sections newer than `current` up to `target` (what the update brings)."""
    lo, hi = parse(current) or (0, 0, 0), parse(target) or (0, 0, 0)
    keep, out = False, []
    for line in changelog.splitlines():
        m = re.match(r"^## \[(\d+\.\d+\.\d+)\]", line)
        if m:
            v = parse(m.group(1)) or (0, 0, 0)
            keep = lo < v <= hi
        if keep:
            out.append(line)
    return "\n".join(out).strip()


def _changelog(repo: str, version: str) -> str:
    """CHANGELOG.md of a tag: from git, or from GitHub before git is installed."""
    if (REPO_ROOT / ".git").exists():
        _git("fetch", "--quiet", "--tags", "origin", timeout=120)
        return _git("show", f"v{version}:CHANGELOG.md")
    m = re.match(r"https://github\.com/([^/]+/[^/]+?)(?:\.git)?$", repo)
    if not m:
        raise UpdateError("notlar okunamadı")
    url = f"https://raw.githubusercontent.com/{m.group(1)}/v{version}/CHANGELOG.md"
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.read().decode("utf-8")


def check(force: bool = False) -> dict:
    """{"channel", "current", "latest", "available", "notes", "checked"}; cached for hours."""
    ch = channel()
    base = {"channel": bool(ch), "current": __version__, "latest": None, "available": False}
    if not ch:
        return base
    try:
        cached = json.loads(STATE.read_text())
    except (OSError, ValueError):
        cached = {}
    fresh = time.time() - cached.get("checked", 0) < CHECK_EVERY
    if not force and fresh and cached.get("current") == __version__:
        return {**base, **cached}
    try:
        latest = newest(remote_tags(ch["repo"]))
    except (UpdateError, OSError, subprocess.TimeoutExpired) as e:
        return {**base, "error": str(e)}
    info = {"latest": latest, "checked": time.time(), "current": __version__, "notes": ""}
    info["available"] = bool(latest and (parse(latest) or ()) > (parse(__version__) or ()))
    if info["available"]:
        with contextlib.suppress(UpdateError, subprocess.TimeoutExpired, OSError, ValueError):
            info["notes"] = notes(_changelog(ch["repo"], latest), __version__, latest)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(info))
    return {**base, **info}


def _uv() -> str:
    uv = shutil.which("uv") or next(
        (p for p in ("/opt/homebrew/bin/uv", str(Path.home() / ".local/bin/uv")) if Path(p).exists()),
        None,
    )  # fmt: skip
    if not uv:
        raise UpdateError("uv bulunamadı")
    return uv


def apply(version: str, log=print) -> str:
    """Move the installed copy to v<version>. Returns a short summary; raises UpdateError and then
    leaves the copy as it was (same commit, environment synced back, hand edits restored)."""
    ch = channel()
    if not ch:
        raise UpdateError("geliştirici kopyası kendini güncellemez (git kullan)")
    if not parse(version):
        raise UpdateError(f"sürüm: {version}")
    tag = f"v{version.lstrip('v')}"
    if not adopt():
        raise UpdateError("güncelleme için önce Kurulum'daki ilk adımı (Homebrew) tamamla")
    log("Sürüm indiriliyor…")
    _git("fetch", "--quiet", "--tags", "origin", timeout=300)
    old = _git("rev-parse", "HEAD").strip()
    notes = []
    if _git("rev-list", "HEAD", "--not", tag).strip():  # commits made here (by hand or an agent)
        backup = f"yedek-{time.strftime('%Y%m%d-%H%M%S')}"
        _git("branch", backup, old)
        notes.append(f"Bu kopyadaki commit'ler `{backup}` dalında.")
    stashed = bool(_git("status", "--porcelain", "--untracked-files=no").strip())
    if stashed:
        _git("stash", "push", "--quiet", "-m", f"vlogkit {__version__} -> {version} öncesi")
        notes.append("Elle değişmiş dosyalar `git stash` içinde saklandı.")
    try:
        _git("checkout", "--quiet", "-B", "main", tag)
        log("Ortam güncelleniyor…")
        # --frozen: exactly the release's lock, and the lock file stays as shipped (a rewritten
        # uv.lock would count as a hand edit at the next update)
        r = subprocess.run(
            [_uv(), "sync", "--frozen", "--quiet"], cwd=REPO_ROOT, capture_output=True, text=True
        )
        if r.returncode != 0:
            raise UpdateError("uv sync: " + (r.stderr.strip().splitlines() or ["hata"])[-1])
    except (UpdateError, subprocess.TimeoutExpired) as e:
        _rollback(old, stashed)
        raise UpdateError(f"güncelleme olmadı, {__version__} yerinde kaldı: {e}") from e
    log("Yeni kütüphane dosyaları indiriliyor…")
    try:  # new music / SFX in the manifest; a failed download must not stop the update
        subprocess.run(
            [_uv(), "run", "--frozen", "vlogkit", "assets", "fetch"],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=900,
        )
    except (OSError, subprocess.TimeoutExpired):
        notes.append("Bazı kütüphane dosyaları inmedi; sonra `vlogkit assets fetch`.")
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):  # the desktop app, if it is
        subprocess.run(  # there, is made again: a new icon or launcher arrives with the update
            [_uv(), "run", "--frozen", "python", "-c", REFRESH_SHORTCUT],
            cwd=REPO_ROOT,
            capture_output=True,
            timeout=120,
        )
    STATE.unlink(missing_ok=True)
    return " ".join([f"{version} kuruldu.", *notes])


def _rollback(old: str, stashed: bool) -> None:
    """Back to the commit before the update, its environment and the hand edits."""
    with contextlib.suppress(UpdateError, subprocess.TimeoutExpired):
        _git("checkout", "--quiet", "-f", "-B", "main", old)
    with contextlib.suppress(OSError, UpdateError, subprocess.TimeoutExpired):
        subprocess.run([_uv(), "sync", "--frozen", "--quiet"], cwd=REPO_ROOT, capture_output=True)
    if stashed:
        with contextlib.suppress(UpdateError, subprocess.TimeoutExpired):
            _git("stash", "pop", "--quiet")
