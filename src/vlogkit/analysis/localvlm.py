"""A local video-language model (Qwen3.5-9B, 4-bit MLX) that watches raw footage chunk by chunk.

Why: Claude reads contact sheets (a frame every 1-4 s) and cannot afford to look at every chunk
of an hour of footage. The local model watches each ~4 s chunk at 4 fps, so it sees motion
("opens the door and walks out", "puts on shoes"), and it can say when someone handles the
camera. It proposes; Claude decides (it can confuse direction or invent details).

How:
- mlx-vlm lives in its own `uv tool` environment (`vlogkit extras install vlm`), so vlogkit's
  venv stays light. `tools/vlm/worker.py` runs inside that environment and loads the model
  once per batch.
- Each clip is cut into low-res 4 fps pieces in one decode pass (media engine on macOS).
- Raw answers are cached per (clip size + mtime, t0, t1, model, prompt version), one JSON line
  at a time, so an interrupted run resumes where it stopped (and parser fixes reach old answers).
"""

from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import re
import subprocess
import tempfile
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path

from vlogkit.config import BUILD_DIR, REPO_ROOT
from vlogkit.ff import FFmpegError, PathLike, ffmpeg, ffprobe_json


@dataclass(frozen=True)
class Choice:
    repo: str  # Hugging Face id (MLX, 4-bit)
    label: str
    size: float  # bytes to download
    ram: int  # GB of memory it needs with the clips; below that the Mac swaps or kills it
    comfy: int  # GB from which it runs beside the studio and a browser: the one to recommend
    note: str


# The same model family in three sizes (same worker, same prompts); the studio installs and picks
# one in its settings. Bigger watches better: the 2B sees what is there but confuses more.
CHOICES = {
    "qwen3.5-2b": Choice("mlx-community/Qwen3.5-2B-MLX-4bit", "Qwen3.5 2B", 1.75e9, 8, 8, "hafif; kaba"),
    "qwen3.5-4b": Choice("mlx-community/Qwen3.5-4B-MLX-4bit", "Qwen3.5 4B", 3.06e9, 16, 16, "dengeli"),
    "qwen3.5-9b": Choice("mlx-community/Qwen3.5-9B-MLX-4bit", "Qwen3.5 9B", 5.98e9, 16, 24, "en iyisi"),
}  # fmt: skip
SETTINGS = BUILD_DIR / "vlm.json"  # {"model": choice id | "none"}
WORKER = REPO_ROOT / "tools" / "vlm" / "worker.py"
CACHE_DIR = BUILD_DIR / "vlm"
FPS = 4.0  # 2 fps confused directions (in/out of a door, shoes on/off); 4 fps got them right
LONG_SIDE = 448
PROMPT_VERSION = 2

DESCRIBE_PROMPT = (
    "Watch this {dur:.0f}-second clip from a vlogger's raw footage carefully, frame by frame, in "
    "order. First say what the person is doing at the start, then at the end, and the direction "
    "of movement (toward/away from the camera, into/out of a door, putting on/taking off). Then "
    "reply with JSON only: "
    '{{"start": "...", "end": "...", "action": "one short English sentence", '
    '"setting": "a few words", "camera_handling": true or false (someone setting up, adjusting, '
    "picking up or putting down the camera, or leaning into or covering the lens), "
    '"usefulness": 0-3 for a vlog edit, "people": number}}'
)


# --------------------------------------------------------------------------- environment
def tool_python() -> Path | None:
    """The python of the mlx-vlm uv tool environment, if installed."""
    env = os.environ.get("VLOGKIT_VLM_PYTHON")
    if env:
        return Path(env)
    try:
        r = subprocess.run(["uv", "tool", "dir"], capture_output=True, text=True, timeout=20)
        base = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    except (OSError, subprocess.TimeoutExpired):
        base = None
    base = base or Path.home() / ".local" / "share" / "uv" / "tools"
    py = base / "mlx-vlm" / "bin" / "python"
    return py if py.exists() else None


def _hf_hub() -> Path:
    home = os.environ.get("HF_HUB_CACHE") or os.environ.get("HF_HOME")
    if home:
        p = Path(home)
        return p if p.name == "hub" or os.environ.get("HF_HUB_CACHE") else p / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def model_dir(repo: str) -> Path:
    return _hf_hub() / f"models--{repo.replace('/', '--')}"


def _real_files(model_root: Path) -> set[Path]:
    """The files a cached model really uses: its blobs can be links into a shared store."""
    out = set()
    for p in model_root.rglob("*"):
        try:
            real = p.resolve()
        except OSError:
            continue
        if real.is_file():
            out.add(real)
    return out


def model_size(repo: str) -> int:
    return sum(f.stat().st_size for f in _real_files(model_dir(repo)) if f.exists())


def remove_model_files(repo: str) -> None:
    """Delete a cached model and the shared-store files only it uses (another model's are kept)."""
    import shutil

    root = model_dir(repo)
    if not root.exists():
        return
    others = set()
    for d in _hf_hub().glob("models--*"):
        if d != root:
            others |= _real_files(d)
    for f in _real_files(root) - others:
        if root not in f.parents:  # in the shared store
            f.unlink(missing_ok=True)
    shutil.rmtree(root, ignore_errors=True)


def model_cached(model: str | None = None) -> bool:
    model = model or current()
    if not model:
        return False
    snaps = model_dir(model) / "snapshots"
    return any(
        (s / "config.json").exists() and any(s.glob("*.safetensors"))
        for s in (snaps.iterdir() if snaps.is_dir() else [])
    )


def memory_gb() -> int:
    """This Mac's memory in GB; 0 when it cannot be read (then no model is held back)."""
    try:
        r = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True)
        return round(int(r.stdout.strip()) / 2**30)
    except (OSError, ValueError):
        return 0


def unfit(key: str, mem: int | None = None) -> str | None:
    """Why this Mac cannot run the choice (too little memory), or None."""
    c = CHOICES[key]
    mem = memory_gb() if mem is None else mem
    return f"en az {c.ram} GB bellek ister" if mem and mem < c.ram else None


def recommended(mem: int | None = None) -> str | None:
    """The biggest choice this Mac runs comfortably (None when its memory is unknown)."""
    mem = memory_gb() if mem is None else mem
    return next((k for k in reversed(CHOICES) if mem >= CHOICES[k].comfy), None) if mem else None


def pick() -> str | None:
    """What the user picked in the studio: a choice id, "none", or None when never asked."""
    try:
        return json.loads(SETTINGS.read_text()).get("model")
    except (OSError, ValueError, AttributeError):
        return None


def chosen() -> str | None:
    """The choice in use; without a pick the best one already downloaded (so an install made
    before the choices existed keeps its 9B). "none" = do not use a local model."""
    pick_ = pick()
    if pick_ == "none":
        return None
    if pick_ in CHOICES:
        return pick_
    return next((k for k in reversed(CHOICES) if model_cached(CHOICES[k].repo)), None)


def choose(pick: str | None) -> None:
    if pick is not None and pick not in CHOICES:
        raise ValueError(f"bilinmeyen model: {pick}")
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps({"model": pick or "none"}))


def current() -> str | None:
    """The Hugging Face id in use (VLOGKIT_VLM_MODEL overrides the pick), or None."""
    env = os.environ.get("VLOGKIT_VLM_MODEL")
    if env:
        return env
    pick = chosen()
    return CHOICES[pick].repo if pick else None


def available() -> bool:
    return tool_python() is not None and model_cached() and WORKER.exists()


def model_id() -> str | None:
    return current()


# --------------------------------------------------------------------------- parsing
def parse_json(text: str) -> dict | None:
    """The first JSON object in a model answer (code fences, prose before it, trailing commas,
    or a Python-literal dict)."""
    s = re.sub(r"```(?:json)?", "", text or "")
    start = s.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(s)):
            if s[i] == "{":
                depth += 1
            elif s[i] == "}":
                depth -= 1
                if depth == 0:
                    blob = re.sub(r",\s*([}\]])", r"\1", s[start : i + 1])
                    try:
                        return json.loads(blob)
                    except ValueError:
                        pass
                    try:  # the model sometimes writes a Python dict ('...', False)
                        d = ast.literal_eval(blob)
                        if isinstance(d, dict):
                            return d
                    except (ValueError, SyntaxError):
                        pass
                    break
        start = s.find("{", start + 1)
    return None


def normalize(d: dict | None, raw: str = "") -> dict:
    """Fixed keys, sane types: action, start, end, setting, camera_handling, usefulness, people."""
    d = d or {}
    action = str(d.get("action") or "").strip()
    if not action and raw:  # no JSON: keep the first sentence of what it said
        action = re.split(r"(?<=[.!?])\s", raw.strip())[0][:200]
    ch = d.get("camera_handling")
    if isinstance(ch, str):
        ch = ch.strip().lower() in ("true", "yes", "1")
    try:
        use = max(0, min(3, round(float(d.get("usefulness", 1)))))
    except (TypeError, ValueError):
        use = 1
    try:
        people = max(0, int(d.get("people", 0)))
    except (TypeError, ValueError):
        people = 0
    return {
        "action": action,
        "start": str(d.get("start") or "").strip(),
        "end": str(d.get("end") or "").strip(),
        "setting": str(d.get("setting") or "").strip(),
        "camera_handling": bool(ch),
        "usefulness": use,
        "people": people,
    }


# --------------------------------------------------------------------------- cache
def clip_key(path: PathLike) -> str:
    st = Path(path).stat()
    return hashlib.sha1(f"{Path(path).name}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[
        :16
    ]


def _span_key(t0: float, t1: float, model: str | None = None) -> str:
    return f"{t0:.2f}-{t1:.2f}|{model or current()}|p{PROMPT_VERSION}"


def _cache_file(path: PathLike, cache_dir: Path) -> Path:
    return cache_dir / f"{Path(path).stem}-{clip_key(path)}.jsonl"


def cached(
    path: PathLike, spans: Sequence[tuple[float, float]], cache_dir: Path = CACHE_DIR
) -> dict:
    """{(t0, t1): result} already known for this clip (no model needed)."""
    f = _cache_file(path, cache_dir)
    if not f.exists():
        return {}
    known = {}
    for line in f.read_text().splitlines():
        try:
            d = json.loads(line)
        except ValueError:
            continue  # a line cut by an interruption
        # the raw answer is kept: parser fixes apply to old answers too
        known[d["key"]] = normalize(parse_json(d["raw"]), d["raw"]) if "raw" in d else d["result"]
    model = current()
    if model:
        return {(t0, t1): known[k] for t0, t1 in spans if (k := _span_key(t0, t1, model)) in known}
    # no model in use ("Yok"): answers any model gave earlier still fill the log
    out = {}
    for key, result in known.items():
        span, _, rest = key.partition("|")
        if rest.endswith(f"|p{PROMPT_VERSION}"):
            a, _, b = span.partition("-")
            with contextlib.suppress(ValueError):
                out.setdefault((round(float(a), 2), round(float(b), 2)), result)
    return {(t0, t1): out[k] for t0, t1 in spans if (k := (round(t0, 2), round(t1, 2))) in out}


# --------------------------------------------------------------------------- cutting
def _scale() -> str:
    return f"scale='if(gte(iw,ih),{LONG_SIDE},-2)':'if(gte(iw,ih),-2,{LONG_SIDE})':flags=bicubic"


def cut_pieces(src: PathLike, spans: Sequence[tuple[float, float]], out_dir: Path) -> list[Path]:
    """Low-res FPS pieces for contiguous spans, in ONE decode pass (segment muxer). Falls back
    to one cut per span if the spans are not contiguous or the segmenter disagrees."""
    out_dir.mkdir(parents=True, exist_ok=True)
    spans = sorted(spans)
    contiguous = all(abs(b[0] - a[1]) < 0.05 for a, b in pairwise(spans))
    enc = ["-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p"]
    if contiguous and len(spans) > 1:
        t0, t_end = spans[0][0], spans[-1][1]
        bounds = ",".join(f"{b[0] - t0:.3f}" for b in spans[1:])
        for pre in (["-hwaccel", "videotoolbox"], []):
            for old in out_dir.glob("seg_*.mp4"):
                old.unlink()
            try:
                ffmpeg(["-y", *pre, "-ss", f"{t0:.3f}", "-t", f"{t_end - t0:.3f}", "-i", src,
                        "-vf", f"fps={FPS},{_scale()}", *enc, "-force_key_frames", bounds,
                        "-f", "segment", "-segment_times", bounds, "-reset_timestamps", "1",
                        out_dir / "seg_%05d.mp4"])  # fmt: skip
            except FFmpegError:
                continue
            pieces = sorted(out_dir.glob("seg_*.mp4"))
            if len(pieces) == len(spans):
                return pieces
    pieces = []
    for i, (a, b) in enumerate(spans):
        out = out_dir / f"one_{i:05d}.mp4"
        ffmpeg(["-y", "-ss", f"{a:.3f}", "-t", f"{b - a:.3f}", "-i", src,
                "-vf", f"fps={FPS},{_scale()}", *enc, out])  # fmt: skip
        pieces.append(out)
    return pieces


# --------------------------------------------------------------------------- running
def run_worker(
    jobs: list[dict],
    max_tokens: int = 300,
    on_line: Callable[[dict], None] | None = None,
    model: str | None = None,
) -> list[dict]:
    """Run the worker on [{id, video, prompt}], model loaded once. Low CPU priority (nice)."""
    py = tool_python()
    model = model or current()
    if not py or not model or not model_cached(model):
        raise RuntimeError(
            "yerel video modeli kurulu ya da seçili değil: Stüdyo > ⋯ > Yerel model "
            "(ya da uv run vlogkit extras install vlm)"
        )
    with tempfile.TemporaryDirectory() as tmp:
        spec = Path(tmp) / "jobs.json"
        spec.write_text(
            json.dumps({"model": model, "fps": FPS, "max_tokens": max_tokens, "jobs": jobs})
        )
        proc = subprocess.Popen(
            ["nice", "-n", "10", str(py), str(WORKER), str(spec)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
            env={**os.environ, "TOKENIZERS_PARALLELISM": "false"},
        )  # fmt: skip
        results = []
        assert proc.stdout
        for line in proc.stdout:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if "id" in d:
                results.append(d)
                if on_line:
                    on_line(d)
        proc.wait()
    return results


def describe(
    path: PathLike,
    spans: Sequence[tuple[float, float]],
    cache_dir: Path = CACHE_DIR,
    progress: Callable[[int, int], None] | None = None,
) -> dict[tuple[float, float], dict]:
    """{(t0, t1): normalized answer} for every span of one clip; only uncached spans run."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    have = cached(path, spans, cache_dir)
    todo = [s for s in spans if s not in have]
    if not todo:
        return have
    model = current()  # once: a switch in the studio meanwhile must not mislabel answers
    cache = _cache_file(path, cache_dir)
    with tempfile.TemporaryDirectory() as tmp:
        pieces = cut_pieces(path, todo, Path(tmp))
        jobs = [
            {"id": str(i), "video": str(p), "prompt": DESCRIBE_PROMPT.format(dur=b - a)}
            for i, ((a, b), p) in enumerate(zip(todo, pieces, strict=True))
        ]
        done = 0

        def keep(d: dict) -> None:
            nonlocal done
            a, b = todo[int(d["id"])]
            res = normalize(parse_json(d.get("text", "")), d.get("text", ""))
            if d.get("error"):
                res = {**normalize(None), "error": d["error"]}
            else:
                with cache.open("a") as f:
                    f.write(
                        json.dumps({"key": _span_key(a, b, model), "raw": d.get("text", "")}) + "\n"
                    )
            have[(a, b)] = res
            done += 1
            if progress:
                progress(done, len(todo))

        run_worker(jobs, on_line=keep, model=model)
    return have


# --------------------------------------------------------------------------- faces
# In a 448 px frame a face is a few dozen pixels: expressions get lost. For mimics the face is
# cropped from the FULL-resolution source first (Vision face box), then shown to the model.
FACE_PROMPT = (
    "This is a {dur:.1f}-second close-up of a person talking to the camera. Watch it frame by "
    "frame and describe the FACE and delivery, not the room. Answer with JSON only: "
    '{{"expression": "<one or two sentences: mouth, eyes, eyebrows, head moves over time>", '
    '"energy": "low|medium|high", "smile": true/false, "laugh": true/false, '
    '"eye_contact": true/false, "awkward": true/false, '
    '"moments": ["<second>: <visible change, e.g. raises eyebrows, grins, looks away>"]}}'
)
Box = tuple[float, float, float, float]  # x, y, w, h (0-1, top-left)
TRACK_FPS = 2.0


def face_track(path: PathLike, start: float, end: float) -> list[tuple[float, Box | None]]:
    """(time from `start`, largest face or None) at TRACK_FPS, from one decode pass."""
    from vlogkit.analysis import vision

    if not vision.available():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        ffmpeg(["-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", path, "-vf",
                f"fps={TRACK_FPS},scale='if(gte(iw,ih),960,-2)':'if(gte(iw,ih),-2,960)'",
                Path(tmp) / "f%04d.png"])  # fmt: skip
        frames = sorted(Path(tmp).glob("f*.png"))
        seen = vision.read(frames, aesthetics=False)
        out: list[tuple[float, Box | None]] = []
        for i, f in enumerate(frames):
            faces = seen[str(f)].faces if str(f) in seen else []
            out.append(
                ((i + 0.5) / TRACK_FPS, max(faces, key=lambda b: b[2] * b[3]) if faces else None)
            )
        return out


def crop_filter(track: Sequence[tuple[float, Box | None]], zoom: float = 2.6) -> str | None:
    """A square crop that follows the face (ffmpeg `crop` with time expressions).

    Works on the frames as ffmpeg decodes them (rotation applied, like the Vision boxes). The
    side is `zoom` x the median face height; the centre moves
    linearly between the sampled face centres (held where the face is missing), clamped to the
    frame. Head slightly above the centre so chin and shoulders stay in.
    """
    from statistics import median

    from vlogkit.video.expr import piecewise

    faces = [(t, b) for t, b in track if b]
    if not faces:
        return None
    side = min(1.0, zoom * median(b[3] for _, b in faces))  # in frame heights
    keys_x = [(t, b[0] + b[2] / 2) for t, b in faces]
    keys_y = [(t, b[1] + b[3] / 2) for t, b in faces]
    cx, cy = piecewise(keys_x), piecewise(keys_y)
    s = f"{side:.4f}"
    x = f"clip(iw*({cx})-ih*{s}/2,0,iw-ih*{s})"
    y = f"clip(ih*({cy})-ih*{s}*0.42,0,ih-ih*{s})"
    return f"crop=w='trunc(ih*{s}/2)*2':h='trunc(ih*{s}/2)*2':x='{x}':y='{y}'"  # quoted: commas


def cut_face(
    src: PathLike, start: float, end: float, crop: str, out: Path, side: int = 512
) -> Path:
    """The face close-up the model watches: cropped at full resolution, brightened (model input
    only; talking-head takes are often underexposed)."""
    ffmpeg(["-y", "-ss", f"{start:.3f}", "-t", f"{end - start:.3f}", "-i", src, "-vf",
            f"fps={FPS},{crop},scale={side}:{side}:flags=lanczos,eq=gamma=1.35:contrast=1.08",
            "-an", "-map_metadata", "-1", "-write_tmcd", "0", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            out])  # fmt: skip
    return out


def _face_piece(path: PathLike, start: float, end: float, out: Path) -> tuple[Path, int]:
    track = face_track(path, start, end)
    crop = crop_filter(track)
    if crop is None:
        raise ValueError("bu aralıkta yüz bulunamadı (Vision)")
    return cut_face(path, start, end, crop, out), sum(1 for _, b in track if b)


def _in_clip(moments: list[str], dur: float) -> list[str]:
    """Drop moments timed after the clip ends: the model sometimes invents '15 sn' in an 8 s clip."""
    keep = []
    for m in moments:
        num = re.match(r"\s*(\d+(?:[.,]\d+)?)", m)
        if num and float(num.group(1).replace(",", ".")) > dur + 0.5:
            continue
        keep.append(m)
    return keep


def _shift(moment: str, start: float) -> str:
    """'3 sn: grins' in clip time -> '79 sn: grins' in source time."""
    num = re.match(r"\s*(\d+(?:[.,]\d+)?)\s*(?:sn|s)?\s*:?\s*", moment)
    if not num:
        return moment
    t = start + float(num.group(1).replace(",", "."))
    return f"{t:.0f} sn: {moment[num.end() :]}"


def _moment(m) -> str:
    if isinstance(m, dict):
        t = m.get("second", m.get("time", ""))
        what = m.get("visible_change") or m.get("change") or m.get("event") or ""
        return f"{t} sn: {what}".strip()
    return str(m)


def expression(path: PathLike, start: float, end: float, max_tokens: int = 500) -> dict:
    """Facial expression and delivery in a stretch (<= 30 s): what a take looks like on camera.

    The model cannot hear: tone of voice and comic timing are for the user to judge.
    """
    start, end = _span(path, start, end, limit=30)
    with tempfile.TemporaryDirectory() as tmp:
        piece, found = _face_piece(path, start, end, Path(tmp) / "face.mp4")
        out = run_worker(
            [{"id": "face", "video": str(piece), "prompt": FACE_PROMPT.format(dur=end - start)}],
            max_tokens,
        )
    text = out[0].get("text", "") if out else ""
    d = parse_json(text) or {}
    return {
        "expression": str(d.get("expression") or text).strip(),
        "energy": str(d.get("energy", "")).lower(),
        "smile": bool(d.get("smile", False)),
        "laugh": bool(d.get("laugh", False)),
        "eye_contact": bool(d.get("eye_contact", False)),
        "awkward": bool(d.get("awkward", False)),
        "moments": [
            _shift(m, start)
            for m in _in_clip([_moment(m) for m in d.get("moments") or []], end - start)
        ][:8],
        "faces_found": found,
    }


def _span(path: PathLike, start: float, end: float, limit: float) -> tuple[float, float]:
    j = ffprobe_json(path)
    dur = float(j["format"].get("duration", 0.0))
    start, end = max(0.0, start), min(end or dur, dur)
    if end - start > limit:
        raise ValueError(f"en fazla {limit:g} sn'lik bir aralık sor (kısa aralık daha doğru)")
    return start, end


def ask(
    path: PathLike,
    start: float,
    end: float,
    question: str,
    max_tokens: int = 400,
    face: bool = False,
) -> str:
    """A free question about one stretch of a video, answered by the local model.
    face=True shows the model a full-resolution close-up of the face (mimics, reactions)."""
    start, end = _span(path, start, end, limit=60)
    with tempfile.TemporaryDirectory() as tmp:
        if face:
            piece, _ = _face_piece(path, start, end, Path(tmp) / "face.mp4")
        else:
            piece = cut_pieces(path, [(start, end)], Path(tmp))[0]
        prompt = (
            f"This is a {end - start:.1f}-second clip (0 s = {start:.1f} s of the source). Watch it "
            f"frame by frame. {question} Answer briefly; give times in seconds of the clip."
        )
        out = run_worker([{"id": "q", "video": str(piece), "prompt": prompt}], max_tokens)
    if not out:
        raise RuntimeError("yerel model cevap vermedi")
    return out[0].get("text") or out[0].get("error", "")


class Eta:
    """Progress with an estimated finish time (chunks per second so far)."""

    def __init__(self, total: int):
        self.total, self.done, self.t0 = total, 0, time.time()

    def step(self, n: int = 1) -> str:
        self.done += n
        rate = self.done / max(1e-6, time.time() - self.t0)
        left = (self.total - self.done) / rate if rate else 0
        return f"{self.done}/{self.total} parça, ~{int(left // 60)} dk {int(left % 60)} sn kaldı"
