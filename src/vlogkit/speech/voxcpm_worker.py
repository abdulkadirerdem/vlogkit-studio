"""Runs inside the VoxCPM2 tool environment (not vlogkit's): load the model once, speak every line
of the job in the channel's voice, each line with its own delivery. Usage:
python voxcpm_worker.py job.json

job.json = {"backend": "mlx" | "torch", "model": repo, "ref": channel voice wav,
            "items": [{"text", "style", "seed", "out"}]}

The reference is given without its transcript on purpose: that is VoxCPM2's "controllable
cloning", where a parenthesised instruction at the start of the text ("(heyecanlı, merak
uyandıran)") sets the delivery and is not read out. With the transcript it would copy the
reference's delivery and read the instruction aloud.
"""

from __future__ import annotations

import json
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")


def _write(out: Path, audio, sr: int) -> None:
    import soundfile as sf

    tmp = out.with_name(out.stem + ".part.wav")
    sf.write(str(tmp), audio, sr)
    tmp.replace(out)


def run_mlx(job: dict) -> None:
    import mlx.core as mx
    import numpy as np
    import soundfile as sf
    from mlx_audio.tts.utils import load_model

    model = load_model(job["model"])
    x, _sr = sf.read(job["ref"], dtype="float32")
    ref = mx.array(x.mean(1) if x.ndim > 1 else x)
    for i, it in enumerate(job["items"]):
        mx.random.seed(int(it.get("seed", 11)))
        segs = list(
            model.generate(
                text=it["text"], instruct=it.get("style") or None, ref_audio=ref,
                inference_timesteps=int(job.get("steps", 16)), cfg_value=2.0,
            )
        )  # fmt: skip
        audio = np.concatenate([np.array(s.audio, dtype=np.float32) for s in segs])
        _write(Path(it["out"]), audio, int(getattr(segs[0], "sample_rate", 48000)))
        print(f"VKTTS {i + 1}/{len(job['items'])}", flush=True)


def run_torch(job: dict) -> None:
    import numpy as np
    import torch
    from voxcpm import VoxCPM

    model = VoxCPM.from_pretrained(job["model"], load_denoiser=False, optimize=False)
    for i, it in enumerate(job["items"]):
        torch.manual_seed(int(it.get("seed", 11)))
        style = f"({it['style']})" if it.get("style") else ""
        wav = model.generate(
            text=style + it["text"], reference_wav_path=job["ref"], cfg_value=2.0,
            inference_timesteps=int(job.get("steps", 16)),
        )  # fmt: skip
        _write(Path(it["out"]), np.asarray(wav, dtype=np.float32), 48000)
        print(f"VKTTS {i + 1}/{len(job['items'])}", flush=True)


def main() -> None:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    (run_mlx if job.get("backend") == "mlx" else run_torch)(job)


if __name__ == "__main__":
    main()
