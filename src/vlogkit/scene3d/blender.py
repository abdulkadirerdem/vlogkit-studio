"""Finding Blender and running the kit headless, on macOS and Windows.

Where Blender is looked for (first hit wins): VLOGKIT_BLENDER, then the usual install places
(macOS: /Applications and ~/Applications Blender.app, Homebrew's cask; Windows: Program Files
"Blender Foundation", winget's and the Microsoft Store's places), then PATH.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable
from functools import cache
from pathlib import Path

MIN_VERSION = (4, 2)  # EEVEE Next and layered actions; 5.x preferred
RUNNER = Path(__file__).with_name("bpy_kit") / "runner.py"
WINGET_ID = "BlenderFoundation.Blender"
BREW_CASK = "blender"


def _candidates() -> list[Path]:
    home = Path.home()
    system = platform.system()
    out: list[Path] = []
    if system == "Darwin":
        for base in (Path("/Applications"), home / "Applications"):
            out += sorted(base.glob("Blender*.app/Contents/MacOS/Blender"), reverse=True)
    elif system == "Windows":
        roots = [
            Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")),
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")),
            Path(os.environ.get("LOCALAPPDATA", str(home / "AppData" / "Local"))) / "Programs",
        ]
        for r in roots:
            out += sorted(
                (r / "Blender Foundation").glob("Blender*/blender.exe"),
                key=_version_key,
                reverse=True,
            )
        steam = (
            Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
            / "Steam"
            / "steamapps"
            / "common"
            / "Blender"
            / "blender.exe"
        )
        out.append(steam)
    else:
        out += [Path("/usr/bin/blender"), Path("/snap/bin/blender")]
    return out


def _version_key(p: Path) -> tuple:
    m = re.search(r"(\d+)\.(\d+)", str(p.parent.name))
    return (int(m.group(1)), int(m.group(2))) if m else (0, 0)


@cache
def find() -> str | None:
    env = os.environ.get("VLOGKIT_BLENDER")
    if env:
        return env if Path(env).exists() else None
    for p in _candidates():
        if p.exists():
            return str(p)
    return shutil.which("blender")


@cache
def version(exe: str | None = None) -> tuple[int, int, int] | None:
    exe = exe or find()
    if not exe:
        return None
    try:
        r = subprocess.run(
            [exe, "-b", "--factory-startup", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"Blender (\d+)\.(\d+)(?:\.(\d+))?", r.stdout)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else None


def status() -> dict:
    exe = find()
    v = version(exe) if exe else None
    ok = bool(v and v[:2] >= MIN_VERSION)
    return {
        "path": exe,
        "version": ".".join(map(str, v)) if v else None,
        "ok": ok,
        "why": None
        if ok
        else (
            "kurulu değil"
            if not exe
            else f"en az Blender {MIN_VERSION[0]}.{MIN_VERSION[1]} gerekli"
        ),
    }


def install_command() -> list[str] | None:
    """The package manager command that installs Blender here, or None (download by hand)."""
    system = platform.system()
    if system == "Darwin":
        brew = shutil.which("brew") or next(
            (p for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if Path(p).exists()), None
        )
        return [brew, "install", "--cask", BREW_CASK] if brew else None
    if system == "Windows":
        winget = shutil.which("winget")
        if winget:
            return [
                winget,
                "install",
                "--id",
                WINGET_ID,
                "-e",
                "--silent",
                "--accept-package-agreements",
                "--accept-source-agreements",
            ]
    return None


def run(
    plan_path: Path, on_line: Callable[[str], None] | None = None, exe: str | None = None
) -> None:
    """Render a plan with the kit. Raises with the end of Blender's output if it fails."""
    exe = exe or find()
    if not exe:
        raise RuntimeError("Blender bulunamadı: Ayarlar > Kurulum > Blender")
    cmd = [
        exe,
        "-b",
        "--factory-startup",
        "--python-exit-code",
        "1",
        "-P",
        str(RUNNER),
        "--",
        str(plan_path),
    ]
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=flags,
        env=env,
    )
    tail: list[str] = []
    assert proc.stdout
    for line in proc.stdout:
        line = line.rstrip()
        tail = [*tail, line][-40:]
        if on_line:
            on_line(line)
    if proc.wait() != 0:
        errs = [ln for ln in tail if ln and not ln.startswith(("Fra:", "VKFRAME", "VKEDGE"))]
        raise RuntimeError("Blender render başarısız:\n" + "\n".join(errs[-15:]))
