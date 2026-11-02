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

from vlogkit.config import ASSETS_DIR, FONTS_DIR
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


_TR_LOWER = str.maketrans({"I": "ı", "İ": "i"})


def norm_word(w: str) -> str:
    """A word as cues match it: Turkish lower case, no brackets or punctuation."""
    return re.sub(r"[^\wçğıöşü]", "", str(w).translate(_TR_LOWER).lower())


def find_cue(say: str, cue: str) -> int | None:
    """Index of the first word of `say` that starts with the cue (a word or its first letters,
    "zıpla" finds "zıplasaydı"); several words ("aynı anda") match a run of words."""
    words = [norm_word(w) for w in say.replace("\n", " ").split()]
    want = [norm_word(x) for x in str(cue).split() if norm_word(x)]
    if not want:
        return None
    k = len(want)
    for i in range(len(words) - k + 1):
        run = words[i : i + k]
        if run[:-1] == want[:-1] and run[-1].startswith(want[-1]):
            return i
    return None


def cue_time(b: Beat, cue, scope: tuple[float, float] | None = None) -> float:
    """A moment in the beat, in seconds from the beat's start: a fraction of the scope (the beat,
    or the shot it was written in) or a word of the line (when it is spoken)."""
    s0, d = scope or (0.0, b.dur)
    if cue is None:
        return s0
    if isinstance(cue, (int, float)):
        return s0 + float(cue) * d
    i = find_cue(b.raw.get("say", ""), cue)
    if i is None or i >= len(b.words):
        raise ValueError(f"'{cue}' kelimesi cümlede yok: {b.raw.get('say', '')}")
    return b.words[i][1] - b.t0


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
                **{k: v for k, v in st.items() if k not in ("do", "from", "to", "path")},
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


SHOT_KEYS = ("set", "set_opts", "actors", "props", "camera", "fx", "crowd", "look")
MIN_SHOT = 0.45  # s: a shorter cut reads as a glitch


def shot_bounds(b: Beat, fps: float) -> list[tuple[int, int, int]]:
    """Each shot of the beat as (its index in `shots`, first frame, frame count) on the beat's own
    timeline (frame 1 = the beat's first frame). A shot starts at its `cue`, the first one at the
    beat's start; a cut comes no sooner than MIN_SHOT after the last, and a shot with no room
    left before the beat ends is dropped (the one before it runs on)."""
    n = round(b.t1 * fps) - round(b.t0 * fps)
    m = max(1, round(MIN_SHOT * fps))
    raw = b.raw.get("shots") or [{}]
    starts = [(0, 0)]
    for k, s in enumerate(raw[1:], 1):
        f = max(starts[-1][1] + m, round(cue_time(b, s.get("cue", None)) * fps))
        if f > n - m:
            continue
        starts.append((k, f))
    ends = [f for _, f in starts[1:]] + [n]
    return [(k, f + 1, max(1, e - f)) for (k, f), e in zip(starts, ends, strict=True)]


def _actor(a: dict, b: Beat, scope: tuple[float, float]) -> dict:
    s0, d = scope

    def at(v):
        return cue_time(b, v, scope) if isinstance(v, str) else s0 + float(v) * d

    acts = []
    for st in _steps(a):
        acts.append(
            {
                **{k: v for k, v in st.items() if k not in ("from", "to")},
                "t0": at(st["from"]),
                "t1": at(st["to"]),
            }
        )
    talk = [[b.speech_at - b.t0, b.speech_at - b.t0 + b.speech_len]] if a.get("talk") else []
    return {
        "who": a["who"], "at": a.get("at", [0, 0]), "facing": a.get("facing", 0),
        "face": a.get("face", "happy"), "look": a.get("look", [0, 0]), "size": a.get("size"),
        "acts": acts, "talk": talk,
        "faces": [{"face": f["face"], "t": at(f.get("at", 0))} for f in a.get("faces", [])],
    }  # fmt: skip


def _timed(items: list[dict], b: Beat, scope: tuple[float, float], key: str = "at") -> list[dict]:
    """Effects and prop moves: their `at` cue becomes seconds on the beat's timeline."""
    out = []
    for it in items:
        it = dict(it)
        it["t"] = cue_time(b, it.get(key), scope) if it.get(key) is not None else scope[0]
        out.append(it)
    return out


def _props(props: list[dict], b: Beat, scope: tuple[float, float]) -> list[dict]:
    out = []
    for p in props:
        p = dict(p)
        if p.get("anim"):
            p["anim"] = _timed(p["anim"], b, scope)
        if p.get("open"):
            p["open"] = _timed([p["open"]], b, scope)[0]
        hand = p.get("hand")
        if hand:
            steps = [{"who": hand}] if isinstance(hand, str) else hand
            p["hand"] = _timed(steps, b, scope)
        out.append(p)
    return out


def beat_shots(b: Beat, fps: float) -> list[dict]:
    """The beat's shots, resolved: every field a shot does not set comes from the beat; times are
    seconds on the beat's own timeline (fractions count in the beat, or in the shot that set the
    field)."""
    raw = b.raw
    shots_raw = raw.get("shots") or [{}]
    out = []
    beat_scope = (0.0, b.dur)
    for k, f0, nf in shot_bounds(b, fps):
        s = shots_raw[k]
        own = ((f0 - 1) / fps, nf / fps)

        def pick(key, default, s=s, own=own):
            return (s[key], own) if key in s else (raw.get(key, default), beat_scope)

        actors, a_scope = pick("actors", [])
        props, p_scope = pick("props", [])
        fx, f_scope = pick("fx", [])
        crowd, c_scope = pick("crowd", None)
        look, _ = pick("look", None)
        out.append(
            {
                "id": f"b{b.index + 1:02d}"
                + ("" if len(shots_raw) == 1 else "abcdefghijklmnop"[k]),
                "start": f0,
                "frames": nf,
                "span": round(b.t1 * fps) - round(b.t0 * fps),
                "at": round(b.t0 + (f0 - 1) / fps, 4),
                "set": s.get("set", raw.get("set")),
                "set_opts": s.get("set_opts", raw.get("set_opts")) or {},
                "actors": [_actor(a, b, a_scope) for a in actors or []],
                "props": _props(props or [], b, p_scope),
                "fx": _timed(fx or [], b, f_scope),
                "crowd": ({**crowd, "t": cue_time(b, crowd.get("at"), c_scope)} if crowd else None),
                "camera": s.get("camera", raw.get("camera")) or {},
                "look": look,
            }
        )
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
        for shot in beat_shots(b, fps):
            shot["cast"] = {a["who"]: spec["cast"][a["who"]] for a in shot["actors"]}
            # the look is drawn over the frames afterwards: it does not change the render
            keyed = {k: v for k, v in shot.items() if k not in ("look", "at")}
            shot["key"] = hashlib.sha1(
                json.dumps(
                    [keyed, kit, engine, q, size, fps], sort_keys=True, ensure_ascii=False
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
        "moon_dir": str(ASSETS_DIR / "moon"),
        "cast": spec.get("cast") or {},
        "shots": shots,
    }


def shot_at(p: dict, t: float, fps: float) -> tuple[dict, int]:
    """The shot on screen at `t` s and the frame of it (1 = the shot's first frame)."""
    shots = p["shots"]
    cur = shots[0]
    for s in shots:
        if s["at"] <= t + 1e-6:
            cur = s
    return cur, min(cur["frames"], max(1, round((t - cur["at"]) * fps) + 1))
