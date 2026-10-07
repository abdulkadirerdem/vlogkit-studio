"""Apple VideoToolbox frame processing (macOS 26+, Apple silicon) through a small Swift CLI.

- `upscale`: ML super resolution (4x; input up to 1920x1080), optionally after Apple's temporal
  noise filter. For low-res sources (a 464x262 picture on a phone re-export) it rebuilds edges
  where lanczos + sharpening only enlarges the blur and the macroblocks.
- `interpolate`: frame rate conversion, i.e. real in-between frames: `slowmo=True` plays them at
  the source rate (factor x slower), otherwise the frame rate goes up and the duration stays.
- `denoise`: temporal noise filter alone (fast, several hundred fps at phone sizes).
- `motion_blur`: blur from the motion between neighbouring frames (strength 1-100).

The binary is compiled from tools/vt/main.swift into build/bin on first use (swiftc from the
Xcode command line tools) and rebuilt when the source changes.

Two things the wrapper takes care of:
- Inputs are rendered upright and starting at t=0 first (`_prepare`). AVFoundation adds an extra
  frame for a leading empty edit list, which ffmpeg writes whenever the first timestamp is not 0.
- The ML processors shift the tone a little, depending on the content: -3.6 % luma on low-res screen
  footage, brighter on flat test cards. `match=True` fits `source = a * output + b` on luma over a
  few sampled frames and applies it with a 10-bit lutyuv, so the result keeps the source's tone.
"""

from __future__ import annotations

import array
import hashlib
import json
import platform
import shutil
import subprocess
import tempfile
from collections.abc import Sequence
from functools import cache
from pathlib import Path

from vlogkit.config import BUILD_DIR, REPO_ROOT
from vlogkit.ff import PathLike, ffmpeg, ffprobe_json, probe
from vlogkit.video.graph import PRORES_HQ

SOURCE = REPO_ROOT / "tools" / "vt" / "main.swift"
BINARY = BUILD_DIR / "bin" / "vlogkit-vt"
MAX_INPUT = (1920, 1080)


class VTUnavailable(RuntimeError):
    pass


# --------------------------------------------------------------------------- binary
def _source_hash() -> str:
    return hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:16]


def ensure_built() -> Path:
    """Compile the Swift CLI if it is missing or older than tools/vt/main.swift."""
    if platform.system() != "Darwin":
        raise VTUnavailable("Apple VideoToolbox işlemleri yalnız macOS'ta var")
    stamp = BINARY.with_suffix(".sha")
    if BINARY.exists() and stamp.exists() and stamp.read_text() == _source_hash():
        return BINARY
    swiftc = shutil.which("swiftc")
    if not swiftc:
        raise VTUnavailable("swiftc yok: xcode-select --install")
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(
        [swiftc, "-O", "-swift-version", "5", str(SOURCE), "-o", str(BINARY)],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        errors = [ln for ln in r.stderr.splitlines() if "error" in ln]
        raise VTUnavailable("vlogkit-vt derlenemedi:\n" + "\n".join(errors[-10:]))
    stamp.write_text(_source_hash())
    return BINARY


@cache
def info() -> dict | None:
    """What this Mac supports ({"super_resolution": {...}, "frame_rate_conversion": bool, ...})."""
    try:
        r = subprocess.run(
            [str(ensure_built()), "info"], capture_output=True, text=True, timeout=60
        )
        return json.loads(r.stdout) if r.returncode == 0 else None
    except (VTUnavailable, OSError, ValueError, subprocess.TimeoutExpired):
        return None


def available(feature: str = "super_resolution") -> bool:
    i = info()
    if not i:
        return False
    v = i.get(feature)
    return bool(v.get("supported") if isinstance(v, dict) else v)


def _run(args: Sequence[str | PathLike]) -> None:
    r = subprocess.run([str(ensure_built()), *map(str, args)], capture_output=True, text=True)
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-8:])
        raise RuntimeError(f"vlogkit-vt {args[0]} başarısız:\n{tail}")


def command(op: str, src: PathLike, out: PathLike, **opts) -> list[str]:
    """Arguments for the CLI (without the binary): op = upscale | denoise | interpolate | motionblur."""
    args = [op, str(src), str(out)]
    if op == "upscale":
        args += ["--scale", str(opts.get("scale", 4))]
        if opts.get("denoise"):
            args += ["--denoise", "--strength", f"{opts.get('strength', 0.5):g}"]
    elif op == "denoise":
        args += ["--strength", f"{opts.get('strength', 0.5):g}"]
    elif op == "interpolate":
        args += ["--factor", str(opts.get("factor", 2))] + (
            ["--slowmo"] if opts.get("slowmo") else []
        )
    elif op == "motionblur":
        args += ["--blur", str(opts.get("strength", 50))]
    else:
        raise ValueError(f"bilinmeyen işlem: {op}")
    return args


# --------------------------------------------------------------------------- helpers
def _rotated(src: PathLike) -> bool:
    for s in ffprobe_json(src).get("streams", []):
        if s.get("codec_type") != "video":
            continue
        rot = s.get("tags", {}).get("rotate")
        side = [d.get("rotation") for d in s.get("side_data_list", []) if "rotation" in d]
        return bool((rot and rot != "0") or any(side))
    return False


def _prepare(src: PathLike, out: Path, vf: str | None = None) -> Path:
    """Upright, starting at 0, optionally pre-filtered (crop, cfr...): ProRes 422 HQ 10-bit."""
    chain = ",".join(x for x in (vf, "setpts=PTS-STARTPTS") if x)
    ffmpeg(["-y", "-i", src, "-an", "-vf", chain, *PRORES_HQ, out])
    return out


def _luma(path: PathLike, frames: Sequence[int], size: tuple[int, int]) -> list[array.array]:
    """Y planes (10-bit values) of the given frames, scaled to `size` with area averaging."""
    w, h = size
    pick = "+".join(f"eq(n\\,{n})" for n in frames)
    with tempfile.TemporaryDirectory() as tmp:
        raw = Path(tmp) / "y.raw"
        ffmpeg(
            [
                "-y",
                "-i",
                path,
                "-vf",
                f"select='{pick}',scale={w}:{h}:flags=area",
                "-fps_mode",
                "passthrough",
                "-pix_fmt",
                "yuv422p10le",
                "-f",
                "rawvideo",
                raw,
            ]
        )
        data = array.array("H")
        data.frombytes(raw.read_bytes())
    plane, per_frame = w * h, w * h * 2  # Y plane, then U and V at half width
    return [data[i * per_frame : i * per_frame + plane] for i in range(len(data) // per_frame)]


def fit_levels(target: Sequence[int], got: Sequence[int], step: int = 3) -> tuple[float, float]:
    """Least squares `target ≈ a * got + b` (a clamped to 0.85-1.15: never a wild correction)."""
    xs, ys = got[::step], target[::step]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    a = sum((x - mx) * (y - my) for x, y in zip(xs, ys, strict=True)) / var if var else 1.0
    a = min(1.15, max(0.85, a))
    return a, my - a * mx


def levels_filter(a: float, b: float) -> str:
    return f"lutyuv=y=clip(val*{a:.5f}+{b:.3f}\\,64\\,940)"


def match_levels(reference: PathLike, processed: PathLike, samples: int = 6) -> tuple[float, float]:
    """Fit the processed clip's luma back onto the reference (both 10-bit, compared at the
    reference size)."""
    ref = probe(reference, count_frames=True)
    n = max(1, ref.frames or 1)
    frames = sorted({round(i * (n - 1) / max(1, samples - 1)) for i in range(samples)})
    size = (ref.width or 0, ref.height or 0)
    target = [v for plane in _luma(reference, frames, size) for v in plane]
    got = [v for plane in _luma(processed, frames, size) for v in plane]
    m = min(len(target), len(got))
    return fit_levels(target[:m], got[:m])


def _finish(
    processed: Path,
    out: PathLike,
    audio_from: PathLike | None,
    post: Sequence[str],
) -> Path:
    args: list = ["-y", "-i", processed]
    if audio_from is not None and probe(audio_from).has_audio:
        args += ["-i", audio_from, "-map", "0:v", "-map", "1:a", "-c:a", "pcm_s24le", "-shortest"]
    if post:
        args += ["-vf", ",".join(post)]
    ffmpeg([*args, *PRORES_HQ, out])
    return Path(out)


# --------------------------------------------------------------------------- operations
def upscale(
    src: PathLike,
    out: PathLike,
    *,
    scale: int = 4,
    denoise: bool = True,
    strength: float = 0.5,
    target: tuple[int, int] | None = None,
    vf: str | None = None,
    match: bool = True,
    audio: bool = True,
) -> Path:
    """ML super resolution. vf: pre-filter at the source size (e.g. `reframe.crop(box)`);
    target: final size (e.g. (1920, 1080)), reached from the 4x result with lanczos."""
    if not available("super_resolution"):
        raise VTUnavailable("bu Mac'te ML super resolution yok (macOS 26 + Apple silicon gerekir)")
    with tempfile.TemporaryDirectory() as tmp:
        prep = _prepare(src, Path(tmp) / "in.mov", vf)
        w, h = probe(prep).width or 0, probe(prep).height or 0
        if w > MAX_INPUT[0] or h > MAX_INPUT[1]:
            raise ValueError(f"super resolution girdisi en fazla 1920x1080 ({w}x{h})")
        raw = Path(tmp) / "sr.mov"
        _run(command("upscale", prep, raw, scale=scale, denoise=denoise, strength=strength))
        post = [levels_filter(*match_levels(prep, raw))] if match else []
        if target:
            post.append(f"scale={target[0]}:{target[1]}:flags=lanczos")
        return _finish(raw, out, src if audio and not vf else None, post)


def denoise(src: PathLike, out: PathLike, *, strength: float = 0.5, vf: str | None = None) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        prep = _prepare(src, Path(tmp) / "in.mov", vf)
        raw = Path(tmp) / "dn.mov"
        _run(command("denoise", prep, raw, strength=strength))
        return _finish(raw, out, src if not vf else None, [])


def interpolate(
    src: PathLike,
    out: PathLike,
    *,
    factor: int = 2,
    slowmo: bool = True,
    vf: str | None = None,
    match: bool = True,
    denoise: float | None = None,
) -> Path:
    """factor x frames. slowmo: at the source frame rate (factor x longer, no sound); otherwise
    at factor x the frame rate (same duration, sound kept).

    denoise: temporal noise filter strength (0-1) run on the *result*. On grainy footage (night,
    blue hour) the in-between frames come out smoother than the real ones, and in slow motion that
    alternation reads as flickering grain; filtering after interpolation evens it out (measured on
    a 4K blue-hour pan: frame-to-frame grain spread 7 % -> 1.3 %, tone unchanged). Filtering
    *before* interpolation (strength 0.6) still left the alternation visible."""
    with tempfile.TemporaryDirectory() as tmp:
        prep = _prepare(src, Path(tmp) / "in.mov", vf)
        raw = Path(tmp) / "fi.mov"
        _run(command("interpolate", prep, raw, factor=factor, slowmo=slowmo))
        if denoise:
            clean = Path(tmp) / "fi_dn.mov"
            _run(command("denoise", raw, clean, strength=denoise))
            raw = clean
        post = [levels_filter(*match_levels(prep, raw))] if match and not slowmo else []
        return _finish(raw, out, None if slowmo or vf else src, post)


def motion_blur(src: PathLike, out: PathLike, *, strength: int = 50, vf: str | None = None) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        prep = _prepare(src, Path(tmp) / "in.mov", vf)
        raw = Path(tmp) / "mb.mov"
        _run(command("motionblur", prep, raw, strength=strength))
        return _finish(raw, out, src if not vf else None, [])
