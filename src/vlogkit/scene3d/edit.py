"""Scene3DEdit: a vlogkit project whose picture is rendered by Blender from scene.json.

A 3D project folder holds scene.json (the video), NOTES.md and a two-line edit.py:

    from vlogkit.scene3d.edit import Scene3DEdit
    EDIT = Scene3DEdit.for_project(__file__)

and builds with the usual steps (`vlogkit build PROJE`): base = Blender frames -> ProRes, overlay =
counter + captions + end card, audio = narration + music + effects, compose = the delivery mp4.
`vlogkit 3d preview PROJE -t 3` renders single frames first.

Environment: VLOGKIT_3D_ENGINE=eevee|cycles|workbench (default eevee; cycles without a GPU),
VLOGKIT_TTS=auto|pocket|system.
"""

from __future__ import annotations

import json
import os
import shutil
from fractions import Fraction
from functools import cached_property
from pathlib import Path

from vlogkit.audio import synth
from vlogkit.audio.mix import AudioGraph
from vlogkit.export.encode import SHORTS
from vlogkit.graphics.elements import EndCard, caption
from vlogkit.graphics.style import VERTICAL, tr_upper
from vlogkit.project import Edit
from vlogkit.scene3d import blender, framing, plan
from vlogkit.scene3d import spec as specmod
from vlogkit.scene3d.hud import Hud
from vlogkit.video.graph import PRORES_HQ

FPS = 30
CAPTION_Y = 1010  # mid-frame, over the action, clear of the bottom title block
CAPTION_SIZE = 104


class Scene3DEdit(Edit):
    variants = ("v1",)
    fps = Fraction(FPS)
    preset = SHORTS
    layout = VERTICAL
    project_dir: Path = Path(".")

    @classmethod
    def for_project(cls, edit_py: str) -> type[Scene3DEdit]:
        """The edit class for the project folder that holds this edit.py and scene.json."""
        here = Path(edit_py).resolve().parent
        spec = specmod.load(here / "scene.json")
        return type(f"Scene3D_{here.name}", (cls,), {"project_dir": here, "output": spec["output"]})

    # ------------------------------------------------------------------ data
    @cached_property
    def spec(self) -> dict:
        return specmod.load(self.project_dir / "scene.json")

    @cached_property
    def beats(self) -> list[plan.Beat]:
        return plan.narrate(self.spec, self.ctx.work, os.environ.get("VLOGKIT_TTS"))

    @property
    def nframes(self) -> int:
        return round(self.beats[-1].t1 * FPS)

    @property
    def engine(self) -> str:
        return os.environ.get("VLOGKIT_3D_ENGINE", "eevee")

    def render_plan(self, quality: str | None = None) -> dict:
        w, h = self.layout.size
        p = plan.render_plan(
            self.spec, self.beats, self.ctx.work / "frames", FPS, (w, h), self.engine, quality
        )
        scale = float(os.environ.get("VLOGKIT_3D_RES", "1") or 1)  # drafts, machines without a GPU
        if scale < 1:
            p["resolution_scale"] = max(0.1, scale)
            for s in p["shots"]:  # a smaller render is another render: its own cache key
                s["key"] += f"@{p['resolution_scale']:.2f}"
        return p

    def cuts(self) -> list[float]:
        return [b.t0 for b in self.beats[1:]]

    def notes(self) -> list[tuple[float, str]]:
        return [
            (b.t0, n) for b in self.beats for n in ([b.raw["notes"]] if b.raw.get("notes") else [])
        ]

    # ------------------------------------------------------------------ base: Blender
    def build_base(self, out: Path) -> None:
        p = self.render_plan()
        plan_path = self.ctx.work / "render_plan.json"
        plan_path.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        total = sum(s["frames"] for s in p["shots"])
        done = [0]

        edges = framing.Collector(
            {s["id"]: b.t0 for s, b in zip(p["shots"], self.beats, strict=True)}
        )

        def progress(line: str) -> None:
            if edges.feed(line):
                return
            if line.startswith("VKFRAME"):
                done[0] += 1
                if done[0] % 15 == 0 or done[0] == total:
                    print(f"   3B: {done[0]}/{total} kare", flush=True)
            elif line.startswith("VKSKIP"):
                print(f"   3B: {line.split()[1]} önbellekte", flush=True)

        blender.run(plan_path, progress)
        for note in edges.notes():
            print(f"   3B: {note}", flush=True)
        seq = self.ctx.work / "frames" / "_seq"
        if seq.exists():
            shutil.rmtree(seq)
        seq.mkdir(parents=True)
        n = 0
        for shot in p["shots"]:
            for f in range(1, shot["frames"] + 1):
                src = Path(shot["out"]) / f"{f:05d}.png"
                dst = seq / f"{n:06d}.png"
                try:
                    os.link(src, dst)
                except OSError:  # another drive, a file system without hard links
                    shutil.copyfile(src, dst)
                n += 1
        from vlogkit.ff import ffmpeg

        ffmpeg(
            [
                "-y",
                "-framerate",
                str(FPS),
                "-i",
                str(seq / "%06d.png"),
                "-vf",
                f"scale={self.layout.w}:{self.layout.h}:out_color_matrix=bt709:out_range=tv:"
                "flags=lanczos+accurate_rnd+full_chroma_int,format=yuv422p10le",
                *PRORES_HQ,
                "-r",
                str(FPS),
                str(out),
            ]
        )
        shutil.rmtree(seq)

    # ------------------------------------------------------------------ overlay
    def elements(self) -> list:
        els: list = []
        end = self.spec.get("end")
        caps = self.spec.get("captions", True)
        for b in self.beats:
            if caps and b.raw.get("caption", True):
                groups = plan.chunks(b.words)
                for k, (text, t0, t1) in enumerate(groups):
                    # each group stays until the next one starts (no two on screen at once); the
                    # last one holds a beat after the line so it can be read
                    until = groups[k + 1][1] if k + 1 < len(groups) else min(b.t1, t1 + 0.35)
                    els.append(
                        caption(
                            tr_upper(text),
                            t0,
                            until,
                            size=CAPTION_SIZE,
                            cy=CAPTION_Y,
                            layout=self.layout,
                        )
                    )
        hud = self.spec.get("hud")
        if hud:
            keys = []
            for b in self.beats:
                h = b.raw.get("hud")
                if h is not None:
                    keys.append(
                        (b.speech_at, float(h.get("value", 0)), h.get("text"), h.get("tag"))
                    )
            if keys:
                t_end = self.beats[-1].t1 - (float(end.get("seconds", 2.0)) if end else 0)
                els.append(Hud(hud.get("label", ""), keys, t_end, self.layout))
        if end:
            d = float(end.get("seconds", 2.0))
            T = self.beats[-1].t1
            els.append(
                EndCard(
                    T - d,
                    T,
                    tr_upper(end.get("tag", "PART 2 İÇİN")),
                    tr_upper(end.get("title", "TAKİPTE KAL")),
                    self.layout,
                )
            )
        return els

    # ------------------------------------------------------------------ audio
    def audio(self) -> AudioGraph:
        g = AudioGraph(self.duration)
        for b in self.beats:
            if b.speech is None:
                continue
            i = g.input(b.speech)
            ms = round(b.speech_at * 1000)
            g.chain(
                f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms},volume=1.0",
                stem="voice",
            )
        music = self.spec.get("music")
        if music and music.get("id"):
            i = g.input(self.ctx.asset(music["id"]))
            level = float(music.get("level", -26))
            fade = max(0.0, self.duration - 1.2)
            g.chain(
                f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:{self.duration:.3f},"
                f"volume={10 ** ((level + 12) / 20):.4f},afade=t=out:st={fade:.3f}:d=1.2",
                stem="music",
            )
        for b in self.beats:
            for s in b.raw.get("sfx") or []:
                at = max(0.0, b.t0 - (0.25 if s in ("whoosh", "riser") else 0.0))
                chain = {
                    "whoosh": lambda a: synth.whoosh(a, 0.45, gain=0.5),
                    "riser": lambda a: synth.whoosh(a, 0.9, center_hz=900, gain=0.45),
                    "pop": lambda a: synth.pop(a, gain=0.35),
                    "ding": lambda a: synth.pop(a, freq=1900, dur=0.25, gain=0.25),
                    "impact": lambda a: synth.impact(a, gain=0.7),
                    "boom": lambda a: synth.impact(a, freq=38, dur=1.2, gain=0.9),
                }[s](at)
                g.chain(chain, stem="sfx")
        # every counter change ticks
        for b in self.beats:
            if b.raw.get("hud") is not None and self.spec.get("hud") and b.index > 0:
                g.chain(synth.pop(b.speech_at, freq=1500, gain=0.18), stem="sfx")
        return g

    def sidecars(self) -> dict[str, str]:
        """The narration as text; the credits of the 3D library and of the voice model."""
        from vlogkit.scene3d import library

        out = {
            ".anlatim.txt": "\n".join(specmod.spoken(b["say"]) for b in self.spec["beats"]) + "\n"
        }
        if library.ready():
            out[".3b-lisans.md"] = library.credits_md()
        if any(p.parent.name == "voice" for p in [b.speech for b in self.beats if b.speech]):
            from vlogkit.speech import tts

            if tts.pick_engine(
                os.environ.get("VLOGKIT_TTS")
                or (self.spec.get("voice") or {}).get("engine", "auto")
            ) in ("pocket", "qwen"):
                eng = tts.pick_engine(
                    os.environ.get("VLOGKIT_TTS")
                    or (self.spec.get("voice") or {}).get("engine", "auto")
                )
                L = tts.QWEN_LICENSE if eng == "qwen" else tts.POCKET_LICENSE
                out[".ses-lisans.md"] = (
                    f"# Seslendirme\n\n- {L['title']}: {L['author']}\n- Lisans: {L['license']}\n- {L['page']}\n"
                )
        return out
