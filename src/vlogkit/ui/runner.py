"""Run an agent CLI headless for UI jobs: Claude Code (`claude -p … --output-format stream-json`)
by default, or Codex (`codex exec --json`, see ui/codex.py).

A job is one agent session (one video task). Each message the user sends is a *turn*: the first
turn starts the session, later turns resume it (`--resume <session_id>`), so "plan first, then
build after I approve" works across turns. If the CLI has deleted the old session, the turn
starts a new one with a summary of the earlier turns (ui/history.py).

Auth: the subprocess environment drops ANTHROPIC_API_KEY / ANTHROPIC_AUTH_TOKEN, so the CLI uses
the machine's logged-in Claude subscription instead of API billing.
"""

from __future__ import annotations

import contextlib
import json
import os
import re
import shutil
import subprocess
import threading
import time
import uuid
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from vlogkit import disk
from vlogkit.config import BUILD_DIR, RELEASE, REPO_ROOT, VLOGS_ROOT, tools
from vlogkit.ui import codex, history

ENGINES = ("claude", "codex")
PERMISSION_MODES = ("acceptEdits", "auto", "dontAsk", "bypassPermissions")
PERMISSIONS_FILE = REPO_ROOT / ".claude" / "settings.json"  # allow/deny list for UI runs

# Models: the same list Claude Code's own /model menu shows. The CLI answers an SDK "initialize"
# control request with it (no model call); the answer is cached in build/ui/claude-models.json and
# refreshed in the background. Aliases ("opus", "sonnet") always resolve to the newest model of
# the family. Our default is Opus with the 1M context window, kept on top of the list.
DEFAULT_MODEL = "opus[1m]"
MODEL_SEEN = BUILD_DIR / "ui" / "models.json"  # alias -> model id the CLI reported (labels)
MODELS_CACHE = BUILD_DIR / "ui" / "claude-models.json"
MODELS_MAX_AGE = 12 * 3600
_SEED = {"opus[1m]": "claude-opus-5-5[1m]"}
_FALLBACK = [  # until the CLI has answered once (verified 2026-09-28)
    {"id": "opus", "label": "Opus 5.5", "model": "claude-opus-5-5"},
    {"id": "claude-fable-5-1", "label": "Fable 5.1", "model": "claude-fable-5-1"},
    {"id": "sonnet", "label": "Sonnet 5.5", "model": "claude-sonnet-5-5"},
    {"id": "haiku", "label": "Haiku 4.5", "model": "claude-haiku-4-5-20251001"},
]
EFFORTS = (
    "low",
    "medium",
    "high",
    "xhigh",
    "max",
    "ultra",
)  # all engines; each model lists its own
DEFAULT_EFFORT = "xhigh"
EFFORT_NAMES = {"low": "Düşük", "medium": "Orta", "high": "Yüksek", "xhigh": "Extra high",
                "max": "Maks", "ultra": "Ultra"}  # fmt: skip
EFFORT_ORDER = {e: i for i, e in enumerate(EFFORTS)}


def model_label(model_id: str) -> str:
    """claude-opus-5-5[1m] -> 'Opus 5.5 · 1M', claude-sonnet-5 -> 'Sonnet 5'."""
    m = re.match(r"claude-([a-z]+)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?(\[1m\])?$", model_id or "")
    if not m:
        return model_id
    family, major, minor, big = m.groups()
    name = f"{family.capitalize()} {major}{'.' + minor if minor else ''}"
    return name + (" · 1M" if big else "")


def seen_models() -> dict[str, str]:
    try:
        return {**_SEED, **json.loads(MODEL_SEEN.read_text())}
    except (OSError, ValueError):
        return dict(_SEED)


def remember_model(alias: str, model_id: str) -> None:
    if not re.match(r"claude-[a-z]+-\d", model_id or ""):
        return  # only learn real Claude model ids
    seen = seen_models()
    if seen.get(alias) != model_id:
        seen[alias] = model_id
        MODEL_SEEN.parent.mkdir(parents=True, exist_ok=True)
        MODEL_SEEN.write_text(json.dumps(seen, indent=2))


def fetch_claude_models(timeout: float = 40) -> list[dict] | None:
    """Ask the installed CLI for its /model list (an SDK initialize request; no tokens used)."""
    claude = tools().claude
    if not claude:
        return None
    try:
        proc = subprocess.Popen(
            [
                claude,
                "-p",
                "--input-format",
                "stream-json",
                "--output-format",
                "stream-json",
                "--verbose",
            ],
            cwd=REPO_ROOT,
            env=subscription_env(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
        )
    except OSError:
        return None
    timer = threading.Timer(timeout, proc.kill)
    timer.start()
    try:
        req = {
            "type": "control_request",
            "request_id": "models",
            "request": {"subtype": "initialize"},
        }
        proc.stdin.write(json.dumps(req) + "\n")
        proc.stdin.flush()
        for line in proc.stdout:
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if obj.get("type") == "control_response":
                models = (obj.get("response") or {}).get("response", {}).get("models") or []
                return [
                    {
                        "id": m["value"],
                        "label": m.get("displayName") or m["value"],
                        "description": m.get("description", ""),
                        "model": m.get("resolvedModel", ""),
                        "efforts": m.get("supportedEffortLevels") or [],
                    }
                    for m in models
                    if m.get("value") and m["value"] != "default"  # "default" is Opus again
                ] or None
        return None
    except (OSError, ValueError):
        return None
    finally:
        timer.cancel()
        proc.kill()
        proc.wait()


def refresh_claude_models(force: bool = False) -> None:
    try:
        age = time.time() - json.loads(MODELS_CACHE.read_text())["fetched"]
    except (OSError, ValueError, KeyError):
        age = float("inf")
    if not force and age < MODELS_MAX_AGE:
        return
    models = fetch_claude_models()
    if models:
        MODELS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        MODELS_CACHE.write_text(json.dumps({"fetched": time.time(), "models": models}, indent=2))


def model_options() -> list[dict]:
    try:
        models = json.loads(MODELS_CACHE.read_text())["models"]
    except (OSError, ValueError, KeyError):
        models = _FALLBACK
    opus = next((m for m in models if m["id"] == "opus"), None)
    seen = seen_models().get(DEFAULT_MODEL)
    label = model_label(seen) if seen else f"{opus['label'] if opus else 'Opus'} · 1M"
    top = {
        "id": DEFAULT_MODEL,
        "label": label,
        "description": "1M bağlam, uzun işler için",
        "efforts": (opus or {}).get("efforts"),  # None = unknown (fallback list)
    }
    return [top, *(m for m in models if m["id"] != DEFAULT_MODEL)]


MEDIA_EXT = {
    ".mp4": "video",
    ".mov": "video",
    ".m4v": "video",
    ".webm": "video",
    ".png": "image",
    ".jpg": "image",
    ".jpeg": "image",
    ".gif": "image",
    ".webp": "image",
    ".wav": "audio",
    ".mp3": "audio",
    ".m4a": "audio",
    ".md": "text",
    ".json": "text",
    ".txt": "text",
    ".html": "text",
    ".srt": "text",
}
_PATH = re.compile(
    r"(?:(?<=\s)|^|(?<=[`'\"(]))((?:/|~/)[^\s`'\"()<>]+?\.(?:"
    + "|".join(e[1:] for e in MEDIA_EXT)
    + r"))(?=$|[\s`'\"),.;:])",
    re.M,
)

UI_SYSTEM_PROMPT = """\
Bu oturum `vlogkit ui` arayüzünden başlatıldı ve headless çalışıyor. Kullanıcı ekranda \
yalnızca senin metin mesajlarını ve araç adımlarını görüyor; anlık soru-cevap ve izin penceresi yok.
- Kullanıcıdan bir karar ya da bilgi gerekiyorsa işi o noktada bitir ve son mesajında net, numaralı \
sorularla sor. Kullanıcı arayüzden yanıt yazacak, oturum kaldığı yerden devam edecek. \
AskUserQuestion ve plan modu kullanma; skill'lerin etkileşimli soru/onay adımlarını atla, bu kural \
onlardan önce gelir.
- Bir komut izin kurallarına takılıp reddedilirse izin verilen başka bir yolla dene (ör. `uv run \
vlogkit ...`). Olmuyorsa son mesajda hangi iznin gerektiğini yaz.
- Kullanıcıya Türkçe yaz, kısa ve net ol. Mesajlarında emoji kullanma; videodaki emoji \
kullanımında CLAUDE.md'deki emoji kuralına uy.
- Bu iş için gerekmeyen ama vlogkit'e eklenirse sonraki editlerde işe yarayacak bir şey fark \
edersen (yeni efekt, araç, ön ayar, arayüz iyileştirmesi) son mesajında "Öneri:" ile başlayan tek \
satırda söyle ve kendiliğinden yapma. Kullanıcı "öneriyi uygula" derse CLAUDE.md'deki "vlogkit'i \
geliştirince" adımlarıyla ekle.
- Kullanıcının dinleyerek ya da bakarak seçmesi gereken seçeneklerde (müzik, kapak, renk) son \
mesajında "Seçim: <soru>" satırı ve altına "1. <etiket> — /mutlak/yol" maddeleri yaz: arayüz \
bunları önizlemeli kart olarak gösterir. Müzik için bu bloğu `vlogkit music` hazır verir.
- Son mesajının en sonunda, bu turda ürettiğin ya da güncellediğin dosyaları mutlak yollarıyla \
"Çıktılar:" başlığı altında madde madde listele (video, görsel, rapor). Arayüz bunları önizler.\
"""
if RELEASE:  # an installed copy: updates replace vlogkit's own files, so leave them alone
    UI_SYSTEM_PROMPT += """
- Bu bir kullanıcı kurulumu, güncellemelerle gelir: vlogkit'in kendi dosyalarını (src/, tools/, \
docs/, CLAUDE.md, assets/manifest.toml) değiştirme, commit atma. İşi projects/<proje>/ altında yap; \
yeni lisanslı medyayı assets/manifest.local.toml'a yaz. vlogkit'te eksik bir şey görürsen yalnız \
"Öneri:" satırı yaz, kullanıcı geliştiriciye iletir.\
"""


# --------------------------------------------------------------------------- stream-json -> events
def _summary(name: str, inp: dict) -> str:
    if name == "Bash":
        return inp.get("command", "")
    for key in ("file_path", "path", "pattern", "url", "skill", "description", "query", "prompt"):
        if inp.get(key):
            return str(inp[key])
    return ""


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""


def translate(obj: dict) -> list[dict]:
    """One stream-json object -> zero or more UI events (without index/timestamps)."""
    t = obj.get("type")
    if t == "system" and obj.get("subtype") == "init":
        src = obj.get("apiKeySource") or "none"
        auth = "abonelik" if src == "none" else f"API anahtarı ({src})"
        return [
            {
                "kind": "system",
                "session_id": obj.get("session_id"),
                "model": obj.get("model"),
                "text": f"Oturum başladı · model {obj.get('model', '?')} · {auth}",
                "auth": auth,
            }
        ]
    if t == "assistant":
        events = []
        for c in obj.get("message", {}).get("content", []):
            if c.get("type") == "text" and c.get("text", "").strip():
                events.append({"kind": "text", "text": c["text"]})
            elif c.get("type") == "tool_use":
                inp = c.get("input") or {}
                events.append(
                    {
                        "kind": "tool",
                        "id": c.get("id"),
                        "name": c.get("name", "?"),
                        "summary": _summary(c.get("name", ""), inp)[:600],
                    }
                )
        return events
    if t == "user":
        events = []
        content = obj.get("message", {}).get("content", [])
        for c in content if isinstance(content, list) else []:
            if c.get("type") == "tool_result":
                text = _text_of(c.get("content"))
                events.append(
                    {
                        "kind": "tool_result",
                        "id": c.get("tool_use_id"),
                        "ok": not c.get("is_error", False),
                        "preview": text[:800],
                    }
                )
        return events
    if t == "result":
        return [
            {
                "kind": "result",
                "ok": not obj.get("is_error", False) and obj.get("subtype") == "success",
                "subtype": obj.get("subtype"),
                "text": obj.get("result") or "",
                "session_id": obj.get("session_id"),
                "cost_usd": obj.get("total_cost_usd"),
                "duration_ms": obj.get("duration_ms"),
                "num_turns": obj.get("num_turns"),
            }
        ]
    if t == "stream_event":
        # Only with --include-partial-messages. Headless mode never exposes the thinking text,
        # but a block starting tells the UI what Claude is doing right now.
        ev = obj.get("event") or {}
        if ev.get("type") == "content_block_start":
            block = ev.get("content_block") or {}
            kind = {"thinking": "thinking", "redacted_thinking": "thinking", "text": "writing"}
            if block.get("type") in kind:
                return [{"kind": "activity", "state": kind[block["type"]]}]
            if block.get("type") in ("tool_use", "server_tool_use"):
                return [{"kind": "activity", "state": "tool", "name": block.get("name", "")}]
        return []
    if t == "rate_limit_event":
        info = obj.get("rate_limit_info") or {}
        if info.get("status") not in (None, "allowed"):
            return [{"kind": "system", "text": f"Kullanım limiti: {info.get('status')}"}]
    return []


def allowed_roots() -> list[Path]:
    return [VLOGS_ROOT.resolve(), BUILD_DIR.resolve()]


def is_allowed(path: Path, roots: list[Path] | None = None) -> bool:
    p = path.expanduser().resolve()
    return any(p == r or r in p.parents for r in roots or allowed_roots())


def find_outputs(text: str, extra_roots: list[Path] | None = None) -> list[dict]:
    """Existing media/report files mentioned in Claude's final message (for previews)."""
    roots = allowed_roots() + [Path(r).resolve() for r in extra_roots or []]
    seen, out = set(), []
    for m in _PATH.finditer(text):
        p = Path(m.group(1)).expanduser()
        if p in seen or not p.is_file() or not is_allowed(p, roots):
            continue
        seen.add(p)
        out.append({"path": str(p), "kind": MEDIA_EXT.get(p.suffix.lower(), "text")})
    return out


# --------------------------------------------------------------------------- jobs
@dataclass
class Turn:
    prompt: str
    started: float
    ended: float | None = None
    ok: bool | None = None
    result: str = ""
    cost_usd: float | None = None
    duration_ms: int | None = None


@dataclass
class Job:
    id: str
    title: str
    created: float
    video: str | None = None
    permission_mode: str = "acceptEdits"
    engine: str = "claude"
    model: str | None = None
    effort: str | None = None
    extra_dirs: list[str] = field(default_factory=list)
    session_id: str | None = None
    status: str = "idle"  # running | done | error | stopped | interrupted
    pinned: bool = False  # never removed by the retention rule
    queue: list[dict] = field(default_factory=list)  # {"text", "files"} sent while running
    # turns dropped by editing an earlier message: {"at", "ts", "turns": [Turn as dict]}
    branches: list[dict] = field(default_factory=list)
    turns: list[Turn] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)

    def summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "created": self.created,
            "status": self.status,
            "engine": self.engine,
            "pinned": self.pinned,
            "video": self.video,
            "turns": len(self.turns),
            "cost_usd": sum(t.cost_usd or 0 for t in self.turns),
            "queued": len(self.queue),
            # latest activity: a new message or an answer moves the chat to the top
            "updated": max(
                [
                    self.created,
                    *(t.started for t in self.turns),
                    *(t.ended or 0 for t in self.turns),
                ]
                + ([self.events[-1].get("ts", 0)] if self.events else [])
            ),
        }


def claude_command(job: Job, prompt: str | None = None) -> list[str]:
    """The prompt itself goes to stdin (see `_run`): as an argument, a message starting with "-"
    was taken for an option ("error: unknown option '- 7 için ...'") and very long messages
    could hit the argument size limit."""
    claude = tools().claude
    if not claude:
        raise RuntimeError("claude CLI bulunamadı (Claude Code kurulu mu?)")
    cmd = [
        claude,
        "-p",
        "--output-format",
        "stream-json",
        # messages go in as JSON lines and stdin stays open while the turn runs: a message
        # written meanwhile reaches Claude at its next tool boundary (like the Claude Code CLI);
        # its replay on stdout says when it was taken
        "--input-format",
        "stream-json",
        "--replay-user-messages",
        "--verbose",
        "--include-partial-messages",
        "--permission-mode",
        job.permission_mode,
        "--add-dir",
        str(VLOGS_ROOT),
        "--append-system-prompt",
        UI_SYSTEM_PROMPT,
    ]
    # Project .claude/settings.json is ignored while the folder has never been "trusted" in an
    # interactive session (and -p cannot show that dialog), so hand the allow/deny list over
    # explicitly: flag settings are trusted because the caller chose them.
    if PERMISSIONS_FILE.exists():
        cmd += ["--settings", str(PERMISSIONS_FILE)]
    for d in job.extra_dirs:
        cmd += ["--add-dir", d]
    effort = claude_effort(job)
    if effort:
        cmd += ["--effort", effort]
    if job.model:
        cmd += ["--model", job.model]
    if job.session_id:
        cmd += ["--resume", job.session_id]
    return cmd


TAKE_WAIT = 45.0  # s after an answer: a message written to Claude but not taken by then is resent
EDIT_TOOLS = (
    "Edit",
    "Write",
    "MultiEdit",
    "NotebookEdit",
    "apply_patch",
)  # tools that change files


def claude_effort(job) -> str | None:
    """The job's effort as the model takes it (the nearest lower level it has); None for a model
    without levels (Haiku)."""
    info = next((m for m in model_options() if m["id"] == (job.model or DEFAULT_MODEL)), None)
    supported = info.get("efforts") if info else None
    if not job.effort or supported == []:  # [] = the model has no effort levels
        return None
    return codex.clamp_effort(supported or [], job.effort)


def control_line(subtype: str, **fields) -> str:
    """A control request for `--input-format stream-json` (the SDK's channel)."""
    req = {"type": "control_request", "request_id": str(uuid.uuid4())}
    return json.dumps(req | {"request": {"subtype": subtype, **fields}}) + "\n"


def user_line(text: str, uid: str) -> str:
    """One user message for `--input-format stream-json`. Claude replays it with the same uuid
    when it takes it (`--replay-user-messages`), also when it merges several into one turn."""
    msg = {"type": "user", "uuid": uid, "message": {"role": "user", "content": text}}
    return json.dumps(msg) + "\n"


def _keep_awake(pid: int) -> None:
    """macOS: no idle sleep while the agent runs (a sleeping Mac pauses the job). Display may sleep."""
    caffeinate = shutil.which("caffeinate")
    if caffeinate and os.environ.get("VLOGKIT_CAFFEINATE", "1") != "0":
        with contextlib.suppress(OSError):
            subprocess.Popen(
                [caffeinate, "-i", "-w", str(pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )


def _merge(queue: list) -> tuple[str, list[str]]:
    """Queued messages -> one message (texts in order, all attachments)."""
    items = [q if isinstance(q, dict) else {"text": str(q), "files": []} for q in queue]
    return "\n\n".join(i["text"] for i in items), [f for i in items for f in i.get("files", [])]


def attachment_block(files: Sequence[str], engine: str = "claude") -> str:
    """The attachments of a message, as text the agent acts on (paths it can open)."""
    if not files:
        return ""
    tool = "view_image" if engine == "codex" else "Read"
    return (
        f"\n\nEkler (bu mesajla verildi; görsellere {tool} aracıyla bak, videolara "
        "ffprobe / vlogkit sheet ile):\n" + "\n".join(f"- {f}" for f in files)
    )


def claude_session_exists(session_id: str) -> bool:
    home = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    return any((home / "projects").glob(f"*/{session_id}.jsonl"))


def subscription_env() -> dict[str, str]:
    env = {
        k: v
        for k, v in os.environ.items()
        if k not in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
    }
    env.setdefault("NO_COLOR", "1")
    return env


class JobStore:
    """In-memory jobs + JSON files in build/ui/jobs (survives UI restarts)."""

    def __init__(self, root: Path = BUILD_DIR / "ui" / "jobs"):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.settings_file = root.parent / "settings.json"
        self.on_finish = None  # callback(job) when a turn ends on its own (not stopped)
        self.jobs: dict[str, Job] = {}
        self.procs: dict[str, subprocess.Popen] = {}
        # Claude jobs whose stdin is still open: messages written now join the running turn
        self.live: dict[str, Any] = {}
        self.stopping: set[str] = (
            set()
        )  # stop requested; final status is set when the process exits
        self.cond = threading.Condition()
        for f in sorted(self.root.glob("*.json")):
            try:
                d = json.loads(f.read_text())
                d["turns"] = [Turn(**t) for t in d.get("turns", [])]
                job = Job(**d)
                if job.status == "running":
                    job.status = "interrupted"
                for q in job.queue:  # written to a process that is gone: plain queue items now
                    q.pop("sent", None)
                    q.pop("uuid", None)
                self.jobs[job.id] = job
            except Exception:  # a corrupt file must not break the UI
                continue

    # ---- persistence / events
    def save(self, job: Job) -> None:
        tmp = self.root / f"{job.id}.json.tmp"
        tmp.write_text(json.dumps(asdict(job), ensure_ascii=False))
        tmp.replace(self.root / f"{job.id}.json")

    def emit(self, job: Job, event: dict) -> None:
        with self.cond:
            event = {"i": len(job.events), "ts": time.time(), "turn": len(job.turns) - 1, **event}
            job.events.append(event)
            self.cond.notify_all()

    def wait(self, job: Job, after: int, timeout: float = 15.0) -> list[dict]:
        with self.cond:
            if len(job.events) <= after and job.status == "running":
                self.cond.wait(timeout)
            return job.events[after:]

    # ---- settings / history
    def _setting(self, key: str) -> int:
        try:
            return int(json.loads(self.settings_file.read_text()).get(key, 0))
        except (OSError, ValueError, TypeError, AttributeError):
            return 0

    def _set(self, key: str, value: int) -> None:
        try:
            data = json.loads(self.settings_file.read_text())
        except (OSError, ValueError):
            data = {}
        self.settings_file.write_text(json.dumps({**data, key: value}))

    @property
    def retention_days(self) -> int:
        return self._setting("retention_days")

    def set_retention(self, days: int) -> None:
        if days not in history.RETENTION_DAYS:
            raise ValueError(f"saklama süresi: {days}")
        self._set("retention_days", days)

    @property
    def clean_days(self) -> int:
        """Build intermediates untouched this many days are deleted hourly (0 = by hand)."""
        return self._setting("clean_days")

    def set_clean_days(self, days: int) -> None:
        if days not in disk.CLEAN_DAYS:
            raise ValueError(f"ara dosya süresi: {days}")
        self._set("clean_days", days)

    def busy(self) -> bool:
        return any(j.status == "running" for j in self.jobs.values())

    def pin(self, job: Job, on: bool) -> None:
        job.pinned = on
        self.save(job)

    def delete(self, job: Job) -> Path | None:
        """Remove a job; its digest stays in the work folder (VLOGKIT-NOTLAR.md)."""
        if job.status == "running":
            raise RuntimeError("çalışan iş silinemez, önce durdur")
        note = history.write_note(job)
        (self.root / f"{job.id}.json").unlink(missing_ok=True)
        self.jobs.pop(job.id, None)
        return note

    def cleanup(self, now: float | None = None) -> list[str]:
        """Apply the retention rule: unpinned jobs idle for longer than N days go."""
        days = self.retention_days
        gone = [j for j in list(self.jobs.values()) if history.expired(j, days, now)]
        for j in gone:
            self.delete(j)
        return [j.id for j in gone]

    # ---- api
    def list(self) -> list[dict]:
        return sorted((j.summary() for j in self.jobs.values()), key=lambda s: -s["updated"])

    def create(
        self,
        title: str,
        video: str | None,
        permission_mode: str,
        model: str | None,
        effort: str | None = DEFAULT_EFFORT,
        engine: str = "claude",
    ) -> Job:
        if permission_mode not in PERMISSION_MODES:
            raise ValueError(f"izin modu: {permission_mode}")
        if engine not in ENGINES:
            raise ValueError(f"motor: {engine}")
        if effort and effort not in EFFORTS:
            raise ValueError(f"efor: {effort}")
        extra = []
        if video:
            parent = Path(video).expanduser().resolve()
            parent = parent if parent.is_dir() else parent.parent
            if not is_allowed(parent, [VLOGS_ROOT.resolve()]):
                extra.append(str(parent))
        job = Job(
            id=time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4],
            title=title,
            created=time.time(),
            video=video,
            permission_mode=permission_mode,
            engine=engine,
            model=model or None,
            effort=effort or None,
            extra_dirs=extra,
        )
        self.jobs[job.id] = job
        self.save(job)
        return job

    def send(self, job: Job, prompt: str, files: Sequence[str] = ()) -> bool:
        """Start a turn, or queue the message while one is running (like Claude Code's CLI).

        `files`: attachments (images, videos, documents). Their paths go into the message for the
        agent to open, and folders outside the vlogs root become extra allowed dirs.

        Returns True when queued. Claude: a message sent while a turn runs is written to the
        agent at once and joins that turn at its next tool boundary (`sent`); it shows in the
        thread when Claude takes it. Codex (and Claude after its last answer) queue as before:
        the queue goes out as the next turn when the running one ends well; after a stop or an
        error it waits (`flush` / `unqueue`).
        """
        files = [str(Path(f)) for f in files]
        known = len(job.extra_dirs)
        self._allow(job, files)
        # a file from a new folder needs --add-dir, which only a new run gets: queue it
        new_dir = len(job.extra_dirs) > known
        with self.cond:
            if job.status == "running":
                item = {"text": prompt, "files": files}
                stdin = None if new_dir else self.live.get(job.id)
                if stdin is not None:
                    uid = str(uuid.uuid4())
                    try:
                        stdin.write(user_line(prompt + attachment_block(files, job.engine), uid))
                        stdin.flush()
                        item |= {"sent": True, "uuid": uid}
                    except (OSError, ValueError):  # the agent just closed its input
                        self.live.pop(job.id, None)
                job.queue.append(item)
                self.emit(job, {"kind": "queue", "items": list(job.queue)})
                self.save(job)
                return True
            self._start(job, prompt, files)
        return False

    def set_effort(self, job: Job, effort: str) -> str:
        """Change a job's effort after it started. A running Claude takes it at once (flag
        settings over its open input; it applies from its next model call). Otherwise, and for
        Codex, it holds from the next run. Returns when it applies: "now" | "next"."""
        if effort not in EFFORTS:
            raise ValueError(f"efor: {effort}")
        with self.cond:
            job.effort = effort
            when = "next"
            stdin = self.live.get(job.id) if job.status == "running" else None
            level = claude_effort(job) if stdin is not None else None
            if level:
                try:
                    stdin.write(
                        control_line("apply_flag_settings", settings={"effortLevel": level})
                    )
                    stdin.flush()
                    when = "now"
                except (OSError, ValueError):  # the agent just closed its input
                    self.live.pop(job.id, None)
            note = "bir sonraki adımdan itibaren" if when == "now" else "sonraki turdan itibaren"
            self.emit(job, {"kind": "system", "text": f"Efor: {EFFORT_NAMES[effort]}, {note}."})
            self.save(job)
        return when

    def _allow(self, job: Job, files: Sequence[str]) -> None:
        for f in files:
            parent = str(Path(f).expanduser().resolve().parent)
            if not is_allowed(Path(parent)) and parent not in job.extra_dirs:
                job.extra_dirs.append(parent)

    def edit(self, job: Job, index: int, prompt: str, files: Sequence[str] = ()) -> None:
        """The user rewrote message `index`: that turn and the ones after it are set aside
        (kept in job.branches) and the conversation goes on from there in a fresh session,
        told what still holds and which files the dropped turns had changed (not undone).
        Works the same for Claude and Codex."""
        files = [str(Path(f)) for f in files]
        self._allow(job, files)
        with self.cond:
            if job.status == "running":
                raise RuntimeError("çalışan işte mesaj düzenlenemez, önce durdur")
            if not 0 <= index < len(job.turns):
                raise ValueError(f"mesaj yok: {index + 1}")
            dropped = job.turns[index:]
            changed = list(
                dict.fromkeys(
                    path
                    for e in job.events
                    if e.get("turn", 0) >= index
                    and e.get("kind") == "tool"
                    and e.get("name") in EDIT_TOOLS
                    # a Codex file_change lists all its paths in one summary
                    for path in (
                        e.get("summary", "").split(", ")
                        if job.engine == "codex"
                        else [e.get("summary", "")]
                    )
                    if path
                )
            )
            job.branches.append(
                {"at": index, "ts": time.time(), "turns": [asdict(t) for t in dropped]}
            )
            job.turns = job.turns[:index]
            kept = [e for e in job.events if e.get("turn", 0) < index]
            for i, e in enumerate(kept):
                e["i"] = i
            job.events = kept
            job.session_id = None  # queued messages stay: they follow the edited one
            agent = history.branch_context(job.turns, prompt, changed)
            self._start(job, prompt, files, agent_prompt=agent)
            self.emit(
                job,
                {
                    "kind": "system",
                    "text": f"Mesaj düzenlendi: sonraki {len(dropped)} tur ayrıldı, konuşma "
                    "buradan yeni oturumla devam ediyor."
                    + (f" Değişen {len(changed)} dosya geri alınmadı." if changed else ""),
                },
            )

    def _start(
        self, job: Job, prompt: str, files: Sequence[str] = (), agent_prompt: str | None = None
    ) -> None:
        full = prompt + attachment_block(files, job.engine)
        # what the agent gets can carry more than the user wrote (an edit's context)
        agent = agent_prompt + attachment_block(files, job.engine) if agent_prompt else full
        with self.cond:
            job.turns.append(Turn(prompt=full, started=time.time()))
            job.status = "running"
            shown = [
                {"path": f, "kind": MEDIA_EXT.get(Path(f).suffix.lower(), "text")} for f in files
            ]
            self.emit(job, {"kind": "user", "text": prompt, **({"files": shown} if shown else {})})
            self.emit(job, {"kind": "status", "status": "running"})
            self.save(job)
        threading.Thread(target=self._run, args=(job, agent), daemon=True).start()

    def unqueue(self, job: Job, index: int) -> None:
        with self.cond:
            # a message already written to Claude cannot be taken back: it answers it anyway
            if 0 <= index < len(job.queue) and not job.queue[index].get("sent"):
                job.queue.pop(index)
                self.emit(job, {"kind": "queue", "items": list(job.queue)})
                self.save(job)

    def flush(self, job: Job) -> bool:
        """Send everything queued as one message (after a stop or an error)."""
        with self.cond:
            if job.status == "running" or not job.queue:
                return False
            text, files = _merge(job.queue)
            job.queue.clear()
            self.emit(job, {"kind": "queue", "items": []})
        self.send(job, text, files)
        return True

    def stop(self, job: Job) -> None:
        proc = self.procs.get(job.id)
        if proc and proc.poll() is None:
            self.stopping.add(job.id)
            proc.terminate()

    def _taken(self, job: Job, uid: str | None, answered: bool) -> bool:
        """Claude took a message written while it worked (its replay, same uuid): show it in the
        thread. After an answer it starts a new turn; mid-turn it joins the running one. Replays
        of anything else (the first message, notices) are not ours: False."""
        with self.cond:
            item = next((q for q in job.queue if uid and q.get("uuid") == uid), None)
            if item is None:
                return False
            job.queue.remove(item)
            full = item["text"] + attachment_block(item.get("files", []), job.engine)
            if answered:
                job.turns[-1].ended = job.turns[-1].ended or time.time()
                job.turns.append(Turn(prompt=full, started=time.time()))
            else:
                job.turns[-1].prompt += "\n\n[İş sürerken eklenen mesaj]\n" + full
            shown = [
                {"path": f, "kind": MEDIA_EXT.get(Path(f).suffix.lower(), "text")}
                for f in item.get("files", [])
            ]
            self.emit(job, {"kind": "queue", "items": list(job.queue)})
            self.emit(
                job,
                {"kind": "user", "text": item["text"], "live": not answered}
                | ({"files": shown} if shown else {}),
            )
            self.save(job)
            return True

    def _close_input(self, job: Job, wait: float = TAKE_WAIT) -> None:
        """After an answer with nothing pending: close stdin so the agent finishes. With a
        message on its way Claude answers it as the next turn; if it never takes it (no replay,
        nothing new for `wait` s) the run ends anyway and the message goes out as a new run."""
        with self.cond:
            if any(q.get("sent") for q in job.queue):
                t = threading.Timer(wait, self._close_if_idle, args=(job, len(job.events)))
                t.daemon = True
                t.start()
                return
            stdin = self.live.pop(job.id, None)
        if stdin is not None:
            with contextlib.suppress(OSError):
                stdin.close()

    def _close_if_idle(self, job: Job, mark: int) -> None:
        with self.cond:
            if len(job.events) != mark or not any(q.get("sent") for q in job.queue):
                return  # it took the message (or more happened): the next answer decides
            stdin = self.live.pop(job.id, None)
        if stdin is not None:
            with contextlib.suppress(OSError):
                stdin.close()

    def _run(self, job: Job, prompt: str) -> None:
        turn = job.turns[-1]
        got_result = False
        answered = False  # the latest turn has its result; a replay now starts a new turn
        first = str(uuid.uuid4())  # the message that starts this run (replayed too)
        last_activity: dict | None = None
        is_codex = job.engine == "codex"
        exists = codex.session_exists if is_codex else claude_session_exists
        if job.session_id and not exists(job.session_id):
            job.session_id = None
            prompt = history.context(job, prompt)
            self.emit(
                job,
                {
                    "kind": "system",
                    "text": "Eski oturum bulunamadı, önceki turların özetiyle yeni oturum açıldı.",
                },
            )
        translate_fn = codex.Translator(len(job.turns) - 1, job.model) if is_codex else translate
        try:
            proc = subprocess.Popen(
                codex.command(job, prompt, UI_SYSTEM_PROMPT) if is_codex else claude_command(job),
                cwd=REPO_ROOT,
                env=codex.env() if is_codex else subscription_env(),
                stdin=subprocess.DEVNULL if is_codex else subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            if not is_codex:  # Claude reads messages from stdin (never parsed as an option)
                assert proc.stdin
                proc.stdin.write(user_line(prompt, first))
                proc.stdin.flush()
                with self.cond:
                    self.live[job.id] = proc.stdin
        except Exception as e:
            self._finish(job, turn, ok=False, error=str(e))
            return
        self.procs[job.id] = proc
        _keep_awake(proc.pid)
        stderr_tail: list[str] = []
        reader = threading.Thread(
            target=lambda: stderr_tail.extend(proc.stderr.readlines()), daemon=True
        )
        reader.start()
        assert proc.stdout
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("type") == "control_response":  # the answer to an effort change
                r = obj.get("response") or {}
                if r.get("subtype") == "error":
                    self.emit(
                        job, {"kind": "system", "text": f"Ajan ayarı almadı: {r.get('error')}"}
                    )
                continue
            if obj.get("type") == "user" and obj.get("isReplay"):
                uid = obj.get("uuid")
                if uid != first and self._taken(job, uid, answered):
                    got_result = got_result and not answered  # a new turn needs its own result
                    answered = False
                    turn = job.turns[-1]
                continue
            for ev in translate_fn(obj):
                if ev["kind"] == "activity":
                    if last_activity == ev:  # same block type again, nothing new to show
                        continue
                    last_activity = ev
                elif ev["kind"] in ("tool_result", "text"):
                    last_activity = None
                if ev["kind"] == "system" and ev.get("session_id"):
                    job.session_id = ev["session_id"]
                    if ev.get("model"):
                        ev.setdefault("label", model_label(ev["model"]))
                        if job.model and not is_codex:
                            remember_model(job.model, ev["model"])
                if ev["kind"] == "result":
                    got_result = True
                    turn.ok, turn.result = ev["ok"], ev["text"]
                    turn.cost_usd, turn.duration_ms = ev["cost_usd"], ev["duration_ms"]
                    job.session_id = ev.get("session_id") or job.session_id
                self.emit(job, ev)
                if ev["kind"] == "result":
                    files = find_outputs(ev["text"], [Path(d) for d in job.extra_dirs])
                    if files:
                        self.emit(job, {"kind": "outputs", "files": files})
                    answered = True
                    if not is_codex:
                        self._close_input(job)
        code = proc.wait()
        reader.join(timeout=2)
        self.procs.pop(job.id, None)
        with self.cond:
            self.live.pop(job.id, None)
            for q in job.queue:  # written but never taken (a stop, a crash): send them again later
                q.pop("sent", None)
                q.pop("uuid", None)
        turn = job.turns[-1]
        if job.id in self.stopping:
            self.stopping.discard(job.id)
            self._finish(job, turn, ok=False, error="Durduruldu.", status="stopped")
        elif not got_result:
            noise = ("rmcp::", "Reading additional input")  # Codex MCP / stdin chatter
            lines = [ln for ln in stderr_tail if not any(n in ln for n in noise)]
            tail = "".join(lines[-12:]).strip() or f"{job.engine} çıkış kodu {code}"
            self._finish(job, turn, ok=False, error=tail)
        else:
            self._finish(job, turn, ok=bool(turn.ok))

    def _finish(
        self, job: Job, turn: Turn, ok: bool, error: str | None = None, status: str | None = None
    ) -> None:
        turn.ended = time.time()
        turn.ok = ok if turn.ok is None else turn.ok
        if error:
            self.emit(job, {"kind": "error", "text": error})
        with self.cond:
            final = status or ("done" if ok else "error")
            if final == "done" and job.queue:
                # the queued messages are the next turn: the job never leaves "running", so open
                # event streams keep going and nobody gets a "finished" notification in between
                text, files = _merge(job.queue)
                job.queue.clear()
                self.emit(job, {"kind": "queue", "items": []})
                self._start(job, text, files)
                return
            job.status = final
            with contextlib.suppress(OSError):
                free = disk.free_bytes()
                if free < disk.LOW:
                    self.emit(
                        job,
                        {
                            "kind": "system",
                            "text": f"Diskte {disk.gb(free)} kaldı: sol alttaki Ayarlar > Depolama > "
                            "Temizle eski derlemelerin ara dosyalarını siler.",
                        },
                    )
            self.emit(job, {"kind": "status", "status": job.status})
            self.save(job)
        if self.on_finish and job.status in ("done", "error"):
            with contextlib.suppress(Exception):  # a notification must never break the job
                self.on_finish(job)
