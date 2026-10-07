"""Hide or highlight a moving thing: blur strangers' faces or a licence plate (privacy), or put a
soft spotlight on one subject ("şu kartala bak": everything else darker and a little greyer).

1. Find the boxes with Apple's Vision framework. A small Swift helper (tools/track/track.swift,
   compiled on first use into build/bin/vlogkit-track) reads raw frames from an ffmpeg pipe, so
   sample i is exactly decode frame i (rotation and size are ffmpeg's job):
   - `faces(video, start, duration)`: face detection at a reduced rate (8/s by default); the
     detections are linked into tracks (`link`: nearest centre with a similar size, best pairs
     first, gaps up to ~0.5 s bridged), boxes padded for hair and chin.
   - `track(video, box, at)`: one object followed from a box you give (`VNTrackObjectRequest`).
     When Vision's confidence stays low the track ends there (`Track.lost`); it never guesses on.
   Raw Vision output is cached in build/redact/cache (source, range, rate, helper hash).
2. `render(video, out, tracks, mode)`: one ffmpeg pass in 10-bit. A small mask (long side 960) is
   drawn by overlaying one soft rounded sprite per track piece whose x/y follow `expr.piecewise`
   (fixed size per piece, so the graph stays small however long the clip). The mask is scaled up
   and mixes the source with a blurred copy (`blur`) or with a darker, less saturated copy
   (`spotlight`, which fades in and out with the track). ProRes HQ 10-bit + the source audio.

Boxes are (x, y, w, h), 0-1 of the frame, top-left origin, in the frame as ffmpeg decodes it.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from bisect import bisect_left, bisect_right
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from functools import partial
from itertools import pairwise
from pathlib import Path

from vlogkit.config import BUILD_DIR, REPO_ROOT, require, tools
from vlogkit.ff import FFmpegError, PathLike, ffmpeg, ffprobe_json, probe
from vlogkit.timecode import fmt
from vlogkit.video.background import matte_size, video_info
from vlogkit.video.expr import between, piecewise
from vlogkit.video.graph import PRORES_HQ

SOURCE = REPO_ROOT / "tools" / "track" / "track.swift"
BINARY = BUILD_DIR / "bin" / "vlogkit-track"
CACHE_DIR = BUILD_DIR / "redact" / "cache"
MODES = ("blur", "spotlight")
MASK_SIDE = 960  # long side of the mask the sprites are drawn on
MAIN_MIN_HEIGHT = 0.1  # the vlogger's face (keep_main) is at least this tall (of the frame)
MAIN_MIN_SHARE = 0.5  # ... and on screen at least this share of the scanned range
BIG_BLUR = 0.15  # blur sigma >= this x the tallest box (padded face: ~0.25 x the face height)

Box = tuple[float, float, float, float]  # x, y, w, h (0-1, top-left origin)


# --------------------------------------------------------------------------- the Swift helper
def available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("swiftc")) and SOURCE.exists()


def ensure_built() -> Path:
    """Compile tools/track/track.swift on first use (and again whenever the source changes)."""
    digest = hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:12]
    stamp = BINARY.with_suffix(".sha")
    if BINARY.exists() and stamp.exists() and stamp.read_text() == digest:
        return BINARY
    if not available():
        raise RuntimeError(
            "vlogkit-track için macOS + swiftc gerekli (Xcode komut satırı araçları)"
        )
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["swiftc", "-O", str(SOURCE), "-o", str(BINARY)], check=True,
                       capture_output=True, text=True)  # fmt: skip
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"vlogkit-track derlenemedi:\n{e.stderr[-2000:]}") from e
    stamp.write_text(digest)
    return BINARY


# --------------------------------------------------------------------------- tracks
@dataclass
class Track:
    """A thing's box over time. `keys` are (source seconds, box), sorted by time."""

    keys: list[tuple[float, Box]]
    kind: str = "object"  # face | object
    lost: float | None = None  # object: Vision lost it here (None: followed to the end)
    hold: float = 0.0  # the box also covers this long before the first / after the last key

    @property
    def t0(self) -> float:
        return self.keys[0][0]

    @property
    def t1(self) -> float:
        return self.keys[-1][0]

    def at(self, t: float) -> Box | None:
        """The box at source time t, linear between keys (None outside the track + hold)."""
        if not self.keys or t < self.t0 - self.hold or t > self.t1 + self.hold:
            return None
        if t <= self.t0:
            return self.keys[0][1]
        for (ta, a), (tb, b) in pairwise(self.keys):
            if ta <= t <= tb:
                k = (t - ta) / (tb - ta) if tb > ta else 0.0
                return tuple(p + (q - p) * k for p, q in zip(a, b, strict=True))  # type: ignore[return-value]
        return self.keys[-1][1]

    def to_json(self) -> dict:
        return {"kind": self.kind, "lost": self.lost, "hold": self.hold,
                "keys": [[round(t, 4), [round(v, 5) for v in b]] for t, b in self.keys]}  # fmt: skip

    @staticmethod
    def from_json(d: dict) -> Track:
        keys = [(float(t), tuple(float(v) for v in b)) for t, b in d["keys"]]
        return Track(keys, d.get("kind", "object"), d.get("lost"), float(d.get("hold", 0.0)))  # type: ignore[arg-type]


def _centre(b: Box) -> tuple[float, float]:
    return b[0] + b[2] / 2, b[1] + b[3] / 2


def _cost(a: Box, b: Box) -> float:
    """Centre distance in box sizes (per axis, so the frame's aspect does not matter); inf when
    the sizes differ more than 2x."""
    if max(a[3] / b[3], b[3] / a[3]) > 2:
        return math.inf
    (ax, ay), (bx, by) = _centre(a), _centre(b)
    return math.hypot((ax - bx) / max(a[2], b[2]), (ay - by) / max(a[3], b[3]))


def _predict(keys: list[tuple[float, Box]], t: float) -> Box:
    """Where an open track's box should be at t: the last box moved at its last speed."""
    tl, last = keys[-1]
    if len(keys) < 2 or t <= tl:
        return last
    tp, prev = keys[-2]
    k = min(1.0, (t - tl) / max(tl - tp, 1e-6))  # at most one more step's worth
    dx, dy = (last[0] - prev[0]) * k, (last[1] - prev[1]) * k
    return (last[0] + dx, last[1] + dy, last[2], last[3])


def link(
    samples: Sequence[tuple[float, Sequence[Box]]], *, max_gap: float = 0.5, min_hits: int = 2
) -> list[Track]:
    """Per-sample detections -> tracks.

    Each detection joins the open track it is nearest to (centre within one box size of the last
    box or of where it was heading, size within 2x), best pairs first; the rest start new tracks.
    A track not seen for longer than `max_gap` is closed. Tracks seen fewer than `min_hits` times
    are dropped: a one-sample flicker is more often a false detection than a face.
    """
    open_: list[list[tuple[float, Box]]] = []
    closed: list[list[tuple[float, Box]]] = []
    for t, boxes in sorted(samples, key=lambda s: s[0]):
        alive = [k for k in open_ if t - k[-1][0] <= max_gap + 1e-6]
        closed += [k for k in open_ if t - k[-1][0] > max_gap + 1e-6]
        open_ = alive
        pairs = []
        for ti, keys in enumerate(open_):
            guess = _predict(keys, t)
            for di, b in enumerate(boxes):
                c = min(_cost(keys[-1][1], b), _cost(guess, b))
                if c < 1:
                    pairs.append((c, ti, di))
        taken_t: set[int] = set()
        taken_d: set[int] = set()
        for _, ti, di in sorted(pairs):
            if ti not in taken_t and di not in taken_d:
                open_[ti].append((t, tuple(boxes[di])))  # type: ignore[arg-type]
                taken_t.add(ti)
                taken_d.add(di)
        open_ += [[(t, tuple(b))] for di, b in enumerate(boxes) if di not in taken_d]  # type: ignore[misc]
    found = sorted(closed + open_, key=lambda k: k[0][0])
    return [Track(keys, "face") for keys in found if len(keys) >= min_hits]


def pad_box(b: Box, pad: float, top: float = 0.5) -> Box:
    """Grow a box by `pad` x its size on each side, plus `top` x pad more above (hair)."""
    x, y, w, h = b
    return (x - w * pad, y - h * pad * (1 + top), w * (1 + 2 * pad), h * (1 + pad * (2 + top)))


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    return s[len(s) // 2] if s else 0.0


def _follows(a: Track, b: Track, max_gap: float = 2.0) -> bool:
    """b starts where a ended (same place and size, soon after): one face seen twice."""
    gap = b.t0 - a.t1
    return -0.25 <= gap <= max_gap and _cost(a.keys[-1][1], b.keys[0][1]) < 1.5


def split_main(
    tracks: Sequence[Track], span: float | None = None
) -> tuple[list[Track], list[Track]]:
    """(the vlogger's face tracks, the others).

    The vlogger: the most face area x time, nearer the centre counts more; big enough
    (`MAIN_MIN_HEIGHT`) and, when `span` (seconds scanned) is given, on screen for at least
    `MAIN_MIN_SHARE` of it: a selfie face is there nearly all the time, a stranger passing close
    to the camera is not. Its fragments (the same face picked up again after a gap) go with it.
    ([], all) when nobody qualifies: then nobody is spared.
    """

    def score(tr: Track) -> float:
        return sum(b[2] * b[3] * (1 - min(1.0, math.dist(_centre(b), (0.5, 0.5))))
                   for _, b in tr.keys)  # fmt: skip

    big = [tr for tr in tracks if _median([b[3] for _, b in tr.keys]) >= MAIN_MIN_HEIGHT]
    if not big:
        return [], list(tracks)
    main = [max(big, key=score)]
    rest = [tr for tr in tracks if tr is not main[0]]
    grew = True
    while grew:
        grew = False
        for tr in list(rest):
            if any(_follows(m, tr) or _follows(tr, m) for m in main):
                main.append(tr)
                rest.remove(tr)
                grew = True
    if span and sum(tr.t1 - tr.t0 + tr.hold for tr in main) < MAIN_MIN_SHARE * span:
        return [], list(tracks)
    return sorted(main, key=lambda tr: tr.t0), rest


# --------------------------------------------------------------------------- Vision runs
def sample_filter(rate: str) -> str:
    """Frame k of the output = the frame on screen at start + k/rate.

    ffmpeg's default `fps` rounding hands over the last frame that *rounds* to each tick: at
    8/s from 30 fps that is ~0.05 s late, and the boxes trail a panning crowd. `round=up` takes
    the last frame at or before the tick; `start_time=0` keeps tick 0 even when the first frame
    after the seek sits a millisecond late (test: test_samples_are_the_frames_on_screen)."""
    return f"fps={rate}:round=up:start_time=0"


def _scan(src: Path, args: list[str], *, start: float, duration: float | None, rate: str,
          long_side: int) -> list[dict]:  # fmt: skip
    """Decode src[start, start+duration) at `rate` frames/s, pipe it through vlogkit-track."""
    info = video_info(src)
    w, h = matte_size(info.width, info.height, long_side)
    binary = ensure_built()
    ff = require(tools().ffmpeg, "ffmpeg")
    seek = ["-ss", f"{start:.3f}"] + (["-t", f"{duration:.3f}"] if duration else [])
    attempts = []
    if not info.rotated:  # media engine decode + GPU scale (the CPU stays free for Vision)
        hw_fmt = "p010le" if info.ten_bit else "nv12"
        hw = ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
        vt = f"scale_vt=w={w}:h={h},hwdownload,format={hw_fmt},format=bgra"
        attempts.append((hw, f"{sample_filter(rate)},{vt}"))
    attempts.append(([], f"{sample_filter(rate)},scale={w}:{h}:flags=area,format=bgra"))
    log = ""
    for pre, vf in attempts:
        with tempfile.TemporaryFile() as err:
            dec = subprocess.Popen(
                [ff, "-hide_banner", "-v", "error", *pre, *seek, "-i", str(src), "-an", "-vf", vf,
                 "-f", "rawvideo", "-pix_fmt", "bgra", "-"],
                stdout=subprocess.PIPE, stderr=err)  # fmt: skip
            tool = subprocess.Popen([str(binary), str(w), str(h), *args], stdin=dec.stdout,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)  # fmt: skip
            assert dec.stdout is not None
            dec.stdout.close()  # the tool holds it now: EOF / EPIPE propagate
            out, tool_err = tool.communicate()
            dec.wait()
            err.seek(0)
            log = err.read().decode(errors="replace")[-800:] + tool_err[-800:]
        rows = [json.loads(line) for line in out.splitlines() if line.strip()]
        done = rows[-1] if rows and "done" in rows[-1] else None
        # a tool that stopped early (object lost) leaves the decoder with a broken pipe: fine
        if (
            tool.returncode == 0
            and done
            and done["done"] > 0
            and (dec.returncode == 0 or done["lost"])
        ):
            return rows[:-1]
    raise RuntimeError(f"Vision taraması olmadı (aralıkta kare yok ya da çözülemedi):\n{log}")


def _rate(fps: float | Fraction) -> str:
    f = Fraction(fps).limit_denominator(1001)
    return f"{f.numerator}/{f.denominator}"


def _cached(name: str, key: str, compute) -> list[dict]:
    path = CACHE_DIR / f"{name}_{hashlib.sha1(key.encode()).hexdigest()[:10]}.json"
    if path.exists():
        d = json.loads(path.read_text())
        if d.get("key") == key:
            return d["rows"]
    rows = compute()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"key": key, "rows": rows}))
    return rows


def _key(src: Path, *parts: object) -> str:
    st = src.stat()
    sha = BINARY.with_suffix(".sha").read_text()
    return "|".join(map(str, (src, st.st_size, st.st_mtime_ns, *parts, sha)))


def merge_boxes(boxes: Sequence[Box], overlap: float = 0.5) -> list[Box]:
    """One box per face: the tiles overlap, so a face can come back twice (or cut in half at a
    tile edge). Larger boxes first; a box mostly covered by a kept one (intersection over the
    smaller box) is the same face."""
    kept: list[Box] = []
    for b in sorted(boxes, key=lambda b: -b[2] * b[3]):
        if all(_inter(b, k) < overlap * min(b[2] * b[3], k[2] * k[3]) for k in kept):
            kept.append(b)
    return kept


def _inter(a: Box, b: Box) -> float:
    ix = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    iy = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0.0, ix) * max(0.0, iy)


def detect_faces(video: PathLike, start: float = 0.0, duration: float | None = None, *,
                 fps: float = 8.0, grid: int = 3,
                 long_side: int = 1920) -> list[tuple[float, list[Box]]]:  # fmt: skip
    """(source seconds, face boxes) every 1/fps s. `grid`: also look in grid x grid overlapping
    tiles (small crowd faces; 1 = whole frame only). Cached."""
    src = Path(video).resolve()
    ensure_built()
    rate = _rate(fps)
    args = ["faces", str(grid)]
    key = _key(src, f"{start:.3f}", duration, sample_filter(rate), long_side, *args)
    run = partial(_scan, src, args, start=start, duration=duration, rate=rate,
                  long_side=long_side)  # fmt: skip
    step = 1 / Fraction(rate)
    rows = _cached(f"{src.stem}_faces", key, run)
    return [(start + float(r["i"] * step), merge_boxes([tuple(f[:4]) for f in r["faces"]]))
            for r in rows]  # type: ignore[misc]  # fmt: skip


def faces(
    video: PathLike,
    start: float = 0.0,
    duration: float | None = None,
    *,
    fps: float = 8.0,
    min_size: float = 0.0,
    keep_main: bool = False,
    pad: float = 0.3,
    grid: int = 3,
    long_side: int = 1920,
) -> list[Track]:
    """Face tracks in video[start, start+duration), boxes padded by `pad` (hair and chin in).

    `min_size`: drop faces whose median height is below this (0-1 of the frame height).
    `keep_main`: leave the vlogger's own face out (`split_main`); nobody is left out when no face
    is big enough and on screen long enough to be the vlogger.
    """
    samples = detect_faces(video, start, duration, fps=fps, grid=grid, long_side=long_side)
    tracks = link(samples, max_gap=max(0.5, 2.5 / fps))
    tracks = [tr for tr in tracks if _median([b[3] for _, b in tr.keys]) >= min_size]
    if keep_main:
        span = samples[-1][0] - samples[0][0] + 1 / fps if samples else None
        tracks = split_main(tracks, span)[1]
    return [Track([(t, pad_box(b, pad)) for t, b in tr.keys], "face", None, 1 / fps)
            for tr in tracks]  # fmt: skip


def track(
    video: PathLike,
    box: Box,
    at: float,
    until: float | None = None,
    *,
    fps: float | None = None,
    min_conf: float = 0.3,
    long_side: int = 1280,
) -> Track:
    """Follow the thing in `box` (at source time `at`) forward until `until` (default: the end)
    or until Vision loses it (`Track.lost`). `fps`: default the source rate, at most 30."""
    x, y, w, h = box
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError(f"kutu 0-1 arası x,y,en,boy olmalı: {box}")
    src = Path(video).resolve()
    ensure_built()
    src_fps = video_info(src).fps
    rate = _rate(fps if fps else min(src_fps, Fraction(30)))
    step = 1 / Fraction(rate)
    patience = max(3, round(0.3 / step))  # ~0.3 s of weak frames = gone
    duration = until - at if until is not None else None
    if duration is not None and duration <= 0:
        raise ValueError("until, at'ten sonra olmalı")
    args = ["object", *(f"{v:.5f}" for v in box), f"{min_conf}", str(patience)]
    key = _key(src, f"{at:.3f}", duration, sample_filter(rate), long_side, *args)
    run = partial(_scan, src, args, start=at, duration=duration, rate=rate, long_side=long_side)
    rows = _cached(f"{src.stem}_track", key, run)
    lost = next((at + float(r["i"] * step) for r in rows if r.get("lost")), None)
    keys = [(at + float(r["i"] * step), tuple(r["box"])) for r in rows
            if "box" in r and r["conf"] >= min_conf and (lost is None or at + r["i"] * step < lost)]  # fmt: skip
    return Track(keys, "object", lost, float(step) / 2)  # type: ignore[arg-type]


# --------------------------------------------------------------------------- mask windows
@dataclass(frozen=True)
class Window:
    """One sprite on the mask: a fixed-size box (mask px) whose centre follows `path`
    ((t, x, y), render seconds and mask px), shown during [t0, t1]."""

    t0: float
    t1: float
    w: float
    h: float
    path: tuple[tuple[float, float, float], ...]


def _smooth(keys: list[tuple[float, Box]], radius: float) -> list[tuple[float, Box]]:
    """Centred triangular moving average over +-radius seconds (Vision boxes jitter a little)."""
    if radius <= 0 or len(keys) < 3:
        return keys
    times = [t for t, _ in keys]
    out = []
    for t, _ in keys:
        acc = [0.0] * 4
        total = 0.0
        for u, b in keys[bisect_left(times, t - radius) : bisect_right(times, t + radius)]:
            wgt = 1 - abs(u - t) / (radius * 1.0001)
            total += wgt
            acc = [a + wgt * v for a, v in zip(acc, b, strict=True)]
        out.append((t, tuple(a / total for a in acc)))
    return out  # type: ignore[return-value]


def _simplify(
    path: list[tuple[float, float, float]], tol: float
) -> list[tuple[float, float, float]]:
    """Drop path points that linear interpolation between the kept ones reproduces within `tol`
    (Ramer-Douglas-Peucker on x(t), y(t); iterative): shorter expressions, same motion."""
    if len(path) < 3:
        return path
    keep = {0, len(path) - 1}
    stack = [(0, len(path) - 1)]
    while stack:
        a, b = stack.pop()
        (ta, xa, ya), (tb, xb, yb) = path[a], path[b]
        worst, wi = tol, None
        for i in range(a + 1, b):
            t, x, y = path[i]
            k = (t - ta) / (tb - ta) if tb > ta else 0.0
            err = max(abs(xa + (xb - xa) * k - x), abs(ya + (yb - ya) * k - y))
            if err > worst:
                worst, wi = err, i
        if wi is not None:
            keep.add(wi)
            stack += [(a, wi), (wi, b)]
    return [path[i] for i in sorted(keep)]


def windows(
    tr: Track,
    mask: tuple[int, int],
    *,
    start: float = 0.0,
    end: float = math.inf,
    smooth: float = 0.12,
    ratio: float = 1.3,
    tail: float = 0.0,
) -> list[Window]:
    """A track -> mask sprites. Each piece keeps one size (the largest box in it); a new piece
    starts when the box grows or shrinks more than `ratio`, and the old one stays until then.
    Times become render-relative (`start` = 0); `tail` keeps the last box that much longer."""
    if not tr.keys:
        return []
    mw, mh = mask
    keys = _smooth(tr.keys, smooth)
    pieces: list[list[tuple[float, Box]]] = [[keys[0]]]
    lo, hi = keys[0][1][2:], keys[0][1][2:]  # running min / max of (w, h) in the piece
    for k in keys[1:]:
        lo2 = (min(lo[0], k[1][2]), min(lo[1], k[1][3]))
        hi2 = (max(hi[0], k[1][2]), max(hi[1], k[1][3]))
        if hi2[0] > ratio * lo2[0] or hi2[1] > ratio * lo2[1]:
            pieces.append([k])
            lo, hi = k[1][2:], k[1][2:]
        else:
            pieces[-1].append(k)
            lo, hi = lo2, hi2
    out = []
    for i, piece in enumerate(pieces):
        nxt = pieces[i + 1][0] if i + 1 < len(pieces) else None
        t0 = piece[0][0] - (tr.hold if i == 0 else 0)
        t1 = nxt[0] if nxt else piece[-1][0] + tr.hold + tail
        if t1 < start or t0 > end:
            continue
        pts = piece + ([nxt] if nxt else [])  # glide into the next piece's first position
        path = [(t - start, (b[0] + b[2] / 2) * mw, (b[1] + b[3] / 2) * mh) for t, b in pts]
        w = max(b[2] for _, b in piece) * mw
        h = max(b[3] for _, b in piece) * mh
        out.append(Window(t0 - start, t1 - start, w, h, tuple(_simplify(path, 0.4))))
    return out


# --------------------------------------------------------------------------- the graph
@dataclass(frozen=True)
class Plan:
    w: int  # output (= source) size
    h: int
    mask: tuple[int, int]
    rate: str  # sprite sources' frame rate ("30000/1001")
    mode: str  # blur | spotlight
    windows: tuple[Window, ...]
    strength: float  # blur: sigma in px at 1080p; spotlight: 0-1 how dark outside
    feather: float  # soft edge, x the box's shorter side
    envelope: tuple[tuple[float, float], ...] = ()  # spotlight on/off (t, 0-1); () = always on


ROUND = {"blur": 0.35, "spotlight": 0.5}  # corner radius, x half the shorter side


def sprite(win: Window, feather: float, rate: str, roundness: float = 0.35) -> str:
    """A lavfi source: white with a rounded-box alpha, solid inside the box, smooth ramp outside."""
    fe = max(1.5, feather * min(win.w, win.h))
    sw, sh = math.ceil(win.w + 2 * fe) + 2, math.ceil(win.h + 2 * fe) + 2
    r = roundness * min(win.w, win.h) / 2
    qx = f"max(abs(X+0.5-{fmt(sw / 2)})-{fmt(win.w / 2 - r)},0)"
    qy = f"max(abs(Y+0.5-{fmt(sh / 2)})-{fmt(win.h / 2 - r)},0)"
    s = f"clip(1-(hypot({qx},{qy})-{fmt(r)})/{fmt(fe)},0,1)"
    alpha = f"255*{s}*{s}*(3-2*{s})"  # smoothstep
    # drawn once, then looped (geq per frame per sprite would cost more than the whole render)
    return (f"color=c=white:s={sw}x{sh}:r={rate},trim=end_frame=1,format=yuva444p,"
            f"geq=lum='255':cb='128':cr='128':a='{alpha}',loop=loop=-1:size=1:start=0")  # fmt: skip


def _xy(win: Window, feather: float) -> tuple[str, str]:
    """Overlay x / y: the sprite's top-left corner, centred on the moving box (rounded)."""
    fe = max(1.5, feather * min(win.w, win.h))
    sw, sh = math.ceil(win.w + 2 * fe) + 2, math.ceil(win.h + 2 * fe) + 2
    xs = piecewise([(t, x) for t, x, _ in win.path])
    ys = piecewise([(t, y) for t, _, y in win.path])
    return f"floor({xs}-{fmt(sw / 2 - 0.5)})", f"floor({ys}-{fmt(sh / 2 - 0.5)})"


def _geq_time(expr: str) -> str:
    """`t` -> `T`: geq names the frame time T (the piecewise helpers write t)."""
    return re.sub(r"(?<![A-Za-z_])t(?![A-Za-z_(])", "T", expr)


def blur_strength(strength: float, wins, mask: tuple[int, int], w: int, h: int) -> float:
    """The blur sigma (px at 1080p of the short side, the unit `_blur_chain` takes) raised to
    BIG_BLUR x the tallest window, measured in the same unit: on a vertical frame a box is
    compared with the short side too (measuring it against the height gave Shorts ~44 % less)."""
    box_px = max(win.h for win in wins) / mask[1] * h
    return max(strength, BIG_BLUR * box_px * 1080 / min(w, h))


def _blur_chain(w: int, h: int, strength: float) -> str:
    """A strong, cheap blur: down, gblur, back up (sigma `strength` px at 1080p)."""
    px = strength * min(w, h) / 1080
    f = max(1.0, min(8.0, px / 6))
    sw, sh = max(2, round(w / f / 2) * 2), max(2, round(h / f / 2) * 2)
    return f"scale={sw}:{sh}:flags=area,gblur=sigma={px / f:.2f},scale={w}:{h}:flags=bicubic"


def _dim(strength: float) -> str:
    """Darker and a little greyer (10-bit, lutyuv: never 8-bit eq/curves)."""
    k, c = 1 - strength, 1 - 0.5 * strength
    return (f"lutyuv=y='64+(val-64)*{k:.4f}':u='512+(val-512)*{c:.4f}'"
            f":v='512+(val-512)*{c:.4f}'")  # fmt: skip


def build_graph(p: Plan) -> str:
    """filter_complex for input [0] = the source range. Output label [v]."""
    mw, mh = p.mask
    g = ["[0:v]format=yuv444p10le,split=3[src][fx_in][cv_in]"]
    if p.mode == "blur":
        g.append(f"[fx_in]{_blur_chain(p.w, p.h, p.strength)}[fx]")
    else:
        g.append(f"[fx_in]{_dim(p.strength)}[fx]")
    # the mask canvas: black, same frames and timestamps as the source
    g.append(f"[cv_in]scale={mw}:{mh}:flags=neighbor,format=yuv444p,lutyuv=y=0:u=128:v=128[c0]")
    roundness = ROUND.get(p.mode, 0.35)
    for i, win in enumerate(p.windows):
        x, y = _xy(win, p.feather)
        g.append(f"{sprite(win, p.feather, p.rate, roundness)}[s{i}]")
        # shortest: the sprite loops forever, the source decides when the mask ends
        g.append(f"[c{i}][s{i}]overlay=x='{x}':y='{y}':format=yuv444:shortest=1:"
                 f"enable='{between(win.t0, win.t1)}'[c{i + 1}]")  # fmt: skip
    m = ["extractplanes=y", "format=gray10le"]  # 10-bit before scaling: full white stays 1023
    if p.envelope:  # spotlight off: the mask is all white (nothing dimmed)
        m.append(f"geq=lum='1023-(1023-lum(X,Y))*({_geq_time(piecewise(p.envelope))})'")
    m.append(f"scale={p.w}:{p.h}:flags=bicubic")
    g.append(f"[c{len(p.windows)}]{','.join(m)},mergeplanes=map0s=0:map0p=0:map1s=0:map1p=0:"
             f"map2s=0:map2p=0:format=yuv444p10le[alpha]")  # fmt: skip
    pair = "[src][fx]" if p.mode == "blur" else "[fx][src]"  # mask white -> blurred / kept
    g.append(f"{pair}[alpha]maskedmerge,format=yuv422p10le[v]")
    return ";".join(g)


def envelope(
    spans: Sequence[tuple[float, float]], end: float, ramp: float = 0.4
) -> list[tuple[float, float]]:
    """Spotlight strength over render time: 1 inside the spans, `ramp` s fades in after a span
    starts and out after it ends; no fade at the range's own edges. [] = on the whole time."""
    merged: list[list[float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1] + 2 * ramp:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    if len(merged) == 1 and merged[0][0] <= 0.01 and merged[0][1] >= end - 0.01:
        return []
    keys: list[tuple[float, float]] = []
    for a, b in merged:
        keys += [(a, 1.0)] if a <= 0.01 else [(a, 0.0), (a + ramp, 1.0)]
        keys += [(b, 1.0)] if b >= end - 0.01 else [(b, 1.0), (b + ramp, 0.0)]
    return keys


# --------------------------------------------------------------------------- render
def _prores(src: PathLike) -> list[str]:
    """PRORES_HQ, but with the source's colour tags: redact never converts colour (YUV in, YUV
    out), so an HLG phone clip must stay tagged HLG, not BT.709."""
    v = next(s for s in ffprobe_json(src)["streams"] if s["codec_type"] == "video")
    tags = {"-color_primaries": v.get("color_primaries"), "-color_trc": v.get("color_transfer"),
            "-colorspace": v.get("color_space")}  # fmt: skip
    out = list(PRORES_HQ)
    for i in range(0, len(out) - 1):
        value = tags.get(out[i])
        if value and value != "unknown":
            out[i + 1] = value
    return out


def render(
    video: PathLike,
    out: PathLike,
    tracks: Sequence[Track],
    mode: str = "blur",
    *,
    start: float = 0.0,
    duration: float | None = None,
    strength: float | None = None,
    feather: float | None = None,
    audio: bool = True,
) -> Path:
    """video[start, start+duration) with the tracked boxes blurred or spotlit -> ProRes HQ 10-bit
    .mov (+ PCM audio), source size and timing.

    blur: `strength` = blur sigma in px at 1080p (default 30), raised to `BIG_BLUR` x the
    tallest box so a close face is as unreadable as a far one (one blurred copy serves every
    box; the small ones only get smoother). `feather` = soft edge outside the box, x its
    shorter side (default 0.15).
    spotlight: `strength` 0-1 = how much darker outside (default 0.5; colour drops half as much),
    `feather` default 0.6 (a wide, soft pool of light). Fades in/out with the track.
    """
    if mode not in MODES:
        raise ValueError(f"mod: {' | '.join(MODES)}")
    src = Path(video)
    info = video_info(src)
    length = duration if duration is not None else probe(src).duration - start
    mask = matte_size(info.width, info.height, MASK_SIDE)
    blur = mode == "blur"
    strength = (30.0 if blur else 0.5) if strength is None else strength
    feather = (0.15 if blur else 0.6) if feather is None else feather
    if not blur and not 0 < strength <= 1:
        raise ValueError("spotlight gücü 0-1 arası olmalı")
    ramp = 0.0 if blur else 0.4
    wins: list[Window] = []
    spans = []
    for tr in tracks:
        ws = windows(tr, mask, start=start, end=start + length, smooth=0.15 if tr.kind == "face"
                     else 0.1, tail=ramp)  # fmt: skip
        wins += ws
        if ws:
            spans.append((max(0.0, ws[0].t0), min(length, ws[-1].t1 - ramp)))
    if not wins:
        raise ValueError("bu aralıkta takip edilen bir şey yok")
    if blur:
        strength = blur_strength(strength, wins, mask, info.width, info.height)
    rate = _rate(info.fps)
    env = () if blur else tuple(envelope(spans, length, ramp))
    plan = Plan(info.width, info.height, mask, rate, mode, tuple(wins), strength, feather, env)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        graph = Path(tmp) / "graph.txt"  # long piecewise paths: a file, not an argument
        graph.write_text(build_graph(plan))
        hw = [] if info.rotated else ["-hwaccel", "videotoolbox"]
        seek = ["-ss", f"{start:.3f}"] + (["-t", f"{duration:.3f}"] if duration else [])
        amap = ["-map", "0:a?", "-c:a", "pcm_s16le"] if audio else ["-an"]
        tail = ["-/filter_complex", graph, "-map", "[v]", *amap, *_prores(src), out]
        try:
            ffmpeg(["-y", *hw, *seek, "-i", src, *tail])
        except FFmpegError:
            if not hw:
                raise
            ffmpeg(["-y", *seek, "-i", src, *tail])  # software decode fallback
    return out


# --------------------------------------------------------------------------- CLI helpers
def _seconds(text: str) -> float:
    total = 0.0
    for part in text.strip().split(":"):
        total = total * 60 + float(part)
    return total


def parse_box(text: str) -> tuple[Box, float]:
    """'x,y,w,h@SN' (0-1, top-left origin; SN = 12.5 or 1:02.5) -> (box, seconds)."""
    m = re.fullmatch(r"\s*([^@]+)@\s*([\d:.]+)\s*", text)
    if not m:
        raise ValueError(f"kutu x,y,en,boy@sn olmalı: {text!r}")
    try:
        vals = [float(v) for v in m.group(1).split(",")]
        at = _seconds(m.group(2))
    except ValueError as e:
        raise ValueError(f"kutu okunamadı: {text!r}") from e
    if len(vals) != 4:
        raise ValueError(f"kutu dört sayı ister (x,y,en,boy): {text!r}")
    x, y, w, h = vals
    if not (0 <= x < 1 and 0 <= y < 1 and 0 < w <= 1 and 0 < h <= 1 and x + w <= 1.001
            and y + h <= 1.001):  # fmt: skip
        raise ValueError(f"kutu karenin içinde, 0-1 arası olmalı: {text!r}")
    return (x, y, w, h), at
