"""Runs inside the pocket-tts-turkish tool environment (not vlogkit's): load the model once, render
every line of the job file. Usage: python pocket_worker.py job.json

job.json = {"voice_file": path | null, "items": [{"text", "voice", "emotion", "speed", "out"}]}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    from pocket_tts_turkish import TurkishTTS, save_wav

    tts = TurkishTTS.from_pretrained()
    cloned = tts.voice_from_file(job["voice_file"]) if job.get("voice_file") else None
    for i, it in enumerate(job["items"]):
        kw = {"voice": cloned if cloned is not None else it.get("voice") or "male_1"}
        if it.get("emotion"):
            kw["emotion"] = it["emotion"]
        try:
            audio = tts.generate(it["text"], **kw)
        except TypeError:  # an older package without emotion
            kw.pop("emotion", None)
            audio = tts.generate(it["text"], **kw)
        out = Path(it["out"])
        tmp = out.with_name(out.stem + ".part.wav")
        save_wav(str(tmp), audio, tts.sample_rate)
        tmp.replace(out)
        print(f"VKTTS {i + 1}/{len(job['items'])}", flush=True)


if __name__ == "__main__":
    main()
