"""First run and the optional parts, for the studio's welcome screen and settings.

- Agents: is Claude Code / Codex installed, and signed in with a subscription? Installing runs the
  vendor's own installer in the background (Claude Code's native installer, Codex via Homebrew);
  signing in opens Terminal with the login command, because both need a browser round trip.
- Basics: ffmpeg-full, whisper and its model, aubio. What this Mac already has counts as done and
  is not installed again; the uninstaller leaves what was here before (`found`).
- Local video model: optional. Three sizes of the same model (analysis/localvlm.CHOICES); the
  screen shows which fit this Mac's memory, installs one with progress, picks or removes it.

Long installs run in background threads (`tasks`), polled by the studio.
"""

from __future__ import annotations

import contextlib
import json
import re
import shlex
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from vlogkit import disk
from vlogkit.config import BUILD_DIR, WHISPER_MODEL_HOME, ffmpeg_full, tools

CLAUDE_INSTALL = "set -o pipefail; curl -fsSL https://claude.ai/install.sh | bash"  # offline: fails
AUTH_TTL = 30.0  # s: signed-in answers are reused this long (the screen polls)
MODEL_SPARE = 5e9  # bytes left free after a model download (and the engine on the first one)

_lock = threading.Lock()
tasks: dict[str, dict] = {}  # name -> {"status": running|done|error, "log": str, "progress": float}
_auth_cache: dict[str, tuple[float, dict]] = {}


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


# --------------------------------------------------------------------------- setup steps
# install.sh only puts the studio on the Mac (uv, vlogkit, Python: ~150 MB, a minute or two). The
# heavy parts come from the studio's setup screen, each with its size, one click each or all.
BREW_PACKAGES = ("ffmpeg-full", "whisper-cpp", "aubio", "terminal-notifier")
FOUND = BUILD_DIR / "ui" / "found.json"  # what this Mac had at the first setup check
HOMEBREW_INSTALL = (
    '/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
    " && (grep -qs 'brew shellenv' ~/.zprofile || echo 'eval \"$(/opt/homebrew/bin/brew shellenv)\"'"
    ' >> ~/.zprofile) && echo && echo "Bitti: vlogkit Stüdyo\'ya dönebilirsin."'
)
WHISPER_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-large-v3-turbo.bin"


def is_admin() -> bool:
    if sys.platform == "win32":
        from vlogkit.winsupport import is_admin as win_admin

        return win_admin()
    import getpass

    r = subprocess.run(
        ["dseditgroup", "-o", "checkmember", "-m", getpass.getuser(), "admin"], capture_output=True
    )
    return r.returncode == 0


def tool_status() -> dict[str, bool]:
    """Which of the Homebrew packages this Mac already has, by what vlogkit runs (any install:
    Homebrew, MacPorts, a build of its own). terminal-notifier is optional (notifications)."""
    from vlogkit.ui.notify import notifier

    t = tools()
    return {
        "ffmpeg-full": ffmpeg_full(t.ffmpeg),  # plain ffmpeg lacks filters vlogkit uses
        "whisper-cpp": bool(t.whisper_cli),
        "aubio": bool(t.aubio),
        "terminal-notifier": bool(notifier()),
    }


def found() -> set[str]:
    """Packages and models this Mac had before vlogkit installed anything (written at the first
    check): the setup does not install them again and the uninstaller leaves them."""
    try:
        return set(json.loads(FOUND.read_text()))
    except (OSError, ValueError):
        pass
    from vlogkit.analysis import localvlm

    have = {name for name, ok in tool_status().items() if ok}
    if WHISPER_MODEL_HOME.exists():
        have.add("speech")
    have |= {c.repo for c in localvlm.CHOICES.values() if localvlm.model_cached(c.repo)}
    with contextlib.suppress(OSError):
        FOUND.parent.mkdir(parents=True, exist_ok=True)
        FOUND.write_text(json.dumps(sorted(have)))
    return have


def _library_done() -> tuple[int, int]:
    from vlogkit import assets

    m = assets.manifest()
    return sum(a.path.exists() for a in m.values()), len(m)


def steps() -> list[dict]:
    """The setup checklist in order; each says whether it is done and what installing it takes."""
    if sys.platform == "win32":  # winget instead of Homebrew; the 3D rows as on macOS
        from vlogkit import winsupport
        from vlogkit.scene3d import setup as scene3d_setup

        rows = (
            winsupport.setup_rows(winsupport.tool_status(), _library_done()) + scene3d_setup.rows()
        )
        done = {r["id"]: r["done"] for r in rows}
        for r in rows:
            r["ready"] = not r.get("needs") or done[r["needs"]]
            task = tasks.get(f"step:{r['id']}")
            r["task"] = {k: task.get(k) for k in ("status", "progress", "error")} if task else None
        return rows
    t = tools()
    found()  # first check: remember what was here before
    have, total = _library_done()
    status = tool_status()
    need = [k for k in TOOLS if not status[k]]
    tools_done = not need
    speech = t.whisper_model
    rows = [
        {
            "id": "homebrew",
            "label": "Apple geliştirici araçları ve Homebrew",
            "detail": "Video araçları bu Mac'te var: gerekmiyor."
            if tools_done and not _brew()
            else "Video araçlarının kurulduğu yer. Terminal açılır, Mac şifren sorulur.",
            "size": "~2 GB",
            "done": bool(_brew()) or tools_done,
            "terminal": True,
            "admin": is_admin(),
        },
        {
            "id": "tools",
            "label": "Video ve ses araçları",
            "detail": _tools_detail(status, need),
            "size": "~1,5 GB" if "ffmpeg-full" in need else "~100 MB",
            "done": tools_done,
            "needs": "homebrew",
        },
        {
            "id": "speech",
            "label": "Konuşma modeli",
            "detail": "Konuşmayı internetsiz yazıya döker (whisper large-v3-turbo)"
            + (
                f"; bu Mac'te var: {_home(speech)}"
                if speech != WHISPER_MODEL_HOME and speech.exists()
                else ""
            ),
            "size": "1,5 GB",
            "done": speech.exists(),
        },
        {
            "id": "library",
            "label": "Müzik ve ses kütüphanesi",
            "detail": f"Lisanslı müzik ve efektler ({have}/{total})",
            "size": "~90 MB",
            "done": have == total,
            "needs": "tools",
        },
    ]
    from vlogkit.scene3d import setup as scene3d_setup  # optional rows: Blender, voice model

    rows += scene3d_setup.rows()
    done = {r["id"]: r["done"] for r in rows}
    for r in rows:
        r["ready"] = not r.get("needs") or done[r["needs"]]
        task = tasks.get(f"step:{r['id']}")
        r["task"] = {k: task.get(k) for k in ("status", "progress", "error")} if task else None
    return rows


TOOLS = {"ffmpeg-full": "ffmpeg-full", "whisper-cpp": "whisper", "aubio": "aubio"}  # required


def _home(p: Path) -> str:
    return str(p).replace(str(Path.home()), "~", 1)


def _tools_detail(status: dict[str, bool], need: list[str]) -> str:
    if not need:
        return "ffmpeg-full, whisper, aubio: bu Mac'te var"
    if len(need) == len(TOOLS):
        return "ffmpeg, whisper, aubio (bağımlılıklarıyla ~115 paket)"
    have = ", ".join(TOOLS[k] for k in TOOLS if status[k])
    note = "; ffmpeg var ama ffmpeg-full değil" if "ffmpeg-full" in need and tools().ffmpeg else ""
    return f"Bu Mac'te var: {have}. Eksik: {', '.join(TOOLS[k] for k in need)}{note}"


def _brew_plan(brew: str, packages: list[str]) -> int:
    """How many formulae `brew install packages` pours: the packages and their dependencies this
    Mac does not have yet (for the progress)."""
    deps = subprocess.run([brew, "deps", "--union", *packages], capture_output=True, text=True)
    have = subprocess.run([brew, "list", "--formula", "-1"], capture_output=True, text=True)
    return len({*packages, *deps.stdout.split()} - set(have.stdout.split()))


# Homebrew 4.5+ fetches every bottle first (one "✔︎ Bottle name (version)" line each, while the
# download, most of the time, runs), then pours them one by one ("==> Pouring ..."); older ones
# fetch and pour per formula ("==> Fetching name"). Downloads are 70 % of the bar, pours 30 %.
_FETCHED = re.compile(r"^(?:✔\S*\s+Bottle\s+(?!Manifest)\S|==> Fetching \S+$)")


def brew_progress(task: dict, line: str, total: int) -> None:
    line = line.strip()
    if _FETCHED.match(line):
        task["fetched"] = task.get("fetched", 0) + 1
    elif line.startswith("==> Pouring"):
        task["poured"] = task.get("poured", 0) + 1
    else:
        return
    n = max(1, total)
    done = 0.7 * min(1.0, task.get("fetched", 0) / n) + 0.3 * min(1.0, task.get("poured", 0) / n)
    task["progress"] = min(0.99, max(task.get("progress", 0.0), done))


def _download(name: str, url: str, dest: Path) -> None:
    """A big file with progress; .part first, so an interrupted one never counts as done."""
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(url, timeout=60) as r, part.open("wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            got += len(chunk)
            if total:
                with _lock:
                    tasks[name]["progress"] = min(0.99, got / total)
    part.replace(dest)


def run_step(step: str) -> None:
    """Start one setup step in the background ("all": every step that can run now, in order)."""
    import sys

    from vlogkit.config import REPO_ROOT

    rows = {r["id"]: r for r in steps()}
    if sys.platform == "win32" and step == "all":
        from vlogkit import winsupport

        for sid in ("ffmpeg", "git"):
            if (
                not rows[sid]["done"]
                and (tasks.get(f"step:{sid}") or {}).get("status") != "running"
            ):
                winsupport.run_step(sid, _run_task)
        return
    if step == "all":
        if not rows["speech"]["done"]:
            run_step("speech")
        if rows["tools"]["ready"] and not rows["tools"]["done"]:
            _start_tools(then_library=not rows["library"]["done"])
        elif rows["library"]["ready"] and not rows["library"]["done"]:
            run_step("library")
        return
    row = rows.get(step)
    if row is None:
        raise ValueError(f"bilinmeyen adım: {step}")
    if not row["ready"]:
        raise RuntimeError("önce bir önceki adımı tamamla")
    if sys.platform == "win32":
        from vlogkit import winsupport

        if winsupport.run_step(step, _run_task):
            return
    if row.get("optional"):  # the 3D rows (scene3d/setup.py)
        from vlogkit.scene3d import setup as scene3d_setup

        scene3d_setup.run(step, _run_task)
        return
    if step == "homebrew":
        if not row["admin"]:
            raise RuntimeError("Homebrew için bu Mac'te yönetici hesabı gerekli")
        _terminal(HOMEBREW_INSTALL)
    elif step == "tools":
        _start_tools(then_library=False)
    elif step == "speech":  # always into our own place (a copy found elsewhere is not ours)
        _run_task(
            "step:speech",
            [],
            after=lambda: _download("step:speech", WHISPER_URL, WHISPER_MODEL_HOME),
        )
    elif step == "library":
        _, total = _library_done()
        cmd = [sys.executable, "-m", "vlogkit.cli", "assets", "fetch"]
        _run_task(
            "step:library",
            [cmd],
            cwd=REPO_ROOT,
            progress=lambda: _library_done()[0] / max(1, total),
        )


def _start_tools(then_library: bool) -> None:
    brew = _brew()
    if not brew:
        raise RuntimeError("Homebrew yok: önce ilk adım")
    status = tool_status()
    packages = [p for p in BREW_PACKAGES if not status[p]]  # only what this Mac lacks
    after = (lambda: run_step("library")) if then_library else None
    if not packages:
        _run_task("step:tools", [], after=after)
        return
    total = _brew_plan(brew, packages)

    def on_line(line: str) -> None:
        with _lock:
            brew_progress(tasks["step:tools"], line, total)

    _run_task("step:tools", [[brew, "install", *packages]], after=after, on_line=on_line)


def _terminal(command: str) -> None:
    """Run a command in a new Terminal window (it needs the user: a password, a browser)."""
    if sys.platform == "win32":
        from vlogkit.winsupport import terminal

        terminal(command)
        return
    cmd = command.replace("\\", "\\\\").replace('"', '\\"')
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


# --------------------------------------------------------------------------- background tasks
def _run_task(
    name: str, steps: list[list[str]], after=None, progress=None, on_line=None, cwd=None
) -> None:
    def work():
        log: list[str] = []
        try:
            for cmd in steps:
                win = sys.platform == "win32"  # no console windows; UTF-8 output
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    cwd=cwd,
                    **(
                        {"encoding": "utf-8", "errors": "replace", "creationflags": 0x08000000}
                        if win
                        else {}
                    ),
                )
                assert proc.stdout
                for line in proc.stdout:
                    log.append(line.rstrip())
                    if on_line:
                        on_line(line)
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
    if sys.platform == "win32" and name == "claude":
        from vlogkit.winsupport import claude_install_cmd

        _run_task("agent:claude", [claude_install_cmd()])
        return
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
    if sys.platform == "win32":  # PowerShell runs a quoted path with &
        from vlogkit.winsupport import ps_quote

        return f"& {ps_quote(exe)} auth login" if name == "claude" else f"& {ps_quote(exe)} login"
    return f"{shlex.quote(exe)} auth login" if name == "claude" else f"{shlex.quote(exe)} login"


def open_login(name: str) -> None:
    """Terminal with the login command (it opens the browser); the screen polls until done."""
    _terminal(login_command(name))
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


def blocked(key: str, mem: int | None = None) -> str | None:
    """Why this Mac cannot take the model: too little memory, or too little disk for the
    download plus room left for macOS and the builds. None = it can be installed."""
    from vlogkit.analysis import localvlm

    c = localvlm.CHOICES[key]
    if why := localvlm.unfit(key, mem):
        return why
    need = c.size + MODEL_SPARE
    if disk.free_bytes(localvlm.model_dir(c.repo)) < need:
        return f"diskte {need / 1e9:.0f} GB boş yer ister"
    return None


def models() -> dict:
    from vlogkit.analysis import localvlm

    mem = localvlm.memory_gb()
    pick = localvlm.chosen()
    best = localvlm.recommended(mem)
    rows = []
    for key, c in localvlm.CHOICES.items():
        task = tasks.get(f"model:{key}", {})
        installed = localvlm.model_cached(c.repo)
        if task.get("status") == "running":
            why = None  # its own download eats the disk
        elif installed:  # from an older install: stays usable, the row says it is too big
            why = localvlm.unfit(key, mem)
        else:
            why = blocked(key, mem)
        rows.append(
            {
                "id": key,
                "label": c.label,
                "note": c.note,
                "size_gb": round(c.size / 1e9, 1),
                "ram": c.ram,
                "blocked": why,
                "recommended": key == best,
                "installed": installed,
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
    if why := blocked(key):
        raise RuntimeError(f"{c.label} bu Mac'e kurulmaz: {why}")
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
    localvlm.remove_model_files(c.repo)
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
