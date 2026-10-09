"""Music structure for beat-synced edits: beats, bars (downbeats), energy per bar and drops.

- Beats: aubio's beat tracker, regularised: missed beats are filled in and double hits dropped,
  so every bar really has `meter` beats (a hole would make a bar twice as long).
- Bars: the beats grouped by `meter` (4/4). The downbeat phase is the one whose beats carry the
  most bass: in pop/trap/EDM the kick lands on the "one".
- Energy: momentary loudness (400 ms windows every 100 ms) of the full mix and of the bass band
  (< 150 Hz), averaged per bar in the power domain.
- Drop: a bar whose bass jumps well above the bars just before it (after a build-up or a break)
  and is among the loudest of the song. That is where the edit hits hardest.
"""

from __future__ import annotations

import math
import re
import statistics
from dataclasses import dataclass, field
from itertools import pairwise
from pathlib import Path

from vlogkit.analysis.beats import beats as aubio_beats
from vlogkit.ff import PathLike, ffmpeg, probe

_M = re.compile(r"lavfi\.r128\.M=(-?[0-9.]+|-inf)")
SILENT = -70.0


@dataclass(frozen=True)
class Bar:
    start: float
    end: float
    energy: float  # LUFS, full mix
    bass: float  # LUFS, < 150 Hz
    level: str = "mid"  # "low" | "mid" | "high"


@dataclass(frozen=True)
class Music:
    path: Path
    duration: float
    bpm: float
    beats: list[float]
    downbeats: list[float]
    bars: list[Bar]
    drops: list[float] = field(default_factory=list)

    @property
    def beat_len(self) -> float:
        return 60.0 / self.bpm if self.bpm else 0.5

    def bar_at(self, t: float) -> Bar | None:
        return next((b for b in self.bars if b.start <= t < b.end), None)

    def beats_in(self, t0: float, t1: float) -> list[float]:
        return [b for b in self.beats if t0 <= b < t1]

    def nearest_downbeat(self, t: float) -> float:
        return min(self.downbeats, key=lambda d: abs(d - t)) if self.downbeats else t


def loudness_series(path: PathLike, bass: bool = False) -> list[float]:
    """Momentary loudness every 100 ms (index i = time (i + 1) * 0.1 s)."""
    chain = ("lowpass=f=150,lowpass=f=150," if bass else "") + (
        "ebur128=metadata=1,ametadata=print:key=lavfi.r128.M"
    )
    r = ffmpeg(["-i", path, "-vn", "-af", chain, "-f", "null", "-"], loglevel="info", capture=True)
    return [SILENT if v == "-inf" else max(SILENT, float(v)) for v in _M.findall(r.stderr)]


def _at(series: list[float], t: float) -> float:
    i = min(len(series) - 1, max(0, round(t / 0.1) - 1))
    return series[i] if series else SILENT


def power_mean(series: list[float], t0: float, t1: float) -> float:
    """Mean loudness over [t0, t1) in the power domain (a loud hit counts like a loud hit)."""
    vals = [v for i, v in enumerate(series) if t0 <= (i + 1) * 0.1 < t1] or [_at(series, t0)]
    p = sum(10 ** (v / 10) for v in vals) / len(vals)
    return 10 * math.log10(p) if p > 0 else SILENT


def regularize(beats: list[float], period: float) -> list[float]:
    """Fill gaps of n periods with n-1 evenly spaced beats; drop hits closer than half a period."""
    out: list[float] = []
    for b in beats:
        if out and b - out[-1] < 0.5 * period:
            continue
        if out:
            n = round((b - out[-1]) / period)
            out += [out[-1] + (b - out[-1]) * k / n for k in range(1, n)] if n > 1 else []
        out.append(b)
    return out


def downbeat_phase(beats: list[float], bass: list[float], meter: int = 4) -> int:
    def weight(p: int) -> float:
        picks = beats[p::meter]
        return statistics.fmean(_at(bass, b + 0.05) for b in picks) if picks else SILENT

    return max(range(min(meter, len(beats)) or 1), key=weight)


def levels(bars: list[Bar]) -> list[Bar]:
    """high: within 3 LU of the loudest bars; low: 9+ LU below them; mid: the rest."""
    if not bars:
        return bars
    top = sorted((b.energy for b in bars), reverse=True)
    ref = top[min(len(top) - 1, max(0, len(top) // 10))]  # 90th percentile: ignore one spike
    out = []
    for b in bars:
        lvl = "high" if b.energy >= ref - 3 else "low" if b.energy <= ref - 9 else "mid"
        out.append(Bar(b.start, b.end, b.energy, b.bass, lvl))
    return out


def drops(bars: list[Bar], jump: float = 6.0) -> list[float]:
    """Bars where the bass jumps `jump` dB above the two bars before and the level is high."""
    out = []
    for i in range(2, len(bars)):
        before = max(bars[i - 1].bass, bars[i - 2].bass)
        if bars[i].level == "high" and bars[i].bass - before >= jump:
            out.append(bars[i].start)
    return out


def analyze(path: PathLike, meter: int = 4) -> Music:
    path = Path(path)
    dur = probe(path).duration
    bt = aubio_beats(path)
    if len(bt) < 2:
        raise ValueError(f"vuruş bulunamadı: {path.name}")
    period = statistics.median(b - a for a, b in pairwise(bt))
    bt = regularize(bt, period)
    bpm = 60.0 / period
    full, bass = loudness_series(path), loudness_series(path, bass=True)
    phase = downbeat_phase(bt, bass, meter)
    downs = bt[phase::meter]
    marks = [*downs, dur]
    bars = [
        Bar(a, b, power_mean(full, a, b), power_mean(bass, a, b))
        for a, b in pairwise(marks)
        if b - a > 0.2
    ]
    bars = levels(bars)
    return Music(path, dur, round(bpm, 2), bt, downs, bars, drops(bars))


_GRID_LEVEL = {".": ("low", -22.0, -40.0), "-": ("mid", -14.0, -20.0), "#": ("high", -9.0, -10.0)}


def grid(
    bpm: float,
    energy: str,
    first_downbeat: float = 0.0,
    meter: int = 4,
    path: PathLike = "tempo-map",
) -> Music:
    """A song's structure from its tempo map, without the audio file.

    For a song that may not be downloaded (a trending track the user adds later in the Instagram
    app): BPM and section layout come from a public source or are counted by ear. `energy` has
    one character per bar, like `energy_map` prints: '.' low, '-' mid, '#' high, 'D' drop (a high
    bar the edit hits hardest); spaces and '|' are ignored, so "....|--##|D###" reads well.
    Time 0 is the song time the map starts at; `first_downbeat` is where its first bar begins.
    The beats are an exact grid: on a steady-tempo song every cut lands on a beat once the first
    drop is lined up.
    """
    bars_spec = [c for c in energy if c not in " |"]
    if not bars_spec or any(c not in ".-#D" for c in bars_spec):
        raise ValueError(f"enerji haritası yalnız . - # D içerebilir: {energy!r}")
    beat = 60.0 / bpm
    bar_len = beat * meter
    beats = [first_downbeat + k * beat for k in range(len(bars_spec) * meter)]
    downs = beats[::meter]
    bars, drop_times = [], []
    for t, c in zip(downs, bars_spec, strict=True):
        level, e, b = _GRID_LEVEL["#" if c == "D" else c]
        bars.append(Bar(t, t + bar_len, e, b, level))
        if c == "D":
            drop_times.append(t)
    duration = first_downbeat + len(bars_spec) * bar_len
    return Music(Path(path), duration, round(bpm, 3), beats, downs, bars, drop_times)


def anchored(
    bpm: float, drop: float, energy: str | None = None, meter: int = 4, cover: float = 30.0
) -> tuple[str, float]:
    """`grid`'s energy map and first downbeat for a song known by its tempo and drop time only.

    A drop starts a bar, so its time (heard in the app, or read from synced lyrics) fixes the
    grid's phase: the bars before it are counted back towards the start of the song. Without
    `energy` the map is a common layout: mid bars up to the drop, eight loud bars from it, then
    mid bars until `cover` s after the drop. With `energy`, its first 'D' bar lands on the drop.
    """
    if bpm <= 0 or drop < 0:
        raise ValueError(f"tempo pozitif, drop 0 ya da sonrası olmalı (bpm {bpm:g}, drop {drop:g})")
    bar = 60.0 / bpm * meter
    if energy is None:
        before = int((drop + 1e-6) // bar)
        after = max(8, math.ceil(cover / bar) + 1)
        energy = "-" * before + "D" + "#" * 7 + "-" * (after - 8)
    else:
        bars_spec = [c for c in energy if c not in " |"]
        if "D" not in bars_spec:
            raise ValueError(f"haritada drop (D) yok: {energy!r}")
        before = bars_spec.index("D")
    first = drop - before * bar
    if first < -1e-6:
        raise ValueError(
            f"haritada drop'tan önce {before} ölçü ({before * bar:.1f} sn) var, "
            f"ama drop şarkının {drop:g}. saniyesinde"
        )
    return energy, round(max(first, 0.0), 4)


def energy_map(m: Music) -> str:
    """One character per bar: '.' low, '-' mid, '#' high, 'D' drop."""
    drop_set = {round(d, 3) for d in m.drops}
    chars = {"low": ".", "mid": "-", "high": "#"}
    return "".join("D" if round(b.start, 3) in drop_set else chars[b.level] for b in m.bars)


def report(m: Music) -> list[str]:
    first = m.downbeats[0] if m.downbeats else 0.0
    lines = [
        f"{m.path.name}: {m.duration:.1f} sn, {m.bpm:g} BPM (vuruş {m.beat_len:.3f} sn), "
        f"{len(m.bars)} ölçü, ilk ölçü başı {first:.2f} sn",
        f"enerji (ölçü başına; . düşük, - orta, # yüksek, D drop): {energy_map(m)}",
    ]
    lines += [f"drop: {d:.2f} sn" for d in m.drops] or ["drop bulunamadı (düz enerji)"]
    return lines
