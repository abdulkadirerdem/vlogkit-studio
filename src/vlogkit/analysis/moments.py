"""`vlogkit moments`: Short candidates in a long video, with the signals to judge them by.

The tool does not score: hand-tuned "virality" formulas pick worse than a model looking at the
words and the frames (and nobody can show they predict views). It cuts the speech into
paragraphs (pauses >= 0.9 s), builds every 15-60 s window that starts and ends on a paragraph
edge, and writes for each: the opening words (the hook), how dense the speech is, the loudest
moment, how much the picture moves, and a row of frames. The agent then rates each candidate
on the rubric in docs/viral-edit.md (hook, flow, value, 1-5 each, one-line reason) and shows a
ranking, never a prediction.

Without speech (a music vlog) the shots are the units instead of paragraphs.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from itertools import pairwise
from pathlib import Path

from vlogkit.analysis.transcribe import Segment
from vlogkit.ff import PathLike, probe

PARAGRAPH_GAP = 0.9  # s of silence between sentences that ends a paragraph
UNIT_MAX = 45.0  # a paragraph longer than this is split at its sentences


@dataclass
class Unit:
    t0: float
    t1: float
    text: str
    sentences: list[tuple[float, str]] = field(default_factory=list)  # (start, text)


@dataclass
class Moment:
    t0: float
    t1: float
    text: str
    hook: str  # what is said in the first 3 s
    words_per_s: float
    loudest: float  # time of the loudest 400 ms (momentary LUFS)
    loudest_lufs: float
    motion: float  # mean frame difference (0-100) across the window
    units: int
    frames: list[float] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.t1 - self.t0


def paragraphs(
    segs: Sequence[Segment], gap: float = PARAGRAPH_GAP, cap: float = UNIT_MAX
) -> list[Unit]:
    """Sentences joined while the pause between them is short and the paragraph stays short."""
    units: list[Unit] = []
    for s in segs:
        text = s.text.strip()
        if not text or s.suspicious:
            continue
        last = units[-1] if units else None
        if last and s.start - last.t1 < gap and s.end - last.t0 <= cap:
            last.t1, last.text = s.end, f"{last.text} {text}"
            last.sentences.append((s.start, text))
        else:
            units.append(Unit(s.start, s.end, text, [(s.start, text)]))
    return units


def shot_units(cuts: Sequence[float], duration: float, cap: float = 8.0) -> list[Unit]:
    """No speech: consecutive shots grouped into ~`cap` s units."""
    marks = [0.0, *sorted(c for c in cuts if 0 < c < duration), duration]
    units: list[Unit] = []
    for a, b in pairwise(marks):
        if units and b - units[-1].t0 <= cap:
            units[-1].t1 = b
        else:
            units.append(Unit(a, b, ""))
    return units


def windows(units: Sequence[Unit], lo: float = 15.0, hi: float = 60.0) -> list[tuple[int, int]]:
    """(first, last) unit index of every window between lo and hi seconds that starts and ends on
    a unit edge; per start the longest one that fits (the agent trims, it rarely extends)."""
    out = []
    for i in range(len(units)):
        best = None
        for j in range(i, len(units)):
            d = units[j].t1 - units[i].t0
            if d > hi:
                break
            if d >= lo:
                best = j
        if best is not None:
            out.append((i, best))
    return out


def _mean(xs: Sequence[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def build(
    units: Sequence[Unit],
    spans: Sequence[tuple[int, int]],
    loud: Sequence[tuple[float, float]],
    motion: Sequence[tuple[float, float]],
) -> list[Moment]:
    out = []
    for i, j in spans:
        a, b = units[i].t0, units[j].t1
        text = " ".join(u.text for u in units[i : j + 1] if u.text)
        hook = " ".join(t for u in units[i : j + 1] for st, t in u.sentences if st < a + 3.0)
        words = len(text.split())
        inside = [(t, v) for t, v in loud if a <= t <= b and v > -70]
        lt, lv = max(inside, key=lambda x: x[1]) if inside else (a, -70.0)
        mv = _mean([v for t, v in motion if a <= t <= b])
        frames = [a + 0.5, a + (b - a) / 3, a + 2 * (b - a) / 3, b - 0.5]
        out.append(Moment(a, b, text, hook[:160], words / (b - a), lt, lv, mv, j - i + 1, frames))
    return out


def find(
    path: PathLike,
    lang: str = "tr",
    lo: float = 15.0,
    hi: float = 60.0,
) -> list[Moment]:
    """All candidates of one video (transcript and measurements are cached / one pass each)."""
    from vlogkit.analysis.loudness import momentary
    from vlogkit.analysis.pacing import scores
    from vlogkit.analysis.transcribe import transcribe

    info = probe(path)
    segs: list[Segment] = []
    if info.has_audio:
        try:
            segs = transcribe(path, lang)
        except Exception:  # no whisper: fall back to shots
            segs = []
    if lo >= hi:
        raise ValueError("--min, --max'tan küçük olmalı")
    motion = scores(path)
    units = paragraphs(segs)
    spans = windows(units, lo, hi)
    if not spans:  # no speech, or too little to make a window: the shots are the units
        from vlogkit.analysis.pacing import changes

        cuts, _ = changes(motion)
        units = shot_units(cuts, info.duration)
        spans = windows(units, lo, hi)
    loud = momentary(path) if info.has_audio else []
    return build(units, spans, loud, motion)


def write(moments: Sequence[Moment], path: PathLike, out_dir: Path) -> tuple[Path, list[Path]]:
    """moments.md (the table the agent rates), moments.json and frame pages (4 frames each)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    per = 10
    pages = [
        _page(path, moments[p : p + per], p, out_dir / f"moments_{p // per + 1}.jpg")
        for p in range(0, len(moments), per)
    ]
    lines = [
        f"# Short adayları: {Path(path).name}",
        "",
        "Sıralama sende: her adaya Kanca, Akış, Değer (1-5) ver, gerekçeyi tek satır yaz "
        "(docs/viral-edit.md). Bu bir tahmin değil, sıralama.",
        "",
        "| # | Aralık | Süre | Açılış (ilk 3 sn) | Kelime/sn | En yüksek ses | Hareket |",
        "|---|---|---|---|---|---|---|",
    ]
    for k, m in enumerate(moments, 1):
        hook = m.hook.replace("|", "/") or "(konuşma yok)"
        lines.append(
            f"| {k} | {_stamp(m.t0)}-{_stamp(m.t1)} | {m.length:.0f} sn | {hook} | "
            f"{m.words_per_s:.1f} | {_stamp(m.loudest)} ({m.loudest_lufs:.0f} LUFS) | {m.motion:.1f} |"
        )
    lines += ["", "Kare sayfaları: " + ", ".join(str(p) for p in pages), ""]
    for k, m in enumerate(moments, 1):
        if m.text:
            lines += [f"**{k}.** {m.text}", ""]
    md = out_dir / "moments.md"
    md.write_text("\n".join(lines))
    (out_dir / "moments.json").write_text(
        json.dumps([asdict(m) for m in moments], ensure_ascii=False, indent=1)
    )
    return md, pages


def _page(path: PathLike, page: Sequence[Moment], offset: int, out: Path) -> Path:
    """Four frames per candidate (start, thirds, end), one row each."""
    from PIL import Image, ImageDraw

    from vlogkit.analysis.sheets import grab
    from vlogkit.graphics.style import font

    info = probe(path)
    size = (108, 192) if info.vertical else (192, 108)
    flat = grab(path, [t for m in page for t in m.frames], size)
    label_w = 120
    im = Image.new(
        "RGB", (label_w + 4 * (size[0] + 2), len(page) * (size[1] + 6) + 6), (18, 20, 23)
    )
    d = ImageDraw.Draw(im)
    for r, m in enumerate(page):
        y = 6 + r * (size[1] + 6)
        d.text(
            (8, y + 4), f"Aday {offset + r + 1}", font=font("ExtraBold", 15), fill=(255, 207, 64)
        )
        d.text(
            (8, y + 26),
            f"{_stamp(m.t0)}-{_stamp(m.t1)}",
            font=font("SemiBold", 12),
            fill=(220, 220, 220),
        )
        for c in range(len(m.frames)):
            f = flat[r * 4 + c]
            if f is not None:
                im.paste(f, (label_w + c * (size[0] + 2), y))
    im.save(out, quality=88)
    return out


def _stamp(t: float) -> str:
    m, s = divmod(round(t), 60)
    return f"{m}:{s:02d}"
