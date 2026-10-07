"""Building blocks for time-varying ffmpeg expressions (`t` = frame timestamp in seconds).

Two traps these helpers exist for:
- `0 * exp(big)` is `0 * inf = NaN`. Wrap windowed terms with `when(...)`: ffmpeg's `if()` only
  evaluates the chosen branch.
- While a filter graph (re)configures, `t` is NaN. Filters that size frames (scale) must get a
  finite value then -> `nan_safe(...)`.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise

from vlogkit.timecode import fmt


def between(t0: float, t1: float) -> str:
    return f"between(t,{fmt(t0)},{fmt(t1)})"


def when(cond: str, expr: str, otherwise: str = "0") -> str:
    return f"if({cond},{expr},{otherwise})"


def window(t0: float, t1: float, expr: str) -> str:
    """`expr` inside [t0, t1], 0 elsewhere (lazily evaluated)."""
    return when(between(t0, t1), expr)


def ramp(t0: float, t1: float) -> str:
    """0 -> 1 linearly across [t0, t1], clamped outside."""
    return f"clip((t-{fmt(t0)})/{fmt(t1 - t0)},0,1)"


def nan_safe(expr: str, fallback: str) -> str:
    return f"if(isnan(t),{fallback},{expr})"


def total(base: str, terms: list[str]) -> str:
    return f"({base}" + "".join(f"+{x}" for x in terms) + ")"


def piecewise(keys: Sequence[tuple[float, float]]) -> str:
    """Linear interpolation through (t, value) keys; holds the first/last value outside.

    Two keys close together make a step (e.g. a new value exactly at a cut).

    Built as a balanced tree of `if(lt(t,mid),left,right)`: ffmpeg's expression parser rejects
    flat sums of more than ~100 terms, and the tree evaluates only log2(n) branches per frame.
    """
    if not keys:
        return "0"
    segs: list[tuple[float, str]] = [(float("-inf"), fmt(keys[0][1]))]  # (start, expr)
    for (ta, va), (tb, vb) in pairwise(keys):
        if tb <= ta:
            continue
        seg = fmt(va) if va == vb else f"({fmt(va)}+{fmt(vb - va)}*(t-{fmt(ta)})/{fmt(tb - ta)})"
        segs.append((ta, seg))
    segs.append((keys[-1][0], fmt(keys[-1][1])))

    def tree(lo: int, hi: int) -> str:
        if hi - lo == 1:
            return segs[lo][1]
        mid = (lo + hi) // 2
        return f"if(lt(t,{fmt(segs[mid][0])}),{tree(lo, mid)},{tree(mid, hi)})"

    return tree(0, len(segs))


def piecewise_at(keys: Sequence[tuple[float, float]], t: float) -> float:
    """Python twin of `piecewise` (tests, plots)."""
    if t < keys[0][0]:
        return keys[0][1]
    for (ta, va), (tb, vb) in pairwise(keys):
        if ta <= t < tb:
            return va + (vb - va) * (t - ta) / (tb - ta)
    return keys[-1][1]
