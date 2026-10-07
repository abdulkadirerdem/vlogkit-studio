"""The end of a video: stop right after the payoff, and let a Short loop.

docs/viral-edit.md: never signal "the video is over"; cutting the last second of a Short raised
retention from 83% to 88% (Jenny Hoyos); Shorts whose end flows into the start get replayed
(and every replay counts as a view since March 2025).

- `tail`: seconds after the last spoken word (end cards excluded by the caller if intended).
- `loop_candidates`: how much each of the last frames looks like the first frame. A cut there
  makes the loop seam (almost) invisible; the last sentence leading into the first is the
  editor's part.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from pathlib import Path

from PIL import Image, ImageChops, ImageStat

from vlogkit.analysis.hook import Check
from vlogkit.analysis.transcribe import Segment
from vlogkit.ff import PathLike, extract_frame, ffmpeg, probe

SIZE = "96:-2"


def tail(duration: float, words: Sequence[Segment]) -> float | None:
    words = [w for w in words if not w.suspicious]
    return duration - words[-1].end if words else None


def _similarity(a: Image.Image, b: Image.Image) -> float:
    diff = ImageStat.Stat(ImageChops.difference(a, b)).mean
    return 1 - sum(diff) / (len(diff) * 255)


def loop_candidates(path: PathLike, search: float = 1.5) -> list[tuple[float, float]]:
    """(time, similarity 0-1 to the first frame) for every frame in the last `search` seconds."""
    info = probe(path)
    start = max(0.0, info.duration - search)
    with tempfile.TemporaryDirectory() as tmp:
        first = Image.open(extract_frame(path, 0.0, Path(tmp) / "first.png", vf=f"scale={SIZE}"))
        first = first.convert("RGB")
        ffmpeg(
            [
                "-y",
                "-ss",
                f"{start:.3f}",
                "-i",
                path,
                "-an",
                "-vf",
                f"scale={SIZE}",
                Path(tmp) / "e%04d.png",
            ]
        )
        frames = sorted(Path(tmp).glob("e*.png"))
        fps = float(info.fps or 30)
        return [
            (start + i / fps, _similarity(first, Image.open(f).convert("RGB")))
            for i, f in enumerate(frames)
        ]


def check(path: PathLike, kind: str | None = None, words: Sequence[Segment] = ()) -> list[Check]:
    info = probe(path)
    kind = kind or ("short" if info.vertical else "long")
    out = []
    t = tail(info.duration, words)
    if t is None:
        out.append(Check("Bitiş", None, "konuşma yok: son sözden sonraki süre ölçülemedi"))
    elif kind == "short":
        out.append(
            Check(
                "Bitiş",
                t <= 1.0,
                f"son sözden sonra {t:.2f} sn var (Short'ta <= 1 sn; ödülden sonra hemen bitir)",
            )
        )
    else:
        out.append(
            Check(
                "Bitiş",
                None,
                f"son sözden sonra {t:.1f} sn (bitiş kartı ise sorun yok, uzun veda olmasın)",
            )
        )
    if kind == "short":
        cands = loop_candidates(path)
        if cands:
            best_t, best = max(cands, key=lambda c: c[1])
            last = cands[-1][1]
            if last >= 0.9:
                out.append(Check("Loop", True, f"son kare ilk kareye %{last * 100:.0f} benziyor"))
            elif best >= 0.9:  # loops are optional: a hint, never a failure
                out.append(
                    Check(
                        "Loop",
                        None,
                        f"isteğe bağlı: {best_t:.2f} sn'de kesilirse son kare başa "
                        f"%{best * 100:.0f} benziyor (şu an %{last * 100:.0f})",
                    )
                )
            else:
                out.append(
                    Check(
                        "Loop",
                        None,
                        f"isteğe bağlı: son kare başa %{last * 100:.0f} benziyor; sonu başa "
                        "bağlayan bir cümle ya da kare düşünülebilir",
                    )
                )
    return out
