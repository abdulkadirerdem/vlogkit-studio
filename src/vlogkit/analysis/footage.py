"""Log raw footage before editing: what happens where, and which moments are usable.

An edit made from sparse glances at hours of raw clips picks meaningless moments: the second the
creator leans into the lens to stop the recording instead of the door opening. The fix is the
editor's own habit: *log first, cut second.*

`log(folder)` goes through every clip once (4K HEVC decoded on the media engine, scaled on the GPU)
and writes, per clip:
- chunks: scene cuts plus ~4 s pieces of long takes, each with Vision scene labels, face size,
  motion, sharpness, brightness, aesthetics, the words spoken in it (whisper) and automatic flags:
    kurulum    camera handling: a take's head/tail until the picture settles (reaching for the
               button, putting the camera down), or a short burst of a face at the lens
    çok yakın  a face filling the frame (someone leaning into the lens)
    karanlık   lens covered / too dark
    bulanık    much blurrier than the rest of the clip
    sarsıntı   the camera is being swung around
- one timestamped contact sheet covering the whole clip (log/sheets/).
Claude then *looks at every sheet* and fills `desc` (what happens), `beat` (its place in the story)
and `keep` per chunk in log.json. Notes survive re-runs (merged by clip + t0). The plan is built
from story beats with the chunk that shows each beat best; flagged chunks are not used.
"""

from __future__ import annotations

import contextlib
import json
import math
import re
import shutil
import statistics
import tempfile
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from itertools import pairwise
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageStat

from vlogkit.config import FONTS_DIR
from vlogkit.ff import FFmpegError, PathLike, ffmpeg, ffprobe_json

VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mkv"}
SAMPLE_FPS = 2.0  # analysis frames per second
MOTION_FPS = 10.0
CACHE_VERSION = 2
GRID = 4  # 4x4 tiles: where in the frame something changed
_DJI = re.compile(r"DJI_(\d{14})")
_FRAME = re.compile(r"pts_time:([0-9.]+)")
_SCORE = re.compile(r"lavfi\.scd\.score=([0-9.]+)")

# Vision's taxonomy is English and full of umbrella terms; show the useful ones in Turkish.
LABELS_TR = {
    "door": "kapı",
    "portal": "kapı",
    "doorway": "kapı",
    "stairs": "merdiven",
    "staircase": "merdiven",
    "street": "sokak",
    "road": "yol",
    "path": "patika",
    "sidewalk": "kaldırım",
    "car": "araba",
    "automobile": "araba",
    "vehicle": "araç",
    "bus": "otobüs",
    "train": "tren",
    "airplane": "uçak",
    "building": "bina",
    "house": "ev",
    "apartment": "apartman",
    "room": "oda",
    "kitchen": "mutfak",
    "bedroom": "yatak odası",
    "bathroom": "banyo",
    "window": "pencere",
    "furniture": "mobilya",
    "sofa": "kanepe",
    "bed": "yatak",
    "table": "masa",
    "chair": "sandalye",
    "shoe": "ayakkabı",
    "footwear": "ayakkabı",
    "clothing": "kıyafet",
    "mountain": "dağ",
    "hill": "tepe",
    "sky": "gökyüzü",
    "cloud": "bulut",
    "tree": "ağaç",
    "forest": "orman",
    "plant": "bitki",
    "grass": "çimen",
    "flower": "çiçek",
    "water": "su",
    "sea": "deniz",
    "lake": "göl",
    "river": "nehir",
    "beach": "sahil",
    "snow": "kar",
    "sunset": "gün batımı",
    "night_sky": "gece",
    "food": "yemek",
    "meal": "yemek",
    "drink": "içecek",
    "coffee": "kahve",
    "tea": "çay",
    "restaurant": "restoran",
    "cafe": "kafe",
    "bottle": "şişe",
    "fence": "korkuluk",
    "railing": "korkuluk",
    "hallway": "koridor",
    "corridor": "koridor",
    "shelf": "raf",
    "backpack": "sırt çantası",
    "bag": "çanta",
    "luggage": "bavul",
    "shop": "dükkan",
    "store": "dükkan",
    "market": "market",
    "people": "insan",
    "adult": "insan",
    "child": "çocuk",
    "baby": "bebek",
    "crowd": "kalabalık",
    "dog": "köpek",
    "cat": "kedi",
    "computer": "bilgisayar",
    "screen": "ekran",
    "phone": "telefon",
    "office": "ofis",
    "sport": "spor",
    "running": "koşu",
    "bicycle": "bisiklet",
    "elevator": "asansör",
    "parking_lot": "otopark",
    "bridge": "köprü",
    "city": "şehir",
    "cityscape": "şehir",
}
# Too generic to tell anything apart.
LABEL_NOISE = {
    "structure",
    "machine",
    "conveyance",
    "land",
    "material",
    "outdoor",
    "indoor",
    "interior_room",
    "textile",
    "wood_processed",
    "housewares",
    "consumer_electronics",
    "container",
    "equipment",
    "decoration",
    "art",
    "document",
    "screenshot",
    "blue_sky",
    "wall",
}


# --------------------------------------------------------------------------- data
@dataclass
class Sample:
    """One analysis frame (every 1 / SAMPLE_FPS s)."""

    t: float
    luma: float  # mean Y 0-255
    sharp: float  # Laplacian stddev (compare within a clip)
    exposure: float  # 0-1
    face: float = 0.0  # tallest face, fraction of the frame height
    face_edge: bool = False  # a big face cut by the frame border
    humans: int = 0
    labels: list[tuple[str, float]] = field(default_factory=list)
    aesthetics: float | None = None
    human: float = 0.0  # tallest human body box, fraction of the frame height
    human_w: float = 0.0  # ... and its width
    tile_luma: list[float] = field(default_factory=list)  # GRID x GRID, row by row
    tile_sharp: list[float] = field(default_factory=list)


@dataclass
class Chunk:
    clip: str
    t0: float
    t1: float
    labels: list[str] = field(default_factory=list)
    face: float = 0.0
    motion: float = 0.0
    sharp: float = 1.0  # relative to the clip's median
    luma: float = 0.0
    aesthetics: float | None = None
    speech: str = ""
    flags: list[str] = field(default_factory=list)
    # the local video model's view (vlogkit log --vlm): action, setting, camera_handling, ...
    local: dict | None = None
    # filled by Claude (or the user) after looking at the sheet
    desc: str = ""
    beat: str = ""
    keep: bool | None = None

    @property
    def usable(self) -> bool:
        """Kept, or not flagged with a blocking flag ("çok yakın" / "sarsıntı" only inform)."""
        if self.keep is not None:
            return self.keep
        return not any(f in BLOCKING for f in self.flags)


@dataclass
class Clip:
    path: str
    name: str
    start: str | None  # ISO time the recording started, if known
    duration: float
    width: int
    height: int
    cuts: list[float] = field(default_factory=list)
    chunks: list[Chunk] = field(default_factory=list)
    sheets: list[str] = field(default_factory=list)


@dataclass
class Log:
    folder: str
    clips: list[Clip] = field(default_factory=list)

    def save(self, path: Path) -> Path:
        path.write_text(json.dumps(asdict(self), ensure_ascii=False, indent=1))
        return path

    @staticmethod
    def load(path: Path) -> Log:
        d = json.loads(Path(path).read_text())
        clips = []
        for c in d.get("clips", []):
            chunks = [Chunk(**k) for k in c.pop("chunks", [])]
            clips.append(Clip(**c, chunks=chunks))
        return Log(d.get("folder", ""), clips)

    @property
    def chunks(self) -> list[Chunk]:
        return [k for c in self.clips for k in c.chunks]


# --------------------------------------------------------------------------- clips
def recorded_at(path: PathLike) -> datetime | None:
    """DJI_YYYYMMDDhhmmss in the name, else the container's creation_time."""
    m = _DJI.search(Path(path).name)
    if m:
        return datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    try:
        tag = ffprobe_json(path)["format"].get("tags", {}).get("creation_time")
        return (
            datetime.fromisoformat(tag.replace("Z", "+00:00")).replace(tzinfo=None) if tag else None
        )
    except Exception:
        return None


def clips_in(paths_or_folder: PathLike | list[PathLike]) -> list[Path]:
    """Video files, in the order they were recorded."""
    if isinstance(paths_or_folder, (str, Path)) and Path(paths_or_folder).is_dir():
        paths = [p for p in Path(paths_or_folder).iterdir() if p.suffix.lower() in VIDEO_EXT]
    elif isinstance(paths_or_folder, (str, Path)):
        paths = [Path(paths_or_folder)]
    else:
        paths = [Path(p) for p in paths_or_folder]
    paths = [p for p in paths if not p.name.startswith(".")]
    return sorted(paths, key=lambda p: (recorded_at(p) or datetime.max, p.name))


def _video_info(path: PathLike) -> tuple[float, int, int, bool]:
    j = ffprobe_json(path)
    v = next(s for s in j["streams"] if s["codec_type"] == "video")
    ten_bit = "10" in (v.get("pix_fmt") or "")
    return float(j["format"].get("duration", 0.0)), int(v["width"]), int(v["height"]), ten_bit


def _decode(path: PathLike, frames_dir: Path, w: int, h: int, ten_bit: bool) -> str:
    """One pass: SAMPLE_FPS jpgs + MOTION_FPS scene scores (stderr). Media engine + GPU scaling
    on macOS (4K HEVC 10-bit decodes ~6x real time); plain software decode as a fallback."""
    tail = (
        f"split=2[a][b];[a]fps={SAMPLE_FPS}[fr];"
        f"[b]fps={MOTION_FPS},scale=160:-2,scdet=threshold=100,"
        "metadata=print:key=lavfi.scd.score[sc]"
    )
    outs = [
        "-map",
        "[fr]",
        "-q:v",
        "4",
        frames_dir / "f%05d.jpg",
        "-map",
        "[sc]",
        "-f",
        "null",
        "-",
    ]
    hw_fmt = "p010le" if ten_bit else "nv12"
    attempts = [
        (
            ["-hwaccel", "videotoolbox", "-hwaccel_output_format", "videotoolbox_vld"],
            f"[0:v]scale_vt=w={w}:h={h},hwdownload,format={hw_fmt},format=yuv420p,{tail}",
        ),
        ([], f"[0:v]scale={w}:{h},format=yuv420p,{tail}"),
    ]
    last: Exception | None = None
    for pre, graph in attempts:
        for old in frames_dir.glob("f*.jpg"):
            old.unlink()
        try:
            r = ffmpeg(
                ["-y", *pre, "-i", path, "-an", "-filter_complex", graph, *outs],
                loglevel="info",
                capture=True,
            )
            return r.stderr
        except FFmpegError as e:
            last = e
    raise RuntimeError(f"çözülemedi: {path}") from last


def _measure(img: Image.Image) -> tuple[float, float, float]:
    from vlogkit.analysis.thumbs import measure

    sharp, _, exposure = measure(img)
    return ImageStat.Stat(img.convert("L")).mean[0], sharp, exposure


def _tiles(img: Image.Image) -> tuple[list[float], list[float]]:
    """Brightness and detail per tile: a body or a hand at the lens changes a region of an
    otherwise identical static shot."""
    from vlogkit.analysis.thumbs import _LAPLACE

    gray = img.convert("L")
    edges = gray.filter(_LAPLACE)
    w, h = gray.size
    lum, sharp = [], []
    for r in range(GRID):
        for c in range(GRID):
            box = (c * w // GRID, r * h // GRID, (c + 1) * w // GRID, (r + 1) * h // GRID)
            lum.append(round(ImageStat.Stat(gray.crop(box)).mean[0], 1))
            sharp.append(round(ImageStat.Stat(edges.crop(box)).stddev[0], 2))
    return lum, sharp


def analyze_clip(path: PathLike, cache_dir: Path, speech: bool = True, lang: str = "tr") -> dict:
    """Per-clip measurements, cached by path + size + mtime (the slow part: decode + Vision)."""
    path = Path(path)
    st = path.stat()
    key = f"{path.stem}-{st.st_size}-{int(st.st_mtime)}-v{CACHE_VERSION}"
    cached = cache_dir / f"{key}.json"
    if cached.exists():
        data = json.loads(cached.read_text())
        if data.get("speech_done") or not speech:
            _prune(cache_dir, path.stem, cached)
            return data
    else:
        data = None
    if data is None:
        dur, w, h, ten_bit = _video_info(path)
        long_side = 480
        sw, sh = (
            (long_side, round(long_side * h / w / 2) * 2)
            if w >= h
            else (round(long_side * w / h / 2) * 2, long_side)
        )
        with tempfile.TemporaryDirectory() as tmp:
            fdir = Path(tmp)
            log = _decode(path, fdir, sw, sh, ten_bit)
            times = [float(x) for x in _FRAME.findall(log)]
            scores = [float(x) for x in _SCORE.findall(log)]
            motion = [s for _, s in zip(times, scores, strict=False)]
            files = sorted(fdir.glob("f*.jpg"))
            seen = {}
            from vlogkit.analysis import vision

            if vision.available():
                seen = vision.read(files)
            samples = []
            for i, f in enumerate(files):
                with Image.open(f) as im:
                    rgb = im.convert("RGB")
                    luma, sharp, exposure = _measure(rgb)
                    tl, ts = _tiles(rgb)
                s = seen.get(str(f))
                tall = max(s.humans, key=lambda b: b[3], default=None) if s else None
                face = s.face_height if s else 0.0
                edge = bool(s) and any(
                    b[3] > 0.3
                    and (b[0] < 0.01 or b[1] < 0.01 or b[0] + b[2] > 0.99 or b[1] + b[3] > 0.99)
                    for b in s.faces
                )
                samples.append(
                    Sample(
                        round(i / SAMPLE_FPS, 3),
                        round(luma, 1),
                        round(sharp, 2),
                        round(exposure, 3),
                        round(face, 3),
                        edge,
                        len(s.humans) if s else 0,
                        [(a, round(c, 3)) for a, c in s.labels] if s else [],
                        round(s.aesthetics, 3) if s and s.aesthetics is not None else None,
                        round(tall[3], 3) if tall else 0.0,
                        round(tall[2], 3) if tall else 0.0,
                        tl,
                        ts,
                    )
                )
            thumbs_dir = cache_dir / key
            thumbs_dir.mkdir(parents=True, exist_ok=True)
            for f in files:  # keep small thumbnails for the sheets (not the analysis frames)
                with Image.open(f) as im:
                    im.thumbnail((240, 240))
                    im.save(thumbs_dir / f.name, quality=80)
        data = {
            "path": str(path),
            "duration": dur,
            "width": w,
            "height": h,
            "motion": [round(m, 2) for m in motion],
            "samples": [asdict(s) for s in samples],
            "thumbs": str(thumbs_dir),
            "speech": [],
            "speech_done": False,
        }
        same = f"{path.stem}-{st.st_size}-{int(st.st_mtime)}-"
        for older in cache_dir.glob(f"{same}v*.json"):  # words don't depend on the picture
            prev = json.loads(older.read_text())
            if older != cached and prev.get("speech_done"):
                data["speech"], data["speech_done"] = prev["speech"], True
                break
    if speech and not data.get("speech_done"):
        data["speech"] = _speech(path, lang)
        data["speech_done"] = True
    cached.write_text(json.dumps(data))
    _prune(cache_dir, path.stem, cached)
    return data


def _prune(cache_dir: Path, stem: str, keep: Path) -> None:
    """Drop older analyses of the same clip (other versions, or the file changed since)."""
    for older in cache_dir.glob(f"{stem}-*.json"):
        if older == keep:
            continue
        with contextlib.suppress(OSError, ValueError):
            thumbs = Path(json.loads(older.read_text()).get("thumbs", ""))
            if thumbs.is_dir() and thumbs != keep.with_suffix(""):
                shutil.rmtree(thumbs, ignore_errors=True)
        older.unlink(missing_ok=True)
    for d in cache_dir.glob(f"{stem}-*"):  # thumbnails of an interrupted run
        if d.is_dir() and d != keep.with_suffix(""):
            shutil.rmtree(d, ignore_errors=True)


def _speech(path: Path, lang: str) -> list[list]:
    from vlogkit.analysis.transcribe import transcribe

    try:
        return [[s.start, s.end, s.text] for s in transcribe(path, lang) if not s.suspicious]
    except Exception:  # no whisper / no audio: the log still works without words
        return []


# --------------------------------------------------------------------------- chunks
def cuts_from(motion: list[float], threshold: float = 8.0, min_gap: float = 1.0) -> list[float]:
    out: list[float] = []
    for i, s in enumerate(motion):
        t = i / MOTION_FPS
        if s >= threshold and (not out or t - out[-1] >= min_gap):
            out.append(round(t, 2))
    return out


def chunk_spans(
    duration: float, cuts: list[float], target: float = 4.0, min_len: float = 1.0
) -> list[tuple[float, float]]:
    """Scene cuts, then long spans split into ~target pieces; slivers merge into a neighbour."""
    marks = [0.0, *[c for c in cuts if min_len <= c <= duration - min_len], duration]
    spans: list[tuple[float, float]] = []
    for a, b in pairwise(marks):
        n = max(1, round((b - a) / target))
        spans += [(a + (b - a) * k / n, a + (b - a) * (k + 1) / n) for k in range(n)]
    merged: list[tuple[float, float]] = []
    for a, b in spans:
        if merged and (b - a < min_len or merged[-1][1] - merged[-1][0] < min_len):
            merged[-1] = (merged[-1][0], b)
        else:
            merged.append((a, b))
    return [(round(a, 2), round(b, 2)) for a, b in merged]


def top_labels(samples: list[Sample], n: int = 3) -> list[str]:
    score: Counter = Counter()
    for s in samples:
        for name, conf in s.labels:
            if name not in LABEL_NOISE:
                score[LABELS_TR.get(name, name.replace("_", " "))] += conf
    return [name for name, _ in score.most_common(n)]  # translations merge ("people", "adult")


# --------------------------------------------------------------------------- sheets
def _fmt(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m}:{s:02d}"


def make_sheets(
    name: str, thumbs: list[tuple[float, Path]], out_dir: Path, per_sheet: int = 48, cols: int = 8
) -> list[Path]:
    """Timestamped grids covering a whole clip (several sheets for long takes)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.truetype(str(FONTS_DIR / "Montserrat-ExtraBold.ttf"), 20)
    sheets = []
    pages = [thumbs[i : i + per_sheet] for i in range(0, len(thumbs), per_sheet)] or [[]]
    for p, page in enumerate(pages, 1):
        if not page:
            continue
        with Image.open(page[0][1]) as first:
            tw, th = first.size
        rows = math.ceil(len(page) / cols)
        sheet = Image.new("RGB", (cols * (tw + 4) + 4, rows * (th + 4) + 4), (20, 20, 20))
        draw = ImageDraw.Draw(sheet)
        for i, (t, f) in enumerate(page):
            x, y = 4 + (i % cols) * (tw + 4), 4 + (i // cols) * (th + 4)
            with Image.open(f) as im:
                sheet.paste(im.convert("RGB"), (x, y))
            label = _fmt(t)
            box = draw.textbbox((x + 4, y + 3), label, font=font)
            draw.rectangle((box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2), fill=(0, 0, 0))
            draw.text((x + 4, y + 3), label, font=font, fill=(255, 214, 0))
        path = out_dir / f"{Path(name).stem}_{p}.jpg"
        sheet.save(path, quality=85)
        sheets.append(path)
    return sheets


def sheet_step(duration: float) -> float:
    """Seconds between thumbnails: 1 s for short clips, 2 s up to 5 min, then 4 s."""
    return 1.0 if duration <= 60 else 2.0 if duration <= 300 else 4.0


# --------------------------------------------------------------------------- flags
# Tuned on DJI Osmo raw clips (28-09-vlog): see tests/test_footage.py for the rules in isolation.
CLOSE_ABS = 0.5  # a face taller than half the frame is at the lens, whatever the clip
CLOSE_REL = 1.8  # ... or this much bigger than the clip's usual face
CLOSE_MIN = 0.24  # ... and at least this tall (a small face growing a bit is not a lean-in)
DARK_ABS = 8.0  # mean luma: lens covered / in a pocket, even at night
DARK_REL = 0.35  # ... or this much darker than the clip usually is (a night drive is not "dark")
BLUR = 0.4  # sharpness below this share of the clip's median
SPIKE = 8.0  # frame difference of a jolt (someone grabs the camera)
SHAKE = 9.0  # mean frame difference of a chunk with the camera swinging around
SETTLE = 1.0  # seconds of calm picture that end a take's head / start its tail
MAX_HEAD = 25.0  # placing the camera and walking away can take a while; never longer than this
CHAIN_GAP = 1.5  # the head / tail runs on through close moments this near to it
EDGE = 3.0  # a close moment touching the first / last seconds is the record button being pressed
MAX_BURST = 8.0  # a mid-take handling burst (adjusting / picking up the camera) is short
BURST_PAD = 1.0  # a burst reaches this far into the unsettled picture around it
STATIC = 1.0  # median frame difference of a tripod / propped-up camera
OCCLUDED_TILES = 3  # tiles (of 16) that must change for "something is in front of the lens"
BLOCKING = ("kurulum", "karanlık", "bulanık")  # not used unless kept on purpose
SOFT_HANDLING = "kurulum?"  # only the local model saw camera handling: look before using it


@dataclass
class Measured:
    """A sample plus the clip-relative judgements the flags use."""

    t: float
    close: bool
    dark: bool
    blurry: bool
    spike: bool
    occluded: bool = False  # static shot: a large region suddenly blurry / different (at the lens)
    at_lens: bool = False  # a face so big or cut off that someone must be touching the camera

    @property
    def touched(self) -> bool:
        """Signs of hands on the camera, beyond a person merely being close."""
        return self.dark or self.occluded or self.at_lens or self.spike or self.blurry

    @property
    def anchor(self) -> bool:
        """Evidence of someone at the camera, not just a busy picture."""
        return self.close or self.dark or self.occluded

    @property
    def unsettled(self) -> bool:
        return self.anchor or self.blurry or self.spike


def occluded(s: Sample, med_luma: list[float], med_sharp: list[float]) -> bool:
    """Part of a static background hidden: several tiles lost their usual detail and changed
    brightness while at least half of the frame still shows the usual background. (If the
    whole picture changed, the camera moved: that is a new scene, not something at the lens.)"""
    if not s.tile_luma or len(s.tile_luma) != len(med_luma):
        return False
    hit = match = 0
    for lum, shp, ml, ms in zip(s.tile_luma, s.tile_sharp, med_luma, med_sharp, strict=True):
        diff = max(8.0, 0.18 * ml)  # a night scene changes by less in absolute terms
        if ms > 0 and (shp < 0.25 * ms or (shp < 0.45 * ms and abs(lum - ml) > diff)):
            hit += 1
        elif abs(lum - ml) <= diff and ms > 0 and 0.5 * ms <= shp <= 2 * ms:
            match += 1
    return hit >= OCCLUDED_TILES and match >= len(med_luma) // 2


def _low(values: list[float], q: float = 0.3) -> float:
    v = sorted(values)
    return v[min(len(v) - 1, int(q * len(v)))]


def judge(samples: list[Sample], motion: list[float]) -> list[Measured]:
    # "usual" = the lower third: in a propped-up shot the creator hanging around the camera
    # must not become the norm; in a selfie the face is big all the time, so it still is
    faces = [s.face for s in samples if s.face > 0]
    usual = _low(faces) if len(faces) >= max(3, len(samples) // 5) else 0.14
    bodies = [s.human for s in samples if s.human > 0]
    usual_body = _low(bodies) if len(bodies) >= max(3, len(samples) // 5) else 0.5
    lumas = [s.luma for s in samples]
    dark = max(DARK_ABS, DARK_REL * statistics.median(lumas)) if lumas else DARK_ABS
    sharp = statistics.median([s.sharp for s in samples]) if samples else 1.0
    static = bool(motion) and statistics.median(motion) < STATIC
    tiled = [s for s in samples if s.tile_luma]
    med_luma = (
        [statistics.median(v) for v in zip(*(s.tile_luma for s in tiled), strict=True)]
        if tiled
        else []
    )
    med_sharp = (
        [statistics.median(v) for v in zip(*(s.tile_sharp for s in tiled), strict=True)]
        if tiled
        else []
    )
    out = []
    for s in samples:
        a, b = int((s.t - 0.25) * MOTION_FPS), int((s.t + 0.25) * MOTION_FPS) + 1
        peak = max(motion[max(0, a) : b], default=0.0)
        close = (
            s.face >= CLOSE_ABS
            or (s.face >= CLOSE_MIN and s.face >= CLOSE_REL * usual)
            or (s.face_edge and s.face >= 0.3)
            # a body filling the frame height, where bodies usually don't (a desk scene does)
            or (s.human >= 0.95 and s.human_w >= 0.3 and usual_body < 0.8)
        )
        at_lens = s.face >= CLOSE_ABS or (s.face_edge and s.face >= 0.3)
        out.append(
            Measured(
                s.t,
                close,
                s.luma < dark,
                sharp > 0 and s.sharp < BLUR * sharp,
                peak >= SPIKE,
                static and occluded(s, med_luma, med_sharp),
                at_lens,
            )
        )
    return out


def _settled_run(ms: list[Measured], i: int, step: int) -> bool:
    n = max(1, int(SETTLE * SAMPLE_FPS))
    run = ms[i : i + n] if step > 0 else ms[max(0, i - n + 1) : i + 1]
    return len(run) == n and not any(m.unsettled for m in run)


def handling(ms: list[Measured], duration: float) -> list[tuple[float, float]]:
    """Camera-handling ranges: the head and tail until the picture settles, plus short bursts
    of a face at the lens / covered lens in between."""
    if not ms:
        return []
    out: list[tuple[float, float]] = []
    chain = int(CHAIN_GAP * SAMPLE_FPS)
    head = next((i for i in range(len(ms)) if _settled_run(ms, i, +1)), len(ms))
    if head > 0:
        # walking away from the camera just placed: close moments right after the head belong to it
        while True:
            nxt = next(
                (x for x in range(head, min(len(ms), head + chain + 1)) if ms[x].anchor), None
            )
            if nxt is None:
                break
            head = next((i for i in range(nxt, len(ms)) if _settled_run(ms, i, +1)), len(ms))
        out.append((0.0, min(ms[head].t if head < len(ms) else duration, MAX_HEAD)))
    tail = next((i for i in range(len(ms) - 1, -1, -1) if _settled_run(ms, i, -1)), -1)
    if tail < len(ms) - 1:
        while tail >= 0:  # ... and walking up to it to stop the recording
            prv = next(
                (x for x in range(tail, max(-1, tail - chain - 1), -1) if ms[x].anchor), None
            )
            if prv is None:
                break
            tail = next((i for i in range(prv, -1, -1) if _settled_run(ms, i, -1)), -1)
        start = ms[tail + 1].t if tail >= 0 else 0.0
        out.append((max(start, duration - MAX_HEAD), duration))
    # mid-take bursts: runs of evidence (close face / covered lens / something at the lens),
    # gaps up to 1 s bridged, reaching BURST_PAD into the unsettled picture on both sides
    step = 1 / SAMPLE_FPS
    gap, pad = int(1.0 * SAMPLE_FPS), int(BURST_PAD * SAMPLE_FPS)
    i = 0
    while i < len(ms):
        if not ms[i].anchor:
            i += 1
            continue
        j = i
        while True:
            nxt = next((x for x in range(j + 1, min(len(ms), j + gap + 2)) if ms[x].anchor), None)
            if nxt is None:
                break
            j = nxt
        k, e = i, j
        while k - 1 >= 0 and i - (k - 1) <= pad and ms[k - 1].unsettled:
            k -= 1
        while e + 1 < len(ms) and (e + 1) - j <= pad and ms[e + 1].unsettled:
            e += 1
        a, b = ms[k].t, min(duration, ms[e].t + step)
        # only with hands on the camera: a selfie brought closer or someone next to the lens
        # is content ("çok yakın"), not handling. At the very start / end of a take a close
        # moment *is* the hand on the record button.
        edge = a <= EDGE or b >= duration - EDGE
        if b - a <= MAX_BURST and (edge or any(m.touched for m in ms[k : e + 1])):
            out.append((a, b))
        i = j + 1
    return _merge_spans(out)


def _merge_spans(spans: list[tuple[float, float]], gap: float = 0.5) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for a, b in sorted(spans):
        if merged and a <= merged[-1][1] + gap:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))
    return [(round(a, 2), round(b, 2)) for a, b in merged]


def chunk_flags(ms: list[Measured], mean_motion: float, in_handling: bool) -> list[str]:
    if in_handling:
        return ["kurulum"]
    flags = []
    half = max(1, len(ms) // 2 + len(ms) % 2)
    if sum(m.close or m.occluded for m in ms) >= half:
        flags.append("çok yakın")
    if sum(m.dark for m in ms) >= half:
        flags.append("karanlık")
    if sum(m.blurry for m in ms) >= half:
        flags.append("bulanık")
    if mean_motion >= SHAKE:
        flags.append("sarsıntı")
    return flags


# --------------------------------------------------------------------------- the log
def build_clip(data: dict, out_dir: Path, target: float = 4.0) -> Clip:
    path = Path(data["path"])
    samples = [Sample(**{**s, "labels": [tuple(x) for x in s["labels"]]}) for s in data["samples"]]
    motion, dur = data["motion"], data["duration"]
    ms = judge(samples, motion)
    hand = handling(ms, dur)
    cuts = cuts_from(motion)
    marks = sorted({*cuts, *(x for span in hand for x in span)})
    spans = chunk_spans(dur, marks, target)
    sharp_med = statistics.median([s.sharp for s in samples]) if samples else 1.0
    chunks = []
    for a, b in spans:
        idx = (
            [i for i, s in enumerate(samples) if a <= s.t < b]
            or [min(range(len(samples)), key=lambda i: abs(samples[i].t - a))]
            if samples
            else []
        )
        ss = [samples[i] for i in idx]
        mseg = motion[int(a * MOTION_FPS) : max(int(a * MOTION_FPS) + 1, int(b * MOTION_FPS))]
        mean_m = sum(mseg) / len(mseg) if mseg else 0.0
        in_hand = any(ha <= (a + b) / 2 < hb for ha, hb in hand)
        aes = [s.aesthetics for s in ss if s.aesthetics is not None]
        words = " ".join(t for s0, s1, t in data.get("speech", []) if s0 < b and s1 > a)
        chunks.append(
            Chunk(
                clip=path.name,
                t0=a,
                t1=b,
                labels=top_labels(ss),
                face=round(max((s.face for s in ss), default=0.0), 2),
                motion=round(mean_m, 1),
                sharp=round(statistics.median([s.sharp for s in ss]) / sharp_med, 2)
                if ss and sharp_med
                else 1.0,
                luma=round(statistics.fmean(s.luma for s in ss), 1) if ss else 0.0,
                aesthetics=round(statistics.fmean(aes), 2) if aes else None,
                speech=words.strip(),
                flags=chunk_flags([ms[i] for i in idx], mean_m, in_hand),
            )
        )
    step = sheet_step(dur)
    every = max(1, int(step * SAMPLE_FPS))
    thumbs = sorted(Path(data["thumbs"]).glob("f*.jpg"))
    picks = [(i / SAMPLE_FPS, p) for i, p in enumerate(thumbs) if i % every == 0]
    sheets = make_sheets(path.name, picks, out_dir / "sheets")
    when = recorded_at(path)
    return Clip(
        str(path),
        path.name,
        when.isoformat(timespec="seconds") if when else None,
        dur,
        data["width"],
        data["height"],
        cuts,
        chunks,
        [str(s) for s in sheets],
    )


def merge_notes(new: Log, old: Log) -> Log:
    """Keep what Claude / the user wrote (desc, beat, keep) for chunks that still exist."""
    notes = {
        (c.clip, round(c.t0, 1)): c for c in old.chunks if c.desc or c.beat or c.keep is not None
    }
    for c in new.chunks:
        o = notes.get((c.clip, round(c.t0, 1)))
        if o:
            c.desc, c.beat, c.keep = o.desc, o.beat, o.keep
    return new


def apply_local(clip: Clip, results: dict) -> None:
    """Put the local model's answers on the chunks; its camera-handling call becomes a soft flag
    where the heuristics saw nothing (the two disagree sometimes; Claude looks at the sheet)."""
    for k in clip.chunks:
        r = results.get((k.t0, k.t1))
        if not r:
            continue
        k.local = {
            x: r[x] for x in ("action", "setting", "camera_handling", "usefulness") if x in r
        }
        if r.get("camera_handling") and "kurulum" not in k.flags and SOFT_HANDLING not in k.flags:
            k.flags.append(SOFT_HANDLING)


def _local_pass(result: Log, out_dir: Path, vlm: bool, progress) -> None:
    """Fill `local` from the cache, and with vlm=True run the model on what is missing.

    Saved after every clip, so an interrupted run keeps its work and resumes from the cache."""
    from vlogkit.analysis import localvlm

    cache = out_dir / "vlm"
    todo = []
    for c in result.clips:
        spans = [(k.t0, k.t1) for k in c.chunks]
        have = localvlm.cached(c.path, spans, cache) if cache.exists() else {}
        apply_local(c, have)
        if len(have) < len(spans):
            todo.append((c, spans, len(spans) - len(have)))
    if not vlm or not todo:
        return
    if not localvlm.available():
        raise RuntimeError("yerel video modeli kurulu değil: uv run vlogkit extras install vlm")
    eta = localvlm.Eta(sum(n for _, _, n in todo))
    for c, spans, _ in todo:

        def tick(done: int, total: int, name=c.name) -> None:
            msg = eta.step()
            if progress and (done == total or done % 10 == 0):
                progress(f"model: {name} {done}/{total} · toplam {msg}")

        apply_local(c, localvlm.describe(c.path, spans, cache, progress=tick))
        result.save(out_dir / "log.json")
        (out_dir / "log.md").write_text(markdown(result, out_dir))


def log(
    paths_or_folder: PathLike | list[PathLike],
    out_dir: PathLike,
    speech: bool = True,
    lang: str = "tr",
    workers: int = 2,
    progress=None,
    vlm: bool = False,
) -> Log:
    """Analyse every clip (cached), write log.json, log.md and the sheets into `out_dir`.

    vlm=True also runs the local video model on every chunk (slow: ~2-3 s per chunk; cached and
    resumable). Answers already in the cache are always filled in."""
    from concurrent.futures import ThreadPoolExecutor

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clips = clips_in(paths_or_folder)

    def one(p: Path) -> dict:
        d = analyze_clip(p, out_dir / "cache", speech, lang)
        if progress:
            progress(p.name)
        return d

    with ThreadPoolExecutor(max(1, workers)) as ex:  # the media engine decodes 2 streams at once
        datas = list(ex.map(one, clips))
    folder = str(Path(paths_or_folder)) if isinstance(paths_or_folder, (str, Path)) else ""
    result = Log(folder, [build_clip(d, out_dir) for d in datas])
    old = out_dir / "log.json"
    if old.exists():
        result = merge_notes(result, Log.load(old))
    result.save(out_dir / "log.json")
    (out_dir / "log.md").write_text(markdown(result, out_dir))
    _local_pass(result, out_dir, vlm, progress)
    result.save(out_dir / "log.json")
    (out_dir / "log.md").write_text(markdown(result, out_dir))
    return result


def selects(lg: Log, min_len: float = 1.0) -> list[tuple[str, float, float]]:
    """Usable ranges per clip: unflagged (or kept on purpose) chunks, neighbours merged."""
    out: list[tuple[str, float, float]] = []
    for c in lg.chunks:
        if not c.usable:
            continue
        if out and out[-1][0] == c.clip and abs(out[-1][2] - c.t0) < 0.05:
            out[-1] = (c.clip, out[-1][1], c.t1)
        else:
            out.append((c.clip, c.t0, c.t1))
    return [s for s in out if s[2] - s[1] >= min_len]


def _t(x: float) -> str:
    m, s = divmod(x, 60)
    return f"{int(m)}:{s:04.1f}"


def _rows(chunks: list[Chunk]) -> list[tuple[Chunk, Chunk]]:
    """Table rows: consecutive quiet chunks (same labels, no flags, words or notes) share a row."""
    rows: list[list[Chunk]] = []
    for k in chunks:
        quiet = not (k.flags or k.speech or k.desc or k.beat or k.keep is not None)
        last = rows[-1] if rows else None
        if (
            quiet
            and last
            and not (last[0].flags or last[0].speech or last[0].desc or last[0].beat)
            and last[0].keep is None
            and set(last[0].labels[:2]) == set(k.labels[:2])
            and _said(last[0]) == _said(k)
        ):
            last.append(k)
        else:
            rows.append([k])
    return [(r[0], r[-1]) for r in rows]


def _said(k: Chunk) -> str:
    """The local model's line for the table ("" without it)."""
    if not k.local:
        return ""
    a = (k.local.get("action") or "").strip().rstrip(".")
    return (a[:90] + "…" if len(a) > 90 else a) + (
        " [kamera]" if k.local.get("camera_handling") else ""
    )


def markdown(lg: Log, out_dir: Path | None = None) -> str:
    total = sum(c.duration for c in lg.clips)
    flagged = sum(k.t1 - k.t0 for k in lg.chunks if k.flags)
    lines = [
        f"# Ham çekim kaydı: {lg.folder or 'klipler'}",
        "",
        f"{len(lg.clips)} klip, {total / 60:.1f} dk, {len(lg.chunks)} parça; "
        f"{flagged / 60:.1f} dk bayraklı.",
        "",
        "Bayraklar: `kurulum` kamerayı kurma/kapama/ayarlama (kullanma), `çok yakın` lense yaklaşan "
        "yüz, `karanlık`, `bulanık`, `sarsıntı`. Her klibin sayfasına bak, log.json'da her parçaya "
        "`desc` (ne oluyor), `beat` (hikâyedeki yeri) ve `keep` yaz; plan beat'lerden kurulur.",
        "",
    ]
    if any(k.local for k in lg.chunks):
        lines += [
            "`model`: yerel video modelinin (4 kare/sn izledi) tek cümlelik gözlemi, İngilizce. "
            "Aday bulmak için kullan, sayfayla doğrula: bazen yönü karıştırır (giriyor/çıkıyor). "
            f"`{SOFT_HANDLING}`: sadece model kamera kullanımı gördü, bak ve karar ver.",
            "",
        ]
    for n, c in enumerate(lg.clips, 1):
        when = c.start[11:16] if c.start else "?"
        sheets = ", ".join(Path(s).name if out_dir else s for s in c.sheets)
        lines += [
            f"## {n}. {c.name} · {when} · {_t(c.duration)} · {c.width}x{c.height}",
            f"Sayfa: {sheets}",
            "",
            "| zaman | görünen | model | yüz | hareket | konuşma | bayrak | not |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for k0, k1 in _rows(c.chunks):
            words = (k0.speech[:70] + "…") if len(k0.speech) > 70 else k0.speech
            note = " · ".join(x for x in (k0.beat, k0.desc) if x)
            if k0.keep is False:
                note = ("✗ " + note).strip()
            lines.append(
                f"| {_t(k0.t0)}-{_t(k1.t1)} | {', '.join(k0.labels)} | {_said(k0)} | "
                f"{k0.face:.2f} | {k0.motion:g} | {words} | {', '.join(k0.flags)} | {note} |"
            )
        lines.append("")
    return "\n".join(lines)
