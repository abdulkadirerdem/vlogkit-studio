"""`vlogkit find`: the moments of raw footage that match some words, from the footage log.

It searches what `vlogkit log` knows about every ~4 s chunk: Claude's `desc` and `beat`, the local
video model's action and setting (English), the Vision labels and the speech. The model column is
English, so give the words in both languages ("ateş fire campfire"). Matching ignores case and
Turkish letters (göl = gol) and lets a word match the start of a longer one ("göl" finds "gölde",
"göle"): Turkish suffixes do not hide a hit; in the English model column a word of 4+ letters
also matches inside a compound ("fire" in "campfire"). A word of 3 letters can also hit an unrelated longer
word ("göl" / "gölge"); the frames page is there to check.

Ranking: a term counts once, by the strongest field it is found in (desc/beat 3, model 2, speech 2,
labels 1); chunks that match more of the terms come first. Neighbouring hits in one clip become one
range. Chunks the log flagged as unusable (setup, dark, blurry) are listed last and marked.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

from vlogkit.analysis.footage import Chunk, Log

WEIGHTS = {"desc": 3.0, "beat": 3.0, "model": 2.0, "speech": 2.0, "labels": 1.0}
_FOLD = str.maketrans("çğıöşüâîû", "cgiosuaiu")


def norm(text: str) -> list[str]:
    """Words, lower case the Turkish way, Turkish letters folded to ASCII (göl -> gol)."""
    text = str(text).replace("İ", "i").replace("I", "ı").lower().translate(_FOLD)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.findall(r"[a-z0-9]+", text)


def term_hits(term: str, words: Sequence[str], inside: bool = False) -> bool:
    """A whole word, the start of a word (Turkish suffixes) or, with inside=True and 4+ letters,
    anywhere in a word (English compounds in the model column: "fire" in "campfire")."""
    for w in words:
        if w == term or (len(term) >= 3 and w.startswith(term)):
            return True
        if inside and len(term) >= 4 and term in w:
            return True
    return False


def fields(c: Chunk) -> dict[str, list[str]]:
    local = c.local or {}
    model = " ".join(str(local.get(k, "")) for k in ("action", "setting"))
    return {
        "desc": norm(c.desc),
        "beat": norm(c.beat),
        "model": norm(model),
        "speech": norm(c.speech),
        "labels": norm(" ".join(c.labels)),
    }


RUN_MAX = 16.0  # s: a longer run of matching chunks is split (a range must stay specific)


@dataclass
class Hit:
    clip: str
    t0: float
    t1: float
    best: tuple[float, float]  # the best single chunk in the range
    score: float  # of the best chunk
    matched: list[str]  # terms the best chunk matches
    snippet: str
    usable: bool
    chunks: list[Chunk] = field(default_factory=list, repr=False)


def score(c: Chunk, terms: Sequence[str]) -> tuple[float, list[str]]:
    fs = fields(c)
    total, matched = 0.0, []
    for t in terms:
        best = max(
            (WEIGHTS[name] for name, ws in fs.items() if term_hits(t, ws, inside=name == "model")),
            default=0.0,
        )
        if best:
            total += best
            matched.append(t)
    return total, matched


def _snippet(c: Chunk) -> str:
    local = c.local or {}
    parts = [c.desc, str(local.get("action", "")), c.speech[:80], ", ".join(c.labels[:3])]
    return " | ".join(p for p in parts if p)


def _hit(clip: str, run: list[tuple[Chunk, float, list[str]]]) -> Hit:
    c, s, m = max(run, key=lambda x: (x[0].usable, len(x[2]), x[1]))
    return Hit(
        clip,
        run[0][0].t0,
        run[-1][0].t1,
        (c.t0, c.t1),
        s,
        m,
        _snippet(c),
        c.usable,
        [x[0] for x in run],
    )


def search(lg: Log, query: Sequence[str], limit: int = 15) -> list[Hit]:
    """Best ranges first: the best chunk's matched terms, then its score; unusable last."""
    terms = [t for q in query for t in norm(q)]
    if not terms:
        return []
    hits: list[Hit] = []
    for clip in lg.clips:
        run: list[tuple[Chunk, float, list[str]]] = []
        for c in clip.chunks:
            s, matched = score(c, terms)
            joins = (
                run
                and abs(c.t0 - run[-1][0].t1) < 0.05
                and c.t1 - run[0][0].t0 <= RUN_MAX
                and c.usable == run[-1][0].usable  # a flagged stretch is its own (last) row
            )
            if s and joins:
                run.append((c, s, matched))
                continue
            if run:
                hits.append(_hit(clip.path, run))
            run = [(c, s, matched)] if s else []
        if run:
            hits.append(_hit(clip.path, run))
    hits.sort(key=lambda h: (not h.usable, -len(h.matched), -h.score, h.clip, h.t0))
    return hits[:limit]


def log_path(target: Path) -> Path:
    """A log.json, or the log of a raw folder: build/log/<name>/log.json when it is that
    folder's log (two folders are often both called "ham"), else any log made for it."""
    import json

    from vlogkit.config import BUILD_DIR

    target = Path(target).expanduser()
    if target.is_file():
        return target
    want = target.resolve()

    def folder_of(p: Path) -> Path | None:
        try:
            return Path(json.loads(p.read_text()).get("folder", "")).expanduser().resolve()
        except (OSError, ValueError):
            return None

    first = BUILD_DIR / "log" / target.name / "log.json"
    for p in [first, *sorted((BUILD_DIR / "log").glob("*/log.json"))]:
        if p.exists() and folder_of(p) == want:
            return p
    raise FileNotFoundError(
        f"{target} için log yok: önce `uv run vlogkit log {target}` (model sütunu için --vlm)"
    )


def frames_page(hits: Sequence[Hit], out: Path) -> Path:
    """Three frames per hit (start, best chunk, end of the range), one row each, labelled."""
    from concurrent.futures import ThreadPoolExecutor

    from PIL import Image, ImageDraw

    from vlogkit.analysis.sheets import grab
    from vlogkit.ff import probe
    from vlogkit.graphics.style import font

    jobs = []
    for h in hits:
        try:
            size = (108, 192) if probe(h.clip).vertical else (192, 108)
        except Exception:  # the clip moved since the log was made: an empty row
            size = (192, 108)
        times = [h.t0 + 0.3, (h.best[0] + h.best[1]) / 2, max(h.t0, h.t1 - 0.3)]
        jobs.append((h, times, size))

    def frames_of(job):
        h, ts, size = job
        try:
            return grab(h.clip, ts, size)
        except Exception:  # a clip that moved or cannot be read: an empty row
            return [None] * len(ts)

    with ThreadPoolExecutor(4) as pool:
        grabbed = list(pool.map(frames_of, jobs))
    label_w = 230
    width = label_w + 3 * (max((s[0] for *_, s in jobs), default=0) + 2)
    height = sum(s[1] + 6 for *_, s in jobs) + 6
    im = Image.new("RGB", (width, max(height, 40)), (18, 20, 23))
    d = ImageDraw.Draw(im)
    y = 6
    for k, ((h, _, size), frames) in enumerate(zip(jobs, grabbed, strict=True), 1):
        color = (255, 207, 64) if h.usable else (255, 110, 110)
        d.text((8, y + 4), f"{k}. {Path(h.clip).name[:26]}", font=font("ExtraBold", 13), fill=color)
        d.text(
            (8, y + 24),
            f"{h.t0:.1f}-{h.t1:.1f} sn",
            font=font("SemiBold", 12),
            fill=(220, 220, 220),
        )
        d.text(
            (8, y + 42), ", ".join(h.matched)[:34], font=font("SemiBold", 12), fill=(160, 160, 160)
        )
        if not h.usable:
            d.text((8, y + 60), "bayraklı", font=font("SemiBold", 12), fill=(255, 110, 110))
        for c, f in enumerate(frames):
            if f is not None:
                im.paste(f, (label_w + c * (size[0] + 2), y))
        y += size[1] + 6
    out.parent.mkdir(parents=True, exist_ok=True)
    im.save(out, quality=88)
    return out
