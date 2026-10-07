"""First run and the optional parts, for the studio's welcome screen and settings.

- Agents: is Claude Code / Codex installed, and signed in with a subscription? Installing runs the
  vendor's own installer in the background (Claude Code's native installer, Codex via Homebrew);
  signing in opens Terminal with the login command, because both need a browser round trip.
- Basics: ffmpeg-full, whisper and its model, aubio (install.sh sets them up; the screen says
  what is missing and how to fix it).
- Local video model: optional. Three sizes of the same model (analysis/localvlm.CHOICES); the
  screen shows which fit this Mac's memory, installs one with progress, picks or removes it.

Long installs run in background threads (`tasks`), polled by the studio.
"""

from __future__ import annotations

import json
import shlex
import shutil
import subprocess
import threading
import time
from pathlib import Path

from vlogkit.config import tools

CLAUDE_INSTALL = "set -o pipefail; curl -fsSL https://claude.ai/install.sh | bash"  # offline: fails
AUTH_TTL = 30.0  # s: signed-in answers are reused this long (the screen polls)

_lock = threading.Lock()
tasks: dict[str, dict] = {}  # name -> {"status": running|done|error, "log": str, "progress": float}
_auth_cache: dict[str, tuple[float, dict]] = {}


def memory_gb() -> int:
    try:
        r = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
        return round(int(r.stdout.strip()) / 2**30)
    except (OSError, ValueError):
        return 0


def _brew() -> str | None:
    return shutil.which("brew") or next(
        (p for p in ("/opt/homebrew/bin/brew", "/usr/local/bin/brew") if Path(p).exists()), None
    )


# --------------------------------------------------------------------------- agents
def _claude_auth(exe: str) -> dict:
    from vlogkit.ui.runner import subscription_env

    try:
        r = subprocess.run(
            [exe, "auth", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=20,
            env=subscription_env(),
        )
        d = json.loads(r.stdout or "{}")
        return {"logged_in": bool(d.get("loggedIn")), "plan": d.get("subscriptionType")}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"logged_in": None, "plan": None}  # unknown: an old CLI without `auth status`


def _codex_auth(exe: str) -> dict:
    from vlogkit.ui import codex

    try:
        r = subprocess.run(
            [exe, "login", "status"], capture_output=True, text=True, timeout=20, env=codex.env()
        )
        text = r.stdout + r.stderr
        return {"logged_in": r.returncode == 0 and "Logged in" in text, "plan": None}
    except (OSError, subprocess.TimeoutExpired):
        return {"logged_in": None, "plan": None}


def agents(fresh: bool = False) -> dict[str, dict]:
    """{"claude": {installed, logged_in, plan, ready}, "codex": {...}}."""
    t = tools()
    out = {}
    for name, exe, check in (("claude", t.claude, _claude_auth), ("codex", t.codex, _codex_auth)):
        info = {"installed": bool(exe), "logged_in": False, "plan": None}
        if exe:
            hit = _auth_cache.get(name)
            if fresh or not hit or time.time() - hit[0] > AUTH_TTL:
                hit = (time.time(), check(exe))
                _auth_cache[name] = hit
            info |= hit[1]
        info["ready"] = bool(info["installed"] and info["logged_in"] is not False)
        out[name] = info
    return out


def basics() -> list[dict]:
    t = tools()
    rows = [
        ("ffmpeg", "ffmpeg (ffmpeg-full)", bool(t.ffmpeg), "brew install ffmpeg-full"),
        ("whisper", "whisper (konuşmayı yazıya döker)", bool(t.whisper_cli), "brew install whisper-cpp"),
        ("whisper-model", "whisper modeli", t.whisper_model.exists(), "kurulumu yeniden çalıştır"),
        ("aubio", "aubio (müzik vuruşları)", bool(t.aubio), "brew install aubio"),
    ]  # fmt: skip
    return [{"id": i, "label": label, "ok": ok, "fix": fix} for i, label, ok, fix in rows]


# --------------------------------------------------------------------------- background tasks
def _run_task(name: str, steps: list[list[str]], after=None, progress=None) -> None:
    def work():
        log: list[str] = []
        try:
            for cmd in steps:
                proc = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
                )
                assert proc.stdout
                for line in proc.stdout:
                    log.append(line.rstrip())
                    with _lock:
                        tasks[name]["log"] = "\n".join(log[-12:])
                if proc.wait() != 0:
                    raise RuntimeError(log[-1] if log else f"çıkış kodu {proc.returncode}")
            if after:
                after()
            with _lock:
                tasks[name] |= {"status": "done", "progress": 1.0}
        except Exception as e:
            with _lock:
                tasks[name] |= {"status": "error", "error": str(e)}
        finally:
            tools.cache_clear()
            _auth_cache.clear()

    with _lock:
        if tasks.get(name, {}).get("status") == "running":
            raise RuntimeError("zaten kuruluyor")
        tasks[name] = {"status": "running", "log": "", "progress": 0.0, "started": time.time()}
    threading.Thread(target=work, daemon=True).start()
    if progress:  # a size-based progress for downloads that print none we can parse

        def watch():
            while tasks.get(name, {}).get("status") == "running":
                with _lock:
                    tasks[name]["progress"] = min(0.99, progress())
                time.sleep(1.0)

        threading.Thread(target=watch, daemon=True).start()


def install_agent(name: str) -> None:
    if name == "claude":
        _run_task("agent:claude", [["/bin/bash", "-c", CLAUDE_INSTALL]])
    elif name == "codex":
        brew = _brew()
        if not brew:
            raise RuntimeError("Homebrew yok: önce vlogkit kurulumunu çalıştır")
        _run_task("agent:codex", [[brew, "install", "--cask", "codex"]])
    else:
        raise ValueError(f"bilinmeyen ajan: {name}")


def login_command(name: str) -> str:
    t = tools()
    exe = t.claude if name == "claude" else t.codex if name == "codex" else None
    if not exe:
        raise RuntimeError(f"{name} kurulu değil")
    return f"{shlex.quote(exe)} auth login" if name == "claude" else f"{shlex.quote(exe)} login"


def open_login(name: str) -> None:
    """Terminal with the login command (it opens the browser); the screen polls until done."""
    cmd = login_command(name).replace("\\", "\\\\").replace('"', '\\"')
    subprocess.run(
        [
            "osascript",
            "-e",
            'tell application "Terminal" to activate',
            "-e",
            f'tell application "Terminal" to do script "{cmd}"',
        ],
        check=True,
        capture_output=True,
    )
    _auth_cache.pop(name, None)


# --------------------------------------------------------------------------- local video model
def _dir_size(path: Path) -> int:
    total = 0
    for p in path.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                total += p.stat().st_size
        except OSError:
            continue
    return total


def models() -> dict:
    from vlogkit.analysis import localvlm

    mem = memory_gb()
    pick = localvlm.chosen()
    rows = []
    for key, c in localvlm.CHOICES.items():
        task = tasks.get(f"model:{key}", {})
        rows.append(
            {
                "id": key,
                "label": c.label,
                "note": c.note,
                "size_gb": round(c.size / 1e9, 1),
                "ram": c.ram,
                "fits": not mem or mem >= c.ram,
                "installed": localvlm.model_cached(c.repo),
                "selected": key == pick,
                "task": {k: task.get(k) for k in ("status", "progress", "error")} if task else None,
            }
        )
    return {
        "memory_gb": mem,
        "selected": pick,
        "choices": rows,
        "engine": bool(localvlm.tool_python()),
    }


def install_model(key: str) -> None:
    from vlogkit.analysis import localvlm

    c = localvlm.CHOICES.get(key)
    if c is None:
        raise ValueError(f"bilinmeyen model: {key}")
    if any(k.startswith("model:") and t.get("status") == "running" for k, t in tasks.items()):
        raise RuntimeError("bir model zaten kuruluyor: bitmesini bekle")
    uv = shutil.which("uv") or next(
        (p for p in ("/opt/homebrew/bin/uv", str(Path.home() / ".local/bin/uv")) if Path(p).exists()),
        None,
    )  # fmt: skip
    if not uv:
        raise RuntimeError("uv bulunamadı: vlogkit kurulumunu yeniden çalıştır")
    steps = [] if localvlm.tool_python() else [[uv, "tool", "install", "mlx-vlm"]]

    def download():
        from vlogkit.extras import download_cmd

        py = localvlm.tool_python()
        if not py:
            raise RuntimeError("mlx-vlm kuruldu ama python'u bulunamadı")
        r = subprocess.run(download_cmd(py, c.repo), capture_output=True, text=True)
        if r.returncode != 0 or not localvlm.model_cached(c.repo):
            raise RuntimeError((r.stderr or "indirme bitmedi").strip().splitlines()[-1])
        if localvlm.pick() is None:  # nothing picked yet (not even "Yok"): use this one
            localvlm.choose(key)

    _run_task(
        f"model:{key}",
        steps,
        after=download,
        progress=lambda: _dir_size(localvlm.model_dir(c.repo)) / c.size,
    )


def remove_model(key: str) -> None:
    from vlogkit.analysis import localvlm

    c = localvlm.CHOICES[key]
    if tasks.get(f"model:{key}", {}).get("status") == "running":
        raise RuntimeError("model kuruluyor: bitmesini bekle")
    was = localvlm.chosen() == key
    shutil.rmtree(localvlm.model_dir(c.repo), ignore_errors=True)
    if was:  # the next best installed one, or none
        nxt = next(
            (
                k
                for k in reversed(localvlm.CHOICES)
                if localvlm.model_cached(localvlm.CHOICES[k].repo)
            ),
            None,
        )
        localvlm.choose(nxt)
