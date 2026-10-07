"""Jump cuts: keep only the given segments of a clip, picture and sound together.

Segment edges snap to source frames, so picture and audio stay in sync; each audio piece gets a
10 ms fade in/out, otherwise every cut clicks. Use `remap` to move anything timed on the source
(captions, SFX, zoom keys) to the cut timeline.
"""

from __future__ import annotations

from collections.abc import Sequence
from fractions import Fraction
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg, probe
from vlogkit.timecode import before_frame
from vlogkit.video.graph import PRORES_HQ, concat

FADE = 0.01


def snap(segments: Sequence[tuple[float, float]], fps: Fraction) -> list[tuple[int, int]]:
    """Seconds -> [start_frame, end_frame) on the source's frame grid; empty ones dropped."""
    out = []
    for a, b in segments:
        fa, fb = round(a * fps), round(b * fps)
        if fb > fa:
            out.append((fa, fb))
    return out


def remap(t: float, segments: Sequence[tuple[float, float]]) -> float | None:
    """Source time -> time on the cut timeline (None if `t` was cut out)."""
    offset = 0.0
    for a, b in segments:
        if a <= t < b:
            return offset + t - a
        offset += b - a
    return None


def graph(frames: Sequence[tuple[int, int]], fps: Fraction, audio: bool = True) -> str:
    parts, vl, al = [], [], []
    for i, (fa, fb) in enumerate(frames):
        # time-based trim just before each frame: exact on CFR sources, sane on VFR phone clips
        t0, t1 = max(0.0, before_frame(fa, fps)), before_frame(fb, fps)
        parts.append(f"[0:v]trim=start={t0:.6f}:end={t1:.6f},setpts=PTS-STARTPTS[v{i}]")
        vl.append(f"v{i}")
        if audio:
            a, d = float(fa / fps), float((fb - fa) / fps)
            parts.append(
                f"[0:a]atrim=start={a:.6f}:duration={d:.6f},asetpts=PTS-STARTPTS,"
                f"afade=t=in:d={FADE},afade=t=out:st={max(0.0, d - FADE):.6f}:d={FADE}[a{i}]"
            )
            al.append(f"a{i}")
    parts.append(concat(vl, fps))
    if audio:
        parts.append("".join(f"[{x}]" for x in al) + f"concat=n={len(al)}:v=0:a=1[a]")
    return ";".join(parts)


def jumpcut(
    src: PathLike,
    segments: Sequence[tuple[float, float]],
    out_video: PathLike,
    out_audio: PathLike | None = None,
) -> tuple[Path, Path | None]:
    """Render the kept segments: picture as ProRes HQ, sound (if asked) as 48 kHz WAV."""
    info = probe(src)
    fps = info.fps or Fraction(30000, 1001)
    frames = snap(segments, fps)
    if not frames:
        raise ValueError("kesmelerden sonra hiçbir şey kalmıyor")
    audio = out_audio is not None and info.has_audio
    args: list = ["-y", "-i", src, "-filter_complex", graph(frames, fps, audio)]
    args += ["-map", "[v]", *PRORES_HQ, "-an", out_video]
    if audio:
        args += ["-map", "[a]", "-c:a", "pcm_s24le", "-ar", "48000", "-vn", out_audio]
    ffmpeg(args)
    return Path(out_video), Path(out_audio) if audio else None
