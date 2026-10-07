"""Pacing: where does the picture stay the same for too long?

Retention advice (docs/viral-edit.md): the same framing should not stay on screen longer than
about 2-3 s in a Short or 3-5 s in a long video. Run this on the *rendered* video: burned-in
captions, zoom punches and flashes are then visual changes too.

A "change" is either a cut (a big frame-difference score, also inside fast sections such as a
rewind) or a pop: a jump well above the recent level (a punch-in, a flash). Continuous handheld
motion is *not* a change: the same shot wobbling is still the same shot.

Small graphics (a caption popping in) barely move the frame difference (score < 1), so with a
project the overlay elements' start times are added as changes (`extra`).
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass
from itertools import pairwise

from vlogkit.ff import PathLike, ffmpeg, probe

_FRAME = re.compile(r"pts_time:([0-9.]+)")
_SCORE = re.compile(r"lavfi\.scd\.score=([0-9.]+)")
TARGET = {"short": 3.0, "long": 5.0}  # longest stretch without a change (s)


@dataclass(frozen=True)
class Pace:
    duration: float
    cuts: list[float]
    changes: list[float]  # cuts + pops, sorted
    stretches: list[tuple[float, float]]  # longer than `limit` without any change
    limit: float

    @property
    def avg_shot(self) -> float:
        return self.duration / (len(self.cuts) + 1)

    @property
    def avg_change(self) -> float:
        return self.duration / (len(self.changes) + 1)

    @property
    def static_share(self) -> float:
        return sum(b - a for a, b in self.stretches) / self.duration if self.duration else 0.0


def scores(
    path: PathLike, fps: float = 10.0, start: float = 0.0, duration: float | None = None
) -> list[tuple[float, float]]:
    """(time, frame-difference score 0-100) at `fps` on a small copy of the picture."""
    cut = (["-ss", f"{start:.3f}"] if start else []) + (
        ["-t", f"{duration:.3f}"] if duration else []
    )
    r = ffmpeg(
        [
            *cut,
            "-i",
            path,
            "-an",
            "-vf",
            f"fps={fps},scale=160:-2,scdet=threshold=100,metadata=print:key=lavfi.scd.score",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
        capture=True,
    )
    times = [start + float(x) for x in _FRAME.findall(r.stderr)]
    vals = [float(x) for x in _SCORE.findall(r.stderr)]
    return list(zip(times, vals, strict=False))


def changes(
    series: list[tuple[float, float]],
    cut: float = 8.0,
    pop: float = 3.0,
    ratio: float = 2.5,
    window: float = 1.0,
    min_gap: float = 0.3,
) -> tuple[list[float], list[float]]:
    """(cuts, all changes) from a score series. A pop must beat `ratio` x the recent median."""
    cuts, events = [], []
    for i, (t, s) in enumerate(series):
        recent = [v for (u, v) in series[max(0, i - 30) : i] if t - u <= window]
        base = statistics.median(recent) if recent else 0.0
        is_cut = s >= cut  # absolute: a cut inside a busy section is still a cut
        is_pop = s >= pop and s >= ratio * max(base, 0.5)
        if not (is_cut or is_pop) or (events and t - events[-1] < min_gap):
            continue
        events.append(t)
        if is_cut:
            cuts.append(t)
    return cuts, events


def stretches(events: list[float], duration: float, limit: float) -> list[tuple[float, float]]:
    marks = [0.0, *events, duration]
    return [(a, b) for a, b in pairwise(marks) if b - a > limit]


def analyze(
    path: PathLike,
    kind: str | None = None,
    limit: float | None = None,
    extra: list[float] | None = None,
) -> Pace:
    """kind: "short" | "long" (default: from the aspect ratio). extra: overlay start times."""
    info = probe(path)
    kind = kind or ("short" if info.vertical else "long")
    limit = limit or TARGET[kind]
    cuts, events = changes(scores(path))
    events = sorted({round(t, 2) for t in [*events, *(extra or [])] if 0 <= t <= info.duration})
    return Pace(info.duration, cuts, events, stretches(events, info.duration, limit), limit)


def overlay_starts(elements) -> list[float]:
    """When each graphic appears (captions, cards, clocks...): visual changes the diff misses."""
    return [float(t) for e in elements if (t := getattr(e, "t0", None)) is not None]


def report(p: Pace) -> list[str]:
    lines = [
        f"{len(p.cuts)} kesme, {len(p.changes)} görsel değişim; ortalama plan {p.avg_shot:.1f} sn, "
        f"ortalama değişim aralığı {p.avg_change:.1f} sn (hedef <= {p.limit:g} sn)"
    ]
    if not p.stretches:
        lines.append(f"✓ {p.limit:g} sn'den uzun değişimsiz aralık yok")
    for a, b in p.stretches:
        lines.append(
            f"! {a:6.2f}-{b:6.2f} sn ({b - a:.1f} sn değişimsiz): punch-in, B-roll ya da yazı ekle"
        )
    return lines
