"""scene.json: what a 3D video is, in the few hundred lines the agent writes.

    {
      "title": "Peki ya herkes aynı anda zıplasaydı?",
      "output": "peki-ya/ziplama",                  # under ~/yt-vlogs, no extension
      "voice": {"engine": "auto", "voice": "male_1", "emotion": "heyecanli"},
      "quality": "normal",                          # draft | normal | high
      "music": {"id": "<library id>", "level": -26},  # optional; a kind="music" asset
      "cast": {"ali": {"shirt": "#f2b134", "hair": "short"}},
      "hud": {"label": "ZIPLAYAN İNSAN"},           # optional counter, top left
      "beats": [
        {"say": "Peki ya dünyadaki herkes aynı anda [zıplasaydı]?",
         "set": "room", "set_opts": {},
         "actors": [{"who": "ali", "at": [0, 0], "facing": 0, "face": "surprised",
                     "do": "jump", "talk": false}],
         "props": [{"kind": "calendar", "at": [1, 2], "text": "1"}],
         "camera": {"frame": "medium", "on": "ali", "move": "push"},
         "hud": {"value": 1, "text": "1", "tag": "BAŞLIYOR"},
         "sfx": ["whoosh"], "hold": 0.2}
      ],
      "end": {"tag": "PART 2 İÇİN", "title": "TAKİPTE KAL", "seconds": 2.0}
    }

- One beat = one narration line = one shot; its length is the measured speech plus `hold`.
- `do` is an action name, or a list of steps [{"do": "walk", "from": 0, "to": 0.6, "path": [...]},
  {"do": "shock", "from": 0.6}] with `from`/`to` as fractions of the beat.
- `[word]` in `say` is the yellow emphasis in the captions (brackets are not spoken).

`load()` validates everything and reports every problem at once, in Turkish, with the allowed
names, so a wrong name is fixed before a minute of rendering is spent.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from vlogkit.scene3d import catalog
from vlogkit.speech import tts

QUALITY = {  # samples, motion blur
    "draft": {"samples": 8, "motion_blur": False},
    "normal": {"samples": 24, "motion_blur": True},
    "high": {"samples": 64, "motion_blur": True},
}
_TOP = {
    "title",
    "output",
    "voice",
    "quality",
    "music",
    "cast",
    "hud",
    "beats",
    "end",
    "fps",
    "captions",
    "notes",
}
_BEAT = {
    "say",
    "set",
    "set_opts",
    "actors",
    "props",
    "camera",
    "hud",
    "sfx",
    "hold",
    "caption",
    "notes",
}
_ACTOR = {"who", "at", "facing", "face", "do", "path", "talk", "look", "size", "faces"}
_CAMERA = {
    "frame",
    "on",
    "move",
    "angle",
    "tilt",
    "amount",
    "zoom",
    "lens",
    "offset",
    "dof",
    "fstop",
    "shake",
    "ease",
}
_CAST = {
    "body",
    "skin",
    "shirt",
    "pants",
    "shoes",
    "hair",
    "hair_color",
    "sleeves",
    "beard",
    "mustache",
    "glasses",
    "outfit",
    "hood_color",
    "cap_color",
    "style",
    "sex",
    "top",
    "bottom",
    "height",
    "build",
}
_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}){1,2}$")


class SpecError(ValueError):
    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("scene.json'da düzeltilecekler:\n" + "\n".join(f"- {p}" for p in problems))


def spoken(text: str) -> str:
    """The narration as spoken: emphasis brackets removed."""
    return re.sub(r"\s+", " ", text.replace("[", "").replace("]", "")).strip()


def _names(d) -> str:
    return ", ".join(sorted(d))


def _check_steps(where: str, a: dict, out: list[str]) -> None:
    do = a.get("do")
    steps = do if isinstance(do, list) else ([{"do": do}] if do else [])
    for i, st in enumerate(steps):
        if not isinstance(st, dict) or "do" not in st:
            out.append(
                f'{where}: do listesi {{"do": ..., "from": 0, "to": 1}} adımlarından oluşmalı'
            )
            continue
        if st["do"] not in catalog.ACTIONS:
            out.append(
                f"{where}: bilinmeyen hareket '{st['do']}' (var olanlar: {_names(catalog.ACTIONS)})"
            )
        for k in ("from", "to"):
            if k in st and not (isinstance(st[k], (int, float)) and 0 <= st[k] <= 1):
                out.append(f"{where} adım {i + 1}: '{k}' 0 ile 1 arasında bir kesir olmalı")
        if st["do"] in ("walk", "run", "sneak") and not (st.get("path") or a.get("path")):
            out.append(f"{where}: '{st['do']}' için path gerekli: [[x, y], [x, y], ...]")


def validate(spec: dict) -> list[str]:
    out: list[str] = []
    for k in set(spec) - _TOP:
        out.append(f"üst düzeyde bilinmeyen alan '{k}' (olanlar: {_names(_TOP)})")
    if not spec.get("output"):
        out.append("output gerekli: ~/yt-vlogs altında, uzantısız yol (ör. 'peki-ya/ziplama')")
    if spec.get("quality", "normal") not in QUALITY:
        out.append(f"quality: {_names(QUALITY)}")
    voice = spec.get("voice") or {}
    if voice.get("engine", "auto") not in tts.ENGINES:
        out.append(f"voice.engine: {', '.join(tts.ENGINES)}")
    if voice.get("emotion") and str(voice["emotion"]).lower() not in tts.POCKET_EMOTION_TAGS:
        out.append(f"voice.emotion '{voice['emotion']}' yok: {', '.join(tts.POCKET_EMOTIONS)}")
    if (
        voice.get("voice")
        and voice.get("engine", "auto") in ("auto", "pocket")
        and voice["voice"] not in tts.POCKET_VOICES
    ):
        out.append(f"voice.voice '{voice['voice']}' yok: {_names(tts.POCKET_VOICES)}")
    cast = spec.get("cast") or {}
    for name, c in cast.items():
        for k in set(c) - _CAST:
            out.append(f"cast.{name}: bilinmeyen alan '{k}' (olanlar: {_names(_CAST)})")
        if c.get("body", "adult") not in catalog.BODIES:
            out.append(f"cast.{name}.body: {', '.join(catalog.BODIES)}")
        if c.get("hair", "short") not in catalog.HAIR:
            out.append(f"cast.{name}.hair: {', '.join(catalog.HAIR)}")
        if c.get("outfit", "casual") not in catalog.OUTFITS:
            out.append(f"cast.{name}.outfit: {', '.join(catalog.OUTFITS)}")
        if c.get("style", "realistic") not in ("realistic", "toon"):
            out.append(f"cast.{name}.style: realistic | toon")
        if c.get("sex", "male") not in ("male", "female"):
            out.append(f"cast.{name}.sex: male | female")
        if c.get("top", "tshirt") not in catalog.TOPS:
            out.append(f"cast.{name}.top: {', '.join(catalog.TOPS)}")
        if c.get("bottom", "jeans") not in catalog.BOTTOMS:
            out.append(f"cast.{name}.bottom: {', '.join(catalog.BOTTOMS)}")
        if "skin" in c and c["skin"] not in ("light", "dark") and not _HEX.match(str(c["skin"])):
            out.append(f"cast.{name}.skin: light | dark | '#rrggbb'")
        for k in ("shirt", "pants", "shoes", "hair_color", "hood_color", "cap_color"):
            if k in c and not _HEX.match(str(c[k])):
                out.append(f"cast.{name}.{k}: renk '#rrggbb' biçiminde olmalı")
    beats = spec.get("beats") or []
    if not beats:
        out.append("beats boş: en az bir beat gerekli")
    for i, b in enumerate(beats, 1):
        w = f"beat {i}"
        for k in set(b) - _BEAT:
            out.append(f"{w}: bilinmeyen alan '{k}' (olanlar: {_names(_BEAT)})")
        if not spoken(b.get("say", "")):
            out.append(f"{w}: 'say' (anlatım cümlesi) boş")
        if b.get("set") not in catalog.SETS:
            out.append(
                f"{w}: bilinmeyen mekân '{b.get('set')}' (var olanlar: {_names(catalog.SETS)})"
            )
        for j, a in enumerate(b.get("actors") or [], 1):
            aw = f"{w} oyuncu {j}"
            for k in set(a) - _ACTOR:
                out.append(f"{aw}: bilinmeyen alan '{k}' (olanlar: {_names(_ACTOR)})")
            if a.get("who") not in cast:
                out.append(f"{aw}: '{a.get('who')}' cast'te yok (cast: {_names(cast) or 'boş'})")
            if a.get("face", "happy") not in catalog.FACES:
                out.append(
                    f"{aw}: yüz ifadesi '{a.get('face')}' yok (olanlar: {', '.join(catalog.FACES)})"
                )
            _check_steps(aw, a, out)
        for j, p in enumerate(b.get("props") or [], 1):
            if p.get("kind") not in catalog.PROPS:
                out.append(
                    f"{w} eşya {j}: bilinmeyen eşya '{p.get('kind')}' (var olanlar: {_names(catalog.PROPS)})"
                )
        cam = b.get("camera") or {}
        for k in set(cam) - _CAMERA:
            out.append(f"{w} kamera: bilinmeyen alan '{k}' (olanlar: {_names(_CAMERA)})")
        if cam.get("frame", "medium") not in catalog.FRAMES:
            out.append(
                f"{w} kamera: frame '{cam.get('frame')}' yok (olanlar: {_names(catalog.FRAMES)})"
            )
        if cam.get("move", "push") not in catalog.MOVES:
            out.append(
                f"{w} kamera: move '{cam.get('move')}' yok (olanlar: {_names(catalog.MOVES)})"
            )
        on = cam.get("on")
        names = {a.get("who") for a in b.get("actors") or []}
        if isinstance(on, str) and on not in names:
            out.append(
                f"{w} kamera: on='{on}' bu beat'te oyuncu değil (oyuncular: {_names(names) or 'yok'})"
            )
        for s in b.get("sfx") or []:
            if s not in catalog.SFX:
                out.append(f"{w}: ses efekti '{s}' yok (olanlar: {', '.join(catalog.SFX)})")
    return out


def load(path: Path) -> dict:
    try:
        spec = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SpecError([f"JSON okunamadı: {e}"]) from e
    problems = validate(spec)
    if problems:
        raise SpecError(problems)
    return spec
