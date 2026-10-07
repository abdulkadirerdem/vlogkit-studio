"""Edit projects: one folder per video in projects/<name>/ with an edit.py defining `EDIT`.

A build runs four steps into build/<name>/<variant>/ and writes the delivery file next to the
footage (or --out):

    base     graded, re-cut picture                    -> base.mov    (ProRes 422 HQ)
    overlay  captions / motion graphics                -> overlay.mov (ProRes 4444, alpha)
    audio    music + voice + SFX, loudness-normalised  -> audio.wav
    compose  base + overlay + audio                    -> <output>.mp4 (+ sidecar files)

Variants (e.g. "v1", "meme") share the edit class and get their own work dir and output file, so
an approved version is never overwritten by an experiment.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import time
from abc import ABC, abstractmethod
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from vlogkit import assets
from vlogkit.audio.loudness import normalize
from vlogkit.audio.mix import AudioGraph
from vlogkit.config import BUILD_DIR, PROJECTS_DIR, VLOGS_ROOT
from vlogkit.export.encode import SHORTS, EncodePreset, compose
from vlogkit.graphics.elements import Element, emoji_notes
from vlogkit.graphics.render import render_overlay
from vlogkit.graphics.style import VERTICAL, Layout
from vlogkit.timecode import FPS_NTSC

STEPS = ("base", "overlay", "audio", "compose")


@dataclass(frozen=True)
class Context:
    name: str
    variant: str
    project_dir: Path
    work: Path
    out: Path | None = None

    def footage(self, rel: str) -> Path:
        """A source file relative to the vlogs root, e.g. 'kackar/Kackar_Short_01.mp4'."""
        p = VLOGS_ROOT / rel
        if not p.exists():
            raise FileNotFoundError(p)
        return p

    def asset(self, asset_id: str) -> Path:
        return assets.path(asset_id)


class Edit(ABC):
    """Subclass per video. Keep *data* (times, captions, SFX) readable at the top of edit.py."""

    variants: tuple[str, ...] = ("v1",)
    fps: Fraction = FPS_NTSC
    preset: EncodePreset = SHORTS
    layout: Layout = VERTICAL  # canvas of the graphics layer (LANDSCAPE for YouTube long videos)
    output: str = ""  # relative to VLOGS_ROOT, without extension; variants add "_<variant>"

    def __init__(self, ctx: Context):
        if ctx.variant not in self.variants:
            raise ValueError(f"variant '{ctx.variant}' yok. Seçenekler: {', '.join(self.variants)}")
        self.ctx = ctx
        self.variant = ctx.variant
        ctx.work.mkdir(parents=True, exist_ok=True)

    # --- to implement -------------------------------------------------------------------------
    @property
    @abstractmethod
    def nframes(self) -> int: ...

    @abstractmethod
    def build_base(self, out: Path) -> None: ...

    @abstractmethod
    def elements(self) -> list[Element]: ...

    @abstractmethod
    def audio(self) -> AudioGraph: ...

    def sidecars(self) -> dict[str, str]:
        """Text files delivered next to the video: {suffix: content}, e.g. {".zh.srt": ...}."""
        return {}

    def notes(self) -> list[tuple[float, str]]:
        """Notes at times on the delivered timeline: open questions, things to check by ear,
        the user's time-anchored comments still to do. Shown in the Studio timeline and as
        Resolve markers. Default: the module-level NOTES list of edit.py, e.g.
        NOTES = [(12.3, "müzik geçişini dinle")]; override for per-variant notes."""
        module = sys.modules.get(type(self).__module__)
        return [(float(t), str(text)) for t, text in getattr(module, "NOTES", [])]

    def cuts(self) -> list[float] | None:
        """Shot changes on the delivered timeline (s). Used to split the picture into shots for
        editors (Resolve export); None = detect them in base.mov."""
        return None

    # --- paths --------------------------------------------------------------------------------
    @property
    def duration(self) -> float:
        return float(self.nframes / self.fps)

    @property
    def base_path(self) -> Path:
        return self.ctx.work / "base.mov"

    @property
    def overlay_path(self) -> Path:
        return self.ctx.work / "overlay.mov"

    @property
    def audio_path(self) -> Path:
        return self.ctx.work / "audio.wav"

    @property
    def audio_meta_path(self) -> Path:
        """How audio.wav was made (final gain), so stems can be rendered at the same level."""
        return self.ctx.work / "audio.json"

    @property
    def output_path(self) -> Path:
        if self.ctx.out:
            return self.ctx.out
        suffix = "" if self.variant == self.variants[0] else f"_{self.variant}"
        return VLOGS_ROOT / f"{self.output}{suffix}.mp4"

    # --- steps --------------------------------------------------------------------------------
    def run(self, steps: Sequence[str] = STEPS) -> Path:
        from vlogkit import disk

        steps = self.plan_steps(steps)
        note = disk.ensure(self.space_needed(steps), self.ctx.work)
        if note:
            print(f"   ! {note}", flush=True)
        from vlogkit.export import licenses

        for step in steps:
            t = time.time()
            print(f"== {step}", flush=True)
            with assets.recording() as used:  # library files this step used (licenses)
                getattr(self, f"_step_{step}")()
            if step != "compose":
                licenses.record(self.ctx.work, step, used)
            print(f"   {step} ok ({time.time() - t:.0f}s)", flush=True)
        return self.output_path

    def space_needed(self, steps: Sequence[str]) -> float:
        """Bytes the steps add on disk: what they write minus the files they overwrite (ffmpeg
        truncates them, so a rebuild of a 27 GB base.mov needs little new space)."""
        from vlogkit import disk

        w, h = self.layout.size
        made = {
            "base": self.base_path,
            "overlay": self.overlay_path,
            "audio": self.audio_path,
            "compose": self.output_path,
        }
        rewritten = sum(made[s].stat().st_size for s in steps if made[s].is_file())
        need = disk.build_need(w, h, float(self.fps), self.duration, steps)
        return max(0.0, need - rewritten)

    def plan_steps(self, steps: Sequence[str]) -> list[str]:
        """The steps in pipeline order, plus any whose file compose needs is gone (disk cleanup
        deletes old intermediates; the delivery stays and a build makes them again)."""
        for step in steps:
            if step not in STEPS:
                raise ValueError(f"bilinmeyen adım: {step}")
        out = set(steps)
        if "compose" in out:
            made = {"base": self.base_path, "overlay": self.overlay_path, "audio": self.audio_path}
            for step, path in made.items():
                if step not in out and not path.exists():
                    print(f"   {path.name} yok: {step} adımı da çalışıyor", flush=True)
                    out.add(step)
        return [s for s in STEPS if s in out]

    def _step_base(self) -> None:
        self.build_base(self.base_path)

    def _step_overlay(self) -> None:
        elements = self.elements()
        for note in emoji_notes(elements):
            print(f"   ! {note}", flush=True)
        render_overlay(elements, self.nframes, self.overlay_path, self.fps, self.layout.size)

    def _step_audio(self) -> None:
        graph = self.audio()
        normalize(graph, self.audio_path)
        m = re.match(r"volume=(-?[\d.]+)dB", graph.last_post or "")
        if m:
            self.audio_meta_path.write_text(json.dumps({"gain_db": float(m.group(1))}))

    def _step_compose(self) -> None:
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        compose(
            self.base_path,
            self.overlay_path,
            self.audio_path,
            self.output_path,
            self.preset,
            self.fps,
        )
        print(f"   -> {self.output_path}")
        for path in self.write_sidecars():
            print(f"   -> {path}")
        lic = self.write_licenses()
        if lic:
            print(f"   -> {lic}")
        self.write_timeline()

    def write_licenses(self) -> Path | None:
        """<video>.lisans.md: third-party media and a dispute text. Never fails a build."""
        from vlogkit.export import licenses

        try:
            return licenses.write(self)
        except Exception as e:  # a missing license note must not cost the render
            print(f"   ! lisans dosyası yazılamadı: {e}", flush=True)
            return None

    def write_timeline(self) -> Path | None:
        """build/timelines/...: the edit as data for the Studio timeline. Never fails a build."""
        from vlogkit.export import timeline

        try:
            return timeline.write(timeline.from_edit(self), self.output_path)
        except Exception as e:  # a missing timeline must not cost the render
            print(f"   ! zaman çizelgesi yazılamadı: {e}", flush=True)
            return None

    def sidecar_path(self, suffix: str) -> Path:
        return self.output_path.with_name(self.output_path.stem + suffix)

    def write_sidecars(self) -> list[Path]:
        paths = []
        for suffix, content in self.sidecars().items():
            path = self.sidecar_path(suffix)
            path.write_text(content, encoding="utf-8")
            paths.append(path)
        return paths


def project_dir(name_or_path: str) -> Path:
    p = Path(name_or_path)
    if (p / "edit.py").exists():
        return p.resolve()
    if (PROJECTS_DIR / name_or_path / "edit.py").exists():
        return PROJECTS_DIR / name_or_path
    raise FileNotFoundError(f"proje bulunamadı: {name_or_path} (projects/<ad>/edit.py)")


def load(name_or_path: str, variant: str | None = None, out: Path | None = None) -> Edit:
    pdir = project_dir(name_or_path)
    spec = importlib.util.spec_from_file_location(f"vlogkit_project_{pdir.name}", pdir / "edit.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    # registered first: dataclasses (and anything else that looks a class's module up) need it
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    cls: type[Edit] = mod.EDIT
    variant = variant or cls.variants[0]
    ctx = Context(pdir.name, variant, pdir, BUILD_DIR / pdir.name / variant, out)
    return cls(ctx)


def list_projects() -> list[str]:
    return sorted(
        p.parent.name for p in PROJECTS_DIR.glob("*/edit.py") if not p.parent.name.startswith("_")
    )
