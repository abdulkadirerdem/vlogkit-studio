"""The edit as data: what is on screen when (shots, texts, chapters, notes).

A build writes it to build/timelines/<name>-<key>.json (key = the output file's path) when a
project is composed or a reel rendered. The Studio draws it under the video: a click becomes a
time, a comment becomes "[01:23.4 · plan 12] ...". A video built some other way gets its shots
detected the first time it is asked for (cached in the same place).

Times are seconds on the delivered video. `at(data, t)` answers "what is at 83.4 s" for the
agent turning a comment into a change in edit.py.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from vlogkit.config import BUILD_DIR
from vlogkit.ff import PathLike

VERSION = 1
DIR = BUILD_DIR / "timelines"


def path_for(video: PathLike) -> Path:
    full = str(Path(video).expanduser().resolve())
    key = hashlib.sha1(full.encode()).hexdigest()[:16]
    return DIR / f"{Path(video).stem[:40]}-{key}.json"


def _stamp(video: PathLike) -> dict:
    st = os.stat(video)
    return {"size": st.st_size, "mtime": round(st.st_mtime, 3)}


def item(t0: float, t1: float, label: str, **extra) -> dict:
    return {"t0": round(float(t0), 3), "t1": round(float(t1), 3), "label": label, **extra}


def shots_track(cuts: Sequence[float], duration: float, detected: bool = False) -> dict:
    marks = [0.0, *sorted(c for c in cuts if 0 < c < duration), duration]
    items = [item(a, b, str(k)) for k, (a, b) in enumerate(pairwise(marks), 1) if b - a > 1e-3]
    return {"id": "shots", "label": "Planlar", "items": items, "detected": detected}


def _plain(text: str) -> str:
    return " ".join(str(text).replace("[", "").replace("]", "").split())


def text_track(elements: Sequence) -> dict:
    """Every element with a known time window, labelled by kind and text."""
    from vlogkit.export.resolve import time_window

    items = []
    for e in elements:
        w = time_window(e)
        if w is None:
            continue
        kind = type(e).__name__
        text = _plain(getattr(e, "text", "") or "")  # Karaoke keeps its words in .text too
        label = f"{kind}: {text[:70]}" if text else kind
        items.append(item(w[0], w[1], label, kind=kind))
    items.sort(key=lambda x: (x["t0"], x["t1"]))
    return {"id": "text", "label": "Grafikler", "items": items}


def chapters_track(chapters: Sequence, duration: float) -> dict:
    starts = sorted(chapters, key=lambda c: c.start)
    ends = [c.start for c in starts[1:]] + [duration]
    items = [item(c.start, e, c.title) for c, e in zip(starts, ends, strict=True) if e > c.start]
    return {"id": "chapters", "label": "Bölümler", "items": items}


def notes_track(notes: Sequence[tuple[float, str]]) -> dict:
    return {"id": "notes", "label": "Notlar", "items": [item(t, t, text) for t, text in notes]}


def _chapters_of(edit) -> list:
    chapters = getattr(edit, "chapters", None)
    if callable(chapters):
        try:
            return list(chapters())
        except Exception:  # a project whose chapters need a build step
            return []
    return []


def from_edit(edit, video: PathLike | None = None) -> dict:
    """The timeline of a built project. Shots come from Edit.cuts(); a project without a cut
    list gets them detected later (the Studio asks, `ensure_shots` answers)."""
    video = Path(video or edit.output_path)
    duration = edit.duration
    tracks = []
    cuts = edit.cuts()
    if cuts is not None:
        tracks.append(shots_track(cuts, duration))
    elements = edit.elements()
    texts = text_track(elements)
    if texts["items"]:
        tracks.append(texts)
    chapters = _chapters_of(edit)
    if chapters:
        tracks.append(chapters_track(chapters, duration))
    notes = edit.notes() if callable(getattr(edit, "notes", None)) else []
    if notes:
        tracks.append(notes_track(notes))
    data = {
        "version": VERSION,
        "video": str(video.resolve()),
        "duration": round(duration, 3),
        "fps": float(edit.fps),
        "project": edit.ctx.name,
        "variant": edit.variant,
        "tracks": tracks,
    }
    if getattr(edit.ctx, "work", None):  # third-party media the build used (the studio's card)
        from vlogkit.export import licenses

        items = licenses.for_edit(edit)
        if items:
            data["licenses"] = {
                "items": items,
                "dispute": licenses.dispute_text(video.name, items),
                "file": str(licenses.sidecar(video)),
            }
    return data


def from_plan(plan, video: PathLike, fps: float) -> dict:
    """A beat-cut reel (video/beatcut.Plan): its shots with their source clips."""
    items = []
    for k, s in enumerate(plan.shots, 1):
        label = f"{k} · {Path(s.src).name} @ {s.src_in:.1f}" + (
            f" · {s.accent}" if s.accent else ""
        )
        items.append(item(s.start, s.end, label))
    tracks = [{"id": "shots", "label": "Planlar", "items": items, "detected": False}]
    if plan.drops:
        tracks.append(
            {"id": "notes", "label": "Notlar", "items": [item(d, d, "drop") for d in plan.drops]}
        )
    return {
        "version": VERSION,
        "video": str(Path(video).resolve()),
        "duration": round(plan.length, 3),
        "fps": fps,
        "project": None,
        "variant": None,
        "tracks": tracks,
    }


def write(data: dict, video: PathLike) -> Path:
    """Save the timeline for `video` (stamped with the file's size and time: a later change
    to the video by other means marks it stale)."""
    data = {**data, "video": str(Path(video).resolve()), "stamp": _stamp(video)}
    out = path_for(video)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_name(f"{out.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(out)
    return out


def load(video: PathLike) -> dict | None:
    p = path_for(video)
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    try:
        data["stale"] = data.get("stamp") != _stamp(video)
    except OSError:
        data["stale"] = True
    return data


def track(data: dict, tid: str) -> dict | None:
    return next((t for t in data.get("tracks", []) if t["id"] == tid), None)


def ensure_shots(video: PathLike) -> dict:
    """The saved timeline, with a shots track: detected from the video itself when the build did
    not give one (or there was no build). Slow the first time (one full-rate scan), then cached."""
    from vlogkit.analysis.cutcheck import frame_stats, spikes
    from vlogkit.ff import probe

    data = load(video)
    if data is not None and not data.get("stale") and track(data, "shots"):
        return data
    before = _stamp(video)  # the video and its timeline file as they were before the slow scan
    saved = path_for(video).stat().st_mtime if path_for(video).exists() else None
    info = probe(video)
    if data is None or data.get("stale"):
        data = {
            "version": VERSION,
            "duration": round(info.duration, 3),
            "fps": float(info.fps) if info.fps else None,
            "project": None,
            "variant": None,
            "tracks": [],
        }
    cuts = spikes(frame_stats(video))
    data["tracks"] = [t for t in data["tracks"] if t["id"] != "shots"]
    data["tracks"].insert(0, shots_track(cuts, info.duration, detected=True))
    data.pop("stale", None)
    now = path_for(video).stat().st_mtime if path_for(video).exists() else None
    if _stamp(video) != before or now != saved:  # rebuilt meanwhile: the new timeline wins
        return {**data, "stale": True}
    write(data, video)
    return {**data, "stale": False}


def at(data: dict, t: float) -> dict[str, list[dict]]:
    """What is on every track at time t (shots/texts covering it, the nearest note)."""
    out: dict[str, list[dict]] = {}
    for tr in data.get("tracks", []):
        if tr["id"] == "notes":
            near = [x for x in tr["items"] if abs(x["t0"] - t) <= 1.0]
            hits = sorted(near, key=lambda x: abs(x["t0"] - t))[:1]
        else:
            hits = [x for x in tr["items"] if x["t0"] <= t < x["t1"]]
        if hits:
            out[tr["id"]] = hits
    return out


def describe(data: dict, t: float) -> str:
    """One line for a comment anchor: '01:23.4 · plan 12 (01:20.1-01:24.9) · Caption: ...'."""
    parts = [stamp(t)]
    hits = at(data, t)
    for x in hits.get("shots", []):
        shots = track(data, "shots")
        n = len(shots["items"]) if shots else 0
        parts.append(f"plan {x['label'].split(' ')[0]}/{n} ({stamp(x['t0'])}-{stamp(x['t1'])})")
    for x in hits.get("text", [])[:2]:
        parts.append(x["label"])
    for x in hits.get("chapters", []):
        parts.append(f"bölüm: {x['label']}")
    for x in hits.get("notes", []):
        parts.append(f"not ({stamp(x['t0'])}): {x['label']}")
    return " · ".join(parts)


def stamp(t: float, digits: int = 1) -> str:
    """83.42 -> '01:23.4' (rounded first: 59.96 is '01:00.0', never '00:60.0')."""
    t = round(max(0.0, t), digits)
    m, s = divmod(t, 60)
    return f"{int(m):02d}:{s:0{3 + digits}.{digits}f}"


def words(video: PathLike, lang: str = "tr") -> list[dict]:
    """The delivered video's words with their times (cached transcript, hallucinated runs out)."""
    from vlogkit.analysis.transcribe import drop_hallucinated_words, transcribe
    from vlogkit.ff import probe

    if not probe(video).has_audio:  # a silent delivery (reel _muziksiz): nothing to say
        return []
    ws = drop_hallucinated_words([w for w in transcribe(video, lang, words=True) if w.text.strip()])
    return [{"t0": round(w.start, 3), "t1": round(w.end, 3), "w": w.text.strip()} for w in ws]
