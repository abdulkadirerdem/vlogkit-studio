"""Colour grade as data -> ffmpeg filter chain.

Order: denoise -> eq (contrast/brightness/saturation/gamma) -> colorbalance -> curves -> sharpen
-> extra looks. Any eq value may be a time expression (str); then eval=frame is added.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, replace
from itertools import pairwise

from vlogkit.timecode import fmt
from vlogkit.video.expr import between

Num = float | str | None


@dataclass(frozen=True)
class Grade:
    denoise: str | None = "2:1.5:4:3"  # hqdn3d (low light phone/GoPro noise)
    contrast: Num = 1.07
    brightness: Num = 0.01
    saturation: Num = 1.2
    gamma: Num = 1.07
    colorbalance: str | None = "rs=-0.02:bs=0.03:rm=0.035:gm=0.005:bm=-0.03:rh=0.02:bh=-0.02"
    curves: str | None = "0/0 0.1/0.09 0.5/0.52 0.9/0.93 1/1"  # soft S, no crushed shadows
    sharpen: str | None = "5:5:0.45:5:5:0"  # unsharp, luma only
    extra: tuple[str, ...] = ()

    def but(self, **changes) -> Grade:
        return replace(self, **changes)

    def filter(self) -> str:
        parts: list[str] = []
        if self.denoise:
            parts.append(f"hqdn3d={self.denoise}")
        eq = [(k, getattr(self, k)) for k in ("contrast", "brightness", "saturation", "gamma")]
        eq = [(k, v) for k, v in eq if v is not None]
        if eq:
            dynamic = any(isinstance(v, str) for _, v in eq)
            body = ":".join(f"{k}='{v}'" if isinstance(v, str) else f"{k}={fmt(v)}" for k, v in eq)
            parts.append(f"eq={body}" + (":eval=frame" if dynamic else ""))
        if self.colorbalance:
            parts.append(f"colorbalance={self.colorbalance}")
        if self.curves:
            parts.append(f"curves=master='{self.curves}'")
        if self.sharpen:
            parts.append(f"unsharp={self.sharpen}")
        parts.extend(self.extra)
        return ",".join(parts)


# Dim indoor phone/GoPro footage: warm mids, slightly cool shadows, more pop, light denoise.
INDOOR_WARM = Grade()
# Bright outdoor action-cam footage: already contrasty/saturated, just a touch.
OUTDOOR_MILD = Grade(
    denoise=None,
    contrast=1.05,
    brightness=None,
    saturation=1.08,
    gamma=None,
    colorbalance="rm=0.02:bm=-0.02:rh=0.015:bh=-0.01",
    curves=None,
    sharpen="5:5:0.3:5:5:0",
)


def lift(spans: Iterable[tuple[float, float, float] | tuple[float, float, float, float]]) -> str:
    """Gamma multiplier expression: 1 + amount inside each span (t0, t1, amount[, fade_out]).

    fade_out ramps the lift back to 0 over the last seconds of the span; use it when a dark shot
    brightens *within* the same shot (a hard switch would be a visible jump).
    """
    terms = []
    for span in spans:
        t0, t1, amount, *rest = span
        fade = rest[0] if rest else 0.0
        if fade:
            terms.append(f"{fmt(amount)}*{between(t0, t1 - fade)}")
            terms.append(f"{fmt(amount)}*{between(t1 - fade, t1)}*({fmt(t1)}-t)/{fmt(fade)}")
        else:
            terms.append(f"{fmt(amount)}*{between(t0, t1)}")
    return "(1" + "".join(f"+{x}" for x in terms) + ")"


def lift_for(luma: float, target: float = 95.0, max_amount: float = 0.3) -> float:
    """Gamma lift that brings a mean luma (0-255) towards `target`: eq's gamma maps x -> x^(1/g),
    so g = ln(mean)/ln(target). Capped: night shots should stay night shots."""
    if luma >= target or luma <= 1:
        return 0.0 if luma >= target else max_amount
    return min(max_amount, math.log(luma / 255) / math.log(target / 255) - 1)


def auto_lift(
    curve: Sequence[tuple[float, float]],
    cuts: Sequence[float],
    target: float = 95.0,
    max_amount: float = 0.3,
    min_amount: float = 0.03,
    smooth: float = 1.5,
    step: float = 0.5,
    half_frame: float = 1 / 60,
) -> list[tuple[float, float]]:
    """Gamma-lift keys (t, amount) from a luma curve: an automatic, shot-aware exposure fix.

    curve  `luma_curve` (measure a letterboxed video with crop=..., the bars read as "dark")
    cuts   shot boundaries incl. 0 and the end; the lift steps at a cut (half a frame early) and
           glides inside a shot (moving average over `smooth` s, a key every `step` s), so a
           room that gets darker as the camera turns is lifted gradually, like auto exposure.

    Use: `Grade.but(gamma=f"(1+{expr.piecewise(keys)})")`.
    """
    keys: list[tuple[float, float]] = []
    for a, b in pairwise(cuts):
        pts = [(t, y) for t, y in curve if a <= t < b]
        if not pts:
            continue

        def amount(t0: float, t1: float, pts=pts) -> float:
            ys = [y for t, y in pts if t0 <= t < t1] or [y for _, y in pts]
            v = lift_for(sum(ys) / len(ys), target, max_amount)
            return v if v >= min_amount else 0.0

        inner = []
        tc = a + step / 2
        while tc < b:
            inner.append((tc, amount(tc - smooth / 2, tc + smooth / 2)))
            tc += step
        if not inner or max(v for _, v in inner) - min(v for _, v in inner) < 0.04:
            v = amount(a, b)
            inner = [(a + (b - a) / 2, v)]
        keys.append((a if not keys else a - half_frame, inner[0][1]))
        keys.extend(inner)
        keys.append((b - half_frame - 1e-3, inner[-1][1]))
    return keys


def mono_look(t0: float, t1: float) -> tuple[str, ...]:
    """Black & white + vignette + grain inside a window ("sigma" edit look)."""
    w = between(t0, t1)
    return (
        f"hue=s='1-{w}'",
        f"vignette=angle=PI/4.2:enable='{w}'",
        f"noise=alls=9:allf=t:enable='{w}'",
    )
