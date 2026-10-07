"""`vlogkit music VIDEO -t A -t B ...`: candidate tracks under the scene, for the user to choose.

Royalty-free music picked from tags and descriptions is often wrong for the scene, and the agent
cannot listen. So it shortlists 3-5 tracks and the user chooses by ear: each preview is the scene
(small, with its own sound) with one track under it at a bed level. A track starts where it gets
going (its first loud stretch, so a long quiet intro does not decide) unless an offset is given:
`id@42`; `id@0` plays it from the top. The scene is encoded once; a preview only mixes audio.

The command prints a "Seçim:" block (question + `N. label — /path` lines). The studio shows that
block as cards with the videos and a "Bunu seç" button; in a terminal it reads as a list.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg, probe

MAX_TRACKS = 6  # more than this and nobody listens to them all
WINDOW = 3.0  # s: loudness is judged over this window when looking for where a track gets going


@dataclass(frozen=True)
class Track:
    path: Path
    label: str
    offset: float | None = None  # None: where it gets going
    page: str = ""  # license page of a library track


@dataclass(frozen=True)
class Preview:
    track: Track
    offset: float
    path: Path


@dataclass(frozen=True)
class Audition:
    video: Path
    start: float
    length: float  # the scene's real length (shorter near the end of the video)
    previews: list[Preview]

    def block(self) -> str:
        """What the agent pastes into its last message; the studio turns it into cards."""
        end = self.start + self.length
        lines = [f"Seçim: {self.video.name} {self.start:g}-{end:g} sn için hangi müzik?"]
        for k, p in enumerate(self.previews, 1):
            lines.append(f"{k}. {p.track.label}, {p.offset:g} sn'den — {p.path}")
        return "\n".join(lines)


def parse(spec: str) -> Track:
    """An asset id or a file, with an optional start: "swiss_view_tvari@56.5", "~/a.mp3@0"."""
    from vlogkit import assets

    name, offset = spec, None
    m = re.fullmatch(r"(.+)@(\d+(?:[.,]\d+)?)", spec)
    if m:
        name, offset = m.group(1), float(m.group(2).replace(",", "."))
    p = Path(name).expanduser()
    lib = assets.manifest().get(name) or next(  # a library file given by its path
        (a for a in assets.manifest().values() if p.is_file() and a.path.resolve() == p.resolve()),
        None,
    )
    if lib is not None and lib.kind == "music":
        return Track(assets.path(lib.id), f"{lib.id} ({lib.author})", offset, lib.page)
    if p.is_file():
        return Track(p.resolve(), p.stem, offset)
    raise ValueError(f"{spec}: kütüphanede müzik değil, dosya da yok (vlogkit assets list)")


def entry(levels: list[float], length: float, duration: float) -> float:
    """Where a track gets going: a second before the first window within 3 LU of its loud part
    (80th percentile of the windows), kept so that `length` seconds still fit."""
    if not levels:
        return 0.0
    step = int(WINDOW / 0.1)
    wins = []
    for i in range(0, max(1, len(levels) - step + 1), 5):  # every 0.5 s
        chunk = levels[i : i + step]
        p = sum(10 ** (v / 10) for v in chunk) / len(chunk)
        wins.append((i * 0.1, 10 * math.log10(p) if p > 0 else -70.0))
    loud = sorted(v for _, v in wins)[int(0.8 * (len(wins) - 1))]
    t = next(t for t, v in wins if v >= loud - 3)
    return round(max(0.0, min(t - 1.0, duration - length)), 1)


def scene(
    video: PathLike, start: float, length: float, out: Path, sound: bool = True
) -> tuple[Path, bool, float]:
    """The scene once, small (long side <= 960) and with its own sound: (file, has sound, s)."""
    info = probe(video)
    sound = sound and info.has_audio
    if start >= info.duration:
        raise ValueError(f"başlangıç {start} sn videonun dışında ({info.duration:.1f} sn)")
    length = min(length, info.duration - start)
    out.parent.mkdir(parents=True, exist_ok=True)
    vf = "scale=960:960:force_original_aspect_ratio=decrease,scale=trunc(iw/2)*2:trunc(ih/2)*2"
    audio = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"] if sound else ["-an"]
    ffmpeg(
        [
            *("-y", "-ss", f"{start:.3f}", "-t", f"{length:.3f}", "-i", video, "-vf", vf),
            *("-c:v", "libx264", "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p"),
            *audio,
            *("-movflags", "+faststart", out),
        ]
    )
    return out, sound, length


def mix(
    scene_file: Path,
    has_sound: bool,
    track: Track,
    offset: float,
    length: float,
    level: float,
    out: Path,
) -> Path:
    """The scene's picture with its sound and the track under it (loudness `level` LUFS)."""
    fade = min(1.5, length / 4)
    music = (
        f"[1:a]loudnorm=I={level}:TP=-2:LRA=11,aresample=48000,apad,"
        f"afade=t=in:d=0.3,afade=t=out:st={length - fade:.3f}:d={fade:.3f}"
    )
    if has_sound:
        # the scene's sound padded: a clip whose audio ends early must not cut the music
        graph = f"{music}[m];[0:a]apad[s];[s][m]amix=inputs=2:normalize=0:duration=first,alimiter=limit=0.9[a]"
    else:
        graph = f"{music}[a]"
    ffmpeg(
        [
            *("-y", "-i", scene_file, "-ss", f"{offset:.3f}", "-i", track.path),
            *("-filter_complex", graph, "-map", "0:v", "-map", "[a]", "-t", f"{length:.3f}"),
            *("-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", out),
        ]
    )
    return out


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40] or "parca"


def audition(
    video: PathLike,
    tracks: list[Track],
    start: float = 0.0,
    length: float = 30.0,
    level: float = -20.0,
    out_dir: Path | None = None,
    sound: bool = True,
) -> Audition:
    from vlogkit.analysis.music import loudness_series
    from vlogkit.config import BUILD_DIR

    if not 1 <= len(tracks) <= MAX_TRACKS:
        raise ValueError(f"1-{MAX_TRACKS} parça ver: fazlası dinlenmiyor")
    video = Path(video)
    # camera names repeat across trips (IMG_0001, DJI_0042): the folder carries the path's hash
    tag = hashlib.sha1(str(video.resolve()).encode()).hexdigest()[:6]
    out_dir = out_dir or BUILD_DIR / "music" / f"{video.stem}-{tag}-{start:g}s"
    for old in out_dir.glob("[0-9]*-*.mp4"):  # an earlier shortlist for this scene
        old.unlink()
    scene_file, has_sound, length = scene(video, start, length, out_dir / "sahne.mp4", sound)
    out = []
    for k, tr in enumerate(tracks, 1):
        dur = probe(tr.path).duration
        if tr.offset is not None:
            if tr.offset >= dur - 1.0:
                raise ValueError(f"{tr.label}: {tr.offset:g} sn parçanın sonunda ({dur:.0f} sn)")
            offset = tr.offset
        else:
            offset = entry(loudness_series(tr.path), length, dur)
        path = out_dir / f"{k}-{_slug(tr.label.split(' (')[0])}.mp4"
        out.append(Preview(tr, offset, mix(scene_file, has_sound, tr, offset, length, level, path)))
    return Audition(video, start, round(length, 1), out)
