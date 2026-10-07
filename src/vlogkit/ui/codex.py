"""Run OpenAI Codex headless (`codex exec --json`) for UI jobs, as an alternative to Claude Code.

Same job model as Claude: the first turn starts a thread, later turns `codex exec resume <id>`.
The JSONL stream is translated into the same UI events the Claude runner produces, so the
browser does not care which engine ran.

Auth: OPENAI_API_KEY / CODEX_API_KEY are dropped from the environment, so Codex uses the ChatGPT
login in ~/.codex (subscription) instead of API billing.

Permissions: the "safe" modes run in Codex's workspace-write sandbox. Writable: the vlogs root
(which contains this repo), uv's cache and the job's extra folders. Network is on for uv and git.
`.git` stays read-only inside that sandbox, so commits need the full-access mode.
"""

from __future__ import annotations

import json
import os
import re
import time
import tomllib
from pathlib import Path

from vlogkit.config import VLOGS_ROOT, tools

HOME = Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
LEVELS = ("low", "medium", "high", "xhigh", "max", "ultra")
_SHELL = re.compile(r"^/bin/(?:zsh|bash|sh) -lc '(.*)'$", re.S)


def default_model() -> str | None:
    """The model Codex uses when none is passed (from ~/.codex/config.toml)."""
    try:
        return tomllib.loads((HOME / "config.toml").read_text()).get("model")
    except (OSError, ValueError):
        return None


def model_label(model_id: str | None) -> str:
    """gpt-6-astra -> 'GPT-6 Astra', gpt-5.1-codex-max -> 'GPT-5.1 Codex Max'."""
    if not model_id:
        return "Codex"
    m = re.match(r"gpt-([\d.]+)(?:-(.+))?$", model_id)
    if not m:
        return model_id
    rest = " ".join(w.capitalize() for w in (m.group(2) or "").split("-") if w)
    return f"GPT-{m.group(1)}" + (f" {rest}" if rest else "")


def models() -> list[dict]:
    """The models Codex's own /model menu lists: models_cache.json, which the CLI keeps fresh."""
    try:
        cache = json.loads((HOME / "models_cache.json").read_text())
    except (OSError, ValueError):
        return []
    listed = [
        m for m in cache.get("models") or [] if m.get("visibility") == "list" and m.get("slug")
    ]
    return [
        {
            "id": m["slug"],
            "label": m.get("display_name") or model_label(m["slug"]),
            "description": m.get("description", ""),
            "efforts": [
                x.get("effort") if isinstance(x, dict) else x
                for x in m.get("supported_reasoning_levels") or []
            ],
        }
        for m in sorted(listed, key=lambda m: m.get("priority", 99))
    ]


def model_options() -> list[dict]:
    # First entry: no -m at all, so Codex uses whatever it is configured to (its newest default).
    listed = models()
    default = default_model()
    info = next((m for m in listed if m["id"] == default), None)
    name = info["label"] if info else model_label(default)
    top = {
        "id": "",
        "label": f"Varsayılan · {name}",
        "description": "Codex ayarlarındaki model",
        "efforts": info["efforts"] if info else list(LEVELS[:4]),
    }
    return [top, *listed]


def clamp_effort(supported: list[str], effort: str | None) -> str | None:
    """The requested level if supported, else the highest supported one below it.

    Shared with the Claude runner. An empty list means "unknown": pass the level through.
    """
    if not effort or not supported or effort in supported:
        return effort
    rank = {e: i for i, e in enumerate(LEVELS)}
    below = [e for e in supported if rank.get(e, 99) <= rank.get(effort, 99)]
    return below[-1] if below else supported[0]


def effort_for(model: str | None, effort: str) -> str | None:
    info = next((m for m in models() if m["id"] == (model or default_model())), None)
    return clamp_effort(info["efforts"] if info else [], effort)


def session_exists(thread_id: str) -> bool:
    return any((HOME / "sessions").glob(f"**/rollout-*{thread_id}.jsonl"))


def env() -> dict[str, str]:
    e = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "CODEX_API_KEY")}
    e.setdefault("NO_COLOR", "1")
    return e


def _toml(value) -> str:
    return json.dumps(value)  # JSON strings and string arrays are valid TOML values


def command(job, prompt: str, instructions: str) -> list[str]:
    codex = tools().codex
    if not codex:
        raise RuntimeError("codex CLI bulunamadı (npm i -g @openai/codex, sonra codex login)")
    cmd = [codex, "exec"] + (["resume"] if job.session_id else [])
    cmd += [
        "--json",
        "--skip-git-repo-check",
        "-c",
        f"developer_instructions={_toml(instructions)}",
        "-c",
        'project_doc_fallback_filenames=["CLAUDE.md"]',  # rules: CLAUDE.md (AGENTS.md links to it)
    ]
    effort = effort_for(job.model, job.effort) if job.effort else None
    if effort:
        cmd += ["-c", f"model_reasoning_effort={_toml(effort)}"]
    if job.model:
        cmd += ["-m", job.model]
    if job.permission_mode == "bypassPermissions":
        cmd.append("--dangerously-bypass-approvals-and-sandbox")
    else:
        roots = [str(VLOGS_ROOT), str(Path.home() / ".cache" / "uv"), *job.extra_dirs]
        cmd += [
            "-c",
            'sandbox_mode="workspace-write"',
            "-c",
            'approval_policy="never"',
            "-c",
            f"sandbox_workspace_write.writable_roots={_toml(roots)}",
            "-c",
            "sandbox_workspace_write.network_access=true",
        ]
    return [*cmd, "--", *([job.session_id] if job.session_id else []), prompt]


def _tool(kind: str, it: dict) -> tuple[str, str] | None:
    if kind == "command_execution":
        c = it.get("command", "")
        m = _SHELL.match(c)
        return "Shell", (m.group(1).replace("'\\''", "'") if m else c)
    if kind == "file_change":
        return "Edit", ", ".join(ch.get("path", "") for ch in it.get("changes") or [])
    if kind == "mcp_tool_call":
        return f"{it.get('server', 'mcp')}.{it.get('tool', '?')}", json.dumps(
            it.get("arguments") or {}, ensure_ascii=False
        )
    if kind == "web_search":
        return "WebSearch", it.get("query", "")
    return None


class Translator:
    """One `codex exec --json` run -> UI events (stateful: the final answer is the last message)."""

    def __init__(self, turn: int, model: str | None):
        self.turn, self.model = turn, model or default_model()
        self.label = model_label(self.model)
        self.thread: str | None = None
        self.last = ""
        self.t0 = time.time()
        self.open: set[str] = set()

    def __call__(self, obj: dict) -> list[dict]:
        t = obj.get("type")
        if t == "thread.started":
            self.thread = obj.get("thread_id")
            return [
                {
                    "kind": "system",
                    "session_id": self.thread,
                    "model": self.model,
                    "label": f"Codex · {self.label}",
                    "text": f"Oturum başladı · Codex {self.label} · abonelik",
                    "auth": "abonelik",
                }
            ]
        if t == "turn.started":
            return [{"kind": "activity", "state": "thinking"}]
        if t in ("item.started", "item.updated", "item.completed"):
            return self._item(t, obj.get("item") or {})
        if t in ("turn.completed", "turn.failed"):
            ok = t == "turn.completed"
            err = (obj.get("error") or {}).get("message", "")
            return [
                {
                    "kind": "result",
                    "ok": ok,
                    "subtype": "success" if ok else "error",
                    "text": self.last if ok else (err or self.last),
                    "session_id": self.thread,
                    "cost_usd": None,
                    "duration_ms": int((time.time() - self.t0) * 1000),
                    "num_turns": None,
                }
            ]
        if t == "error" and obj.get("message"):
            return [{"kind": "system", "text": f"Codex: {obj['message']}"}]
        return []

    def _item(self, t: str, it: dict) -> list[dict]:
        kind = it.get("type")
        if kind == "agent_message":
            text = (it.get("text") or "").strip()
            if t != "item.completed" or not text:
                return []
            self.last = text
            return [{"kind": "text", "text": text}]
        if kind == "reasoning":
            return [{"kind": "activity", "state": "thinking"}] if t == "item.started" else []
        tool = _tool(kind, it)
        if not tool:
            return []
        iid = f"{self.turn}:{it.get('id')}"  # Codex item ids restart every turn
        events = []
        if iid not in self.open:
            self.open.add(iid)
            events.append({"kind": "tool", "id": iid, "name": tool[0], "summary": tool[1][:600]})
        if t == "item.completed":
            ok = it.get("exit_code", 0) == 0 and it.get("status") not in ("failed", "declined")
            out = it.get("aggregated_output") or (it.get("error") or {}).get("message", "")
            events.append({"kind": "tool_result", "id": iid, "ok": ok, "preview": str(out)[:800]})
        return events
