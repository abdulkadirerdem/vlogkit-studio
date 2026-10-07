"""What is left of a studio job once it goes away, and what a new session needs to continue one.

- `write_note`: when a job is deleted (by hand or by the retention rule), its requests, answers
  and outputs are appended to VLOGKIT-NOTLAR.md in the work's folder, next to the footage.
- `context`: the agent CLIs delete old transcripts (Claude Code after `cleanupPeriodDays`,
  30 by default). If a job's session is gone, the next turn starts a fresh session with this
  summary of the earlier turns.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

from vlogkit.config import VLOGS_ROOT

NOTES_FILE = "VLOGKIT-NOTLAR.md"
RETENTION_DAYS = (0, 3, 7, 30)  # 0 = keep forever (default)
_OUTPUTS = re.compile(r"\n+\s*(\*\*)?Çıktılar:?(\*\*)?\s*\n[\s\S]*$", re.I)


def _date(ts: float) -> str:
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))


def _outputs(job) -> list[str]:
    return [f["path"] for e in job.events if e.get("kind") == "outputs" for f in e["files"]]


def _clip(text: str, n: int) -> str:
    text = text.strip()
    return text if len(text) <= n else text[:n].rstrip() + " …"


def has_work(job) -> bool:
    return any(t.result.strip() for t in job.turns)


def work_folder(job) -> Path:
    """The folder the job worked on: the picked video's folder, else its first output's."""
    if job.video:
        p = Path(job.video).expanduser()
        folder = p if p.is_dir() else p.parent
        if folder.is_dir():
            return folder
    for out in _outputs(job):
        if Path(out).parent.is_dir():
            return Path(out).parent
    return VLOGS_ROOT


def digest(job) -> str:
    engine = "Codex" if getattr(job, "engine", "claude") == "codex" else "Claude Code"
    last = job.turns[-1] if job.turns else None
    end = (last.ended or last.started) if last else job.created
    lines = [
        f"## {job.title}",
        "",
        f"{_date(job.created)} → {_date(end)} · {engine} · {len(job.turns)} tur"
        + (f" · kaynak: `{job.video}`" if job.video else ""),
        "",
    ]
    for i, t in enumerate(job.turns, 1):
        lines += [f"**{i}. İstek:**", "", *("> " + ln for ln in _clip(t.prompt, 900).splitlines())]
        if t.result.strip():
            lines += ["", f"**{i}. Sonuç:**", "", _clip(_OUTPUTS.sub("", t.result), 2500)]
        lines.append("")
    outs = _outputs(job)
    if outs:
        lines += ["**Çıktılar:**", "", *(f"- `{p}`" for p in dict.fromkeys(outs)), ""]
    return "\n".join(lines)


def write_note(job) -> Path | None:
    """Append the job's digest to the work folder's notes file. Jobs without an answer: skip."""
    if not has_work(job):
        return None
    path = work_folder(job) / NOTES_FILE
    head = (
        ""
        if path.exists()
        else "# vlogkit notları\n\nStüdyoda silinen işlerin özeti (en yenisi en altta).\n\n"
    )
    with path.open("a", encoding="utf-8") as f:
        f.write(head + digest(job) + "\n---\n\n")
    return path


def context(job, prompt: str) -> str:
    """A fresh session's first message when the old session no longer exists."""
    parts = [
        "Bu işin önceki oturum kaydı artık yok (ajan CLI'ı eski kayıtları siliyor). "
        "Şimdiye kadar olanlar:",
    ]
    for i, t in enumerate(job.turns[:-1], 1):
        parts.append(f"\n{i}. istek:\n{_clip(t.prompt, 1200)}")
        if t.result.strip():
            parts.append(f"{i}. sonuç:\n{_clip(t.result, 1500)}")
    parts.append(f"\nYeni mesaj:\n{prompt}")
    return "\n".join(parts)


def branch_context(turns, prompt: str, changed: list[str]) -> str:
    """A fresh session after the user edited an earlier message: what still holds (the turns
    before it) and what the dropped turns changed on disk, which is not undone by the edit."""
    parts = []
    if turns:
        parts.append(
            "Kullanıcı önceki bir mesajını düzenledi: o mesajdan sonraki konuşma geçersiz, bu "
            "yeni bir oturum. Geçerli olanlar:"
        )
        for i, t in enumerate(turns, 1):
            parts.append(f"\n{i}. istek:\n{_clip(t.prompt, 1200)}")
            if t.result.strip():
                parts.append(f"{i}. sonuç:\n{_clip(t.result, 1500)}")
    if changed:
        parts.append(
            "\nDikkat: Geçersiz kalan turlarda şu dosyalar değişmişti ve geri alınmadı. Yeni isteğe "
            "göre gerekiyorsa geri al (projeler git'te; git diff ile bak):\n"
            + "\n".join(f"- {f}" for f in changed)
        )
    if not parts:
        return prompt
    parts.append(f"\nDüzenlenmiş mesaj:\n{prompt}")
    return "\n".join(parts)


def expired(job, days: int, now: float | None = None) -> bool:
    if not days or getattr(job, "pinned", False) or job.status == "running":
        return False
    last = job.turns[-1] if job.turns else None
    updated = (last.ended or last.started) if last else job.created
    return (now or time.time()) - updated > days * 86400
