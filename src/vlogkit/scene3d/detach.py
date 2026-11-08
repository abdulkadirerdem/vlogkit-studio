"""Long 3D builds that outlive the agent's session.

A studio turn ends when the agent answers; Claude Code then stops whatever the agent left running
in the background, a 30-60 minute Blender render included (it happened: twice cut at 9 and 320 of
1544 frames). `start()` runs the build in its own process session instead (Windows: a detached
process), so it keeps going after the turn; `progress()` reads how far it got from the frames on
disk and the state file the worker keeps.

    vlogkit 3d render PROJE      # starts, returns at once
    vlogkit 3d progress PROJE    # frames done / total, speed, time left, alive?, the outcome
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from vlogkit.config import BUILD_DIR, REPO_ROOT


def _work(project: str, variant: str) -> Path:
    return BUILD_DIR / project / variant


def state_path(project: str, variant: str = "v1") -> Path:
    return _work(project, variant) / "render.json"


def log_path(project: str, variant: str = "v1") -> Path:
    return _work(project, variant) / "render.log"


def _alive(pid: int) -> bool:
    if sys.platform == "win32":
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return str(pid) in r.stdout
    try:
        os.kill(pid, 0)
    except (OSError, ProcessLookupError):
        return False
    return True


def start(project: str, variant: str = "v1", steps: list[str] | None = None) -> dict:
    """Start the build detached; refuse if one is already running for this project."""
    st = read(project, variant)
    if st.get("status") == "running" and _alive(int(st.get("pid", 0))):
        raise RuntimeError(
            f"{project} zaten render ediliyor (pid {st['pid']}): `vlogkit 3d progress {project}`"
        )
    work = _work(project, variant)
    work.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "vlogkit.scene3d.detach", project, variant, *(steps or [])]
    log = log_path(project, variant).open("w", encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    kw: dict = {
        "cwd": REPO_ROOT,
        "stdin": subprocess.DEVNULL,
        "stdout": log,
        "stderr": subprocess.STDOUT,
        "env": env,
    }
    if sys.platform == "win32":
        from vlogkit.winsupport import background_flags

        kw["creationflags"] = background_flags()
    else:
        kw["start_new_session"] = (
            True  # its own session: stopping the agent's shell leaves it alone
        )
    proc = subprocess.Popen(cmd, **kw)
    st = {
        "status": "running",
        "pid": proc.pid,
        "started": time.time(),
        "log": str(log_path(project, variant)),
    }
    state_path(project, variant).write_text(json.dumps(st), encoding="utf-8")
    return st


def read(project: str, variant: str = "v1") -> dict:
    try:
        return json.loads(state_path(project, variant).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


STALL_S = 15 * 60  # no log line for this long: the render is stuck


def progress(project: str, variant: str = "v1") -> dict:
    """{status, frames, total, per_frame, left_s, alive, output, error, log_tail}."""
    st = read(project, variant)
    work = _work(project, variant)
    total = done = 0
    try:
        plan = json.loads((work / "render_plan.json").read_text(encoding="utf-8"))
        since = float(st.get("started", 0))
        for s in plan["shots"]:
            total += s["frames"]
            out = Path(s["out"])
            try:  # finished, for this plan (an older render's frames do not count)
                fin = json.loads((out / "done.json").read_text())["key"] == s.get("key")
            except (OSError, ValueError, KeyError):
                fin = False
            if fin or s.get("reuse"):
                done += s["frames"]
            else:  # in progress: this run's frames, also the ones still in the side folder
                pngs = [*out.glob("*.png"), *out.glob("_anim/*.png")]
                done += sum(1 for f in pngs if f.stat().st_mtime >= since)
    except (OSError, ValueError, KeyError):
        pass
    alive = bool(st.get("pid")) and _alive(int(st["pid"]))
    if st.get("status") == "running" and not alive:
        st["status"] = "killed"  # gone without writing its outcome
    elapsed = time.time() - float(st.get("started", time.time()))
    per = elapsed / done if done and st.get("status") == "running" else None
    # alive but its log has not moved for a long while: stuck (a worker it waits on was killed)
    stalled = False
    with contextlib.suppress(OSError):
        quiet = time.time() - log_path(project, variant).stat().st_mtime
        stalled = st.get("status") == "running" and alive and quiet > STALL_S
    tail: list[str] = []
    with contextlib.suppress(OSError):
        tail = (
            log_path(project, variant)
            .read_text(encoding="utf-8", errors="replace")
            .splitlines()[-6:]
        )
    return {
        **st,
        "alive": alive,
        "stalled": stalled,
        "frames": done,
        "total": total,
        "per_frame": round(per, 2) if per else None,
        "left_s": round(per * (total - done)) if per and total else None,
        "log_tail": tail,
    }


def _worker(project: str, variant: str, steps: list[str]) -> int:
    """The detached process: build, then record the outcome next to the frames."""
    from vlogkit.project import STEPS, load

    if sys.platform == "win32":  # ffmpeg, Blender, the voice model: no windows
        from vlogkit.winsupport import hide_child_windows

        hide_child_windows()

    path = state_path(project, variant)
    st = read(project, variant) | {"pid": os.getpid()}
    try:
        out = load(project, variant).run(steps or STEPS)
        st |= {"status": "done", "ended": time.time(), "output": str(out)}
        code = 0
    except BaseException as e:  # the state file must say what happened, whatever it was
        st |= {"status": "error", "ended": time.time(), "error": f"{type(e).__name__}: {e}"[:2000]}
        code = 1
    path.write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")
    print(f"VK_RENDER {st['status']}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(_worker(sys.argv[1], sys.argv[2], sys.argv[3:]))
