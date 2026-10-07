"""Time effects and cut transitions as ffmpeg filter-chain fragments.

Two kinds, with different contracts:

- **Segment effects** change a segment's length: `SpeedRamp`, `Freeze`. Apply them to one
  trimmed segment (constant frame rate, PTS starting at 0) *before* `graph.concat`. They say in
  Python how many frames they output, so music, captions and cuts can be planned without
  rendering.
- **Cut effects** run on the assembled timeline and only touch a few frames around a cut:
  `Glitch`, `WhipPan`. The timeline length never changes. Every filter is gated with
  `enable='...n...'` (frame number, not time) and works in YUV, so frames outside the window stay
  bit-identical. An RGB-only filter such as `rgbashift` would force a YUV->RGB->YUV round trip on
  *every* frame; the "RGB split" here is built from plane offsets in `geq` instead.

Frame indices in the cut effects are frames of the stream the chain runs on: after `concat`
that is the timeline frame (`timecode.frame_at`).
"""

from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field
from fractions import Fraction
from functools import cached_property
from itertools import pairwise

from vlogkit.audio import synth
from vlogkit.timecode import FPS_NTSC, before_frame, fmt
from vlogkit.video.expr import nan_safe, piecewise, window


def _ease(u: float) -> float:
    """Cosine ease 0 -> 1 (zero slope at both ends: no jolt when the speed starts changing)."""
    return 0.5 - 0.5 * math.cos(math.pi * min(max(u, 0.0), 1.0))


def _var(expr: str, var: str) -> str:
    """`expr.piecewise` builds curves in `t`; setpts needs them in the frame counter `N`."""
    return re.sub(r"\bt\b", var, expr)


# --------------------------------------------------------------------------- speed ramp
@dataclass(frozen=True)
class SpeedRamp:
    """Playback speed as a function of *source* time within a segment.

    keys = ((source_seconds, speed), ...): between keys the speed eases (cosine), outside it
    holds. `SpeedRamp.through(3.0, peak=4)` is the classic 1x -> 4x -> 1x.

    How it renders: each source frame i gets the output slot round(out_time(i) * fps) (setpts on
    a 1/fps timebase), then `fps` fills the constant-rate grid. A slot shows the *last* source
    frame that landed on or before it, so speed-ups drop frames and slow-downs (< 1x) repeat
    them (no optical flow). `source_frames()` is the exact Python twin of that rule.
    """

    keys: tuple[tuple[float, float], ...]
    duration: float  # source seconds this segment covers
    fps: Fraction = FPS_NTSC

    @classmethod
    def through(
        cls,
        duration: float,
        peak: float = 4.0,
        ramp: float = 0.4,
        base: float = 1.0,
        fps: Fraction = FPS_NTSC,
    ) -> SpeedRamp:
        """base -> peak over `ramp` s, hold, peak -> base over the last `ramp` s (source time)."""
        r = min(ramp, duration / 2)
        return cls(((0.0, base), (r, peak), (duration - r, peak), (duration, base)), duration, fps)

    def speed(self, u: float) -> float:
        ks = self.keys
        if u <= ks[0][0]:
            return ks[0][1]
        for (ua, sa), (ub, sb) in pairwise(ks):
            if ua <= u <= ub and ub > ua:
                return sa + (sb - sa) * _ease((u - ua) / (ub - ua))
        return ks[-1][1]

    @cached_property
    def _table(self) -> tuple[float, list[float]]:
        """Cumulative output time on a fine source grid (trapezoid on 1/speed)."""
        step = 1 / float(self.fps) / 16
        n = max(1, math.ceil(self.duration / step))
        step = self.duration / n
        out, acc = [0.0], 0.0
        prev = 1 / self.speed(0.0)
        for i in range(1, n + 1):
            cur = 1 / self.speed(i * step)
            acc += (prev + cur) * step / 2
            out.append(acc)
            prev = cur
        return step, out

    def out_time(self, u: float) -> float:
        """Output seconds elapsed when the source reaches `u` seconds into the segment."""
        step, table = self._table
        x = min(max(u, 0.0), self.duration) / step
        i = min(int(x), len(table) - 2)
        return table[i] + (table[i + 1] - table[i]) * (x - i)

    @property
    def src_frames(self) -> int:
        return round(self.duration * self.fps)

    @property
    def out_duration(self) -> float:
        return self.frames / float(self.fps)

    @property
    def frames(self) -> int:
        """Frames this segment outputs (plan the timeline with this)."""
        return max(1, round(self.out_time(self.duration) * float(self.fps)))

    def _keys(self) -> list[tuple[int, int]]:
        """(source frame, output slot) keys for setpts; every frame unless the ramp is long."""
        f = float(self.fps)
        n = self.src_frames
        stride = max(1, math.ceil(n / 500))
        idx = sorted({*range(0, n, stride), n - 1})
        # +1e-6: exact .5 ties (a steady 2x) must round the same way every time, or the cadence
        # stutters on float noise
        return [(i, math.floor(self.out_time(i / f) * f + 0.5 + 1e-6)) for i in idx]

    def slots(self) -> list[int]:
        """Output slot of every source frame, exactly as the setpts curve computes it."""
        keys = self._keys()
        out = []
        for (ia, sa), (ib, sb) in pairwise(keys):
            out += [math.floor(sa + (sb - sa) * (i - ia) / (ib - ia) + 0.5) for i in range(ia, ib)]
        return [*out, keys[-1][1]]

    def source_frames(self) -> list[int]:
        """Which source frame each output frame shows (the `fps` filter's rule, in Python)."""
        slots, out, i = self.slots(), [], 0
        for k in range(self.frames):
            while i + 1 < len(slots) and slots[i + 1] <= k:
                i += 1
            out.append(i)
        return out

    def filter(self) -> str:
        """Chain for a segment starting at PTS 0: output has exactly `frames` frames."""
        # integer keys -> exact at every source frame; between sampled keys, round like slots().
        # `fps` only emits a frame once a later one arrives, so the last source frame would be
        # lost at EOF: a cloned extra frame goes one slot further (and is trimmed off).
        keys = self._keys()
        keys.append((self.src_frames, keys[-1][1] + 1))
        curve = _var(piecewise(keys), "N")
        tb = f"{self.fps.denominator}/{self.fps.numerator}"
        return (
            f"tpad=stop_mode=clone:stop=1,settb=expr={tb},setpts='floor({curve}+0.5)',"
            f"fps={self.fps.numerator}/{self.fps.denominator}:round=near,"
            f"tpad=stop_mode=clone:stop=2,trim=end_frame={self.frames},setpts=PTS-STARTPTS"
        )

    def peak_time(self) -> float:
        """Output time (in the segment) of the fastest moment: where a whoosh should peak."""
        top = max(s for _, s in self.keys)
        fastest = [u for u, s in self.keys if s == top]
        return self.out_time((fastest[0] + fastest[-1]) / 2)


def ramp_whoosh(ramp: SpeedRamp, at: float, dur: float | None = None, gain: float = 0.9) -> str:
    """Synth whoosh (audio chain, no label) peaking at the ramp's fastest moment.

    `at` = timeline time where the ramped segment starts. The usual pairing: mute the source
    sound under a fast ramp and let this carry the motion.
    """
    dur = dur or min(0.9, max(0.35, ramp.out_duration * 0.6))
    start = max(0.0, at + ramp.peak_time() - 0.76 * dur)
    return synth.whoosh(start, dur=dur, gain=gain)


def _atempo(speed: float) -> str:
    # one atempo instance handles 0.5..100; chain halves below that
    parts = []
    while speed < 0.5:
        parts.append("atempo=0.5")
        speed /= 0.5
    parts.append(f"atempo={speed:.5f}")
    return ",".join(parts)


def ramp_audio(
    ramp: SpeedRamp,
    input_idx: int,
    src_start: float,
    at: float,
    gain: float = 1.0,
    chunk: float = 0.2,
    tag: str | None = None,
) -> str:
    """The source sound tempo-stretched along the ramp (pitch kept), placed at timeline `at`.

    atempo only takes a constant rate, so the segment is cut into `chunk`-second pieces, each
    stretched by its own average speed, then joined; tiny fades hide the joins. The result is
    padded/trimmed to exactly `ramp.out_duration`. gain < 1 ducks it (e.g. 0.3 under a whoosh).
    Returns a chain for `AudioGraph.chain` (internal labels are prefixed with `tag`).
    """
    tag = tag or f"sr{input_idx}_{round(at * 1000)}"
    n = max(1, round(ramp.duration / chunk))
    edges = [ramp.duration * k / n for k in range(n + 1)]
    parts = [
        f"[{input_idx}:a]atrim={fmt(src_start)}:{fmt(src_start + ramp.duration)},"
        f"asetpts=PTS-STARTPTS,aresample=48000,aformat=channel_layouts=stereo,"
        f"asplit={n}" + "".join(f"[{tag}s{k}]" for k in range(n))
    ]
    for k, (a, b) in enumerate(pairwise(edges)):
        spd = (b - a) / max(1e-6, ramp.out_time(b) - ramp.out_time(a))
        parts.append(
            f"[{tag}s{k}]atrim={fmt(a)}:{fmt(b)},asetpts=PTS-STARTPTS,{_atempo(spd)},"
            f"afade=t=in:d=0.004,areverse,afade=t=in:d=0.004,areverse[{tag}c{k}]"
        )
    ms = round(at * 1000)
    d = f"{ramp.out_duration:.4f}"
    parts.append(
        "".join(f"[{tag}c{k}]" for k in range(n))
        + f"concat=n={n}:v=0:a=1,apad=whole_dur={d},atrim=0:{d},volume={fmt(gain)},"
        f"adelay={ms}|{ms}"
    )
    return ";".join(parts)


# --------------------------------------------------------------------------- freeze frame
@dataclass(frozen=True)
class Freeze:
    """Hold frame `frame` of the segment for `hold` extra seconds.

    punch  zoom-in reached by the end of the hold (0.08 = 8 %), eased; the picture snaps back
           when motion resumes, which reads as "back to action"
    photo  desaturate + contrast + vignette, with a short white flash like a camera shutter
    """

    frame: int
    hold: float = 1.0
    punch: float = 0.0
    photo: bool = False
    fps: Fraction = FPS_NTSC

    @property
    def extra_frames(self) -> int:
        return max(1, round(self.hold * self.fps))

    @property
    def held(self) -> tuple[int, int]:
        """First and last output frame showing the frozen picture."""
        return self.frame, self.frame + self.extra_frames

    def frames(self, src_frames: int) -> int:
        return src_frames + self.extra_frames

    def filter(self, w: int = 1080, h: int = 1920) -> str:
        """Chain for a segment starting at PTS 0 (w x h = its frame size).

        Only filters that run natively on the 10-bit intermediate (loop, hue, lutyuv, scale) are
        used: `eq`, `vignette`, `curves` and `drawbox` would make ffmpeg convert *every* frame.
        """
        a, b = self.held
        tb = f"{self.fps.denominator}/{self.fps.numerator}"
        chain = [
            # `loop` holds the frame *before* `start` (checked by test_freeze_holds_one_frame...)
            f"loop=loop={self.extra_frames}:size=1:start={self.frame + 1}",
            f"settb=expr={tb},setpts=N",
        ]
        if self.photo:
            mid = "(minval+maxval)/2"
            chain += [
                f"hue=s=0.18:enable='between(n,{a},{b})'",
                f"lutyuv=y='clip((val-{mid})*1.15+{mid},minval,maxval)':"
                f"enable='between(n,{a},{b})'",
            ]
            for j in range(4):  # shutter flash, fading over 4 frames
                lift = 0.5 * (1 - j / 4)
                chain.append(
                    f"lutyuv=y='clip(val+{lift:.3f}*(maxval-minval),minval,maxval)':"
                    f"enable='eq(n,{a + j})'"
                )
        if self.punch:
            t0, t1 = before_frame(a, self.fps), before_frame(b + 1, self.fps)
            u = f"(t-{fmt(t0)})/{fmt(t1 - t0)}"
            z = f"(1+{window(t0, t1, f'{fmt(self.punch)}*(0.5-0.5*cos(PI*{u}))')})"
            chain.append(
                f"scale=w='2*trunc({w // 2}*{nan_safe(z, '1')})':h=-2:eval=frame:flags=lanczos,"
                f"crop={w}:{h}:(iw-{w})/2:(ih-{h})/2"
            )
        return ",".join(chain)


# --------------------------------------------------------------------------- cut transitions
def _gate(k: int) -> str:
    return f"enable='eq(n,{k})'"


@dataclass(frozen=True)
class Glitch:
    """A few frames of digital breakup around the cut at `frame` (first frame of the new shot).

    Per frame, a seeded random mix of: luma/chroma plane offsets (reads as an RGB split),
    horizontal band displacement, scanlines and grain, all in one `geq`. Strongest on the two
    frames touching the cut, fading out on both sides. Same seed = same glitch.
    """

    frame: int
    before: int = 3
    after: int = 4
    strength: float = 1.0
    seed: int = 7

    @property
    def window(self) -> range:
        return range(self.frame - self.before, self.frame + self.after)

    def _env(self, k: int) -> float:
        d = (self.frame - 1 - k) if k < self.frame else (k - self.frame)
        span = self.before if k < self.frame else self.after
        return self.strength * max(0.25, 1 - d / max(1, span))

    def filter(self) -> str:
        rng = random.Random(self.seed)
        parts = []
        for k in self.window:
            e = self._env(k)
            bands = []
            for _ in range(rng.randint(3, 6)):
                y0 = rng.uniform(0, 0.92)
                y1 = min(1.0, y0 + rng.uniform(0.015, 0.12))
                bands.append(f"{rng.uniform(-0.14, 0.14) * e:.4f}*between(Y/H,{y0:.3f},{y1:.3f})")
            band = "+".join(bands)
            split = rng.uniform(0.015, 0.035) * e
            sign = rng.choice((-1, 1))

            def plane(off: float, band: str = band) -> str:
                return f"p(mod(X+W*({band}+{off:.4f})+W,W),Y)"

            # "RGB split" without leaving YUV: a shifted ghost of the luma plus chroma pushed the
            # other way (chroma alone hardly shows on low-saturation footage)
            ghost = f"({plane(0)}*0.65+{plane(sign * split)}*0.35)"
            scan = f"(1-{0.22 * e:.3f}*lt(mod(Y,4),2))"
            grain = f"(1+(random(0)-0.5)*{0.16 * self.strength:.3f})"  # `noise` is 8-bit only
            parts.append(
                f"geq=lum='{ghost}*{scan}*{grain}':cb='{plane(-sign * split)}':"
                f"cr='{plane(-sign * split * 1.6)}':{_gate(k)}"
            )
        return ",".join(parts)


@dataclass(frozen=True)
class WhipPan:
    """Whip-pan transition: the old shot flies out, the new one flies in, motion-blurred.

    Outgoing frames accelerate (ease-in) to `travel` of the width at the cut, incoming frames
    arrive from the other side and decelerate (ease-out). Translation wraps around (`scroll`),
    so no black edges; the directional blur hides the wrap seam. direction="left" moves the
    content to the left (a camera whipping to the right).
    """

    frame: int
    before: int = 4
    after: int = 4
    direction: str = "left"
    travel: float = 0.55
    blur: float = 160.0  # dblur radius (px) at the cut, for a 1080-wide frame
    angle: float = 0.0  # 0 = horizontal, 90 = vertical whip

    @property
    def window(self) -> range:
        return range(self.frame - self.before, self.frame + self.after)

    def profile(self) -> list[tuple[int, float, float]]:
        """(frame, signed offset as a width fraction, blur radius) per affected frame."""
        s = 1 if self.direction == "left" else -1
        out = []
        for j in range(self.before, 0, -1):  # j frames before the cut
            p = ((self.before - j + 1) / self.before) ** 2
            out.append((self.frame - j, s * self.travel * p, self.blur * p))
        for j in range(self.after):
            q = (1 - j / self.after) ** 2
            out.append((self.frame + j, -s * self.travel * q, self.blur * q))
        return out

    def filter(self) -> str:
        parts = []
        vertical = abs(self.angle - 90) < 1e-6
        for k, off, r in self.profile():
            pos = off % 1.0
            move = f"vpos={pos:.4f}" if vertical else f"hpos={pos:.4f}"
            parts.append(f"scroll={move}:{_gate(k)}")
            if r >= 1:
                parts.append(f"dblur=angle={fmt(self.angle)}:radius={fmt(r)}:{_gate(k)}")
        return ",".join(parts)


@dataclass
class CutFX:
    """Collects cut effects for one timeline: `CutFX().add(Glitch(120)).add(WhipPan(300))`."""

    items: list = field(default_factory=list)

    def add(self, fx: Glitch | WhipPan) -> CutFX:
        self.items.append(fx)
        return self

    def filter(self) -> str:
        return ",".join(x.filter() for x in self.items) or "null"
