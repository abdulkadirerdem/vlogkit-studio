"""Runs inside the qwen-tts tool environment (not vlogkit's): load the Turkish model once, speak
every line of the job in the channel's voice. Usage: python qwen_worker.py job.json

job.json = {"model": repo, "ref": channel voice wav, "ref_text": what it says (optional),
            "temperature": float (optional), "items": [{"text", "out"}]}

With `ref_text` the clone copies the reference's delivery too (ICL: its pace, energy, the way it
lands on words); without it only the timbre (speaker embedding).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    import soundfile as sf
    import torch
    from qwen_tts import Qwen3TTSModel

    if torch.cuda.is_available():
        kw = {"device_map": "cuda", "dtype": torch.float16}
    elif getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        kw = {"device_map": "mps", "dtype": torch.float32}
    else:
        kw = {"device_map": "cpu", "dtype": torch.float32}
    try:
        model = Qwen3TTSModel.from_pretrained(job["model"], **kw)
    except TypeError:
        model = Qwen3TTSModel.from_pretrained(job["model"])
    ref_text = job.get("ref_text")
    prompt = model.create_voice_clone_prompt(
        ref_audio=job["ref"], ref_text=ref_text, x_vector_only_mode=not ref_text
    )
    extra = {"temperature": float(job["temperature"])} if job.get("temperature") else {}
    for i, it in enumerate(job["items"]):
        wavs, sr = model.generate_voice_clone(
            text=it["text"],
            language="Auto",
            voice_clone_prompt=prompt,
            non_streaming_mode=True,
            **extra,
        )
        w = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
        out = Path(it["out"])
        tmp = out.with_name(out.stem + ".part.wav")
        data = w.squeeze() if hasattr(w, "squeeze") else w
        sf.write(str(tmp), data, sr)
        tmp.replace(out)
        print(f"VKTTS {i + 1}/{len(job['items'])}", flush=True)


if __name__ == "__main__":
    main()
