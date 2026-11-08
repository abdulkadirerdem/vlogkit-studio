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

- One beat = one narration line; its length is the measured speech plus `hold`. A beat is one
  shot, or several (`shots`: each starts at its `cue` word and changes the camera, set, actors,
  props, effects, crowd or look; what it leaves alone carries on from the beat, time running).
- `fx` (effects), prop `anim` / `hand` / `open`, `crowd`, `look` (security, news, phone...): see
  docs/3d.md. Any moment (`from`, `to`, `at`, `cue`) may be a word of the line.
- `do` is an action name, or a list of steps [{"do": "walk", "from": 0, "to": 0.6, "path": [...]},
  {"do": "shock", "from": 0.6}] with `from`/`to` as fractions of the beat.
- `[word]` in `say` is the yellow emphasis in the captions (brackets are not spoken).

`load()` validates everything and reports every problem at once, in Turkish, with the allowed
names, so a wrong name is fixed before a minute of rendering is spent.
"""

from __future__ import annotations

import contextlib
import json
import re
from pathlib import Path

from vlogkit.scene3d import catalog
from vlogkit.speech import tts

QUALITY = {  # samples, motion blur
    "draft": {"samples": 8, "motion_blur": False},
    # measured on an M4 (1080x1920 kesit shot): 24 samples 4.75 s a frame, 12 samples with the
    # lighter shadows below 1.37 s, side by side the same picture (EEVEE converges early)
    "normal": {"samples": 12, "motion_blur": True},
    "high": {"samples": 32, "motion_blur": True},
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
    "cut_whoosh",
    "format",
    "carry",
    "punch",
    "hook",
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
    "shots",
    "fx",
    "crowd",
    "look",
    "remove",
    "ton",
    "choices",
    "punch",
    "term",
    "count",
    "stamp",
}
_SHOT = {
    "cue",
    "set",
    "set_opts",
    "actors",
    "props",
    "camera",
    "fx",
    "crowd",
    "look",
    "notes",
    "wipe",
}
_FX = {"kind", "at", "pos", "on", "to", "size", "dur", "color", "n", "level", "item", "area",
       "target", "amount", "wall", "axis", "gap", "material", "leak", "debris"}  # fmt: skip
_PROP_ANIM = {"at", "to", "by", "rot", "tilt", "scale", "dur", "ease", "hide", "show", "spin"}
_CROWD = {"count", "area", "do", "facing", "seed", "at", "cheap", "spread", "speed"}
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
    "from",
    "from_zoom",
    "level",
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


def _cue_ok(where: str, say: str, cue, out: list[str]) -> None:
    """A moment: a fraction 0..1 or a word of the line."""
    from vlogkit.scene3d.plan import find_cue

    if cue is None or isinstance(cue, bool):
        return
    if isinstance(cue, (int, float)):
        if not 0 <= cue <= 1:
            out.append(f"{where}: an {cue}: 0 ile 1 arasında bir kesir ya da cümleden bir kelime")
        return
    if find_cue(say, str(cue)) is None:
        out.append(f"{where}: '{cue}' kelimesi cümlede yok (an: cümleden bir kelime ya da 0-1)")


def _check_fx(where: str, say: str, items, ids: set[str], out: list[str]) -> None:
    for j, f in enumerate(items or [], 1):
        fw = f"{where} efekt {j}"
        if not isinstance(f, dict) or f.get("kind") not in catalog.FX:
            out.append(f"{fw}: kind bilinmiyor (var olanlar: {_names(catalog.FX)})")
            continue
        for k in set(f) - _FX:
            out.append(f"{fw}: bilinmeyen alan '{k}' (olanlar: {_names(_FX)})")
        _cue_ok(fw, say, f.get("at"), out)
        if (
            f["kind"] in ("split", "pop", "vanish", "collapse", "dig", "drop")
            and f.get("target") not in ids
        ):
            out.append(
                f"{fw}: '{f['kind']}' için target: bu planda bir eşyanın id'si ({_names(ids) or 'yok'})"
            )


def _check_look(where: str, look, out: list[str]) -> None:
    if look is None:
        return
    kind = look.get("kind") if isinstance(look, dict) else look
    if kind not in catalog.LOOKS:
        out.append(f"{where}: look '{kind}' yok (olanlar: {_names(catalog.LOOKS)})")


def _check_props(where: str, say: str, props, actors: set[str], out: list[str]) -> set[str]:
    ids = set()
    for j, p in enumerate(props or [], 1):
        pw = f"{where} eşya {j}"
        if p.get("kind") not in catalog.PROPS:
            out.append(
                f"{pw}: bilinmeyen eşya '{p.get('kind')}' (var olanlar: {_names(catalog.PROPS)})"
            )
        if p.get("id"):
            ids.add(p["id"])
        if p.get("kind") == "layer":
            pits = {q.get("id") for q in props or [] if q.get("kind") == "pit"}
            if p.get("pit") not in pits:
                out.append(
                    f"{pw}: layer için pit: bu planda bir pit id'si ({_names(pits) or 'pit yok'})"
                )
        for k, m in enumerate(p.get("anim") or [], 1):
            for x in set(m) - _PROP_ANIM:
                out.append(f"{pw} anim {k}: bilinmeyen alan '{x}' (olanlar: {_names(_PROP_ANIM)})")
            _cue_ok(f"{pw} anim {k}", say, m.get("at"), out)
        if p.get("open"):
            _cue_ok(f"{pw} open", say, p["open"].get("at"), out)
        if p.get("pump"):
            _cue_ok(f"{pw} pump", say, p["pump"].get("at"), out)
        hand = p.get("hand")
        steps = [{"who": hand}] if isinstance(hand, str) else hand or []
        for st in steps:
            if st.get("who") not in actors:
                out.append(f"{pw} hand: '{st.get('who')}' bu planda oyuncu değil")
            _cue_ok(f"{pw} hand", say, st.get("at"), out)
    return ids


def _check_steps(where: str, a: dict, out: list[str], say: str = "") -> None:
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
            if k in st:
                _cue_ok(f"{where} adım {i + 1} {k}", say, st[k], out)
        if st["do"] in ("walk", "run", "sneak", "jog", "fly") and not (
            st.get("path") or a.get("path")
        ):
            out.append(f"{where}: '{st['do']}' için path gerekli: [[x, y], [x, y], ...]")


def _check_scope(
    w: str, say: str, eff: dict, cast: dict, out: list[str], own: dict, beat: dict, seen: set[int]
) -> None:
    """One shot's actors, props, camera, effects, look and crowd (each list checked once even when
    several shots share the beat's)."""

    def fresh(key: str) -> bool:
        v = eff.get(key)
        if v is None:
            return False
        if key not in own:  # the beat's own: check it with the first shot only
            if id(v) in seen:
                return False
            seen.add(id(v))
        return True

    names = {a.get("who") for a in eff.get("actors") or []}
    if fresh("actors"):
        for j, a in enumerate(eff.get("actors") or [], 1):
            aw = f"{w} oyuncu {j}"
            for k in set(a) - _ACTOR:
                out.append(f"{aw}: bilinmeyen alan '{k}' (olanlar: {_names(_ACTOR)})")
            if a.get("who") not in cast:
                out.append(f"{aw}: '{a.get('who')}' cast'te yok (cast: {_names(cast) or 'boş'})")
            if a.get("face", "happy") not in catalog.FACES:
                out.append(
                    f"{aw}: yüz ifadesi '{a.get('face')}' yok (olanlar: {', '.join(catalog.FACES)})"
                )
            _check_steps(aw, a, out, say)
            for fc in a.get("faces") or []:
                _cue_ok(f"{aw} faces", say, fc.get("at"), out)
    ids = {p.get("id") for p in eff.get("props") or [] if p.get("id")}
    if fresh("props"):
        _check_props(w, say, eff.get("props"), names, out)
    for a in eff.get("actors") or []:
        if isinstance(a.get("facing"), str) and a["facing"] not in names | ids:
            out.append(f"{w}: facing '{a['facing']}' bu planda bir oyuncu ya da eşya id'si değil")
    if fresh("camera"):
        cam = eff.get("camera") or {}
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
        if isinstance(on, list) and on and all(isinstance(x, str) for x in on):
            for x in on:
                if x not in names:
                    out.append(f"{w} kamera: on listesindeki '{x}' bu planda oyuncu değil")
        if isinstance(on, str) and on not in names | ids:
            out.append(
                f"{w} kamera: on='{on}' bu planda oyuncu ya da eşya değil (oyuncular: {_names(names) or 'yok'})"
            )
    if fresh("fx"):
        _check_fx(w, say, eff.get("fx"), ids, out)
    if fresh("look"):
        _check_look(w, eff.get("look"), out)
    if fresh("crowd"):
        c = eff.get("crowd") or {}
        for k in set(c) - _CROWD:
            out.append(f"{w} kalabalık: bilinmeyen alan '{k}' (olanlar: {_names(_CROWD)})")
        if c.get("do", "idle") not in catalog.CROWD_DO:
            out.append(
                f"{w} kalabalık: do '{c.get('do')}' yok (olanlar: {', '.join(catalog.CROWD_DO)})"
            )
        if not 1 <= int(c.get("count", 12)) <= 400:
            out.append(f"{w} kalabalık: count 1-400")
        _cue_ok(f"{w} kalabalık", say, c.get("at"), out)


def validate(spec: dict) -> list[str]:
    """Every problem at once. A build-up format (`carry`) is checked as it will be rendered: each
    beat with what it carries from the beats before."""
    from vlogkit.scene3d import formats

    out: list[str] = []
    if spec.get("format") and spec["format"] not in formats.FORMATS:
        out.append(f"format '{spec['format']}' yok (olanlar: {_names(formats.FORMATS)})")
    with contextlib.suppress(KeyError, TypeError, AttributeError):  # malformed: named below
        spec = formats.expand(spec)
    for k in set(spec) - _TOP:
        out.append(f"üst düzeyde bilinmeyen alan '{k}' (olanlar: {_names(_TOP)})")
    if not spec.get("output"):
        out.append("output gerekli: ~/yt-vlogs altında, uzantısız yol (ör. 'peki-ya/ziplama')")
    cap = spec.get("captions", True)
    if not isinstance(cap, bool) and cap not in ("chunk", "word"):
        out.append("captions: true | false | 'chunk' (2-3 kelime) | 'word' (tek kelime)")
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
        needs_set = not b.get("shots") or any("set" not in sh for sh in b["shots"])
        if (needs_set or "set" in b) and b.get("set") not in catalog.SETS:
            out.append(
                f"{w}: bilinmeyen mekân '{b.get('set')}' (var olanlar: {_names(catalog.SETS)})"
            )
        say = b.get("say", "")
        shots = b.get("shots") or []
        if shots and not isinstance(shots, list):
            out.append(f"{w}: shots bir liste olmalı")
            shots = []
        scopes = (
            [(w, {**b, **sh}, sh) for sh in [{}]]
            if not shots
            else [(f"{w} plan {k}", {**b, **sh}, sh) for k, sh in enumerate(shots, 1)]
        )
        cn = b.get("count")
        if cn is not None:
            if not isinstance(cn, dict) or not all(
                isinstance(cn.get(k), (int, float)) for k in ("from", "to")
            ):
                out.append(f"{w}: count {{from, to, at, dur, unit, label}} olmalı (from/to sayı)")
            else:
                _cue_ok(f"{w} count", say, cn.get("at"), out)
        stp = b.get("stamp")
        if stp is not None:
            if not isinstance(stp, dict) or not str(stp.get("text", "")).strip():
                out.append(f"{w}: stamp {{text, at, ok}} olmalı")
            else:
                _cue_ok(f"{w} stamp", say, stp.get("at"), out)
        tm = b.get("term")
        if tm is not None:
            if not isinstance(tm, dict) or not str(tm.get("text", "")).strip():
                out.append(f"{w}: term {{text, at}} olmalı")
            else:
                _cue_ok(f"{w} term", say, tm.get("at"), out)
        ch = b.get("choices")
        if ch is not None:
            items = ch.get("items") if isinstance(ch, dict) else None
            if not isinstance(items, list) or not 2 <= len(items) <= 4:
                out.append(f"{w}: choices.items 2-4 seçenek olmalı")
            elif any(len(str(x)) > 18 for x in items):
                out.append(f"{w}: choices seçenekleri kısa olmalı (en çok 18 harf)")
            if isinstance(ch, dict):
                _cue_ok(f"{w} choices", say, ch.get("at"), out)
                pk = ch.get("pick")
                if pk is not None:
                    n = pk.get("n") if isinstance(pk, dict) else None
                    if not isinstance(n, int) or not 1 <= n <= len(items or []):
                        out.append(f"{w}: choices.pick.n seçeneklerden birinin numarası olmalı")
                    else:
                        _cue_ok(f"{w} choices.pick", say, pk.get("at"), out)
        for k, sh in enumerate(shots, 1):
            wp = sh.get("wipe")
            if wp is not None and k == 1 and i == 1:
                out.append(f"{w} plan 1: wipe önceki planla karşılaştırır, ilk planda olamaz")
            if isinstance(wp, dict) and set(wp) - {"labels", "hold"}:
                out.append(f"{w} plan {k}: wipe alanları labels, hold")
            for x in set(sh) - _SHOT:
                out.append(f"{w} plan {k}: bilinmeyen alan '{x}' (olanlar: {_names(_SHOT)})")
            if k > 1 and sh.get("cue") is None:
                out.append(f"{w} plan {k}: cue gerekli (planın başladığı kelime ya da 0-1)")
            _cue_ok(f"{w} plan {k}", say, sh.get("cue"), out)
            if "set" in sh and sh["set"] not in catalog.SETS:
                out.append(
                    f"{w} plan {k}: bilinmeyen mekân '{sh['set']}' (var olanlar: {_names(catalog.SETS)})"
                )
        seen: set[int] = set()
        for sw, eff, own in scopes:
            _check_scope(sw if shots else w, say, eff, cast, out, own, b, seen)
        for s in b.get("sfx") or []:
            sid = s.get("id") if isinstance(s, dict) else s
            if sid not in catalog.SFX:
                out.append(f"{w}: ses efekti '{sid}' yok (olanlar: {', '.join(catalog.SFX)})")
            if isinstance(s, dict):
                _cue_ok(f"{w} ses efekti", say, s.get("at"), out)
        if isinstance(b.get("hud"), dict):
            _cue_ok(f"{w} sayaç", say, b["hud"].get("at"), out)
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
