"""Stabilization with vid.stab (ffmpeg-full: vidstabdetect + vidstabtransform), two passes.

1. `analyze(src, trf)`: pass 1 measures the camera shake frame by frame into a .trf file.
2. `transform_filter(trf)`: pass 2, a filter for the render chain, smooths the camera path.

Rules:
- **Same frames in both passes.** The .trf is indexed by frame number. Analyze exactly the frames
  the transform will see: same source, same `start`/`duration`, nothing before it that drops or
  adds frames (no fps, no trim in between). Frame count is unchanged.
- **8-bit only.** vid.stab accepts only 8-bit YUV; ffmpeg silently converts a 10-bit input down.
  So it goes first in the chain, on the 8-bit phone decode, and `format=yuv422p10le` follows it.
  On a 10-bit HDR source the stabilized shot is rounded to 8-bit: stabilize only shots that need
  it. It is a whole-shot filter; never use it inside an `enable=` window (pitfall 21).
- **Zoom.** Smoothing moves the frame, so borders appear; `optzoom` zooms in just enough to hide
  them (1 = one static zoom for the whole shot, 2 = adaptive). Every % of zoom costs sharpness,
  hence the light unsharp afterwards.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg
from vlogkit.video.graph import PRORES_HQ


def _escape(path: PathLike) -> str:
    # filter-graph option values: ':' separates options, '\\' and "'" are special
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


@dataclass(frozen=True)
class Stab:
    # pass 1 (vidstabdetect)
    shakiness: int = 5  # 1-10: how shaky the footage is
    accuracy: int = 15  # 1-15
    stepsize: int = 6
    mincontrast: float = 0.3
    # pass 2 (vidstabtransform)
    smoothing: int = 15  # frames on each side of the low-pass: higher = steadier, floatier
    optzoom: int = 1  # 0 none, 1 static zoom that hides the borders, 2 adaptive zoom
    zoom: float = 0.0  # extra % on top of optzoom
    zoomspeed: float = 0.25  # optzoom=2: max % zoom change per frame
    maxshift: int = -1  # px, -1 = unlimited
    maxangle: float = -1  # rad, -1 = unlimited
    tripod: bool = False  # lock to the first frame (a handheld "static" shot)
    sharpen: bool = True  # unsharp after the resample

    def detect(self, trf: PathLike) -> str:
        opts = [
            f"result='{_escape(trf)}'",
            f"shakiness={self.shakiness}",
            f"accuracy={self.accuracy}",
            f"stepsize={self.stepsize}",
            f"mincontrast={self.mincontrast:g}",
        ]
        if self.tripod:
            opts.append("tripod=1")
        return "vidstabdetect=" + ":".join(opts)

    def transform(self, trf: PathLike) -> str:
        opts = [
            f"input='{_escape(trf)}'",
            f"smoothing={self.smoothing}",
            f"optzoom={self.optzoom}",
            f"zoom={self.zoom:g}",
            f"zoomspeed={self.zoomspeed:g}",
            f"maxshift={self.maxshift}",
            f"maxangle={self.maxangle:g}",
            "interpol=bicubic",
            "crop=black",
        ]
        if self.tripod:
            opts.append("tripod=1")
        chain = "vidstabtransform=" + ":".join(opts)
        if self.sharpen:
            chain += ",unsharp=5:5:0.6:3:3:0.3"
        return chain


PRESETS = {
    # running with a phone in hand: big fast shake, keep the forward motion (adaptive zoom)
    "running": Stab(shakiness=8, accuracy=15, smoothing=25, optzoom=2, zoomspeed=0.35),
    # walking / talking to the camera: gentle smoothing, one static zoom
    "walking": Stab(shakiness=5, smoothing=15, optzoom=1),
    # meant to be static (a view, a sign), shot handheld: lock the camera
    "tripod-ish": Stab(shakiness=4, smoothing=0, optzoom=1, tripod=True),
}


def preset(name: str | Stab = "walking", **overrides) -> Stab:
    base = name if isinstance(name, Stab) else PRESETS[name]
    return replace(base, **overrides) if overrides else base


def _cut(start: float | None, duration: float | None) -> list[str]:
    return (["-ss", f"{start:.3f}"] if start else []) + (
        ["-t", f"{duration:.3f}"] if duration else []
    )


def analyze(
    src: PathLike,
    trf: PathLike,
    stab: str | Stab = "walking",
    *,
    start: float | None = None,
    duration: float | None = None,
    vf_before: str | None = None,
) -> Path:
    """Pass 1. `vf_before` = whatever runs before the transform in the render (e.g. a crop)."""
    trf = Path(trf)
    trf.parent.mkdir(parents=True, exist_ok=True)
    vf = ",".join(x for x in (vf_before, preset(stab).detect(trf)) if x)
    ffmpeg(["-y", *_cut(start, duration), "-i", src, "-an", "-vf", vf, "-f", "null", "-"])
    return trf


def transform_filter(trf: PathLike, stab: str | Stab = "walking", **overrides) -> str:
    """Pass 2 as a filter-chain piece; follow it with `format=yuv422p10le` (see module doc)."""
    return preset(stab, **overrides).transform(trf)


def stabilize(
    src: PathLike,
    out: PathLike,
    stab: str | Stab = "walking",
    *,
    start: float | None = None,
    duration: float | None = None,
    trf: PathLike | None = None,
) -> Path:
    """Both passes on (a part of) a clip -> ProRes HQ 10-bit intermediate, same frame count."""
    out = Path(out)
    trf = Path(trf) if trf else out.with_suffix(".trf")
    s = preset(stab)
    analyze(src, trf, s, start=start, duration=duration)
    ffmpeg(
        [
            "-y", *_cut(start, duration), "-i", src, "-an",
            "-vf", f"{s.transform(trf)},setsar=1,format=yuv422p10le",
            *PRORES_HQ, out,
        ]
    )  # fmt: skip
    return out
