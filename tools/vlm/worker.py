"""vlogkit local VLM worker: load a video-language model ONCE, answer a batch of clip prompts.

Runs inside the mlx-vlm uv tool environment (not vlogkit's venv):
    ~/.local/share/uv/tools/mlx-vlm/bin/python tools/vlm/worker.py jobs.json

jobs.json: {"model": "...", "fps": 2.0, "max_tokens": 200,
            "jobs": [{"id": "...", "video": "/path/clip.mp4", "prompt": "..."}]}
Prints one JSON line per job: {"id", "text", "seconds"} (or {"id", "error"}), then
{"done": n, "load_seconds": s, "total_seconds": s}. Lines are flushed as they are produced, so
the caller can cache results and resume after an interruption.
"""

import json
import sys
import time


def main() -> None:
    with open(sys.argv[1]) as f:
        spec = json.load(f)
    t_all = time.time()
    from mlx_vlm import generate, load
    from mlx_vlm.prompt_utils import apply_chat_template

    model, processor = load(spec["model"])
    load_s = time.time() - t_all
    fps = float(spec.get("fps", 2.0))
    done = 0
    for job in spec["jobs"]:
        t = time.time()
        try:
            prompt = apply_chat_template(
                processor,
                model.config,
                job["prompt"],
                num_images=0,
                video=[job["video"]],
                fps=fps,
                enable_thinking=False,
            )
            out = generate(
                model,
                processor,
                prompt,
                video=[job["video"]],
                fps=fps,
                max_tokens=int(spec.get("max_tokens", 200)),
                temperature=0.0,
                enable_thinking=False,
                verbose=False,
            )
            line = {"id": job["id"], "text": out.text.strip(), "seconds": round(time.time() - t, 2)}
        except Exception as e:  # one bad clip must not stop the batch
            line = {"id": job["id"], "error": f"{type(e).__name__}: {e}"[:500]}
        print(json.dumps(line, ensure_ascii=False), flush=True)
        done += 1
    print(
        json.dumps(
            {
                "done": done,
                "load_seconds": round(load_s, 2),
                "total_seconds": round(time.time() - t_all, 2),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
