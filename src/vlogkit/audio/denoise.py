"""Voice denoise with DeepFilterNet 3 (a neural net, MIT / Apache-2.0), when it is installed.

Stronger and cleaner than the ffmpeg chain in `audio.voice` on wind, breathing and crowd noise:
afftdn subtracts a noise *profile* and leaves an "underwater" sound when pushed; DeepFilterNet
predicts the clean speech. Use it on the raw voice track, before the music is mixed in (on a
music bed it treats the music as noise). Then `audio.voice` can still add EQ / de-ess /
compression with `denoise=None`.

- The binary wants 48 kHz WAV and writes `<out_dir>/<same name>`. It keeps the channel count.
- `-D` compensates the model's lookahead/STFT delay: without it the voice lands late against
  the picture. Checked: syllable onsets in == out (5 ms grid); the output is padded back to the
  exact input length.
- `atten_db` caps the reduction (e.g. 18-25 dB) so some room tone stays: a fully silent floor
  between words sounds fake in a vlog.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from vlogkit import extras
from vlogkit.ff import PathLike, ffmpeg, probe


def available() -> bool:
    return extras.find("deepfilter") is not None


def command(
    exe: str, wav: Path, out_dir: Path, atten_db: float | None, post_filter: bool
) -> list[str]:
    cmd = [exe, "-D", "-o", str(out_dir)]
    if atten_db is not None:
        cmd += ["-a", f"{atten_db:g}"]
    if post_filter:
        cmd.append("--pf")
    return [*cmd, str(wav)]


def deepfilter(
    src: PathLike,
    out_wav: PathLike,
    atten_db: float | None = None,
    *,
    start: float = 0.0,
    duration: float | None = None,
    mono: bool = True,
    post_filter: bool = False,
) -> Path:
    """Denoise the audio of `src` (audio or video file) into a 48 kHz 24-bit WAV."""
    exe = extras.find("deepfilter")
    if not exe:
        raise RuntimeError(
            "DeepFilterNet yok: `uv run python -c \"from vlogkit import extras; extras.install('deepfilter')\"`"
        )
    out_wav = Path(out_wav)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "in.wav"
        cut = (["-ss", f"{start:.3f}"] if start else []) + (
            ["-t", f"{duration:.3f}"] if duration else []
        )
        ffmpeg(["-y", *cut, "-i", src, "-vn", "-ar", "48000", *(["-ac", "1"] if mono else []),
                "-c:a", "pcm_f32le", wav])  # fmt: skip
        r = subprocess.run(
            command(exe, wav, Path(tmp) / "out", atten_db, post_filter),
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            raise RuntimeError(f"deep-filter hata verdi:\n{r.stderr[-800:]}")
        produced = Path(tmp) / "out" / wav.name
        # The model eats its last frame (~30 ms): pad back to the exact input length so the track
        # stays sample-aligned with the picture, then the pipeline's usual 24-bit / 48 kHz.
        d = f"{probe(wav).duration:.6f}"
        ffmpeg(["-y", "-i", produced, "-af", f"apad=whole_dur={d}", "-t", d,
                "-c:a", "pcm_s24le", "-ar", "48000", out_wav])  # fmt: skip
    return out_wav
