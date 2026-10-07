"""Hit a loudness target without pumping.

`loudnorm` in linear mode needs headroom; when a quiet mix needs +8 dB it silently falls back to
dynamic mode and pumps. Instead: gain -> brickwall limiter -> measure, and iterate (1-2 passes).
"""

from __future__ import annotations

from pathlib import Path

from vlogkit.analysis.loudness import Loudness, measure, parse_loudnorm
from vlogkit.audio.mix import AudioGraph

OVERSAMPLE = 192000  # limiter rate (4x): a sample-peak limiter at 4x approximates a true-peak one


def normalize(
    graph: AudioGraph,
    out: str | Path,
    target: float = -14.0,
    limit: float = 0.80,
    tol: float = 0.25,
    max_iter: int = 4,
    verbose: bool = True,
    tp_max: float = -1.5,
) -> Loudness:
    """Render `graph` to a 24-bit wav at `target` LUFS; limiter ceiling `limit` (0.80 ≈ -1.9 dBFS).

    The limiter runs at 4x the sample rate, so it also holds the peaks between samples (true
    peak); at 48 kHz short high bursts slipped through to -0.7 dBTP. If the true peak is still
    above `tp_max`, the ceiling is lowered and the pass repeated: the AAC encode adds ~0.3-0.5 dB,
    so a wav at <= -1.5 dBTP keeps the delivery at <= -1 dBTP.
    """
    raw = parse_loudnorm(
        graph.render(
            ["-f", "null", "-"], "loudnorm=I=-14:TP=-1.5:print_format=json", loglevel="info"
        ).stderr
    )
    if verbose:
        print(f"  raw mix: {raw}")
    gain = target - raw.integrated
    got = raw
    for i in range(max_iter):
        graph.render(
            ["-c:a", "pcm_s24le", str(out)],
            f"volume={gain:.2f}dB,aresample={OVERSAMPLE},"
            f"alimiter=limit={limit:.4f}:attack=4:release=60:asc=1:level=0,aresample=48000",
        )
        got = measure(out)
        if verbose:
            print(f"  pass {i}: gain {gain:+.2f} dB, limit {limit:.3f} -> {got}")
        peak_ok = got.true_peak <= tp_max
        if abs(got.integrated - target) < tol and peak_ok:
            break
        if not peak_ok:
            limit *= 10 ** ((tp_max - got.true_peak - 0.1) / 20)
        gain += target - got.integrated
    return got
