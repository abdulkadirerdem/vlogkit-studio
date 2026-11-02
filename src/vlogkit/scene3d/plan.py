"""From scene.json to timings and a render plan.

The narration sets the clock: every beat's line is spoken first (speech.tts), its measured length
plus `hold` is the beat's length, and the shots, captions, counter changes and sound effects all
hang off those times. Nothing is estimated from the text.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from vlogkit.config import FONTS_DIR
from vlogkit.scene3d import library
from vlogkit.scene3d import spec as specmod
from vlogkit.speech import tts

LEAD = 0.15  # s of picture before the first word (the first sound still lands inside 0.5 s)
GAP = 0.12  # s between beats when a beat has no hold of its own
KIT = Path(__file__).with_name("bpy_kit")
VOWELS = set("aeıioöuüAEIİOÖUÜâîû")


@dataclass
class Beat:
    index: int
    t0: float  # start on the delivered timeline (s)
    t1: float  # end (s)
    speech: Path | None
    speech_at: float  # where the line starts (s)
    speech_len: float
    words: list[tuple[str, float, float]] = field(default_factory=list)  # (word with [], t0, t1)
    raw: dict = field(default_factory=dict)

    @property
    def dur(self) -> float:
        return self.t1 - self.t0


def syllables(word: str) -> int:
    """Turkish: one syllable per vowel (a fair proxy for how long a word takes to say)."""
    return max(1, sum(ch in VOWELS for ch in word))


def word_times(text: str, t0: float, length: float) -> list[tuple[str, float, float]]:
    """Spread the line's words over its spoken length by syllables; a comma or a full stop adds a
    short pause after its word."""
    words = text.split()
    weights = [
        syllables(re.sub(r"[^\wçğıöşüÇĞİÖŞÜ]", "", w)) + (0.6 if re.search(r"[,.!?;:]$", w) else 0)
        for w in words
    ]
    total = sum(weights) or 1.0
    out, t = [], t0
    for w, k in zip(words, weights, strict=True):
        d = length * k / total
        out.append((w, t, t + d))
        t += d
    return out


def chunks(
    words: list[tuple[str, float, float]], max_words: int = 3, max_chars: int = 18
) -> list[tuple[str, float, float]]:
    """Caption groups: up to 3 words / 18 characters, broken after punctuation."""
    out: list[tuple[str, float, float]] = []
    cur: list[tuple[str, float, float]] = []
    for w in words:
        text = " ".join(x for x, _, _ in [*cur, w])
        if cur and (len(cur) >= max_words or len(specmod.spoken(text)) > max_chars):
            out.append((" ".join(x for x, _, _ in cur), cur[0][1], cur[-1][2]))
            cur = []
        cur.append(w)
        if re.search(r"[.!?;:]$", w[0]):
            out.append((" ".join(x for x, _, _ in cur), cur[0][1], cur[-1][2]))
            cur = []
    if cur:
        out.append((" ".join(x for x, _, _ in cur), cur[0][1], cur[-1][2]))
    return out


def narrate(spec: dict, work: Path, engine: str | None = None) -> list[Beat]:
    """Speak every beat (cached) and lay the beats out on the timeline."""
    v = spec.get("voice") or {}
    lines = [
        tts.Line(
            specmod.spoken(b["say"]), v.get("voice"), v.get("emotion"), float(v.get("speed", 1.0))
        )
        for b in spec["beats"]
    ]
    vf = Path(v["file"]).expanduser() if v.get("file") else None
    said = tts.speak(lines, work / "voice", engine or v.get("engine", "auto"), vf)
    beats: list[Beat] = []
    t = 0.0
    for i, (b, s) in enumerate(zip(spec["beats"], said, strict=True)):
        lead = LEAD if i == 0 else 0.0
        hold = float(b.get("hold", GAP))
        start = t
        at = t + lead
        end = at + s.duration + hold
        if i == len(spec["beats"]) - 1 and spec.get("end"):
            end += float(spec["end"].get("seconds", 2.0))
        beats.append(
            Beat(
                i,
                start,
                end,
                s.path,
                at,
                s.duration,
                word_times(b["say"].replace("\n", " "), at, s.duration),
                b,
            )
        )
        t = end
    return beats


def kit_version() -> str:
    h = hashlib.sha1()
    for p in sorted(KIT.glob("*.py")):
        h.update(p.read_bytes())
    return h.hexdigest()[:12]


def _steps(a: dict) -> list[dict]:
    do = a.get("do")
    if not do:
        return []
    if isinstance(do, str):
        return [{"do": do, "from": 0.0, "to": 1.0, "path": a.get("path")}]
    out = []
    for i, st in enumerate(do):
        nxt = do[i + 1].get("from", 1.0) if i + 1 < len(do) else 1.0
        out.append(
            {
                "do": st["do"],
                "from": st.get("from", 0.0 if i == 0 else None),
                "to": st.get("to", nxt),
                "path": st.get("path") or a.get("path"),
            }
        )
    for i, st in enumerate(out):  # a step without `from` starts where the previous ended
        if st["from"] is None:
            st["from"] = out[i - 1]["to"]
    return out


def render_plan(
    spec: dict,
    beats: list[Beat],
    frames_dir: Path,
    fps: float,
    size: tuple[int, int],
    engine: str,
    quality: str | None = None,
) -> dict:
    q = specmod.QUALITY[quality or spec.get("quality", "normal")]
    kit = kit_version()
    shots = []
    for b in beats:
        raw = b.raw
        n = round(b.t1 * fps) - round(b.t0 * fps)
        actors = []
        for a in raw.get("actors") or []:
            acts = [
                {
                    "do": st["do"],
                    "t0": st["from"] * b.dur,
                    "t1": st["to"] * b.dur,
                    "path": st.get("path"),
                }
                for st in _steps(a)
            ]
            talk = (
                [[b.speech_at - b.t0, b.speech_at - b.t0 + b.speech_len]] if a.get("talk") else []
            )
            actors.append(
                {"who": a["who"], "at": a.get("at", [0, 0]), "facing": a.get("facing", 0), "face": a.get("face", "happy"),
                 "look": a.get("look", [0, 0]), "size": a.get("size"), "acts": acts, "talk": talk,
                 "faces": [{"face": f["face"], "t": f.get("at", 0) * b.dur} for f in a.get("faces", [])]}
            )  # fmt: skip
        shot = {
            "id": f"b{b.index + 1:02d}",
            "frames": n,
            "set": raw["set"],
            "set_opts": raw.get("set_opts") or {},
            "actors": actors,
            "props": raw.get("props") or [],
            "camera": raw.get("camera") or {},
            "cast": {a["who"]: spec["cast"][a["who"]] for a in actors},
        }
        shot["key"] = hashlib.sha1(
            json.dumps(
                [shot, kit, engine, q, size, fps], sort_keys=True, ensure_ascii=False
            ).encode()
        ).hexdigest()[:16]
        shot["out"] = str(frames_dir / shot["id"])
        shots.append(shot)
    return {
        "fps": fps,
        "size": list(size),
        "engine": engine,
        "samples": q["samples"],
        "motion_blur": q["motion_blur"],
        "font": str(FONTS_DIR / "Montserrat-Black.ttf"),
        "library": str(library.blend_path()) if library.ready() else "",
        "hdri_dir": str(library.hdri_dir()) if library.ready() else "",
        "world": str(library.world_path()) if library.world_ready() else "",
        "cast": spec.get("cast") or {},
        "shots": shots,
    }
