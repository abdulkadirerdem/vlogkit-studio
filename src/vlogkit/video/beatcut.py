"""Beat-synced montage (Reels / Shorts to a song): the song sets the cuts, the best moments hit
the drop.

1. `moments`: per source clip: motion (frame difference at 10 fps), its own cuts, picture
   quality (sharpness, exposure) and burned-in text (Vision OCR) every 0.5 s. Loud bars get moving
   shots, quiet bars calm ones; blurry, washed-out or captioned moments lose points.
2. `rhythm`: cut times from the song's structure. Low bars: one shot per bar. Mid: every 2 beats.
   High: every beat. The bar before a drop doubles up. A drop is always a cut.
3. `plan`: which moment of which clip fills each slot. No clip twice in a row, no moment reused.
   Clips are taken as given in chronological order and the reel keeps that order loosely (a story
   from start to finish). The first slot is the hook: a strong, moving moment.
   Accents: a punch-in and a flash on the drop, a small punch on the bar starts of loud bars.
4. `render`: frame-accurate picture (a cut lands on round(song_time * fps)), flashes, the song
   as audio. Two deliveries: with the song (to watch / archive) and without (to upload and add
   the same song in Instagram; see `instagram_note`).

The plan is plain data (plan.json): Claude or the user can swap moments and render again.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

from vlogkit.analysis import pacing
from vlogkit.analysis.music import Music
from vlogkit.analysis.scenes import detect_cuts
from vlogkit.audio.loudness import normalize
from vlogkit.audio.mix import AudioGraph
from vlogkit.export.encode import SHORTS, compose
from vlogkit.ff import ffmpeg, probe
from vlogkit.graphics.elements import Flash
from vlogkit.graphics.render import render_overlay
from vlogkit.timecode import FPS_NTSC
from vlogkit.video.graph import SEGMENT_TAIL, concat, render_intermediate
from vlogkit.video.zoom import Zoom, zoom_crop

W, H = 1080, 1920


# --------------------------------------------------------------------------- sources
@dataclass
class Source:
    path: str
    duration: float
    motion: list[float]  # frame difference every 0.1 s
    cuts: list[float]
    quality: list[float] = field(default_factory=list)  # 0-1 every 0.5 s (sharp + exposed)
    text: list[bool] = field(default_factory=list)  # burned-in caption (static text) every 0.5 s

    def window_motion(self, t: float, d: float) -> float:
        a, b = int(t * 10), max(int(t * 10) + 1, int((t + d) * 10))
        vals = self.motion[a:b]
        return sum(vals) / len(vals) if vals else 0.0

    def _half(self, series: list, t: float, d: float) -> list:
        return series[int(t * 2) : max(int(t * 2) + 1, int((t + d) * 2) + 1)]

    def window_quality(self, t: float, d: float) -> float:
        vals = self._half(self.quality, t, d)
        return min(vals) if vals else 0.5  # the worst frame of the window counts

    def window_text(self, t: float, d: float) -> bool:
        return any(self._half(self.text, t, d))

    def clean(self, t: float, d: float, margin: float = 0.15) -> bool:
        """Inside the clip and not across one of its own cuts."""
        if t < 0.2 or t + d > self.duration - 0.2:
            return False
        return not any(t - margin < c < t + d + margin for c in self.cuts)


def _looks(path: str | Path, use_ocr: bool) -> tuple[list[float], list[bool]]:
    """Quality and caption flags every 0.5 s from one pass of small frames."""
    import tempfile

    from PIL import Image

    from vlogkit.analysis import ocr, thumbs

    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg(["-y", "-i", path, "-an", "-vf", "fps=2,scale=480:-2", Path(tmp) / "f%05d.png"])
        frames = sorted(Path(tmp).glob("f*.png"))
        raw = []
        for f in frames:
            with Image.open(f) as im:
                raw.append(thumbs.measure(im.convert("RGB").resize((240, 427))))
        found = ocr.read(frames) if use_ocr and ocr.available() else {}
        text = ocr.overlay_flags([found.get(str(f), []) for f in frames])
    if not raw:
        return [], []
    sharp = sorted(r[0] for r in raw)
    med = sharp[len(sharp) // 2] or 1.0
    quality = [0.5 * min(1.0, s / med) + 0.5 * e for s, _, e in raw]
    return quality, text


def moments(path: str | Path, use_ocr: bool = True) -> Source:
    info = probe(path)
    series = pacing.scores(path, fps=10)
    motion = [s for _, s in series]
    quality, text = _looks(path, use_ocr)
    return Source(str(path), info.duration, motion, detect_cuts(path), quality, text)


# --------------------------------------------------------------------------- rhythm
# Shortest shot per energy level (s). The cut step is the smallest whole number of beats that is at
# least this long, so a fast song (150 BPM) cuts every 2 beats where a slow one (90 BPM) cuts on
# every beat.
MIN_SHOT = {"high": 0.55, "mid": 1.1, "low": 2.2}


def step(beat_len: float, level: str) -> int:
    k = 1
    while k * beat_len < MIN_SHOT[level] - 1e-6:
        k *= 2
    return k


def rhythm(music: Music, start: float, length: float, phrase: int = 4) -> list[float]:
    """Cut times (song time) inside [start, start + length), from the song's structure.

    - Each level has its own step (see MIN_SHOT); a step longer than a bar skips bar lines.
    - The last bar of every `phrase`-bar phrase in a loud part goes twice as fast (a fill).
    - The bar right before a drop cuts on every beat (build-up). A drop is always a cut.
    """
    end = start + length
    cuts: set[float] = {start}
    drops = set(music.drops)
    for i, bar in enumerate(music.bars):
        if bar.end <= start or bar.start >= end:
            continue
        beats = [b for b in music.beats if bar.start - 1e-6 <= b < bar.end - 1e-6] or [bar.start]
        next_is_drop = i + 1 < len(music.bars) and music.bars[i + 1].start in drops
        k = step(music.beat_len, bar.level)
        if next_is_drop:
            picks = beats
        elif k >= len(beats):  # slower than one cut per bar: every (k / beats)th bar line
            bars_per_cut = max(1, k // max(1, len(beats)))
            picks = [bar.start] if i % bars_per_cut == 0 else []
        else:
            fill = bar.level == "high" and i % phrase == phrase - 1
            picks = beats[:: max(1, k // 2 if fill else k)]
        cuts.update(t for t in picks if start <= t < end)
    cuts.update(d for d in drops if start <= d < end)
    out = sorted(cuts)
    return [t for i, t in enumerate(out) if i == 0 or t - out[i - 1] > 0.18]  # >= ~5 frames


# --------------------------------------------------------------------------- plan
@dataclass
class Shot:
    start: float  # reel time (s)
    end: float
    src: str
    src_in: float
    accent: str = ""  # "drop" | "punch" | "push" | ""
    x: float = 0.5  # crop centre across a wide source (0 = left edge, 1 = right edge)
    rotate: int = 0  # 90 = turn clockwise (a clip filmed sideways), -90 = counter-clockwise
    speed: float = 1.0  # 2 = twice as fast (reads 2x the source), 0.5 = slow, 0 = freeze frame
    vf: str = ""  # extra filters for this shot only, on the 1080x1920 frame (e.g. lift a dark shot)

    @property
    def dur(self) -> float:
        return self.end - self.start

    @property
    def src_dur(self) -> float:
        """Source seconds the shot consumes."""
        return self.dur * self.speed


@dataclass
class Plan:
    song: str  # audio file, or just the song's name when the edit follows a tempo map
    song_start: float
    length: float
    shots: list[Shot] = field(default_factory=list)
    drops: list[float] = field(default_factory=list)  # reel time
    grid: dict | None = None  # music.grid() arguments when there is no audio file
    hook: str = ""  # headline at the top in the first seconds (graphics.captions.HookTitle)

    def save(self, path: Path) -> Path:
        path.write_text(json.dumps(asdict(self), indent=1, ensure_ascii=False))
        return path

    @staticmethod
    def load(path: Path) -> Plan:
        d = json.loads(Path(path).read_text())
        d["shots"] = [Shot(**s) for s in d["shots"]]
        return Plan(**d)


def auto_start(music: Music, lead: float = 3.0, length: float = 20.0) -> tuple[float, float]:
    """Start so the first drop lands `lead` s in (the hook), end on a bar line after `length`."""
    if music.drops:
        start = max((d for d in music.downbeats if d <= music.drops[0] - lead), default=0.0)
    else:
        loud = [b for b in music.bars if b.level == "high"]
        start = loud[0].start if loud else (music.downbeats[0] if music.downbeats else 0.0)
    ends = [b.end for b in music.bars if b.end - start >= length - 0.01]
    end = ends[0] if ends else music.duration
    return start, end - start


def plan(
    music: Music,
    sources: list[Source],
    start: float,
    length: float,
    seed: int = 0,
    story: bool = True,
) -> Plan:
    rnd = random.Random(seed)
    cuts = rhythm(music, start, length)
    marks = [*cuts, start + length]
    slots = list(pairwise(marks))
    drops = {d for d in music.drops if start <= d < start + length}

    def energy(a: float) -> str:
        if any(abs(a - d) < 1e-6 for d in drops):
            return "drop"
        if abs(a - start) < 1e-6:
            return "hook"  # the first shot decides the swipe
        bar = music.bar_at(a + 1e-6)
        return bar.level if bar else "mid"

    order_of = {s.path: k for k, s in enumerate(sources)}

    def place(src: Source, t: float) -> float:
        """Where this moment sits in the story: 0 (first clip, start) .. 1 (last clip, end)."""
        return (order_of[src.path] + t / max(src.duration, 1e-6)) / len(sources)

    # most important slots choose first: the hook, the drop, then loud, then the rest
    rank = {"hook": 0, "drop": 0, "high": 1, "mid": 2, "low": 3}
    order = sorted(range(len(slots)), key=lambda i: (rank[energy(slots[i][0])], i))
    used: dict[str, list[tuple[float, float]]] = {s.path: [] for s in sources}
    chosen: dict[int, tuple[Source, float]] = {}
    for i in order:
        a, b = slots[i]
        d = b - a
        e = energy(a)
        neighbours = {chosen[j][0].path for j in (i - 1, i + 1) if j in chosen}
        best, best_score = None, float("-inf")
        for allow_text in (False, True):  # captioned moments only if nothing else fits
            if best is not None:
                break
            for src in sources:
                if len(sources) > 1 and src.path in neighbours:
                    continue
                for k in range(2, int((src.duration - d) * 4)):
                    t = k / 4
                    if not src.clean(t, d) or any(
                        t < u1 + 0.8 and t + d > u0 - 0.8 for u0, u1 in used[src.path]
                    ):
                        continue
                    m = src.window_motion(t, d)
                    # loud slots want motion, quiet slots want calm (but not frozen) pictures
                    if e in ("drop", "high", "hook"):
                        score = min(m, 8.0)
                    else:
                        score = -abs(m - 1.5) if e == "low" else -abs(m - 3)
                    score += 2.0 * src.window_quality(t, d)
                    if src.window_text(t, d) and not allow_text:
                        continue
                    if story and e != "hook":  # the hook may flash forward; the rest keeps order
                        score -= 3.0 * abs((a - start) / length - place(src, t))
                    score += rnd.random() * 0.3
                    if score > best_score:
                        best, best_score = (src, t), score
        if best is None:  # out of fresh material: allow reuse
            src = rnd.choice(sources)
            best = (src, max(0.2, rnd.uniform(0.2, max(0.21, src.duration - d - 0.2))))
        chosen[i] = best
        used[best[0].path].append((best[1], best[1] + d))

    shots = []
    for i, (a, b) in enumerate(slots):
        src, t = chosen[i]
        e = energy(a)
        bar = music.bar_at(a + 1e-6)
        accent = (
            "drop"
            if e == "drop"
            else "punch"
            if e == "high" and bar and abs(bar.start - a) < 1e-6
            else "push"
            if e == "low"
            else ""
        )
        shots.append(Shot(round(a - start, 4), round(b - start, 4), src.path, round(t, 3), accent))
    return Plan(str(music.path), start, length, shots, sorted(round(d - start, 4) for d in drops))


# --------------------------------------------------------------------------- render
def _frames(t: float, fps: Fraction) -> int:
    return round(t * fps)


@lru_cache(maxsize=64)
def _fps(path: str) -> Fraction | None:
    return probe(path).fps


TURN = {90: "transpose=clock,", -90: "transpose=cclock,", 180: "hflip,vflip,"}


def shot_chain(s: Shot, n: int, fps: Fraction = FPS_NTSC, src_fps: Fraction | None = None) -> str:
    """Filters for one shot (input at PTS 0) -> exactly n frames of W x H.

    Order: frame rate, rotation, cover-scale, crop at `x` across the width (a 16:9 source keeps
    about a third of its width in 9:16), then speed (a constant `SpeedRamp`: frame-exact).
    """
    rate = "" if (src_fps or fps) == fps else f"fps={fps.numerator}/{fps.denominator},"
    x = min(max(s.x, 0.0), 1.0)
    cover = (
        f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W}:{H}:x='clip({x:.4f}*iw-{W // 2},0,iw-{W})':y='(ih-{H})/2',"
    )
    speed = ""
    if s.speed <= 0:  # freeze: the first frame held for the whole shot
        speed = f"trim=end_frame=1,loop=loop={n}:size=1:start=0,setpts=N/FRAME_RATE/TB,"
    elif abs(s.speed - 1) > 1e-6:
        from vlogkit.video.fx import SpeedRamp

        d = n / float(fps) * s.speed
        ramp = SpeedRamp(((0.0, s.speed), (d, s.speed)), d, fps)
        speed = f"trim=end_frame={ramp.src_frames},setpts=PTS-STARTPTS,{ramp.filter()},"
    look = f"{s.vf}," if s.vf else ""
    return (
        f"{rate}{TURN.get(s.rotate, '')}{cover}{look}{speed}trim=end_frame={n},setpts=PTS-STARTPTS"
    )


def base_graph(
    p: Plan, fps: Fraction = FPS_NTSC, grade: str | None = None, extra: str | None = None
) -> tuple[list, str]:
    """ffmpeg inputs + filter graph for the picture: every shot cut on its frame, zoom accents.

    `extra` runs on the assembled timeline after zoom and grade (e.g. `fx.CutFX().filter()`)."""
    inputs, parts, labels = [], [], []
    zoom = Zoom()
    for i, s in enumerate(p.shots):
        f0, f1 = _frames(s.start, fps), _frames(s.end, fps)
        n = f1 - f0
        read = n / fps * max(s.speed, 0.0) + 0.5
        inputs.append(["-ss", f"{s.src_in:.3f}", "-t", f"{float(read):.3f}", "-i", s.src])
        parts.append(f"[{i}:v]{shot_chain(s, n, fps, _fps(s.src))},{SEGMENT_TAIL}[s{i}]")
        labels.append(f"s{i}")
        t0, t1 = f0 / fps, f1 / fps
        if s.accent == "drop":
            zoom.punch(float(t0), float(t1) - 0.001, 0.14, decay=7)
        elif s.accent == "punch":
            zoom.punch(float(t0), float(t1) - 0.001, 0.06, decay=12)
        elif s.accent == "push":
            zoom.push(float(t0), float(t1) - 0.001, 0.05)
    chain = concat(labels, fps, out="cat")
    post = (
        zoom_crop(zoom, None, W, H)
        + (f",{grade}" if grade else "")
        + (f",{extra}" if extra else "")
    )
    graph = ";".join([*parts, chain, f"[cat]{post},{SEGMENT_TAIL}[v]"])
    return inputs, graph


def music_graph(p: Plan, length: float | None = None) -> AudioGraph:
    """The song under the reel. `length` = the picture's exact length (whole frames): a sound
    track even 6 ms shorter than the picture makes the mp4 lose its last frame."""
    length = length or p.length
    g = AudioGraph(length)
    i = g.input(p.song)
    fade = min(0.5, length / 10)
    g.chain(
        f"[{i}:a]atrim=start={p.song_start:.4f}:duration={length:.4f},asetpts=PTS-STARTPTS,"
        f"afade=t=in:d=0.01,afade=t=out:st={length - fade:.4f}:d={fade:.3f}",
        "song",
        stem="music",
    )
    return g


def instagram_note(p: Plan, name: str) -> str:
    m, s = divmod(p.song_start, 60)
    drops = ", ".join(f"{d:.2f}" for d in p.drops) or "yok"
    song = "aynı şarkıyı" if p.grid is None else f'"{p.song}" şarkısını'
    return (
        "\n".join(
            [
                f"{name}: Instagram'a yükleme",
                "",
                f"1. {name}_muziksiz.mp4 dosyasını Reels olarak aç.",
                f"2. Müzik ekle: {song} Instagram'ın kütüphanesinden seç ve {int(m)}:{s:05.2f}'dan başlat",
                f"   (kurgu şarkının {p.song_start:.2f}-{p.song_start + p.length:.2f} sn arasına göre yapıldı, "
                f"süre {p.length:.2f} sn).",
                f"3. Kontrol: videodaki drop kesmesi {drops} sn'de; müzikteki vuruş oraya oturmalı.",
                "   Kaydıysa başlangıcı birkaç onda bir saniye kaydır. Meta'nın Edits uygulamasında ses dalgasını",
                "   görerek hizalamak daha kolay.",
                "",
                "Not: İşletme hesaplarında sadece Meta Sound Collection kullanılabilir. Telifli bir",
                "şarkıyı videoya gömüp yüklemek susturulma ya da kaldırılma riski taşır; bu yüzden",
                "müziksiz dosyayı yükle.",
                f"Müzik telifsizse (CC0 ya da lisansı sende) {name}.mp4 dosyasını doğrudan yükleyebilirsin."
                if p.grid is None
                else f"{name}.mp4 dosyasındaki ses şarkı değil, rehber ritim (vuruş, ölçü, drop): "
                "onu yükleme.",
            ]
        )
        + "\n"
    )


def render(
    p: Plan,
    work: Path,
    out: Path,
    fps: Fraction = FPS_NTSC,
    grade: str | None = None,
    flash: bool = True,
) -> dict[str, Path]:
    """Base + flashes + song -> <out>.mp4, <out>_muziksiz.mp4, <out>.instagram.txt, plan.json."""
    work.mkdir(parents=True, exist_ok=True)
    base = work / "base.mov"
    inputs, graph = base_graph(p, fps, grade)
    render_intermediate(inputs, graph, base)
    nframes = _frames(p.length, fps)
    overlay = None
    els = [Flash(float(_frames(d, fps) / fps), 0.28, 0.85) for d in p.drops] if flash else []
    if p.hook:
        from vlogkit.graphics.captions import HookTitle

        first_drop = min((d for d in p.drops if d > 1.5), default=3.0)
        els.append(HookTitle(p.hook, 0.0, min(3.0, first_drop)))
    if els:
        overlay = render_overlay(els, nframes, work / "overlay.mov", fps, (W, H))
    audio = work / "audio.wav"
    song = p
    if p.grid is not None:  # no audio file: a metronome guide stands in for the song
        from vlogkit.analysis.music import grid as music_grid
        from vlogkit.audio.synth import guide_track

        m = music_grid(**p.grid)
        guide = work / "guide.wav"
        guide_track(m, guide, p.song_start, p.length + 1)
        song = Plan(str(guide), 0.0, p.length, p.shots, p.drops)
    normalize(music_graph(song, float(nframes / fps)), audio, verbose=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    compose(base, overlay, audio, out, SHORTS, fps)
    silent = out.with_name(out.stem + "_muziksiz.mp4")
    ffmpeg(["-y", "-i", out, "-an", "-c", "copy", "-movflags", "+faststart", silent])
    note = out.with_name(out.stem + ".instagram.txt")
    note.write_text(instagram_note(p, out.stem))
    from vlogkit.export import timeline

    try:
        timeline.write(timeline.from_plan(p, out, float(fps)), out)
    except Exception as e:  # the Studio timeline is a convenience
        print(f"  ! zaman çizelgesi yazılamadı: {e}", flush=True)
    return {"video": out, "silent": silent, "note": note, "plan": p.save(work / "plan.json")}


def summary(p: Plan) -> list[str]:
    lines = [
        f"{len(p.shots)} plan, {p.length:.1f} sn, şarkı {p.song_start:.2f}-{p.song_start + p.length:.2f} sn"
    ]
    for s in p.shots:
        tag = {"drop": "DROP", "punch": "punch", "push": "push"}.get(s.accent, "")
        lines.append(f"{s.start:6.2f}-{s.end:6.2f}  {Path(s.src).name}@{s.src_in:.2f}  {tag}")
    return lines


def load_music_and_sources(song: str | Path, clips: list[str | Path]) -> tuple[Music, list[Source]]:
    from vlogkit.analysis.music import analyze

    return analyze(song), [moments(c) for c in clips]


__all__ = [
    "Plan",
    "Shot",
    "Source",
    "auto_start",
    "base_graph",
    "instagram_note",
    "load_music_and_sources",
    "moments",
    "plan",
    "render",
    "rhythm",
    "summary",
]
