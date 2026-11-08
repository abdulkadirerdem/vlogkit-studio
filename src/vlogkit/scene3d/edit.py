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
from vlogkit.config import ASSETS_DIR
from vlogkit.export.encode import SHORTS
from vlogkit.graphics.elements import EndCard, caption
from vlogkit.graphics.style import VERTICAL, tr_upper
from vlogkit.project import Edit
from vlogkit.scene3d import blender, cards, framing, plan
from vlogkit.scene3d import spec as specmod
from vlogkit.scene3d.hud import Hud
from vlogkit.video.graph import PRORES_HQ

FPS = 30
CAPTION_Y = 1010  # mid-frame, over the action, clear of the bottom title block
CAPTION_SIZE = 104
WORD_SIZE = 124  # a single word on screen reads bigger


def looked(shot: dict, f: int, src: Path):
    """Frame f of a shot (1 = its first) with the shot's look drawn over it."""
    from PIL import Image

    from vlogkit.scene3d import looks

    img = Image.open(src).convert("RGB")
    t = (f - 1) / FPS
    return looks.apply(img, shot["look"], t, shot["at"] + t, seed=f * 7 + len(shot["id"]))


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
        from vlogkit.scene3d import formats

        return formats.expand(specmod.load(self.project_dir / "scene.json"))

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
        """Every shot change (several per beat when a beat has `shots`)."""
        return [s["at"] for s in self.render_plan()["shots"][1:]]

    def when(self, b: plan.Beat, cue, default: float) -> float:
        """A cue of the beat (a word of its line or a fraction) on the video's timeline."""
        return default if cue is None else b.t0 + plan.cue_time(b, cue)

    def notes(self) -> list[tuple[float, str]]:
        return [
            (b.t0, n) for b in self.beats for n in ([b.raw["notes"]] if b.raw.get("notes") else [])
        ]

    # ------------------------------------------------------------------ base: Blender
    def build_base(self, out: Path) -> None:
        p = self.render_plan()
        for line in plan.mark_reuse(p):  # same shot, new length: resample, do not render again
            print(f"   3B: {line}", flush=True)
        plan_path = self.ctx.work / "render_plan.json"
        plan_path.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")
        total = sum(s["frames"] for s in p["shots"] if not s.get("reuse"))
        done = [0]

        edges = framing.Collector({s["id"]: s["at"] for s in p["shots"]})

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
        last = None  # the previous shot's last frame (a wipe compares with it)
        for shot in p["shots"]:
            have = plan.frames_on_disk(Path(shot["out"]), shot["frames"])
            nw = cards.wipe_frames(shot["wipe"], FPS) if shot.get("wipe") and last else 0
            for f in range(1, shot["frames"] + 1):
                src = Path(shot["out"]) / f"{plan.source_frame(f, shot['frames'], have):05d}.png"
                dst = seq / f"{n:06d}.png"
                if f <= nw:  # before | after, side by side, then the new one takes over
                    from PIL import Image

                    now = looked(shot, f, src) if shot.get("look") else Image.open(src)
                    cards.wipe_frame(Image.open(last), now, (f - 1) / FPS, shot["wipe"]).save(dst)
                elif shot.get("look"):  # the security camera, the news, the phone: drawn on top
                    looked(shot, f, src).save(dst)
                else:
                    try:
                        os.link(src, dst)
                    except OSError:  # another drive, a file system without hard links
                        shutil.copyfile(src, dst)
                n += 1
            last = seq / f"{n - 1:06d}.png"
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
        from vlogkit.scene3d import formats

        mode = formats.caption_mode(self.spec)
        for b in self.beats:
            cn = b.raw.get("count")
            if cn:  # a number running up with what happens (the depth while digging)
                t0 = self.when(b, cn.get("at"), b.speech_at)
                dur = float(cn.get("dur", 1.5))
                els.append(
                    cards.Counter(
                        float(cn["from"]), float(cn["to"]), t0, dur,
                        max(t0 + dur + 0.8, b.t1), self.layout,
                        cn.get("unit", ""), cn.get("label", ""),
                    )
                )  # fmt: skip
            tm = b.raw.get("term")
            if tm:  # the word the video teaches, as a big card
                t0 = self.when(b, tm.get("at"), b.speech_at)
                els.append(
                    cards.Term(
                        tm["text"],
                        t0,
                        max(t0 + 1.6, b.t1),
                        self.layout,
                        tm.get("tag", "BUNA DENİR"),
                    )
                )
            ch = b.raw.get("choices")
            ch_at = self.when(b, ch.get("at"), b.speech_at) if ch else None
            if ch:  # the closing question as numbered answers; it replaces the captions
                t_end = b.t1 - (
                    float(end.get("seconds", 2.0)) if end and b is self.beats[-1] else 0
                )
                if ch.get("dur"):  # shown for a while only (a question mid-video)
                    t_end = min(t_end, ch_at + float(ch["dur"]))
                pk = ch.get("pick")
                pick = (
                    {"n": int(pk["n"]), "ok": bool(pk.get("ok")),
                     "t": self.when(b, pk.get("at"), ch_at + 0.6)}
                    if pk else None
                )  # fmt: skip
                els.append(
                    cards.Choices(
                        ch.get("title") or "SENCE?",
                        list(ch["items"]),
                        ch_at,
                        max(ch_at + 1.0, t_end),
                        self.layout,
                        ch.get("ask", "CEVABINI YORUMA YAZ"),
                        pick,
                    )
                )
            st = b.raw.get("stamp")
            if st:  # the verdict: YANLIŞ / DOĞRU slammed on the frame
                t0 = self.when(b, st.get("at"), b.speech_at)
                els.append(
                    cards.Stamp(
                        st["text"], t0, min(b.t1, t0 + float(st.get("dur", 1.3))), self.layout,
                        st.get("color", "#2ecc71" if st.get("ok") else "#ff3b30"),
                    )
                )  # fmt: skip
            if mode != "off" and b.raw.get("caption", True):
                # word mode: one word at a time, bigger (the build-up formats)
                groups = plan.word_groups(b.words) if mode == "word" else plan.chunks(b.words)
                if ch_at is not None and ch.get("dur"):  # captions pause while it is up
                    ch_end = ch_at + float(ch["dur"])
                    groups = [g for g in groups if not (ch_at - 0.05 <= g[1] < ch_end)]
                elif ch_at is not None:
                    groups = [g for g in groups if g[1] < ch_at - 0.05]
                    if groups:
                        groups[-1] = (groups[-1][0], groups[-1][1], min(groups[-1][2], ch_at))
                for k, (text, t0, t1) in enumerate(groups):
                    # each group stays until the next one starts (no two on screen at once); the
                    # last one holds a beat after the line so it can be read
                    until = groups[k + 1][1] if k + 1 < len(groups) else min(b.t1, t1 + 0.35)
                    if ch_at is not None and t0 < ch_at:
                        until = min(until, ch_at)
                    els.append(
                        caption(
                            tr_upper(text),
                            t0,
                            until,
                            size=CAPTION_SIZE if mode != "word" else WORD_SIZE,
                            # a word is up for ~0.3 s: no fade, a quick pop, a heavy outline
                            **(
                                {
                                    "pop": 0.07,
                                    "fade": 0.01,
                                    "s0": 0.86,
                                    "stroke": round(WORD_SIZE * 0.1),
                                }
                                if mode == "word"
                                else {}
                            ),
                            cy=CAPTION_Y,
                            layout=self.layout,
                        )
                    )
        hook = self.spec.get("hook")
        if hook and hook.get("text"):  # the promise as a headline over the first seconds
            from vlogkit.graphics.captions import HookTitle

            # `at`: seconds in, so a dive can land first and the headline arrives with it
            t0 = float(hook.get("at", 0.0))
            # a counter at the top from the first beat (GÜN 1): the headline goes under it
            first_hud = self.spec.get("hud") and (self.beats[0].raw.get("hud") is not None)
            els.append(
                HookTitle(
                    tr_upper(hook["text"]), t0, t0 + float(hook.get("seconds", 2.6)), self.layout,
                    cy=600 * self.layout.scale if first_hud else None,
                )
            )  # fmt: skip
        hud = self.spec.get("hud")
        if hud:
            keys = []
            for b in self.beats:
                h = b.raw.get("hud")
                if h is not None:
                    keys.append(
                        (
                            self.when(b, h.get("at"), b.speech_at),
                            float(h.get("value", 0)),
                            h.get("text"),
                            h.get("tag"),
                        )
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
                cue = s.get("at") if isinstance(s, dict) else None
                s = s.get("id") if isinstance(s, dict) else s
                lead = 0.25 if s in ("whoosh", "riser") else 0.0
                at = max(0.0, self.when(b, cue, b.t0) - lead)
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
            h = b.raw.get("hud")
            if h is not None and self.spec.get("hud") and b.index > 0:
                at = self.when(b, h.get("at") if isinstance(h, dict) else None, b.speech_at)
                g.chain(synth.pop(at, freq=1500, gain=0.18), stem="sfx")
        # every cut inside a beat gets a soft whoosh unless the beat sets its own sounds
        for b in self.beats:
            shots = b.raw.get("shots") or []
            if len(shots) > 1 and not b.raw.get("sfx") and self.spec.get("cut_whoosh", True):
                for sh in shots[1:]:
                    at = self.when(b, sh.get("cue"), b.t0) - 0.12
                    g.chain(synth.whoosh(max(0.0, at), 0.3, gain=0.22), stem="sfx")
        return g

    def _uses_moon(self) -> bool:
        """Space shows the Moon; any shot may place one."""
        for b in self.spec["beats"]:
            for sh in [b, *(b.get("shots") or [])]:
                if sh.get("set") == "space" or any(
                    p.get("kind") == "moon" for p in sh.get("props") or []
                ):
                    return True
        return False

    def sidecars(self) -> dict[str, str]:
        """The narration as text; the credits of the 3D library and of the voice model."""
        from vlogkit.scene3d import library

        out = {
            ".anlatim.txt": "\n".join(specmod.spoken(b["say"]) for b in self.spec["beats"]) + "\n"
        }
        if library.ready():
            out[".3b-lisans.md"] = library.credits_md()
        moon = ASSETS_DIR / "moon" / "CREDITS.md"
        if moon.exists() and self._uses_moon():
            out[".3b-lisans.md"] = (
                out.get(".3b-lisans.md", "") + "\n" + moon.read_text(encoding="utf-8")
            )
        if any(p.parent.name == "voice" for p in [b.speech for b in self.beats if b.speech]):
            from vlogkit.speech import tts

            if tts.pick_engine(
                os.environ.get("VLOGKIT_TTS")
                or (self.spec.get("voice") or {}).get("engine", "auto")
            ) in ("pocket", "qwen", "voxcpm"):
                eng = tts.pick_engine(
                    os.environ.get("VLOGKIT_TTS")
                    or (self.spec.get("voice") or {}).get("engine", "auto")
                )
                L = {"qwen": tts.QWEN_LICENSE, "voxcpm": tts.VOX_LICENSE}.get(
                    eng, tts.POCKET_LICENSE
                )
                out[".ses-lisans.md"] = (
                    f"# Seslendirme\n\n- {L['title']}: {L['author']}\n- Lisans: {L['license']}\n- {L['page']}\n"
                )
        return out
