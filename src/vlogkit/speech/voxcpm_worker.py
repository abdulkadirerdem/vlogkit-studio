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


def _mapped(path: str) -> dict:
    """A .safetensors file's tensors read straight from a read-only mapping of the file, not
    copied into memory: the weights are 4.6 GB and the model holds its own copy, so a plain load
    needs twice that at once (an 8 GB Windows machine runs out). Same values, same dtypes."""
    import numpy as np
    import torch

    kinds = {"BF16": (np.uint16, torch.bfloat16), "F16": (np.float16, None),
             "F32": (np.float32, None), "F64": (np.float64, None), "I64": (np.int64, None),
             "I32": (np.int32, None), "I16": (np.int16, None), "I8": (np.int8, None),
             "U8": (np.uint8, None), "BOOL": (np.bool_, None)}  # fmt: skip
    with open(path, "rb") as f:
        n = int.from_bytes(f.read(8), "little")
        head = json.loads(f.read(n))
    raw = np.memmap(path, dtype=np.uint8, mode="r", offset=8 + n)
    out = {}
    for name, info in head.items():
        if name == "__metadata__":
            continue
        np_kind, view = kinds[info["dtype"]]
        a, b = info["data_offsets"]
        t = torch.from_numpy(raw[a:b].view(np_kind)).reshape(info["shape"])
        out[name] = t.view(view) if view is not None else t
    return out


def run_torch(job: dict) -> None:
    import contextlib

    import numpy as np
    import torch
    from voxcpm import VoxCPM

    # The model is built in float32 and then turned to its bfloat16: 9 GB at the peak. Built in
    # bfloat16 from the start it needs half that, and speaks the same (the loaded weights replace
    # what was built; checked bit for bit). Apple's GPU keeps float32 (voxcpm does too there).
    build_bf16 = not (torch.backends.mps.is_available() and job.get("device") != "cpu")
    try:
        import voxcpm.model.voxcpm2 as v2

        if getattr(v2, "load_file", None) is not None:
            v2.load_file = lambda p, device="cpu": _mapped(p)
    except ImportError:
        pass

    @contextlib.contextmanager
    def default_dtype(dt):
        old = torch.get_default_dtype()
        torch.set_default_dtype(dt)
        try:
            yield
        finally:
            torch.set_default_dtype(old)

    with default_dtype(torch.bfloat16) if build_bf16 else contextlib.nullcontext():
        model = VoxCPM.from_pretrained(
            job["model"], load_denoiser=False, optimize=False, device=job.get("device")
        )
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
