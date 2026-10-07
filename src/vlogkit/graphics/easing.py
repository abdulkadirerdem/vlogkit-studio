"""Easing curves for pop-ins and counters."""

from __future__ import annotations


def clamp(x: float, a: float = 0.0, b: float = 1.0) -> float:
    return max(a, min(b, x))


def ease_out_back(p: float, s: float = 1.9) -> float:
    """Overshoots past 1 then settles: the 'pop' in pop-in captions."""
    p -= 1
    return p * p * ((s + 1) * p + s) + 1


def ease_out_cubic(p: float) -> float:
    return 1 - (1 - p) ** 3
