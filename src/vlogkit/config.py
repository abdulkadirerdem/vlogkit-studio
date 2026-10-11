"""Tool locations and shared paths.

Every path can be overridden with an environment variable, so the same code works on another
machine or with a different folder layout:

    VLOGKIT_VLOGS_ROOT   folder that holds the raw footage folders (default: repo's parent, ~/yt-vlogs)
    VLOGKIT_BUILD        intermediates / work dirs (default: <repo>/build)
    VLOGKIT_LIBRARY      fetched third-party media (default: <repo>/assets/library)
    VLOGKIT_FFMPEG, VLOGKIT_FFPROBE, VLOGKIT_WHISPER_CLI, VLOGKIT_WHISPER_MODEL, VLOGKIT_AUBIO,
    VLOGKIT_CLAUDE, VLOGKIT_CODEX (agent CLIs used by `vlogkit ui`)
"""

from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from functools import cache
from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]  # src/vlogkit -> repo root (editable install)


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else default


ASSETS_DIR = REPO_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MANIFEST = ASSETS_DIR / "manifest.toml"
MANIFEST_LOCAL = ASSETS_DIR / "manifest.local.toml"  # media an installed copy added itself
RELEASE = (REPO_ROOT / ".release").exists()  # an installed copy (release repo), not a checkout
PROJECTS_DIR = REPO_ROOT / "projects"
LIBRARY_DIR = _env_path("VLOGKIT_LIBRARY", ASSETS_DIR / "library")
BUILD_DIR = _env_path("VLOGKIT_BUILD", REPO_ROOT / "build")
VLOGS_ROOT = _env_path("VLOGKIT_VLOGS_ROOT", REPO_ROOT.parent)

# Homebrew's plain `ffmpeg` formula lacks libass/drawtext/whisper -> prefer `ffmpeg-full` (keg-only:
# not on PATH; Apple Silicon and Intel prefixes).
_FFMPEG_FULL_BINS = (
    Path("/opt/homebrew/opt/ffmpeg-full/bin"),
    Path("/usr/local/opt/ffmpeg-full/bin"),
)
FFMPEG_FILTERS = ("drawtext", "scdet", "loudnorm")  # what plain ffmpeg lacks
WHISPER_MODEL_NAME = "ggml-large-v3-turbo.bin"
# where the setup screen downloads the speech model (`tools().whisper_model` may be a copy elsewhere)
WHISPER_MODEL_HOME = Path.home() / ".cache" / "whisper-cpp" / WHISPER_MODEL_NAME
_CLAUDE_HOME_BIN = Path.home() / ".local" / "bin"  # native installer puts `claude` here
# The desktop shortcut runs with a minimal PATH: also look where npm-via-mise and the ChatGPT app
# install Codex.
_CODEX_FALLBACKS = (
    Path.home() / ".local" / "share" / "mise" / "shims" / "codex",
    Path("/Applications/ChatGPT.app/Contents/Resources/codex"),
)


def _tool(env: str, name: str, preferred: tuple[Path, ...] = ()) -> str | None:
    if os.environ.get(env):
        return os.environ[env]
    for d in preferred:
        if (d / name).exists():
            return str(d / name)
    return shutil.which(name)


def hf_hub() -> Path:
    """Hugging Face's download cache (HF_HUB_CACHE, HF_HOME/hub or ~/.cache/huggingface/hub)."""
    home = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    if home:
        p = Path(home)
        return p if p.name == "hub" or os.environ.get("HF_HUB_CACHE") else p / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def _whisper_model() -> Path:
    """Ours, or a copy this Mac already has: a Hugging Face download of whisper.cpp's models (the
    same file setup fetches). A partial download never has the final name."""
    if WHISPER_MODEL_HOME.exists():
        return WHISPER_MODEL_HOME
    snaps = hf_hub() / "models--ggerganov--whisper.cpp" / "snapshots"
    found = [p for p in sorted(snaps.glob(f"*/{WHISPER_MODEL_NAME}")) if p.exists()]
    return found[-1] if found else WHISPER_MODEL_HOME


@dataclass(frozen=True)
class Tools:
    ffmpeg: str | None
    ffprobe: str | None
    whisper_cli: str | None
    whisper_model: Path
    aubio: str | None
    claude: str | None
    codex: str | None


@cache
def tools() -> Tools:
    return Tools(
        ffmpeg=_tool("VLOGKIT_FFMPEG", "ffmpeg", _FFMPEG_FULL_BINS),
        ffprobe=_tool("VLOGKIT_FFPROBE", "ffprobe", _FFMPEG_FULL_BINS),
        whisper_cli=_tool("VLOGKIT_WHISPER_CLI", "whisper-cli"),
        whisper_model=_env_path("VLOGKIT_WHISPER_MODEL", _whisper_model()),
        aubio=_tool("VLOGKIT_AUBIO", "aubio"),
        claude=_tool("VLOGKIT_CLAUDE", "claude", (_CLAUDE_HOME_BIN,)),
        codex=_tool("VLOGKIT_CODEX", "codex")
        or next((str(p) for p in _CODEX_FALLBACKS if p.exists()), None),
    )


@cache
def _filters(ffmpeg: str, mtime: float) -> str:
    try:
        r = subprocess.run(
            [ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True, timeout=20
        )
        return r.stdout
    except (OSError, subprocess.TimeoutExpired):
        return ""


def ffmpeg_full(ffmpeg: str | None) -> bool:
    """Has this ffmpeg the filters vlogkit needs (`FFMPEG_FILTERS`; Homebrew's plain `ffmpeg`
    has not)? Asked once per binary (path + modification time)."""
    if not ffmpeg:
        return False
    try:
        mtime = Path(ffmpeg).stat().st_mtime
    except OSError:
        return False
    out = _filters(ffmpeg, mtime)
    return all(f" {n} " in out for n in FFMPEG_FILTERS)


def require(tool: str | None, name: str) -> str:
    if not tool:
        raise RuntimeError(f"{name} bulunamadı. `vlogkit doctor` ile kurulumu kontrol et.")
    return tool
