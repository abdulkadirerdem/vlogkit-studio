"""Scenarios: researched, scored, fully written ideas for the 3D "what if" channel, waiting to be
produced. The agent writes them (docs/senaryo.md), the studio lists them (Senaryolar), one click
starts the production of one.

One JSON file per scenario in projects/_senaryolar/ (the user's own data: updates never touch
projects/, and the leading "_" keeps it out of the project list):

    {"id": "herkes-ayni-anda-ziplasa", "title": "Peki ya herkes aynı anda zıplasaydı?",
     "hook": "...", "logline": "...", "duration_s": 45, "language": "tr",
     "scores": {"merak": 9, "tirmanis": 8, "gorsel": 9, "hesap": 7, "yorum": 8},
     "why": "...", "sources": [{"title": "...", "url": "..."}],
     "counter": {"label": "ZIPLAYAN İNSAN"},
     "beats": [{"say": "...", "visual": "...", "counter": "...", "fx": "..."}],
     "ending": "...", "next_teaser": "...",
     "titles": {"youtube": ["..."], "instagram": "...", "tiktok": "..."}, "hashtags": ["#pekiya"],
     "status": "yeni", "created": "2026-11-02", "project": null}
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

from vlogkit.config import PROJECTS_DIR

DIR = PROJECTS_DIR / "_senaryolar"
STATUSES = ("yeni", "secildi", "uretiliyor", "uretildi", "arsiv")
SCORES = ("merak", "tirmanis", "gorsel", "hesap", "yorum")
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{1,80}$")


def path(sid: str) -> Path:
    if not _ID.match(sid):
        raise ValueError(f"geçersiz senaryo kimliği: {sid}")
    return DIR / f"{sid}.json"


def validate(s: dict) -> list[str]:
    out = []
    for k in ("id", "title", "hook", "beats"):
        if not s.get(k):
            out.append(f"'{k}' gerekli")
    if s.get("id") and not _ID.match(s["id"]):
        out.append("id: küçük harf, rakam ve tire (ör. herkes-ayni-anda-ziplasa)")
    beats = s.get("beats") or []
    if beats and not 6 <= len(beats) <= 16:
        out.append(f"beats: 6-16 cümle olmalı ({len(beats)} var)")
    for i, b in enumerate(beats, 1):
        if not str(b.get("say", "")).strip():
            out.append(f"beat {i}: 'say' (anlatım cümlesi) boş")
        if not str(b.get("visual", "")).strip():
            out.append(f"beat {i}: 'visual' boş: her cümle ekranda bir olay olmalı")
    sc = s.get("scores") or {}
    for k in SCORES:
        v = sc.get(k)
        if not isinstance(v, (int, float)) or not 1 <= v <= 10:
            out.append(f"scores.{k}: 1-10 arası sayı")
    if s.get("status", "yeni") not in STATUSES:
        out.append(f"status: {', '.join(STATUSES)}")
    return out


def total(s: dict) -> float:
    sc = s.get("scores") or {}
    vals = [float(sc[k]) for k in SCORES if isinstance(sc.get(k), (int, float))]
    return round(sum(vals) / len(vals), 1) if vals else 0.0


def load(sid: str) -> dict:
    return json.loads(path(sid).read_text(encoding="utf-8"))


def summary(s: dict, file: Path) -> dict:
    return {
        "id": s.get("id") or file.stem,
        "title": s.get("title", file.stem),
        "hook": s.get("hook", ""),
        "logline": s.get("logline", ""),
        "duration_s": s.get("duration_s"),
        "beats": len(s.get("beats") or []),
        "scores": s.get("scores") or {},
        "total": total(s),
        "status": s.get("status", "yeni"),
        "project": s.get("project"),
        "created": s.get("created", ""),
        "problems": validate(s),
        "updated": file.stat().st_mtime,
    }


def list_all(include_archived: bool = False) -> list[dict]:
    out = []
    for f in sorted(DIR.glob("*.json")) if DIR.exists() else []:
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        row = summary(s, f)
        if row["status"] == "arsiv" and not include_archived:
            continue
        out.append(row)
    order = {st: i for i, st in enumerate(("yeni", "secildi", "uretiliyor", "uretildi", "arsiv"))}
    return sorted(out, key=lambda r: (order.get(r["status"], 9), -r["total"], -r["updated"]))


def set_status(sid: str, status: str, project: str | None = None) -> dict:
    if status not in STATUSES:
        raise ValueError(f"durum: {', '.join(STATUSES)}")
    p = path(sid)
    s = json.loads(p.read_text(encoding="utf-8"))
    s["status"] = status
    if project:
        s["project"] = project
    s["status_changed"] = time.strftime("%Y-%m-%d %H:%M")
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return s
