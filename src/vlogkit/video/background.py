"""Replace or beautify the background behind a talking head: a per-frame person matte from Apple's
Vision framework + an ffmpeg composite in 10-bit.

1. `matte(src)`: decode -> `vlogkit-matte` (tools/matte, Swift) -> an 8-bit gray FFV1 .mkv, one
   matte per decoded frame (frame-aligned by construction: the helper sees exactly the frames
   ffmpeg decodes; rotation and 10-bit are ffmpeg's job). Computed at a reduced size (default long
   side 1920) and cached in build/matte.
2. `replace(src, out, bg=...)`: refine the matte (erode, temporal smoothing, inward feather),
   build the background, light wrap + sensor-grain transfer, composite -> ProRes HQ 10-bit at the
   source size.

Background specs (`parse_spec`, also the CLI's `--bg`):

    studio | studio:#RRGGBB        soft radial light behind the subject + dark vignette
    keep | keep:#RRGGBB | keep:0.5 the original background (curtain) + a soft backlight glow
                                   that follows the subject (colour, strength 0-1)
    #RRGGBB | color:#RRGGBB        solid colour
    gradient:#top,#bottom          vertical gradient
    PATH.jpg / .png / ...          still image, cover-fit
    PATH.mp4 | PATH.mp4@12.5       a clip (looped), from 12.5 s
    frame:PATH.mp4@12.5            one still frame of a clip

`blur` (px at 1080p) softens image / clip / frame backgrounds: a blurred landscape reads as depth
of field. Rules learned on the rize takes (dark curtain, flat log-like picture):
- **hybrid** matte = foreground-instance edges (sharp hair line) x a dilated person mask (only
  people). `accurate` person masks keep a dark curtain halo around the hair; `balanced` is blurry.
  Presence comes from the foreground mask: on an empty curtain the person masks hallucinate soft
  blobs (the curtain would show through the new background in patches).
- **No temporal smoothing by default**: averaging mattes over frames ghosts fast gestures (a
  half-transparent band around a waving arm). Vision's edges are steady enough frame to frame.
- **Feather inward** (`choke` 0.5): the soft ramp lies inside the matte line, so curtain pixels
  never bleed into the new background (no black fringe).
- **Grain transfer**: a clean generated or blurred background next to a noisy low-light subject
  looks pasted on; the source's own fine grain is added back on top of it.
- Everything stays 10-bit (no eq/curves/noise: they are 8-bit, pitfall 21).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from dataclasses import replace as _but
from fractions import Fraction
from pathlib import Path

from PIL import Image

from vlogkit.config import BUILD_DIR, REPO_ROOT, require, tools
from vlogkit.ff import FFmpegError, PathLike, ffmpeg, ffprobe_json
from vlogkit.timecode import FPS_NTSC
from vlogkit.video.graph import PRORES_HQ

SOURCE = REPO_ROOT / "tools" / "matte" / "matte.swift"
BINARY = BUILD_DIR / "bin" / "vlogkit-matte"
MATTE_DIR = BUILD_DIR / "matte"
MODES = ("hybrid", "fg", "accurate", "balanced")

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".heic", ".tif", ".tiff", ".webp", ".bmp"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv", ".avi", ".mts"}
STUDIO_COLOR = "#5a5e66"  # cool studio grey; sits well behind the flat, dim takes
GLOW_COLOR = "#e8d2b0"  # warm backlight
GENERATED = {"studio", "color", "gradient"}


# --------------------------------------------------------------------------- the Swift helper
def available() -> bool:
    return sys.platform == "darwin" and bool(shutil.which("swiftc")) and SOURCE.exists()


def ensure_built() -> Path:
    """Compile tools/matte/matte.swift on first use (and again whenever the source changes)."""
    digest = hashlib.sha1(SOURCE.read_bytes()).hexdigest()[:12]
    stamp = BINARY.with_suffix(".sha")
    if BINARY.exists() and stamp.exists() and stamp.read_text() == digest:
        return BINARY
    if not available():
        raise RuntimeError(
            "vlogkit-matte için macOS + swiftc gerekli (Xcode komut satırı araçları)"
        )
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["swiftc", "-O", str(SOURCE), "-o", str(BINARY)], check=True,
                       capture_output=True, text=True)  # fmt: skip
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"vlogkit-matte derlenemedi:\n{e.stderr[-2000:]}") from e
    stamp.write_text(digest)
    return BINARY


# --------------------------------------------------------------------------- background specs
@dataclass(frozen=True)
class Spec:
    kind: str  # studio | keep | color | gradient | image | video | frame
    path: Path | None = None
    at: float = 0.0  # video / frame: seconds into the clip
    colors: tuple[str, ...] = ()  # "#rrggbb"
    strength: float | None = None  # keep: glow strength 0-1


_HEX = re.compile(r"^#?([0-9a-fA-F]{6}|[0-9a-fA-F]{3})$")


def _color(text: str) -> str:
    m = _HEX.match(text.strip())
    if not m:
        raise ValueError(f"renk #RRGGBB olmalı: {text!r}")
    h = m.group(1).lower()
    return "#" + (h if len(h) == 6 else "".join(c * 2 for c in h))


def _seconds(text: str) -> float:
    """12.5 | 1:02.5 | 0:01:02.5"""
    parts = text.strip().split(":")
    try:
        values = [float(p) for p in parts]
    except ValueError as e:
        raise ValueError(f"zaman okunamadı: {text!r}") from e
    total = 0.0
    for v in values:
        total = total * 60 + v
    return total


def _media(text: str, still: bool) -> Spec:
    path, at = text, 0.0
    if "@" in text:
        head, tail = text.rsplit("@", 1)
        if re.fullmatch(r"[\d:.]+", tail.strip()):
            path, at = head, _seconds(tail)
    p = Path(path).expanduser()
    ext = p.suffix.lower()
    if still:
        return Spec("frame", p, at)
    if ext in IMAGE_EXT:
        return Spec("image", p)
    if ext in VIDEO_EXT:
        return Spec("video", p, at)
    raise ValueError(f"arka plan tanınmadı: {text!r} (resim, klip ya da studio/keep/#renk)")


def parse_spec(text: str) -> Spec:
    """A `--bg` string -> Spec (see the module docstring for the syntax)."""
    s = text.strip()
    if not s:
        raise ValueError("boş arka plan")
    head, _, rest = s.partition(":")
    key = head.lower()
    if key in ("studio", "keep"):
        colors: list[str] = []
        strength = None
        for arg in filter(None, (a.strip() for a in re.split(r"[:,]", rest))):
            if arg.startswith("#"):
                colors.append(_color(arg))
            else:
                try:
                    strength = float(arg)
                except ValueError as e:
                    raise ValueError(f"{key}: renk ya da 0-1 güç bekleniyordu: {arg!r}") from e
        if strength is not None and not 0 <= strength <= 1:
            raise ValueError(f"{key}: güç 0-1 arası olmalı: {strength}")
        return Spec(key, colors=tuple(colors), strength=strength)
    if key == "color":
        return Spec("color", colors=(_color(rest),))
    if key == "gradient":
        cs = [c for c in re.split(r"[,:]", rest) if c.strip()]
        if len(cs) != 2:
            raise ValueError("gradient:#üst,#alt")
        return Spec("gradient", colors=(_color(cs[0]), _color(cs[1])))
    if key == "frame":
        return _media(rest, still=True)
    if key in ("image", "video"):
        return _media(rest, still=False)
    if _HEX.match(s) and s.startswith("#"):
        return Spec("color", colors=(_color(s),))
    return _media(s, still=False)


# --------------------------------------------------------------------------- probing
@dataclass(frozen=True)
class Video:
    width: int  # display size (after rotation)
    height: int
    fps: Fraction
    ten_bit: bool
    rotated: bool


def video_info(src: PathLike) -> Video:
    j = ffprobe_json(src)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v.get("r_frame_rate", "0/1").split("/"))
    fps = Fraction(num, den) if num and den else FPS_NTSC
    rot = [abs(int(d["rotation"])) for d in v.get("side_data_list", []) if "rotation" in d]
    rot += [abs(int(v.get("tags", {}).get("rotate", 0)))]
    rotated = any(r % 360 for r in rot)
    w, h = int(v["width"]), int(v["height"])
    if any(r % 180 == 90 for r in rot):
        w, h = h, w
    return Video(w, h, fps, "10" in (v.get("pix_fmt") or ""), rotated)


def _even(x: float) -> int:
    return max(2, round(x / 2) * 2)


def matte_size(w: int, h: int, long_side: int = 1920) -> tuple[int, int]:
    """Reduced matte size with the source aspect (never larger than the source)."""
    k = min(1.0, long_side / max(w, h))
    return _even(w * k), _even(h * k)


# --------------------------------------------------------------------------- 1. the matte
def _seek(start: float, duration: float | None) -> list[str]:
    return ["-ss", f"{start:.3f}"] + (["-t", f"{duration:.3f}"] if duration else [])


def _run_pipe(cmds: list[list[str]], logs: Path) -> list[int]:
    """cmd0 | cmd1 | cmd2; stderr of each goes to a file (no pipe deadlocks)."""
    procs: list[subprocess.Popen] = []
    errs = []
    prev = None
    for i, cmd in enumerate(cmds):
        err = open(logs / f"{i}.log", "wb")  # noqa: SIM115 (closed below)
        errs.append(err)
        last = i == len(cmds) - 1
        p = subprocess.Popen(cmd, stdin=prev, stdout=None if last else subprocess.PIPE, stderr=err)
        if prev is not None:
            prev.close()  # the child holds it now: EOF/SIGPIPE propagate
        prev = p.stdout
        procs.append(p)
    codes = [p.wait() for p in procs]
    for e in errs:
        e.close()
    return codes


def matte(
    src: PathLike,
    out: PathLike | None = None,
    *,
    mode: str = "hybrid",
    size: int = 1920,
    start: float = 0.0,
    duration: float | None = None,
) -> Path:
    """Per-frame person matte of src[start, start+duration) -> gray FFV1 .mkv (255 = person).

    `size` is the long side the matte is computed at; `replace` upscales it smoothly. Cached by
    source, range, mode, size and the helper's source hash.
    """
    if mode not in MODES:
        raise ValueError(f"mod: {' | '.join(MODES)}")
    src = Path(src).resolve()
    info = video_info(src)
    w, h = matte_size(info.width, info.height, size)
    binary = ensure_built()
    st = src.stat()
    key = "|".join(map(str, (src, st.st_size, st.st_mtime_ns, f"{start:.3f}", duration, mode, w,
                             h, BINARY.with_suffix(".sha").read_text())))  # fmt: skip
    digest = hashlib.sha1(key.encode()).hexdigest()[:10]
    out = Path(out) if out else MATTE_DIR / f"{src.stem}_{mode}_{digest}.mkv"
    tag = out.with_suffix(".key")
    if out.exists() and tag.exists() and tag.read_text() == key:
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    ff = require(tools().ffmpeg, "ffmpeg")
    rate = f"{info.fps.numerator}/{info.fps.denominator}"
    enc = [ff, "-hide_banner", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "gray",
           "-s", f"{w}x{h}", "-framerate", rate, "-i", "-", "-c:v", "ffv1", str(out)]  # fmt: skip
    tool = [str(binary), str(w), str(h), mode]
    attempts = []
    if not info.rotated:  # media engine decode + GPU scale (CPU stays free for Vision)
        hw_fmt = "p010le" if info.ten_bit else "nv12"
        hw = ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"]
        attempts.append((hw, f"scale_vt=w={w}:h={h},hwdownload,format={hw_fmt},format=bgra"))
    attempts.append(([], f"scale={w}:{h}:flags=area,format=bgra"))
    with tempfile.TemporaryDirectory() as tmp:
        for pre, vf in attempts:
            dec = [ff, "-hide_banner", "-v", "error", *pre, *_seek(start, duration), "-i",
                   str(src), "-an", "-vf", vf, "-f", "rawvideo", "-pix_fmt", "bgra", "-"]  # fmt: skip
            codes = _run_pipe([dec, tool, enc], Path(tmp))
            if not any(codes) and out.exists():
                tag.write_text(key)
                return out
        logs = "\n".join((Path(tmp) / f"{i}.log").read_text(errors="replace")[-800:]
                         for i in range(3))  # fmt: skip
    raise RuntimeError(f"matte çıkarılamadı ({codes}):\n{logs}")


# --------------------------------------------------------------------------- 2. the composite
@dataclass(frozen=True)
class Refine:
    """Matte clean-up + blending. Pixel amounts are px at 1080p (scaled to the output)."""

    erode: int = 0  # 3x3 erosion passes at matte resolution (shrinks the matte)
    # temporal window in frames, centred. Off by default: 3 calms edge shimmer on a still head,
    # but leaves a half-transparent ghost band on fast gestures (measured on the arm-raise take)
    smooth: int = 1
    feather: float = 2.5  # edge softness (gblur sigma); 1.5 shows the mask's steps at 100 %
    choke: float = 0.5  # 0-0.9; 0.5 = the soft ramp lies fully inside the matte line
    wrap: float = 0.35  # light wrap: blurred background light spilling over the subject edge
    grain: float | None = None  # source grain on the new background (None: auto)


def _rgb(hex_color: str) -> tuple[float, float, float]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def _to_yuv10() -> str:
    return "scale=out_color_matrix=bt709:out_range=tv,format=yuv444p10le"


def generated_filter(spec: Spec, w: int, h: int, center: tuple[float, float] = (0.5, 0.42)) -> str:
    """lavfi source for studio / colour / gradient, rendered in 16-bit RGB (no banding)."""
    base = f"color=black:s={w}x{h}:r=1,format=gbrp16le"
    if spec.kind == "color":
        r, g, b = _rgb(spec.colors[0])
        expr = {"r": f"{65535 * r:.1f}", "g": f"{65535 * g:.1f}", "b": f"{65535 * b:.1f}"}
    elif spec.kind == "gradient":
        (r0, g0, b0), (r1, g1, b1) = _rgb(spec.colors[0]), _rgb(spec.colors[1])
        expr = {c: f"65535*({a:.4f}+({b - a:.4f})*Y/{h - 1})"
                for c, a, b in (("r", r0, r1), ("g", g0, g1), ("b", b0, b1))}  # fmt: skip
    elif spec.kind == "studio":
        cx, cy = center[0] * w, center[1] * h
        # light pool behind the head: bright centre, falls to ~18 % at the corners
        light = (f"(0.18+0.82*exp(-1.15*(pow((X-{cx:.0f})/{0.55 * w:.0f},2)"
                 f"+pow((Y-{cy:.0f})/{0.8 * h:.0f},2))))")  # fmt: skip
        r, g, b = _rgb(spec.colors[0] if spec.colors else STUDIO_COLOR)
        expr = {"r": f"{65535 * r:.1f}*{light}", "g": f"{65535 * g:.1f}*{light}",
                "b": f"{65535 * b:.1f}*{light}"}  # fmt: skip
    else:
        raise ValueError(spec.kind)
    geq = ":".join(f"{c}='{e}'" for c, e in expr.items())
    return f"{base},geq={geq},{_to_yuv10()}"


def _cover(w: int, h: int) -> str:
    return f"scale={w}:{h}:force_original_aspect_ratio=increase:flags=lanczos,crop={w}:{h}"


def render_still(spec: Spec, w: int, h: int, out: Path, blur: float = 0.0,
                 center: tuple[float, float] = (0.5, 0.42)) -> Path:  # fmt: skip
    """A one-frame yuv444p10le FFV1 background at the output size (image, frame or generated)."""
    k = min(w, h) / 1080
    soft = f",gblur=sigma={blur * k:.2f}" if blur > 0 else ""
    if spec.kind in GENERATED:
        args = ["-f", "lavfi", "-i", generated_filter(spec, w, h, center)]
        vf = "null"
    elif spec.kind == "image":
        args = ["-i", spec.path]
        vf = f"{_cover(w, h)},format=gbrp16le{soft},{_to_yuv10()}"
    elif spec.kind == "frame":
        args = ["-ss", f"{spec.at:.3f}", "-i", spec.path]
        vf = f"{_cover(w, h)},format=yuv444p10le{soft}"
    else:
        raise ValueError(f"durağan değil: {spec.kind}")
    ffmpeg(["-y", *args, "-frames:v", "1", "-vf", vf, "-c:v", "ffv1", out])
    return out


def _weights(n: int) -> str:
    """Binomial weights (1 2 1, 1 4 6 4 1 ...) for a centred temporal window."""
    row = [1]
    for _ in range(n - 1):
        row = [a + b for a, b in zip([0, *row], [*row, 0], strict=True)]
    return " ".join(map(str, row))


def _curve(src: str, out: str, expr: str) -> str:
    """A 10-bit curve on a gray stream. `lut` clamps gray10 at 1020 (alpha 0.997: the background
    shows faintly through the subject); lut2 on the stream and itself reaches 1023."""
    return f"[{src}]split[{out}_a][{out}_b];[{out}_a][{out}_b]lut2=c0='{expr}'[{out}]"


def matte_chain(r: Refine, w: int, h: int, tb: str, src: str = "1:v", out: str = "m") -> str:
    """gray matte (any size) -> refined gray10le matte at w x h (labels src -> out)."""
    k = min(w, h) / 1080
    parts = [f"settb=expr={tb},setpts=N", "format=gray10le"]
    parts += ["erosion"] * max(0, r.erode)
    n = r.smooth if r.smooth % 2 else r.smooth + 1
    if n > 1:  # tmix looks back; drop (n-1)/2 frames and clone the tail -> centred window
        half = (n - 1) // 2
        parts += [f"tmix=frames={n}:weights='{_weights(n)}'", f"trim=start_frame={half}",
                  f"tpad=stop_mode=clone:stop={half}", "setpts=N"]  # fmt: skip
    parts.append(f"scale={w}:{h}:flags=bicubic")
    if r.feather > 0:
        parts.append(f"gblur=sigma={r.feather * k:.2f}")
    # choke: the ramp moves inside the matte line; the top 1 % becomes solid either way (gblur
    # leaves ~1020 of 1023 deep inside)
    c = min(max(r.choke, 0.0), 0.9)
    curve = f"clip((x-{1023 * c:.1f})*{1 / (0.99 - c):.4f},0,1023)"
    return f"[{src}]{','.join(parts)}[{out}_raw];" + _curve(f"{out}_raw", out, curve)


def _planes(label_in: str, label_out: str) -> str:
    """gray10le -> the same value in Y, U and V (maskedmerge needs one format everywhere)."""
    return (f"[{label_in}]mergeplanes=map0s=0:map0p=0:map1s=0:map1p=0:map2s=0:map2p=0:"
            f"format=yuv444p10le[{label_out}]")  # fmt: skip


@dataclass(frozen=True)
class Plan:
    w: int
    h: int
    fps: Fraction
    spec: Spec
    refine: Refine
    blur: float = 0.0
    lift: Match | None = None


def auto_grain(spec: Spec, blur: float) -> float:
    if spec.kind == "keep":
        return 0.0
    return 1.0 if spec.kind in GENERATED or blur > 0 else 0.0


def build_graph(p: Plan) -> str:
    """filter_complex for inputs [0] source, [1] matte, [2] background (still / clip / glow
    colour). Output label [v]."""
    w, h, r = p.w, p.h, p.refine
    k = min(w, h) / 1080
    tb = f"{p.fps.denominator}/{p.fps.numerator}"
    frames = f"settb=expr={tb},setpts=N"
    g: list[str] = []
    g.append(f"[0:v]{frames},{_cover(w, h)},format=yuv444p10le[src]")
    keep = p.spec.kind == "keep"
    # keep: both layers are the curtain outside the matte line, so feather OUTWARD (choke 0, then
    # x2): the subject's edge pixels stay pure source, no glow leaks onto them as a bright rim
    g.append(matte_chain(_but(r, choke=0) if keep else r, w, h, tb))
    rate = f"{p.fps.numerator}/{p.fps.denominator}"
    # A still loops forever. `fps` first: framesync (ffmpeg 9) honours frame durations, and a
    # still's frame lasts 1 s -> the subject would freeze for a second (measured, not theory).
    loop = f"fps={rate},loop=loop=-1:size=1:start=0,{frames}"
    grain = auto_grain(p.spec, p.blur) if r.grain is None else r.grain
    wrap = 0.0 if keep else r.wrap
    uses = ["merge"] + (["wrap", "wrapblur"] if wrap > 0 else []) + (["glow"] if keep else [])
    g.append(f"[m]split={len(uses)}" + "".join(f"[m_{u}]" for u in uses))
    if keep:
        g.append(_curve("m_merge", "m_out", "clip(x*2,0,1023)"))
        g.append(_planes("m_out", "alpha"))
    else:
        g.append(_planes("m_merge", "alpha"))
    srcs = ["fg"] + (["hp"] if grain > 0 else []) + (["keep"] if keep else [])
    g.append(f"[src]split={len(srcs)}" + "".join(f"[s_{s}]" for s in srcs))
    fg = "s_fg"
    if p.lift and (p.lift.gain != 1 or p.lift.du or p.lift.dv):
        m = p.lift
        g.append(f"[{fg}]lutyuv=y='clip(64+(val-64)*{m.gain:.4f},64,940)':"
                 f"u='clip(val+{m.du:.1f},64,960)':v='clip(val+{m.dv:.1f},64,960)'[fgl]")  # fmt: skip
        fg = "fgl"
    # ---- background
    if keep:
        strength = 0.4 if p.spec.strength is None else p.spec.strength
        g.append(f"[2:v]format=yuv444p10le,{loop}[glowc]")
        # a wide pool of light behind the subject (a tight blur reads as a sticker outline);
        # blurred at 1/8 size: same look, a fraction of the cost
        w8, h8 = _even(w / 8), _even(h / 8)
        g.append(f"[m_glow]scale={w8}:{h8}:flags=area,gblur=sigma={140 * k / 8:.1f},"
                 f"scale={w}:{h}:flags=bicubic,lut=c0='clip(val*{1.5 * strength:.3f},0,1023)'[gm]")  # fmt: skip
        g.append(_planes("gm", "gmask"))
        g.append("[s_keep][glowc][gmask]maskedmerge[bg]")
    elif p.spec.kind == "video":
        soft = f",gblur=sigma={p.blur * k:.2f}" if p.blur > 0 else ""
        g.append(f"[2:v]fps={rate},{_cover(w, h)},"
                 f"format=yuv444p10le{soft},{frames}[bgv]")  # fmt: skip
        if wrap > 0:
            g.append("[bgv]split[bg][bgw]")
            g.append(f"[bgw]scale={_even(w / 4)}:{_even(h / 4)},gblur=sigma={9 * k / 4:.2f},"
                     f"scale={w}:{h}:flags=bicubic[wrapbg]")  # fmt: skip
        else:
            g.append("[bgv]null[bg]")
    else:  # a still: blur once, then loop the frame (never re-decoded)
        if wrap > 0:
            g.append("[2:v]format=yuv444p10le,split[st0][st1]")
            g.append(f"[st0]{loop}[bg]")
            g.append(f"[st1]gblur=sigma={18 * k:.1f},{loop}[wrapbg]")
        else:
            g.append(f"[2:v]format=yuv444p10le,{loop}[bg]")
    bg, wrapbg = "bg", "wrapbg"
    if p.lift and p.lift.bg < 1 and not keep:  # match: the background down towards the subject
        c = p.lift.bg**0.5
        dim = f"lutyuv=y='64+(val-64)*{p.lift.bg:.4f}':u='512+(val-512)*{c:.4f}':v='512+(val-512)*{c:.4f}'"
        g.append(f"[bg]{dim}[bgd]")
        bg = "bgd"
        if wrap > 0:
            g.append(f"[wrapbg]{dim}[wrapd]")
            wrapbg = "wrapd"
    if grain > 0:  # the source's fine grain (high-pass) laid over the new background
        # coring: grain is small (|x| < ~15 of 1023), edges are big (the wall/curtain border,
        # the subject's outline) -> big values fade to 0, so no ghost lines in the new background
        core = "'512+(val-512)*exp(-pow((val-512)/18,2))'"
        g.append(f"[s_hp]split[hp0][hp1];[hp1]gblur=sigma={1.2 * k:.2f}[hpb];"
                 f"[hp0][hpb]blend=all_mode=grainextract,lut=c0={core}:c1={core}:c2={core}[hp]")  # fmt: skip
        g.append(f"[{bg}][hp]blend=all_mode=grainmerge:all_opacity={min(grain, 1.5):.2f}[bgg]")
        bg = "bgg"
    # ---- light wrap: blurred background light over the subject's edge band
    if wrap > 0:
        g.append(f"[m_wrapblur]gblur=sigma={12 * k:.1f}[mwb]")
        g.append(f"[m_wrap][mwb]lut2=c0='x*(1023-y)/1023*{min(wrap, 1) * 2:.3f}'[wm]")
        g.append(_planes("wm", "wmask"))
        g.append(f"[{fg}][{wrapbg}][wmask]maskedmerge[fgw]")
        fg = "fgw"
    g.append(f"[{bg}][{fg}][alpha]maskedmerge,{frames},format=yuv422p10le[v]")
    return ";".join(g)


def _small_rgb(src: PathLike, vf: str, n: int, size: tuple[int, int],
               pre: list[str] | None = None) -> list[Image.Image]:  # fmt: skip
    """n evenly spread frames (after `vf`) as small RGB images."""
    w, h = size
    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg(["-y", *(pre or []), "-i", src, "-vf", f"{vf},scale={w}:{h}:flags=area",
                "-frames:v", str(n), "-fps_mode", "passthrough", Path(tmp) / "f%03d.png"])  # fmt: skip
        return [Image.open(p).convert("RGB") for p in sorted(Path(tmp).glob("f*.png"))]


def subject_center(matte_file: PathLike, frames: int) -> tuple[float, float]:
    """Where the subject is on average (x, y as 0-1 of the frame); (0.5, 0.42) if never seen."""
    step = max(1, frames // 12)
    ims = _small_rgb(matte_file, f"select='not(mod(n\\,{step}))'", 12, (96, 54))
    sx = sy = total = 0.0
    for im in ims:
        m = im.convert("L")
        for y in range(54):
            for x in range(96):
                v = m.getpixel((x, y))
                if v:
                    sx += v * x
                    sy += v * y
                    total += v
    if total < 255 * 20:
        return 0.5, 0.42
    return (sx / total + 0.5) / 96, min(0.45, (sy / total + 0.5) / 54 * 0.7)


def _mean_ycbcr(ims: list[Image.Image], masks: list[Image.Image] | None) -> tuple[float, ...]:
    """Mean Y, Cb, Cr (8-bit) over the pixels where the mask is solid (all pixels without one)."""
    acc = [0.0, 0.0, 0.0]
    weight = 0
    for i, im in enumerate(ims):
        ycc = im.convert("YCbCr").tobytes()
        m = masks[i].convert("L").resize(im.size).tobytes() if masks else None
        for k in range(im.width * im.height):
            if m is None or m[k] > 200:
                acc[0] += ycc[3 * k]
                acc[1] += ycc[3 * k + 1]
                acc[2] += ycc[3 * k + 2]
                weight += 1
    return tuple(a / weight for a in acc) if weight else (0.0, 0.0, 0.0)


@dataclass(frozen=True)
class Match:
    """`match`: a conservative meet-in-the-middle between subject and new background."""

    gain: float = 1.0  # subject luma gain (0.92-1.12)
    du: float = 0.0  # subject chroma nudge, 10-bit units
    dv: float = 0.0
    bg: float = 1.0  # background luma gain (0.7-1.0): a daylight plate behind a dim room take


def match_lift(src_small: list[Image.Image], mattes: list[Image.Image],
               bg_small: list[Image.Image]) -> Match:  # fmt: skip
    """Subject a little towards the background (gain, chroma), the background down towards the
    subject for the rest of the way (at most -30 %). Match() when nothing is measurable."""
    y_s, cb_s, cr_s = _mean_ycbcr(src_small, mattes)
    y_b, cb_b, cr_b = _mean_ycbcr(bg_small, None)
    if y_s < 1 or y_b < 1:
        return Match()
    gain = min(1.12, max(0.92, ((y_b - 16) / max(y_s - 16, 1)) ** 0.25))
    du = max(-4.0, min(4.0, 0.15 * (cb_b - cb_s))) * 4
    dv = max(-4.0, min(4.0, 0.15 * (cr_b - cr_s))) * 4
    lifted = (y_s - 16) * gain
    bg = min(1.0, max(0.7, (lifted / max(y_b - 16, 1)) ** 0.5))
    return Match(gain, du, dv, bg)


def _frame_count(path: PathLike) -> int:
    j = ffprobe_json(path, "-count_frames", "-select_streams", "v:0")
    v = j["streams"][0]
    return int(v.get("nb_read_frames") or 0)


def replace(
    src: PathLike,
    out: PathLike,
    bg: str | Spec = "studio",
    *,
    start: float = 0.0,
    duration: float | None = None,
    blur: float = 0.0,
    feather: float = 2.5,
    erode: int = 0,
    smooth: int = 1,
    choke: float = 0.5,
    wrap: float = 0.35,
    grain: float | None = None,
    match: bool = False,
    size: tuple[int, int] | None = None,
    mode: str = "hybrid",
    matte_file: PathLike | None = None,
    matte_long_side: int = 1920,
    audio: bool = True,
) -> Path:
    """src[start, start+duration) with a new background -> ProRes HQ 10-bit .mov (+ PCM audio).

    `bg` is a spec string or Spec. `matte_file` skips Vision and uses that gray matte video
    (same frames as the range), e.g. an edited or synthetic one.
    """
    spec = bg if isinstance(bg, Spec) else parse_spec(bg)
    if spec.path is not None and not spec.path.exists():
        raise FileNotFoundError(spec.path)
    info = video_info(src)
    w, h = size or (info.width, info.height)
    mfile = Path(matte_file) if matte_file else matte(
        src, mode=mode, size=matte_long_side, start=start, duration=duration)  # fmt: skip
    n = _frame_count(mfile)
    if n == 0:
        raise RuntimeError(f"matte boş: {mfile}")
    refine = Refine(erode=erode, smooth=smooth, feather=feather, choke=choke, wrap=wrap,
                    grain=grain)  # fmt: skip
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        tmpd = Path(tmp)
        if spec.kind == "keep":
            glow = Spec("color", colors=(spec.colors[0] if spec.colors else GLOW_COLOR,))
            bg_input = ["-i", render_still(glow, w, h, tmpd / "glow.mkv")]
        elif spec.kind == "video":
            bg_input = ["-stream_loop", "-1", "-ss", f"{spec.at:.3f}", "-i", spec.path]
        else:
            center = subject_center(mfile, n) if spec.kind == "studio" else (0.5, 0.42)
            bg_input = ["-i", render_still(spec, w, h, tmpd / "bg.mkv", blur, center)]
        lift = None
        if match and spec.kind != "keep":
            step = max(1, n // 6)
            pick = f"select='not(mod(n\\,{step}))'"
            src_small = _small_rgb(src, pick, 6, (160, 90), _seek(start, duration))
            mattes = _small_rgb(mfile, pick, 6, (160, 90))
            bg_small = _small_rgb(bg_input[-1], "null", 1, (160, 90), bg_input[:-2])
            lift = match_lift(src_small[: len(mattes)], mattes[: len(src_small)], bg_small)
        plan = Plan(w, h, info.fps, spec, refine, blur, lift)
        rate = f"{info.fps.numerator}/{info.fps.denominator}"
        hw = [] if info.rotated else ["-hwaccel", "videotoolbox"]
        amap = ["-map", "0:a?", "-c:a", "pcm_s16le"] if audio else ["-an"]
        tail = ["-filter_complex", build_graph(plan), "-map", "[v]", *amap, "-frames:v", str(n),
                "-r", rate, *PRORES_HQ, out]  # fmt: skip
        head = [*_seek(start, duration), "-i", src, "-i", mfile, *bg_input]
        try:
            ffmpeg(["-y", *hw, *head, *tail])
        except FFmpegError:
            if not hw:
                raise
            ffmpeg(["-y", *head, *tail])  # software decode fallback
    return out
