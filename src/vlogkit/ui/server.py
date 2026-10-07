"""Local HTTP server for `vlogkit ui` (stdlib only, binds 127.0.0.1).

Security (a browser tab on any website can send requests to localhost):
  - every /api and /media request must carry the per-run token (header or ?token=) that is only
    embedded in the page this server serves -> other origins cannot read it;
  - the Host header must be 127.0.0.1/localhost (blocks DNS-rebinding);
  - /media only serves files under the vlogs root, the build dir or paths the user picked.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import mimetypes
import os
import secrets
import subprocess
import sys
import threading
import time
from functools import cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from vlogkit import __version__, disk, prompts
from vlogkit.config import BUILD_DIR, RELEASE, REPO_ROOT, VLOGS_ROOT, tools
from vlogkit.ui import codex, history, notify
from vlogkit.ui.runner import (
    DEFAULT_EFFORT,
    DEFAULT_MODEL,
    EFFORTS,
    ENGINES,
    PERMISSION_MODES,
    JobStore,
    is_allowed,
    model_options,
    refresh_claude_models,
)

STATIC = Path(__file__).resolve().parent / "static"
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".webm"}
SKIP_DIRS = {"vlogkit", "node_modules", "build"}
UPLOAD_DIR = VLOGS_ROOT / "studyo-eklenen"  # dropped files that were not found on disk
ATTACH_DIR = BUILD_DIR / "ui" / "attachments"  # images pasted / dropped into a message
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".heif", ".tif", ".tiff"}
DOC_EXT = {".pdf", ".txt", ".md", ".srt", ".json", ".csv"}
# where a dropped file is looked for (browsers never reveal its path), with the search depth
DROP_ROOTS = (
    (VLOGS_ROOT, 4),
    (Path.home() / "Desktop", 3),
    (Path.home() / "Downloads", 3),
    (Path.home() / "Movies", 3),
)


def home_path(p: Path) -> str:
    try:
        return "~/" + str(p.resolve().relative_to(Path.home()))
    except ValueError:
        return str(p)


@cache
def claude_version() -> str | None:
    if not tools().claude:
        return None
    try:
        r = subprocess.run(
            [tools().claude, "--version"], capture_output=True, text=True, timeout=20
        )
        return r.stdout.strip() or None
    except Exception:
        return None


def library() -> list[dict]:
    """Video files under the vlogs root (depth <= 3), grouped by folder."""
    groups: dict[str, list[dict]] = {}
    root = VLOGS_ROOT.resolve()
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root)
        if len(rel.parts) > 3 or any(x.startswith((".", "_")) or x in SKIP_DIRS for x in rel.parts):
            continue
        if p.is_file() and p.suffix.lower() in VIDEO_EXT:
            st = p.stat()
            groups.setdefault(str(rel.parent), []).append(
                {"path": str(p), "name": p.name, "size": st.st_size, "mtime": st.st_mtime}
            )
    for files in groups.values():
        files.sort(key=lambda x: -x["mtime"])  # newest first
    return [
        {"folder": f, "path": str(root / f), "display": home_path(root / f), "files": v}
        for f, v in sorted(groups.items())
    ]


def _walk(root: Path, depth: int):
    base = len(root.parts)
    for dirpath, dirnames, filenames in os.walk(root):
        d = Path(dirpath)
        keep = len(d.parts) - base < depth
        dirnames[:] = [x for x in dirnames if keep and not x.startswith(".") and x not in SKIP_DIRS]
        for n in dirnames + filenames:
            yield d / n


def locate(
    name: str,
    size: int | None = None,
    mtime: float | None = None,
    is_dir: bool = False,
    roots=DROP_ROOTS,
) -> str | None:
    """Find a file (or folder) dropped on the page by its name, size and modification time."""
    name, fallback = Path(name).name, None
    for root, depth in roots:
        if not root.is_dir():
            continue
        for p in _walk(root, depth):
            if p.name != name or p.is_dir() != is_dir:
                continue
            if is_dir:
                return str(p)
            st = p.stat()
            if size is not None and st.st_size != size:
                continue
            if mtime is None or abs(st.st_mtime - mtime) < 3:
                return str(p)
            fallback = fallback or str(p)
    return fallback


def unique_path(p: Path) -> Path:
    n = 2
    out = p
    while out.exists():
        out = p.with_name(f"{p.stem}-{n}{p.suffix}")
        n += 1
    return out


def pick(kind: str) -> str | None:
    """Native macOS open dialog (runs as the logged-in user)."""
    loc = f'default location (POSIX file "{VLOGS_ROOT}")'
    script = (
        f'POSIX path of (choose folder with prompt "Vlog klasörü seç" {loc})'
        if kind == "folder"
        else f'POSIX path of (choose file with prompt "Video seç" of type {{"public.movie"}} {loc})'
    )
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if r.returncode != 0:  # cancelled
        return None
    return r.stdout.strip() or None


def media_info(path: Path) -> dict:
    from vlogkit.ff import probe

    info = probe(path)
    return {
        "path": str(path),
        "display": home_path(path),
        "name": path.name,
        "duration": info.duration,
        "width": info.width,
        "height": info.height,
        "fps": float(info.fps) if info.fps else None,
        "frames": info.frames,
        "has_audio": info.has_audio,
        "vertical": info.vertical,
        "folder": str(path.parent),
        "folder_display": home_path(path.parent),
    }


def contact_sheet(path: Path) -> Path:
    from vlogkit.analysis.sheets import contact_sheet as sheet
    from vlogkit.ff import probe

    st = path.stat()
    key = hashlib.sha1(f"{path}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    out = BUILD_DIR / "ui" / "sheets" / f"{key}.jpg"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        info = probe(path)
        n = 12 if info.vertical else 8
        fps = n / max(info.duration, 1)
        size = (150, 267) if info.vertical else (240, 135)
        sheet(path, out, fps=fps, cols=n, size=size, timestamps=True)
    return out


class Background:
    """Slow, user-triggered analysis (shots of a video, its words) run once per key in a thread;
    the page polls. At most `workers` run at once (each is a full decode); the rest wait. Results
    stay in memory (the oldest are dropped past `keep`); the real caches are on disk."""

    def __init__(self, workers: int = 2, keep: int = 200):
        self.lock = threading.Lock()
        self.state: dict[str, dict] = {}
        self.slots = threading.Semaphore(workers)
        self.keep = keep

    def get(self, key: str, fn) -> dict:
        with self.lock:
            st = self.state.get(key)
            if st is None or (st["status"] == "error" and time.time() - st["at"] > 30):
                st = self.state[key] = {"status": "working", "at": time.time()}
                threading.Thread(target=self._run, args=(key, fn), daemon=True).start()
            return dict(st)

    def _run(self, key: str, fn) -> None:
        with self.slots:
            try:
                result = {"status": "ready", "data": fn()}
            except Exception as e:  # shown to the user, retried after 30 s
                result = {"status": "error", "error": str(e)}
        with self.lock:
            self.state[key] = {**result, "at": time.time()}
            done = [k for k, v in self.state.items() if v["status"] != "working"]
            for k in sorted(done, key=lambda k: self.state[k]["at"])[
                : max(0, len(done) - self.keep)
            ]:
                del self.state[k]

    def forget(self, key: str) -> None:
        with self.lock:
            self.state.pop(key, None)


class App:
    def __init__(self, port: int, jobs_root: Path | None = None):
        self.port = port
        self.token = secrets.token_urlsafe(24)
        self.store = JobStore(jobs_root) if jobs_root else JobStore()
        self.picked: set[Path] = set()
        self.background = Background()
        self.lock = threading.Lock()
        self.httpd: ThreadingHTTPServer | None = None
        self.upgrading: dict = {}  # a running update: status, step / error
        self.store.on_finish = self._finished
        self._sweep()
        # the /model list of the installed Claude Code (cached; refreshed at most twice a day)
        threading.Thread(target=refresh_claude_models, daemon=True).start()

    # ---- updates (installed copies only, see vlogkit/update.py)
    def not_upgrading(self) -> None:
        """New work waits while an update runs: the restart would stop it."""
        if self.upgrading.get("status") in ("running", "restarting"):
            raise RuntimeError("vlogkit güncelleniyor: birazdan tekrar dene")

    def start_update(self, version: str) -> None:
        """Apply the update in the background, then hand the port to a fresh server."""
        from vlogkit import update

        if not update.channel():
            raise RuntimeError("geliştirici kopyası kendini güncellemez (git kullan)")
        if not update.parse(version):
            raise ValueError(f"sürüm: {version}")
        if self.store.busy():
            raise RuntimeError("çalışan iş var: bitince güncelle")
        if self.upgrading.get("status") in ("running", "restarting"):
            raise RuntimeError("güncelleme sürüyor")
        self.upgrading = {"status": "running", "step": "Başlıyor…", "version": version}

        def step(text: str) -> None:
            self.upgrading["step"] = text

        def work() -> None:
            try:
                summary = update.apply(version, log=step)
            except Exception as e:  # nothing restarted: the old version keeps running
                self.upgrading = {"status": "error", "error": str(e)}
                return
            self.upgrading = {"status": "restarting", "step": summary}
            subprocess.Popen(
                [sys.executable, "-m", "vlogkit.ui.launcher", "restart", str(self.port)],
                cwd=REPO_ROOT,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            time.sleep(0.5)  # the page reads "restarting" once more
            self.shutdown()

        threading.Thread(target=work, daemon=True).start()

    def _finished(self, job) -> None:
        turn = job.turns[-1] if job.turns else None
        text = history._OUTPUTS.sub("", turn.result if turn else "").strip()
        first = next((ln.strip(" #*-") for ln in text.splitlines() if ln.strip()), "")
        notify.notify(
            ("Bitti: " if job.status == "done" else "Hata: ") + job.title,
            first[:180],
            f"http://127.0.0.1:{self.port}/#{job.id}",
        )

    def _sweep(self) -> None:
        """Retention rules now and then hourly: old jobs, and the build intermediates of variants
        untouched for N days (never while a job runs: it may be building from them)."""
        with contextlib.suppress(Exception):  # a failed note write must not stop the studio
            self.store.cleanup()
        with contextlib.suppress(Exception):
            days = self.store.clean_days
            if days and not self.store.busy():
                disk.clean(disk.plan(days, disk.units()))
        t = threading.Timer(3600, self._sweep)
        t.daemon = True
        t.start()

    def shutdown(self) -> None:
        for jid in list(self.store.procs):
            self.store.stop(self.store.jobs[jid])
        if self.httpd:
            threading.Thread(target=self.httpd.shutdown, daemon=True).start()

    def media_ok(self, p: Path) -> bool:
        roots = [VLOGS_ROOT.resolve(), BUILD_DIR.resolve()]
        roots += [x if x.is_dir() else x.parent for x in self.picked]
        roots += [Path(d) for j in self.store.jobs.values() for d in j.extra_dirs]
        return is_allowed(p, roots)


def make_handler(app: App) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = f"vlogkit-ui/{__version__}"
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):  # keep the terminal quiet
            pass

        # ---------------------------------------------------------------- helpers
        def _json(self, data, status: int = 200) -> None:
            body = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: int, msg: str) -> None:
            self._json({"error": msg}, status)

        def _body(self) -> dict:
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n else {}

        def _host_ok(self) -> bool:
            host = (self.headers.get("Host") or "").lower()
            return host in {f"127.0.0.1:{app.port}", f"localhost:{app.port}"}

        def _token_ok(self, q: dict) -> bool:
            tok = self.headers.get("X-Vlogkit-Token") or (q.get("token") or [""])[0]
            return secrets.compare_digest(tok, app.token)

        def _route(self, method: str) -> None:
            url = urlparse(self.path)
            q = parse_qs(url.query)
            parts = [p for p in url.path.split("/") if p]
            if not self._host_ok():
                return self._error(HTTPStatus.FORBIDDEN, "host")
            if method == "GET" and url.path in ("/", "/index.html"):
                return self._static("index.html")
            if method == "GET" and parts[:1] == ["static"] and len(parts) == 2:
                return self._static(parts[1])
            if not self._token_ok(q):
                return self._error(HTTPStatus.FORBIDDEN, "token")
            try:
                if parts[:1] == ["media"]:
                    return self._media(Path((q.get("path") or [""])[0]))
                if parts[:1] == ["api"]:
                    return self._api(method, parts[1:], q)
                self._error(HTTPStatus.NOT_FOUND, "yok")
            except (KeyError, FileNotFoundError) as e:
                self._error(HTTPStatus.NOT_FOUND, f"bulunamadı: {e}")
            except (ValueError, RuntimeError) as e:
                self._error(HTTPStatus.BAD_REQUEST, str(e))
            except BrokenPipeError:
                pass

        def do_GET(self):
            self._route("GET")

        def do_POST(self):
            self._route("POST")

        def do_PUT(self):
            self._route("PUT")

        # ---------------------------------------------------------------- static / media
        def _static(self, name: str) -> None:
            f = (STATIC / name).resolve()
            if STATIC.resolve() not in f.parents or not f.is_file():
                return self._error(HTTPStatus.NOT_FOUND, "yok")
            data = f.read_bytes()
            if name == "index.html":
                data = data.replace(b"{{TOKEN}}", app.token.encode())
            ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", f"{ctype}; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _media(self, p: Path) -> None:
            p = p.expanduser()
            if not p.is_file() or not app.media_ok(p):
                return self._error(HTTPStatus.NOT_FOUND, "dosya yok ya da izinli değil")
            size = p.stat().st_size
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if p.suffix.lower() in {".md", ".json", ".txt", ".srt"}:
                ctype = "text/plain; charset=utf-8"
            start, end = 0, size - 1
            rng = self.headers.get("Range")
            if rng and rng.startswith("bytes="):
                a, _, b = rng[6:].partition("-")
                start = int(a) if a else max(0, size - int(b))
                end = int(b) if a and b else size - 1
                end = min(end, size - 1)
                self.send_response(HTTPStatus.PARTIAL_CONTENT)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            with p.open("rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        # ---------------------------------------------------------------- api
        def _api(self, method: str, parts: list[str], q: dict) -> None:
            store = app.store
            match (method, parts):
                case ("GET", ["status"]):
                    from vlogkit import update

                    g = prompts.load()
                    ch = update.channel()
                    if ch and ch["repo"].startswith("https://github.com/"):  # the public guide
                        repo = ch["repo"].removesuffix(".git")
                        g.meta["artifact"] = f"{repo}/blob/main/docs/prompts.md"
                    return self._json(
                        {
                            "vlogkit": __version__,
                            "release": RELEASE,
                            "claude": tools().claude,
                            "claude_version": claude_version(),
                            "api_key_in_env": bool(os.environ.get("ANTHROPIC_API_KEY")),
                            "vlogs_root": str(VLOGS_ROOT),
                            "vlogs_display": home_path(VLOGS_ROOT),
                            "repo": str(REPO_ROOT),
                            "guide": g.meta,
                            "permission_modes": list(PERMISSION_MODES),
                            "models": model_options(),
                            "default_model": DEFAULT_MODEL,
                            "engines": [
                                {
                                    "id": "claude",
                                    "label": "Claude Code",
                                    "available": bool(tools().claude),
                                    "models": model_options(),
                                    "default_model": DEFAULT_MODEL,
                                    "efforts": ["low", "medium", "high", "xhigh", "max"],
                                },
                                {
                                    "id": "codex",
                                    "label": "Codex",
                                    "available": bool(tools().codex),
                                    "models": codex.model_options(),
                                    "default_model": "",
                                    "efforts": list(codex.LEVELS),
                                },
                            ],
                            "retention_days": store.retention_days,
                            "retention_choices": list(history.RETENTION_DAYS),
                            "clean_days": store.clean_days,
                            "clean_choices": list(disk.CLEAN_DAYS),
                            "efforts": list(EFFORTS),
                            "default_effort": DEFAULT_EFFORT,
                        }
                    )
                case ("GET", ["guide"]):
                    g = prompts.load().to_json()
                    if RELEASE:  # an installed copy does not develop vlogkit itself
                        g["stages"] = [st for st in g["stages"] if st["id"] != "sistem"]
                        g["addons"] = [a for a in g["addons"] if "commit" not in a.lower()]
                    return self._json(g)
                case ("GET", ["library"]):
                    return self._json(library())
                case ("POST", ["pick"]):
                    path = pick(self._body().get("kind", "file"))
                    if path:
                        app.picked.add(Path(path).resolve())
                    return self._json({"path": path})
                case ("GET", ["probe"]):
                    p = Path(q["path"][0]).expanduser()
                    if p.is_dir():
                        return self._json(
                            {
                                "path": str(p),
                                "display": home_path(p),
                                "name": p.name,
                                "is_dir": True,
                                "folder": str(p),
                                "folder_display": home_path(p),
                                "videos": sum(
                                    1 for x in p.iterdir() if x.suffix.lower() in VIDEO_EXT
                                ),
                            }
                        )
                    if not p.is_file():
                        raise FileNotFoundError(p)
                    app.picked.add(p.resolve())
                    return self._json(media_info(p))
                case ("GET", ["timeline"]):
                    detect = (q.get("detect") or ["0"])[0] == "1"
                    return self._json(self._timeline(Path(q["path"][0]).expanduser(), detect))
                case ("GET", ["words"]):
                    return self._json(self._words(Path(q["path"][0]).expanduser()))
                case ("GET", ["sheet"]):
                    p = Path(q["path"][0]).expanduser()
                    out = contact_sheet(p)
                    return self._json({"url": f"/media?path={quote(str(out))}"})
                case ("POST", ["locate"]):
                    b = self._body()
                    found = locate(
                        b.get("name") or "", b.get("size"), b.get("mtime"), bool(b.get("dir"))
                    )
                    if found:
                        app.picked.add(Path(found).resolve())
                    return self._json({"path": found})
                case ("PUT", ["upload"]):
                    name = Path((q.get("name") or [""])[0]).name
                    if not name or Path(name).suffix.lower() not in VIDEO_EXT:
                        raise ValueError("sadece video dosyası yüklenebilir")
                    left = int(self.headers.get("Content-Length") or 0)
                    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
                    dest = unique_path(UPLOAD_DIR / name)
                    part = dest.with_name(dest.name + ".part")
                    with part.open("wb") as f:
                        while left > 0:
                            chunk = self.rfile.read(min(1 << 20, left))
                            if not chunk:
                                break
                            f.write(chunk)
                            left -= len(chunk)
                    if left:
                        part.unlink(missing_ok=True)
                        raise ValueError("yükleme yarım kaldı")
                    part.replace(dest)
                    app.picked.add(dest.resolve())
                    return self._json({"path": str(dest)})
                case ("PUT", ["attach"]):
                    return self._json(self._attach(q))
                case ("POST", ["reveal"]):
                    p = Path(self._body().get("path", "")).expanduser()
                    if not p.exists() or not app.media_ok(p):
                        raise FileNotFoundError(p)
                    subprocess.run(["open", "-R", str(p)], check=False)
                    return self._json({"ok": True})
                case ("GET", ["setup"]):
                    from vlogkit import update
                    from vlogkit.ui import setup

                    fresh = (q.get("fresh") or ["0"])[0] == "1"
                    if update.channel():  # developer tools arrived with Homebrew: updates via git
                        with contextlib.suppress(Exception):
                            update.adopt()
                    return self._json(
                        {
                            "agents": setup.agents(fresh),
                            "steps": setup.steps(),
                            "models": setup.models(),
                            "tasks": dict(setup.tasks),
                            "release": bool(update.channel()),
                        }
                    )
                case ("POST", ["setup", "step"]):
                    from vlogkit.ui import setup

                    setup.run_step(str(self._body().get("id") or ""))
                    return self._json({"ok": True})
                case ("POST", ["setup", "agent"]):
                    from vlogkit.ui import setup

                    b = self._body()
                    name = str(b.get("name"))
                    if b.get("action") == "install":
                        setup.install_agent(name)
                    elif b.get("action") == "login":
                        setup.open_login(name)
                    else:
                        raise ValueError("işlem: install | login")
                    return self._json({"ok": True})
                case ("POST", ["setup", "model"]):
                    from vlogkit.analysis import localvlm
                    from vlogkit.ui import setup

                    b = self._body()
                    key, action = b.get("id"), b.get("action")
                    if action == "install":
                        setup.install_model(str(key))
                    elif action == "remove":
                        if store.busy():  # a running job may be using the model
                            raise RuntimeError("çalışan iş varken model kaldırılmaz")
                        setup.remove_model(str(key))
                    elif action == "select":
                        localvlm.choose(str(key) if key else None)
                    else:
                        raise ValueError("işlem: install | remove | select")
                    return self._json(setup.models())
                case ("GET", ["update"]):
                    from vlogkit import update

                    force = (q.get("force") or ["0"])[0] == "1"  # cached for hours otherwise
                    return self._json({**update.check(force), "upgrading": app.upgrading})
                case ("POST", ["update"]):
                    app.start_update(str(self._body().get("version") or ""))
                    return self._json({"ok": True})
                case ("GET", ["uninstall"]):
                    from vlogkit import uninstall

                    mode = (q.get("mode") or ["app"])[0]
                    return self._json({"allowed": uninstall.allowed(), **uninstall.plan(mode)})
                case ("POST", ["uninstall"]):
                    from vlogkit import uninstall

                    if store.busy():
                        raise RuntimeError("çalışan iş varken kaldırılmaz: önce durdur")
                    app.not_upgrading()
                    mode = str(self._body().get("mode") or "")
                    if mode not in uninstall.MODES:
                        raise ValueError(f"kaldırma: {mode}")
                    backup = uninstall.start(mode)
                    self._json({"ok": True, "backup": str(backup)})
                    app.shutdown()
                    return None
                case ("POST", ["shutdown"]):
                    self._json({"ok": True})
                    app.shutdown()
                    return None
                case ("GET", ["jobs"]):
                    return self._json(store.list())
                case ("POST", ["jobs"]):
                    b = self._body()
                    prompt = (b.get("prompt") or "").strip()
                    if not prompt:
                        raise ValueError("prompt boş")
                    app.not_upgrading()
                    engine = b.get("engine") or "claude"
                    if engine not in ENGINES:
                        raise ValueError(f"motor: {engine}")
                    job = store.create(
                        b.get("title") or "İş",
                        b.get("video"),
                        b.get("permission_mode") or "acceptEdits",
                        b.get("model") or (DEFAULT_MODEL if engine == "claude" else None),
                        b.get("effort") or DEFAULT_EFFORT,
                        engine,
                    )
                    store.send(job, prompt, self._files(b))
                    return self._json({"id": job.id})
                case ("GET", ["jobs", jid]):
                    from dataclasses import asdict

                    return self._json(asdict(store.jobs[jid]))
                case ("POST", ["jobs", jid, "send"]):
                    app.not_upgrading()
                    b = self._body()
                    files = self._files(b)
                    prompt = (b.get("prompt") or "").strip() or (
                        "Ekteki dosyalara bak." if files else ""
                    )
                    if not prompt:
                        raise ValueError("mesaj boş")
                    queued = store.send(store.jobs[jid], prompt, files)
                    return self._json({"ok": True, "queued": queued})
                case ("POST", ["jobs", jid, "edit"]):
                    app.not_upgrading()
                    b = self._body()
                    prompt = (b.get("prompt") or "").strip()
                    if not prompt:
                        raise ValueError("mesaj boş")
                    store.edit(store.jobs[jid], int(b.get("turn", -1)), prompt, self._files(b))
                    return self._json({"ok": True})
                case ("POST", ["jobs", jid, "effort"]):
                    when = store.set_effort(store.jobs[jid], str(self._body().get("effort", "")))
                    return self._json({"ok": True, "when": when})
                case ("POST", ["jobs", jid, "queue", "delete"]):
                    store.unqueue(store.jobs[jid], int(self._body().get("index", -1)))
                    return self._json({"ok": True})
                case ("POST", ["jobs", jid, "queue", "send"]):
                    return self._json({"ok": store.flush(store.jobs[jid])})
                case ("POST", ["jobs", jid, "stop"]):
                    store.stop(store.jobs[jid])
                    return self._json({"ok": True})
                case ("POST", ["jobs", jid, "delete"]):
                    note = store.delete(store.jobs[jid])
                    return self._json({"ok": True, "note": str(note) if note else None})
                case ("POST", ["jobs", jid, "pin"]):
                    store.pin(store.jobs[jid], bool(self._body().get("pinned")))
                    return self._json({"ok": True})
                case ("POST", ["settings"]):
                    b = self._body()
                    if "retention_days" in b:
                        store.set_retention(int(b["retention_days"]))
                        store.cleanup()
                    if "clean_days" in b:
                        store.set_clean_days(int(b["clean_days"]))
                    return self._json(
                        {"retention_days": store.retention_days, "clean_days": store.clean_days}
                    )
                case ("GET", ["disk"]):
                    return self._json(self._disk())
                case ("POST", ["disk", "clean"]):
                    if store.busy():
                        raise RuntimeError("çalışan iş varken temizlenmez: bitince dene")
                    days = int(self._body().get("days", 7))
                    freed = disk.clean(disk.plan(days, disk.units()))
                    return self._json({"freed": freed, **self._disk()})
                case ("GET", ["jobs", jid, "events"]):
                    return self._events(store.jobs[jid], int((q.get("after") or ["0"])[0]))
            self._error(HTTPStatus.NOT_FOUND, "api yok")

        def _disk(self) -> dict:
            """Free space and what the cleanup would free (the setting's days, else 7)."""
            days = app.store.clean_days or 7
            units = disk.units()
            files, freed = disk.removable(disk.plan(days, units))
            return {
                "free": disk.free_bytes(),
                "low": disk.LOW,
                "build": disk.total(units),
                "days": days,
                "files": len(files),
                "cleanable": freed,
            }

        def _video(self, p: Path) -> Path:
            if not p.is_file() or not app.media_ok(p):
                raise FileNotFoundError(p)
            return p.resolve()

        def _timeline(self, p: Path, detect: bool = False) -> dict:
            """The edit's tracks for the video under the player. Shots missing (no cut list in
            the build, or not a vlogkit build) are detected only when asked (detect=1: the user
            played the video), never just because a chat was opened."""
            from vlogkit.export import timeline

            p = self._video(p)
            data = timeline.load(p)
            if data and not data.get("stale") and timeline.track(data, "shots"):
                return {"status": "ready", **data}
            if not detect:
                return {"status": "idle", **(data or {})}
            st = os.stat(p)
            key = f"timeline:{p}:{st.st_size}:{st.st_mtime}"
            res = app.background.get(key, lambda: timeline.ensure_shots(p))
            if res["status"] == "ready":
                return {"status": "ready", **res["data"]}
            return {"status": res["status"], "error": res.get("error"), **(data or {})}

        def _words(self, p: Path) -> dict:
            """The video's words (whisper, cached on disk), for cutting by word."""
            from vlogkit.export import timeline

            p = self._video(p)
            st = os.stat(p)
            res = app.background.get(
                f"words:{p}:{st.st_size}:{st.st_mtime}", lambda: timeline.words(p)
            )
            return {"status": res["status"], "error": res.get("error"), "words": res.get("data")}

        def _attach(self, q: dict) -> dict:
            """Store an image/document sent with a message; HEIC becomes JPEG (agents read it)."""
            name = Path((q.get("name") or [""])[0]).name
            ext = Path(name).suffix.lower()
            if not name or ext not in IMAGE_EXT | DOC_EXT:
                raise ValueError("desteklenmeyen dosya: görsel ya da belge ekle")
            left = int(self.headers.get("Content-Length") or 0)
            if left > 200 * 1024 * 1024:
                raise ValueError("dosya çok büyük (en fazla 200 MB)")
            folder = ATTACH_DIR / time.strftime("%Y%m%d")
            folder.mkdir(parents=True, exist_ok=True)
            safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(name).stem)[:60]
            dest = folder / f"{secrets.token_hex(4)}-{safe}{ext}"
            with dest.open("wb") as f:
                while left > 0:
                    chunk = self.rfile.read(min(1 << 20, left))
                    if not chunk:
                        break
                    f.write(chunk)
                    left -= len(chunk)
            if left:
                dest.unlink(missing_ok=True)
                raise ValueError("yükleme yarım kaldı")
            if ext in (".heic", ".heif", ".tif", ".tiff"):
                jpg = dest.with_suffix(".jpg")
                r = subprocess.run(
                    ["sips", "-s", "format", "jpeg", str(dest), "--out", str(jpg)],
                    capture_output=True,
                )
                if r.returncode == 0 and jpg.exists():
                    dest.unlink(missing_ok=True)
                    dest = jpg
            kind = "image" if dest.suffix.lower() in IMAGE_EXT else "text"
            return {"path": str(dest), "name": name, "kind": kind}

        def _files(self, b: dict) -> list[str]:
            """Attachments of a message: existing files the studio is allowed to serve."""
            out = []
            for f in b.get("attachments") or []:
                p = Path(str(f)).expanduser()
                if p.is_file() and app.media_ok(p):
                    out.append(str(p.resolve()))
            return out

        def _events(self, job, after: int) -> None:
            """Server-sent events until the running turn finishes."""
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            if after > len(job.events):  # the job was rewritten (an edited message): start over
                self.wfile.write(b"event: reset\ndata: {}\n\n")
                self.wfile.flush()
                return
            last_ping = time.time()
            while True:
                events = app.store.wait(job, after)
                for ev in events:
                    self.wfile.write(f"data: {json.dumps(ev, ensure_ascii=False)}\n\n".encode())
                after += len(events)
                if not events and time.time() - last_ping > 10:
                    self.wfile.write(b": ping\n\n")
                    last_ping = time.time()
                self.wfile.flush()
                if job.status != "running" and after >= len(job.events):
                    self.wfile.write(b"event: end\ndata: {}\n\n")
                    self.wfile.flush()
                    return

    return Handler


def serve(port: int = 8765, open_browser: bool = True) -> None:
    app = App(port)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    app.httpd = httpd
    httpd.daemon_threads = True
    url = f"http://127.0.0.1:{port}/"
    print(f"vlogkit ui -> {url}   (durdurmak için Ctrl+C)")
    if not tools().claude:
        print("⚠️  claude CLI bulunamadı: işler çalıştırılamaz.")
    if open_browser:
        import webbrowser

        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nkapatılıyor…")
        for jid in list(app.store.procs):
            app.store.stop(app.store.jobs[jid])
    finally:
        httpd.server_close()
