"""Ride the gain of a finished mix, cut by cut, before loudness normalisation.

Normalising alone keeps the mix's loudness range. A vlog that alternates between a quiet music bed
(-37 LUFS) and loud live sound (-17 LUFS) ends up with the bed at ~-30 LUFS after `normalize` to
-14: viewers reach for the volume knob. So: measure every span between cuts, give each a gain
towards a common target, then normalise the result.

Gain changes sit at the cuts (a change inside a shot is audible as a "pump"). When the gain drops
the ramp *ends* on the cut, when it rises it *starts* on the cut: a loud shot never begins with the
boost of the quiet shot before it.

A +16 dB boost also lifts every click and bump in the quiet bed. Put `peak_limiter(target)` right
after the gain: it shaves those spikes with a fast release, so the final (slower) mastering limiter
does not carve 60 ms holes into the music around them.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise

from vlogkit.timecode import fmt
from vlogkit.video.expr import piecewise, piecewise_at

SILENCE = -70.0  # momentary LUFS below this is ignored when measuring a span


@dataclass(frozen=True)
class Span:
    t0: float
    t1: float
    loudness: float  # measured (energy mean of momentary LUFS)
    gain: float  # dB


def energy_mean(values: Sequence[float]) -> float:
    """Loudness average the way LUFS integrates: in the power domain, not dB."""
    return 10 * math.log10(sum(10 ** (v / 10) for v in values) / len(values))


def span_loudness(momentary: Sequence[tuple[float, float]], t0: float, t1: float) -> float | None:
    vals = [v for t, v in momentary if t0 <= t < t1 and v > SILENCE]
    return energy_mean(vals) if vals else None


def plan(
    momentary: Sequence[tuple[float, float]],
    bounds: Sequence[float],
    target: float = -20.0,
    merge_within: float = 3.0,
    max_boost: float = 18.0,
    max_cut: float = 12.0,
    emphasis: Mapping[float, float] | None = None,
) -> list[Span]:
    """One gain per span between consecutive `bounds` (cut times, incl. start and end).

    momentary     `analysis.loudness.momentary` of the source
    target        where every span should sit (momentary LUFS, before normalisation)
    merge_within  neighbours closer than this (LU) share one gain: the music bed stays one bed
    emphasis      {span start: extra LU}, e.g. keep the big stage moment +3 LU above the rest
    """
    emphasis = emphasis or {}
    raw: list[list] = []  # [t0, t1, loudness]; emphasised spans never merge
    for a, b in pairwise(bounds):
        lo = span_loudness(momentary, a, b)
        if lo is None:
            lo = raw[-1][2] if raw else target
        prev = raw[-1] if raw else None
        if (
            prev
            and abs(lo - prev[2]) < merge_within
            and a not in emphasis
            and prev[0] not in emphasis
        ):
            w0, w1 = prev[1] - prev[0], b - a
            prev[2] = 10 * math.log10(
                (w0 * 10 ** (prev[2] / 10) + w1 * 10 ** (lo / 10)) / (w0 + w1)
            )
            prev[1] = b
        else:
            raw.append([a, b, lo])
    return [
        Span(a, b, lo, max(-max_cut, min(max_boost, target + emphasis.get(a, 0.0) - lo)))
        for a, b, lo in raw
    ]


def keyframes(spans: Sequence[Span], ramp: float = 0.12) -> list[tuple[float, float]]:
    """(time, dB) points: flat inside spans, `ramp`-long slopes at the cuts (down before, up after)."""
    if not spans:
        return []
    keys = [(spans[0].t0, spans[0].gain)]
    for a, b in pairwise(spans):
        cut = a.t1
        if b.gain < a.gain:
            keys += [(cut - ramp, a.gain), (cut, b.gain)]
        elif b.gain > a.gain:
            keys += [(cut, a.gain), (cut + ramp, b.gain)]
    keys.append((spans[-1].t1, spans[-1].gain))
    return keys


def gain_at(keys: Sequence[tuple[float, float]], t: float) -> float:
    """dB at time t (same curve as `gain_expr`), for tests and plots."""
    return piecewise_at(keys, t)


def duck_keys(
    spans: Sequence[tuple[float, float]],
    db: float,
    end: float,
    pre: float = 0.25,
    attack: float = 0.2,
    release: float = 0.35,
    bridge: float = 0.6,
) -> list[tuple[float, float]]:
    """(t, dB) keys that hold the music `db` under every span (speech), for `gain_expr`.

    Spans closer than `bridge` s are merged first: one duck per line put a 0 dB key just before
    each next line, and the music jumped up between two sentences cut back to back. The duck
    starts `pre` s before a span (reaching `db` `pre - attack` s before it) and lets go over
    `release` s after it.
    """
    merged: list[list[float]] = []
    gap = max(bridge, pre + release)  # closer than that, two ducks would overlap anyway
    for a, b in sorted(spans):
        if merged and a - merged[-1][1] < gap:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    keys: list[tuple[float, float]] = []
    for a, b in merged:
        if a - pre <= 0:  # speech from the first frame: ducked from the first frame
            keys.append((0.0, db))
        else:
            keys += [(a - pre, 0.0), (min(a, a - pre + attack), db)]
        keys += [(b, db), (b + release, 0.0)]
    if not keys or keys[0][0] > 0:
        keys.insert(0, (0.0, 0.0))
    held = [k for k in keys if k[0] < end]
    held.append((end, piecewise_at(keys, end)))
    return held


def gain_expr(keys: Sequence[tuple[float, float]]) -> str:
    """Linear gain multiplier for `volume='...':eval=frame` (t = stream time of that input)."""
    return f"pow(10,{piecewise(keys)}/20)" if keys else "1"


def peak_limiter(target: float = -20.0, headroom: float = 12.0, release: float = 25.0) -> str:
    """Fast limiter `headroom` dB above the leveling target (spikes only, not the music)."""
    limit = 10 ** ((target + headroom) / 20)
    return f"alimiter=limit={limit:.4f}:attack=1:release={fmt(release)}:level=0:asc=0"
