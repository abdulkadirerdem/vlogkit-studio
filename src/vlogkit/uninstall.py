"""Removing an installed copy from the studio (Ayarlar > Hakkında > Kaldır).

Two levels:
- "app": vlogkit's folder (with its build intermediates) and the desktop app.
- "all": the app and what the setup screen installed: the Homebrew packages (ffmpeg-full,
  whisper-cpp, aubio, terminal-notifier and the dependencies nothing else needs), the speech
  model, the local video models and their runtime (mlx-vlm).

Always kept: the videos and deliveries in ~/yt-vlogs, Homebrew itself, Apple's developer tools,
uv and Claude Code / Codex (other software may use them). The user's projects, job history,
local manifest and vocabulary are copied to ~/yt-vlogs/vlogkit-yedek-<date> first. A developer
checkout (no `.release`) is never removed.

The removal runs as a detached script once the studio has stopped: it deletes the studio's own
folder. The desktop app goes to the Trash through Finder (macOS protects an app another process
made from being deleted directly).
"""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

from vlogkit.config import REPO_ROOT, VLOGS_ROOT, tools

MODES = ("app", "all")
DESKTOP_APP = Path.home() / "Desktop" / "vlogkit Stüdyo.app"
KEEP_FROM_APP = (
    "projects",
    "recipes",
    "build/ui/jobs",
    "assets/vocab.txt",
    "assets/manifest.local.toml",
)


def allowed() -> bool:
    return (REPO_ROOT / ".release").exists()


def _size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    total = 0
    for root, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(root, f)).st_size
            except OSError:
                continue
    return total


def _brew() -> str | None:
    from vlogkit.ui.setup import _brew

    return _brew()


def _models() -> list[str]:
    from vlogkit.analysis import localvlm

    return [c.repo for c in localvlm.CHOICES.values() if localvlm.model_dir(c.repo).exists()]


def _brew_size(brew: str) -> int:
    """The packages and their dependencies (what uninstall + autoremove can free at most)."""
    from vlogkit.ui.setup import BREW_PACKAGES

    r = subprocess.run([brew, "deps", "--union", *BREW_PACKAGES], capture_output=True, text=True)
    cellar = Path(brew).parent.parent / "Cellar"
    names = {*BREW_PACKAGES, *r.stdout.split()}
    return sum(_size(cellar / n) for n in names if (cellar / n).exists())


def plan(mode: str) -> dict:
    """What goes and what stays, with sizes (bytes), for the confirmation screen."""
    if mode not in MODES:
        raise ValueError(f"kaldırma: {mode}")
    remove = [
        {
            "label": "vlogkit ve derleme ara dosyaları",
            "path": str(REPO_ROOT),
            "size": _size(REPO_ROOT),
        },
    ]
    if DESKTOP_APP.exists():
        remove.append({"label": "Masaüstü uygulaması (çöpe)", "path": str(DESKTOP_APP), "size": 0})
    if mode == "all":
        model = tools().whisper_model
        if model.exists():
            remove.append({"label": "Konuşma modeli", "path": str(model), "size": _size(model)})
        from vlogkit.analysis import localvlm

        for repo in _models():
            remove.append(
                {
                    "label": f"Yerel video modeli {repo.split('/')[-1]}",
                    "path": repo,
                    "size": localvlm.model_size(repo),
                }
            )
        brew = _brew()
        if brew:
            size = _brew_size(brew)
            remove.append(
                {
                    "label": "ffmpeg, whisper, aubio (Homebrew) ve kullanılmayan bağımlılıkları",
                    "path": "",
                    "size": size,
                }
            )
    keep = [
        f"Videoların ve teslim dosyaların ({VLOGS_ROOT})",
        "Projelerin ve iş geçmişin: önce yedeklenir",
        "Homebrew, Apple geliştirici araçları, uv, Claude Code ve Codex (başka uygulamalar da kullanabilir)",
    ]
    if mode == "app":
        keep.insert(2, "Konuşma modeli, yerel video modelleri ve Homebrew paketleri")
    return {"mode": mode, "remove": remove, "keep": keep, "backup": str(backup_dir())}  # fmt: skip


def backup_dir(now: float | None = None) -> Path:
    return VLOGS_ROOT / f"vlogkit-yedek-{time.strftime('%Y%m%d-%H%M', time.localtime(now))}"


def script(mode: str, backup: Path) -> str:
    """The shell script that removes it (run detached, after the studio stops)."""
    if mode not in MODES:
        raise ValueError(f"kaldırma: {mode}")
    q = shlex.quote
    lines = [
        "#!/bin/bash",
        "# vlogkit kaldırma (Stüdyo'dan başlatıldı)",
        "set -e  # a backup that fails (a full disk) stops everything before anything is deleted",
        "sleep 3  # the studio answers and stops first",
        f"mkdir -p {q(str(backup))}",
    ]
    for rel in KEEP_FROM_APP:
        src = REPO_ROOT / rel
        lines.append(
            f"[ -e {q(str(src))} ] && mkdir -p {q(str((backup / rel).parent))} "
            f"&& cp -R {q(str(src))} {q(str(backup / rel))}"
        )
    lines.append(f"rm -rf {q(str(backup / 'projects' / '_template'))}")
    if DESKTOP_APP.exists():
        app = str(DESKTOP_APP).replace('"', '\\"')
        lines.append(
            f"osascript -e {q(f'tell application "Finder" to delete (POSIX file "{app}" as alias)')}"
            " >/dev/null 2>&1 || true"
        )
    if mode == "all":
        from vlogkit.ui.setup import BREW_PACKAGES

        lines.append(f"rm -f {q(str(tools().whisper_model))} || true")
        repos = _models()
        if repos:  # a model's files can sit in Hugging Face's shared store: Python removes them
            code = (
                "import sys\nfrom vlogkit.analysis import localvlm\n"
                "for r in sys.argv[1:]: localvlm.remove_model_files(r)"
            )
            py = REPO_ROOT / ".venv" / "bin" / "python"
            lines.append(f"{q(str(py))} -c {q(code)} {' '.join(q(r) for r in repos)} || true")
        lines.append('UV="$(command -v uv || echo "$HOME/.local/bin/uv")"')
        lines.append('"$UV" tool uninstall mlx-vlm >/dev/null 2>&1 || true')
        brew = _brew()
        if brew:
            lines.append(f"{q(brew)} uninstall {' '.join(BREW_PACKAGES)} >/dev/null 2>&1 || true")
            lines.append(f"{q(brew)} autoremove >/dev/null 2>&1 || true")
    lines.append(f"rm -rf {q(str(REPO_ROOT))}")
    return "\n".join(lines) + "\n"


def start(mode: str) -> Path:
    """Write the script next to the build dir's parent and run it detached. Returns the backup."""
    if not allowed():
        raise RuntimeError("geliştirici kopyası buradan kaldırılmaz")
    if REPO_ROOT in (Path.home(), Path("/")) or not (REPO_ROOT / "pyproject.toml").exists():
        raise RuntimeError(f"beklenmedik klasör, kaldırılmadı: {REPO_ROOT}")
    backup = backup_dir()
    path = Path(os.environ.get("TMPDIR", "/tmp")) / f"vlogkit-kaldir-{os.getpid()}.sh"
    path.write_text(script(mode, backup))
    path.chmod(0o700)
    log = Path(os.environ.get("TMPDIR", "/tmp")) / "vlogkit-kaldir.log"
    subprocess.Popen(
        ["/bin/bash", str(path)],
        cwd=str(Path.home()),
        stdin=subprocess.DEVNULL,
        stdout=log.open("wb"),
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    return backup
