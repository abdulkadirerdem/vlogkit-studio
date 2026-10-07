"""Source separation with Demucs v4 (htdemucs, MIT), when it is installed (`extras.install`).

What it is for in a vlog: a clip where your voice sits on top of music you do not own (the race
speakers, a café). Split it into `vocals` (you) and `no_vocals` (the music + ambience), keep the
voice, drop or duck the music, put licensed music under it: fewer Content ID claims and a
cleaner voice. Also: a karaoke-free music bed for a voice-over.

- Runs on Apple Silicon's GPU (`mps`) and falls back to the CPU.
- The model weights (~90 MB) download on first use from Hugging Face (~/.cache/huggingface).
- Speed on an M5 Pro: 15 s of audio in ~2.6 s on `mps` (~7.7 s on the CPU).
- Output: 48 kHz 24-bit WAVs, exactly as long as the input part, so they drop straight into an
  AudioGraph next to the picture.
- Separation is not perfect: loud drums leak into `vocals`, reverb tails get split. Listen.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from vlogkit import extras
from vlogkit.ff import PathLike, ffmpeg, probe

MODEL = "htdemucs"


def available() -> bool:
    return extras.find("demucs") is not None


def command(
    exe: str,
    wav: Path,
    out_dir: Path,
    two_stems: str | None = "vocals",
    device: str = "mps",
    model: str = MODEL,
    shifts: int = 1,
) -> list[str]:
    cmd = [exe, "-n", model, "-d", device, "-o", str(out_dir), "--filename", "{stem}.{ext}",
           "--float32", "--shifts", str(shifts)]  # fmt: skip
    if two_stems:
        cmd += ["--two-stems", two_stems]
    return [*cmd, str(wav)]


def separate(
    src: PathLike,
    out_dir: PathLike,
    two_stems: str | None = "vocals",
    *,
    start: float = 0.0,
    duration: float | None = None,
    device: str | None = None,
    model: str = MODEL,
    shifts: int = 1,
) -> dict[str, Path]:
    """{stem: wav}. two_stems="vocals" -> vocals + no_vocals; None -> drums, bass, other, vocals."""
    exe = extras.find("demucs")
    if not exe:
        raise RuntimeError(
            "Demucs yok: `uv run python -c \"from vlogkit import extras; extras.install('demucs')\"`"
        )
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "in.wav"
        cut = (["-ss", f"{start:.3f}"] if start else []) + (
            ["-t", f"{duration:.3f}"] if duration else []
        )
        # htdemucs works at 44.1 kHz stereo
        ffmpeg(["-y", *cut, "-i", src, "-vn", "-ac", "2", "-ar", "44100", "-c:a", "pcm_f32le", wav])
        length = f"{probe(wav).duration:.6f}"
        err = ""
        for dev in [device] if device else ["mps", "cpu"]:
            r = subprocess.run(
                command(exe, wav, Path(tmp) / "out", two_stems, dev, model, shifts),
                capture_output=True,
                text=True,
            )
            if r.returncode == 0:
                break
            err = r.stderr[-800:]
        else:
            raise RuntimeError(f"demucs hata verdi:\n{err}")
        stems = {}
        for f in sorted((Path(tmp) / "out" / model).glob("*.wav")):
            dest = out_dir / f"{f.stem}.wav"
            ffmpeg(["-y", "-i", f, "-af", f"apad=whole_dur={length}", "-t", length,
                    "-ar", "48000", "-c:a", "pcm_s24le", dest])  # fmt: skip
            stems[f.stem] = dest
    return stems
