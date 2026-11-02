"""Windows: what macOS does with osascript, Homebrew, caffeinate and Finder, done the Windows way.

Only imported on Windows (`sys.platform == "win32"`); every caller keeps its macOS path as it was.
Scope today: the studio, the agent and the 3D videos (docs/3d.md). The Apple-only analysis tools
(Vision, VideoToolbox, the MLX video model) stay macOS features.

- setup rows: winget packages (FFmpeg full build, Git for Windows: Claude Code's shell), the music
  library; the 3D rows come from scene3d/setup.py as on macOS
- a console window for the agent's sign-in, file/folder pickers, "show in Explorer"
- the desktop shortcut (.lnk + .ico), keep-awake while a job runs, stopping a process tree
- UTF-8 for every Python child (Turkish text never meets the ANSI code page)
"""

from __future__ import annotations

import contextlib
import ctypes
import os
import shutil
import subprocess
import threading
from pathlib import Path

CREATE_NO_WINDOW = 0x08000000
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NEW_CONSOLE = 0x00000010

WINGET = {  # setup id -> (winget package id, what it is)
    "ffmpeg": ("Gyan.FFmpeg", "FFmpeg (tam sürüm)"),
    "git": ("Git.Git", "Git for Windows (Claude Code'un kabuğu)"),
}


def utf8_env(env: dict | None = None) -> dict:
    e = dict(os.environ if env is None else env)
    e["PYTHONUTF8"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    return e


def background_flags() -> int:
    return CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP | DETACHED_PROCESS


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def winget() -> str | None:
    found = shutil.which("winget")
    if found:
        return found
    p = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WindowsApps" / "winget.exe"
    return str(p) if p.exists() else None


def winget_links() -> Path:
    """Where winget puts the command-line tools it installs (on PATH for new consoles only)."""
    return (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local")))
        / "Microsoft"
        / "WinGet"
        / "Links"
    )


def powershell() -> str:
    return shutil.which("pwsh") or shutil.which("powershell") or "powershell"


def ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def terminal(command: str) -> None:
    """A PowerShell window running `command` (sign-in needs the user and a browser)."""
    subprocess.Popen(
        [powershell(), "-NoExit", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
        creationflags=CREATE_NEW_CONSOLE,
        env=utf8_env(),
    )


def run_ps(script: str, timeout: float = 600) -> subprocess.CompletedProcess:
    return subprocess.run(
        [powershell(), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-STA", "-Command", script],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, creationflags=CREATE_NO_WINDOW,
    )  # fmt: skip


def pick(kind: str, start: Path) -> str | None:
    """The Windows open dialog (a video, or a folder), in front of the browser."""
    if kind == "folder":
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$d = New-Object System.Windows.Forms.FolderBrowserDialog;"
            f"$d.SelectedPath = {ps_quote(start)}; $d.Description = 'Vlog klasörü seç';"
            "$f = New-Object System.Windows.Forms.Form; $f.TopMost = $true;"
            "if ($d.ShowDialog($f) -eq 'OK') { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $d.SelectedPath }"
        )
    else:
        script = (
            "Add-Type -AssemblyName System.Windows.Forms;"
            "$d = New-Object System.Windows.Forms.OpenFileDialog;"
            f"$d.InitialDirectory = {ps_quote(start)};"
            "$d.Filter = 'Video|*.mp4;*.mov;*.m4v;*.mkv;*.webm|Hepsi|*.*';"
            "$f = New-Object System.Windows.Forms.Form; $f.TopMost = $true;"
            "if ($d.ShowDialog($f) -eq 'OK') { [Console]::OutputEncoding = [Text.Encoding]::UTF8; $d.FileName }"
        )
    r = run_ps(script)
    out = r.stdout.strip()
    return out or None


def reveal(path: Path) -> None:
    subprocess.run(
        ["explorer", f"/select,{Path(path)}"], check=False
    )  # exit code 1 even on success


def keep_awake(proc: subprocess.Popen) -> None:
    """No idle sleep while the agent runs (the display may still sleep)."""
    ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001

    def hold() -> None:
        with contextlib.suppress(Exception):
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
            proc.wait()
            ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS)

    threading.Thread(target=hold, daemon=True).start()


def kill_tree(pid: int) -> None:
    """Stop the agent and everything it started (ffmpeg, Blender, the shell)."""
    subprocess.run(
        ["taskkill", "/T", "/F", "/PID", str(pid)],
        capture_output=True,
        creationflags=CREATE_NO_WINDOW,
    )


def desktop() -> Path:
    r = run_ps("[Environment]::GetFolderPath('Desktop')", timeout=60)
    p = Path(r.stdout.strip()) if r.stdout.strip() else Path.home() / "Desktop"
    return p if p.exists() else Path.home() / "Desktop"


def shortcut(app_name: str, repo: Path, icon_png) -> Path:
    """A desktop (and Start menu) shortcut that opens the studio without a console window."""
    from PIL import Image

    ico = repo / "build" / "ui" / "vlogkit.ico"
    ico.parent.mkdir(parents=True, exist_ok=True)
    png = ico.with_suffix(".png")
    icon_png(png, 256)
    Image.open(png).save(
        ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    )
    uv = shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv.exe")
    pythonw = repo / ".venv" / "Scripts" / "pythonw.exe"
    target, args = (
        (str(pythonw), "-X utf8 -m vlogkit.cli open")
        if pythonw.exists()
        else (uv, "run --frozen vlogkit open")
    )
    out = desktop() / f"{app_name}.lnk"
    start_menu = (
        Path(os.environ.get("APPDATA", ""))
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / f"{app_name}.lnk"
    )
    for lnk in (out, start_menu):
        script = (
            "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(" + ps_quote(lnk) + ");"
            f"$s.TargetPath = {ps_quote(target)}; $s.Arguments = {ps_quote(args)};"
            f"$s.WorkingDirectory = {ps_quote(repo)}; $s.IconLocation = {ps_quote(ico)};"
            "$s.WindowStyle = 7; $s.Description = 'vlogkit Stüdyo'; $s.Save()"
        )
        run_ps(script, timeout=60)
    return out


# --------------------------------------------------------------------------- setup screen
def setup_rows(tool_ok: dict[str, bool], library_done: tuple[int, int]) -> list[dict]:
    have, total = library_done
    wg = winget()
    rows = [
        {
            "id": "ffmpeg",
            "label": "Video araçları (FFmpeg)",
            "detail": "Bu bilgisayarda var"
            if tool_ok.get("ffmpeg")
            else "winget ile kurulur (tam sürüm: altyazı ve ses filtreleriyle)",
            "size": "~200 MB",
            "done": bool(tool_ok.get("ffmpeg")),
        },
        {
            "id": "git",
            "label": "Git for Windows",
            "detail": "Claude Code komutlarını bununla çalıştırır"
            + ("; bu bilgisayarda var" if tool_ok.get("git") else ""),
            "size": "~350 MB",
            "done": bool(tool_ok.get("git")),
        },
        {
            "id": "library",
            "label": "Müzik ve ses kütüphanesi",
            "detail": f"Lisanslı müzik ve efektler ({have}/{total})",
            "size": "~90 MB",
            "done": have == total,
            "needs": "ffmpeg",
        },
    ]
    if not wg:
        for r in rows[:2]:
            if not r["done"]:
                r["manual"] = True
                r["detail"] += ". winget yok: Microsoft Store'dan 'App Installer'ı kur."
    return rows


def tool_status() -> dict[str, bool]:
    from vlogkit.config import ffmpeg_full, tools

    tools.cache_clear()
    return {
        "ffmpeg": ffmpeg_full(tools().ffmpeg),
        "git": bool(shutil.which("git") or Path(r"C:\Program Files\Git\cmd\git.exe").exists()),
    }


def run_step(step: str, run_task) -> bool:
    """Start a Windows setup step; False if it is not one of ours."""
    if step in WINGET:
        wg = winget()
        if not wg:
            raise RuntimeError("winget yok: Microsoft Store'dan 'App Installer'ı kur")
        pkg, _ = WINGET[step]
        cmd = [
            wg,
            "install",
            "--id",
            pkg,
            "-e",
            "--silent",
            "--accept-package-agreements",
            "--accept-source-agreements",
        ]
        run_task(f"step:{step}", [cmd])
        return True
    return False


def claude_install_cmd() -> list[str]:
    return [
        powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        "irm https://claude.ai/install.ps1 | iex",
    ]


def emoji_font() -> str | None:
    p = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "seguiemj.ttf"
    return str(p) if p.exists() else None
