"""Line two recordings of the same moment up by their sound (camera + phone, two cameras).

`offset(ref, other)` says where `other` starts on `ref`'s clock: "phone 0 s = camera 3.345 s".

Each file becomes a loudness envelope: ffmpeg decodes it to mono 8 kHz, keeps the telephone band
(300-3400 Hz: speech, and where a phone and a camera hear alike; below it wind, rumble and the
phone's low cut differ), squares it and resamples the power to 1 kHz. Here it is averaged over
11 ms (hides the voice's pitch pulses) and turned into dB clipped at the file's own floor (its
quietest 20 %), so a different gain, mic or noise floor hardly matters.

The lag is found coarse to fine. 10 Hz, every lag: Pearson r over that lag's own overlap (sum xy
from one FFT product, the rest from prefix sums), so a quiet stretch counts as much as a loud one;
the envelope loses its slow (> 4 s) loudness changes first (music level, fades), which otherwise
make long stretches look alike. Then 100 Hz and 1 kHz around the winner (Pearson over the whole
overlap) and a parabola through the peak for sub-millisecond precision.

Confidence compares the 10 Hz peak with every lag at least 1 s from it (also outside `max_offset`),
as Fisher z (atanh r, so 0.99 beats 0.7 by far more than 0.5 beats 0.2). It is the weaker of
1 - runner-up / peak (one clear answer, not a beat or a repeated take) and the peak's height over
their spread (chance stays under 5 sd; 10 sd = sure). Unrelated recordings score 0, the camera and
the phone that recorded the same talk ~0.8, an exact 15 s excerpt of a 4 min file ~0.6.

Drift is the same measurement in the first and the last third of the overlap; it is reported,
never corrected, and left out (None) when the overlap is short or too noisy to measure it.
"""

from __future__ import annotations

import cmath
import math
import sys
import tempfile
from array import array
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import accumulate, chain, repeat
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg, ffprobe_json

RATE = 1000  # Hz, the finest envelope (1 ms)
SMOOTH = 11  # ms averaged per envelope value
FLOOR = 0.2  # envelope quantile taken as the noise floor
TREND = 41  # 10 Hz samples (4 s): slower loudness changes are left out of the coarse match
EXCLUDE = 10  # 10 Hz lags (1 s) around the peak that are not "other lags"
Z_CHANCE, Z_SURE = 5.0, 10.0  # peak height over the other lags (sd): confidence 0 and 1
REACH = 20  # 100 Hz lags (+-0.2 s) searched around the coarse answer
LOW = 0.4  # confidence below this: the offset is a guess
DRIFT_MIN = 30.0  # s of overlap needed to measure drift
DRIFT_R = 0.4  # 1 kHz correlation both thirds need (noisier ones scatter by 10+ ms)


@dataclass(frozen=True)
class Sync:
    """`other` t=0 is `ref` t=`offset` (negative: `other` started first)."""

    offset: float  # s, averaged over the overlap
    confidence: float  # 0-1, see the module doc
    drift: float | None  # s: offset at the end of the overlap minus at its start
    overlap: float  # s of sound both recordings cover

    @property
    def reliable(self) -> bool:
        return self.confidence >= LOW


@dataclass(frozen=True)
class _Envelope:
    t0: float  # file seconds of the first sample
    fine: list[float]  # dB at 1 kHz, centred
    mid: list[float]  # dB at 100 Hz, centred
    coarse: list[float]  # dB at 10 Hz, zero mean, unit variance


def offset(
    ref: PathLike,
    other: PathLike,
    *,
    max_offset: float | None = None,
    start: float = 0.0,
    duration: float | None = None,
) -> Sync:
    """Where `other` starts on `ref`'s clock, from their sound.

    max_offset  only answers with |offset| <= this (s); a better match outside lowers confidence
    start, duration  read only this stretch of `ref` (a long camera file); offset stays in ref s
    """
    r = _envelope(ref, start, duration)
    o = _envelope(other)
    first, corr = _ncc(r.coarse, o.coarse, _min_overlap(len(r.coarse), len(o.coarse)))
    base = r.t0 - o.t0  # offset = base + lag (10 Hz lag at corr[lag - first])
    lo, hi = first, first + len(corr) - 1
    if max_offset is not None:
        lo = max(lo, math.ceil((-max_offset - base) * 10))
        hi = min(hi, math.floor((max_offset - base) * 10))
        if lo > hi:
            raise ValueError(f"{max_offset:g} sn içinde iki kayıt yeterince üst üste gelmiyor")
    i = max(range(lo - first, hi - first + 1), key=corr.__getitem__)
    confidence = _confidence(corr[i], corr[: max(0, i - EXCLUDE)] + corr[i + EXCLUDE + 1 :])
    best = first + i

    lag, _ = _refine(r, o, best * 100, 0, len(o.fine))  # ms
    a, b = max(0, math.ceil(-lag)), min(len(o.fine), math.floor(len(r.fine) - lag))
    drift = None
    if b - a >= DRIFT_MIN * RATE:
        third = (b - a) // 3
        early, r_early = _refine(r, o, lag, a, a + third)
        late, r_late = _refine(r, o, lag, b - third, b)
        if min(r_early, r_late) >= DRIFT_R:
            drift = (late - early) * 1.5 / RATE  # window centres are 2/3 of the overlap apart
    return Sync(base + lag / RATE, confidence, drift, max(0, b - a) / RATE)


def align_filter(s: Sync) -> str:
    """Audio filter that puts `other` on `ref`'s clock (its first sample = ref t 0): a later start
    is padded with silence, an earlier one trimmed. Use it as `-af` when putting the phone sound
    under the camera picture, or in an `AudioGraph` chain (`[1:a]{filter},...`)."""
    if s.offset >= 0:
        return f"adelay=delays={s.offset * 1000:.3f}:all=1"
    return f"atrim=start={-s.offset:.6f},asetpts=PTS-STARTPTS"


def _confidence(peak: float, others: list[float]) -> float:
    """The weaker of 1 - runner-up / peak and the peak's height over the other lags (in sd),
    both on Fisher z of the correlations."""
    if peak <= 0 or len(others) < 2:
        return 0.0
    peak, others = _fisher(peak), [_fisher(v) for v in others]
    mean = sum(others) / len(others)
    sd = math.sqrt(sum((v - mean) ** 2 for v in others) / len(others))
    height = (peak - mean) / sd if sd > 0 else 0.0
    clear = 1 - max(others) / peak
    above_chance = (height - Z_CHANCE) / (Z_SURE - Z_CHANCE)
    return min(1.0, max(0.0, min(clear, above_chance)))


def _fisher(r: float) -> float:
    return math.atanh(max(-0.999, min(0.999, r)))


def _sound_start(path: PathLike, start: float) -> float:
    """File seconds of the first decoded sample: ffmpeg begins at -ss or where the audio stream
    begins (an mp4 whose sound starts after its picture), whichever is later."""
    j = ffprobe_json(path)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    if a is None:
        raise ValueError(f"{Path(path).name}: ses yok")
    lead = float(a.get("start_time") or 0) - float(j["format"].get("start_time") or 0)
    return max(start, lead)


def _power(path: PathLike, start: float, duration: float | None) -> list[float]:
    """Sound power at 1 kHz: mono, 8 kHz, telephone band, squared, resampled."""
    cut = ["-ss", f"{start:.6f}"] if start else []
    if duration is not None:
        cut += ["-t", f"{duration:.6f}"]
    af = (
        "aformat=channel_layouts=mono,aresample=8000,highpass=f=300,lowpass=f=3400,"
        f"aeval=val(0)*val(0),aresample={RATE}"
    )
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "power.f32"
        ffmpeg([*cut, "-i", path, "-vn", "-map", "0:a:0", "-af", af, "-f", "f32le", raw])
        pcm = array("f")
        pcm.frombytes(raw.read_bytes())
    if sys.byteorder == "big":
        pcm.byteswap()
    return [max(v, 0.0) for v in pcm]  # the resampler rings slightly below zero


def _envelope(path: PathLike, start: float = 0.0, duration: float | None = None) -> _Envelope:
    t0 = _sound_start(path, start)
    p = _power(path, start, duration)
    n = len(p)
    if n < 3 * RATE:
        raise ValueError(f"{Path(path).name}: en az 3 sn ses gerekli")
    h = SMOOTH // 2
    pre = list(accumulate(chain(repeat(0.0, h), p, repeat(0.0, h)), initial=0.0))
    fine = [_db((b - a) / SMOOTH) for a, b in zip(pre, pre[SMOOTH:], strict=False)]
    coarse = [_db((pre[i + h + 100] - pre[i + h]) / 100) for i in range(0, n - 99, 100)]
    mid = fine[5::10]
    floor = sorted(mid)[int(len(mid) * FLOOR)]
    fine, mid, coarse = ([max(v, floor) for v in e] for e in (fine, mid, coarse))
    return _Envelope(t0, _centre(fine), _centre(mid), _standard(_detrend(coarse, TREND)))


def _detrend(e: list[float], k: int) -> list[float]:
    """e minus its centred k-sample moving average (shorter at the ends)."""
    n, h = len(e), k // 2
    pre = list(accumulate(e, initial=0.0))
    return [
        v - (pre[min(n, i + h + 1)] - pre[max(0, i - h)]) / (min(n, i + h + 1) - max(0, i - h))
        for i, v in enumerate(e)
    ]


def _db(v: float) -> float:
    return 10 * math.log10(v) if v > 1e-12 else -120.0


def _centre(e: list[float]) -> list[float]:
    mean = sum(e) / len(e)
    return [v - mean for v in e]


def _standard(e: list[float]) -> list[float]:
    e = _centre(e)
    sd = math.sqrt(math.sumprod(e, e) / len(e))
    return [v / sd for v in e] if sd > 0 else e


def _refine(r: _Envelope, o: _Envelope, guess: float, lo: int, hi: int) -> tuple[float, float]:
    """(lag in ms, correlation) near `guess` ms: 100 Hz within +-REACH, then 1 kHz within
    +-10 ms. lo, hi: the stretch of `other` (ms) that is compared."""
    g = round(guess / 10)
    lags = range(g - REACH, g + REACH + 1)
    mid, _ = _peak(lambda lag: _pearson(r.mid, o.mid, lag, lo // 10, hi // 10), lags)
    g = round(mid * 10)
    return _peak(lambda lag: _pearson(r.fine, o.fine, lag, lo, hi), range(g - 10, g + 11))


def _peak(f: Callable[[int], float], lags: Sequence[int]) -> tuple[float, float]:
    """(best lag with a parabola's sub-step shift, its value)."""
    vals = [f(lag) for lag in lags]
    i = max(range(len(vals)), key=vals.__getitem__)
    shift = 0.0
    if 0 < i < len(vals) - 1:
        a, b, c = vals[i - 1 : i + 2]
        if a - 2 * b + c < 0:
            shift = 0.5 * (a - c) / (a - 2 * b + c)
    return lags[i] + shift, vals[i]


def _pearson(x: list[float], y: list[float], lag: int, lo: int, hi: int) -> float:
    """Correlation of y[lo:hi] with x shifted by `lag`, where both exist."""
    a, b = max(lo, -lag), min(hi, len(x) - lag)
    n = b - a
    if n < 2:
        return 0.0
    xs, ys = x[a + lag : b + lag], y[a:b]
    sx, sy = sum(xs), sum(ys)
    vx = math.sumprod(xs, xs) - sx * sx / n
    vy = math.sumprod(ys, ys) - sy * sy / n
    if vx <= 0 or vy <= 0:
        return 0.0
    return (math.sumprod(xs, ys) - sx * sy / n) / math.sqrt(vx * vy)


def _min_overlap(n: int, m: int) -> int:
    """Samples a lag must overlap: half the shorter recording (60 s at most), never under 3 s.
    A short edge overlap correlates high by chance."""
    return max(30, min(min(n, m) // 2, 600))


def _ncc(x: list[float], y: list[float], need: int) -> tuple[int, list[float]]:
    """Pearson r of y with x shifted by each lag L that overlaps >= `need` samples, over that
    overlap only (a quiet stretch counts as much as a loud one): (first lag, values).
    sum(x*y) for every lag comes from one FFT product, the other sums from prefix sums."""
    n, m = len(x), len(y)
    xy = _xcorr(x, y)
    px, pxx = list(accumulate(x, initial=0.0)), list(accumulate((v * v for v in x), initial=0.0))
    py, pyy = list(accumulate(y, initial=0.0)), list(accumulate((v * v for v in y), initial=0.0))
    out = []
    for lag in range(need - m, n - need + 1):
        a, b = max(0, -lag), min(m, n - lag)
        k = b - a
        sx, sy = px[b + lag] - px[a + lag], py[b] - py[a]
        vx = pxx[b + lag] - pxx[a + lag] - sx * sx / k
        vy = pyy[b] - pyy[a] - sy * sy / k
        if vx <= 1e-6 * k or vy <= 1e-6 * k:  # flat (silent) stretch
            out.append(0.0)
            continue
        out.append(max(-1.0, min(1.0, (xy[lag + m - 1] - sx * sy / k) / math.sqrt(vx * vy))))
    return need - m, out


def _xcorr(x: list[float], y: list[float]) -> list[float]:
    """sum_t x[t + L] * y[t] for every lag L in (-len(y), len(x)), at index L + len(y) - 1."""
    n, m = len(x), len(y)
    size = 1 << (n + m - 2).bit_length()
    fx = _fft([complex(v) for v in x] + [0j] * (size - n))
    fy = _fft([complex(v) for v in y] + [0j] * (size - m))
    c = _fft([a * b.conjugate() for a, b in zip(fx, fy, strict=True)], inverse=True)
    return [c[lag % size].real / size for lag in range(-m + 1, n)]


def _fft(a: list[complex], inverse: bool = False) -> list[complex]:
    """Iterative radix-2 FFT in place (len(a) a power of two), unscaled both ways."""
    n = len(a)
    j = 0
    for i in range(1, n):  # bit-reversal permutation
        bit = n >> 1
        while j & bit:
            j ^= bit
            bit >>= 1
        j |= bit
        if i < j:
            a[i], a[j] = a[j], a[i]
    sign = 1j if inverse else -1j
    size = 2
    while size <= n:
        half = size // 2
        w = [cmath.exp(sign * math.pi * k / half) for k in range(half)]
        for s in range(0, n, size):
            for k in range(half):
                u, v = a[s + k], a[s + k + half] * w[k]
                a[s + k], a[s + k + half] = u + v, u - v
        size *= 2
    return a
