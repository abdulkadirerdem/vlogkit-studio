"""Audio filter-graph builder + meme SFX that briefly duck the music bed."""

from __future__ import annotations

import math
import re
import subprocess
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from vlogkit.config import require, tools
from vlogkit.timecode import fmt

SAMPLE_RATE = 48000


@dataclass(frozen=True)
class Sfx:
    """A sound file placed on the timeline.

    at        when the sound's hit should land (timeline seconds)
    src/dur   which part of the file to use
    gain      linear gain
    duck      music attenuation in dB while it plays (None = no duck)
    duck_at   duck start if different from `at` (e.g. riser whose hit comes later)
    """

    file: str | Path
    at: float
    dur: float
    src: float = 0.0
    gain: float = 1.0
    duck: float | None = None
    duck_at: float | None = None
    duck_len: float = 0.0
    fade_in: float = 0.005
    fade: float = 0.08


def duck_expr(sfx: Iterable[Sfx], attack: float = 0.04, release: float = 0.12) -> str:
    """Music gain multiplier with short ramps into/out of each duck window ('1' if none)."""
    factors = []
    for s in sfx:
        if s.duck is None:
            continue
        a = s.at if s.duck_at is None else s.duck_at
        b = a + s.duck_len
        g = 10 ** (s.duck / 20)
        factors.append(
            f"(1-{1 - g:.4f}*clip(min((t-{a:.3f})/{fmt(attack)},({b:.3f}-t)/{fmt(release)}),0,1))"
        )
    return "*".join(factors) or "1"


def sfx_chain(s: Sfx, input_idx: int) -> str:
    ms = round(s.at * 1000)
    return (
        f"[{input_idx}:a]atrim={s.src}:{s.src + s.dur},asetpts=PTS-STARTPTS,aresample=48000,"
        f"aformat=channel_layouts=stereo,volume={s.gain},"
        f"afade=t=in:d={s.fade_in},afade=t=out:st={s.dur - s.fade:.3f}:d={s.fade},"
        f"adelay={ms}|{ms}"
    )


class AudioGraph:
    """Collects inputs + labelled chains, sums them (amix normalize=0) to a fixed duration.

    Every chain belongs to a *stem* (for editors: the Resolve export can hand the mix over as
    separate tracks). `chain(..., stem=...)` names it; otherwise a chain that reads a file input is
    "main" (camera sound, voice, music) and a synthesized one (whoosh, impact...) is "sfx".
    """

    def __init__(self, duration: float):
        self.duration = duration
        self.inputs: list[str] = []
        self.chains: list[str] = []
        self.labels: list[str] = []
        self.stems: dict[str, str] = {}  # label -> stem name
        self.last_post: str | None = None  # post chain of the latest render (build metadata)

    @property
    def samples(self) -> int:
        """Length in whole 48 kHz samples, rounded *up*. A track even a few samples shorter than
        the picture (57.3573 s = 2753150.4 samples, cut to 2753150) makes the mp4 mux (-shortest)
        drop the last video frame."""
        return math.ceil(round(self.duration * SAMPLE_RATE, 6))

    def input(self, path: str | Path) -> int:
        self.inputs.append(str(path))
        return len(self.inputs) - 1

    def chain(self, chain: str, label: str | None = None, stem: str | None = None) -> str:
        label = label or f"a{len(self.labels)}"
        self.chains.append(f"{chain}[{label}]")
        self.labels.append(label)
        self.stems[label] = stem or ("main" if re.match(r"\[\d+:a\]", chain) else "sfx")
        return label

    def append(self, label: str, filters: str) -> None:
        """More filters at the end of an existing chain (e.g. a timeline duck on the camera
        sound a parent edit already built). The label and its stem stay the same."""
        i = self.labels.index(label)
        self.chains[i] = f"{self.chains[i][: -len(label) - 2]},{filters}[{label}]"

    def sfx(self, s: Sfx) -> str:
        return self.chain(sfx_chain(s, self.input(s.file)), stem="sfx")

    def stem_names(self) -> list[str]:
        """Stems in first-use order, e.g. ['main', 'sfx']."""
        return list(dict.fromkeys(self.stems[x] for x in self.labels))

    def stem_labels(self, stem: str) -> list[str]:
        return [x for x in self.labels if self.stems[x] == stem]

    def sfx_all(self, items: Sequence[Sfx]) -> list[str]:
        return [self.sfx(s) for s in items]

    def filter_complex(self, post: str = "anull", only: Collection[str] | None = None) -> str:
        """The mix graph. `only` = labels to sum (a stem); the other chains end in anullsink.

        A stem also gets a silent first input from t=0: amix takes its output timestamps from its
        first input, and a generated sound (sine/noise + adelay) starts them at its delay (2.33 s
        for a whoosh at 2.33), so the final atrim cut the stem short. The full mix is unchanged:
        its first chain is a file input starting at 0.
        """
        used = [x for x in self.labels if only is None or x in only]
        if not used:
            raise ValueError("no chains to mix")
        ins = "".join(f"[{x}]" for x in used)
        sinks = [f"[{x}]anullsink" for x in self.labels if x not in used]
        n = self.samples
        anchor = []
        if only is not None:
            anchor = [f"anullsrc=r={SAMPLE_RATE}:cl=stereo,atrim=end_sample={n}[_t0]"]
            ins = "[_t0]" + ins
        return ";".join(
            [
                *self.chains,
                *sinks,
                *anchor,
                f"{ins}amix=inputs={len(used) + len(anchor)}:normalize=0:duration=longest,"
                f"aresample={SAMPLE_RATE},apad=whole_len={n},atrim=end_pts={n}[mix]",
                f"[mix]{post}[out]",
            ]
        )

    def render(
        self,
        out_args: Sequence[str],
        post: str = "anull",
        loglevel: str = "error",
        only: Collection[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        self.last_post = post
        cmd = [require(tools().ffmpeg, "ffmpeg"), "-hide_banner", "-v", loglevel, "-y"]
        for path in self.inputs:
            cmd += ["-i", path]
        cmd += ["-filter_complex", self.filter_complex(post, only), "-map", "[out]", *out_args]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            raise RuntimeError("audio render failed:\n" + "\n".join(r.stderr.splitlines()[-15:]))
        return r
