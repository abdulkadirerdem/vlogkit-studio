"""3D video formats: what kind of video a scene.json is. A format is a proven shape for a short
(the story pattern, the visual grammar, the captions, the pacing, the checks), written up for the
agent in docs/formats/<id>.md; this module holds the parts the code needs.

    "format": "kesit"

- `captions`: "chunk" (2-3 words, the default) or "word" (one word at a time, mid-frame).
- `carry`: the scene builds up: every beat starts with the props of the beats before it (moved
  where their `anim` left them; `hide` drops one, the beat's `remove` list drops by id) and with
  the last beat's set and set_opts, so a beat only writes what it adds or changes.
- `beats`: the scenario length range (docs/senaryo.md), `seconds`: the target length.
"""

from __future__ import annotations

import copy

FORMATS: dict[str, dict] = {
    "pekiya": {
        "title": "Peki ya?",
        "line": "Bir 'peki ya' sorusu, sonuçlar tırmanarak ekranda olur",
        "doc": "docs/formats/pekiya.md",
        "captions": "chunk",
        "carry": False,
        "beats": (6, 16),
        "seconds": (30, 60),
    },
    "kesit": {
        "title": "Kesitten inşa",
        "line": "Pasta gibi kesilmiş bir bahçede bir şey adım adım inşa edilir: Eğer… Ama… O yüzden…",
        "doc": "docs/formats/kesit.md",
        "captions": "word",
        "carry": True,
        "beats": (14, 28),
        "seconds": (55, 80),
    },
}
DEFAULT = "pekiya"


def get(spec: dict) -> dict:
    return FORMATS.get(spec.get("format") or DEFAULT, FORMATS[DEFAULT])


def caption_mode(spec: dict) -> str:
    c = spec.get("captions", True)
    if c is False:
        return "off"
    if isinstance(c, str):
        return c
    return get(spec)["captions"]


def _settle(p: dict) -> dict | None:
    """A carried prop as its last beat left it: moved to where its moves ended, no moves left."""
    p = copy.deepcopy(p)
    at = list(p.get("at", [0, 0]))
    for m in p.pop("anim", None) or []:
        if m.get("hide"):
            return None
        if m.get("to") is not None:
            at = list(m["to"])
        if m.get("by") is not None:
            by = [*m["by"], 0, 0][:3]
            at = [*at, 0, 0][:3]
            at = [at[0] + by[0], at[1] + by[1], at[2] + by[2]]
        if m.get("scale") is not None:
            p["scale"] = m["scale"]
        if m.get("rot") is not None:
            p["rot"] = m["rot"]
        if m.get("tilt") is not None:
            p["tilt"] = m["tilt"]
    p["at"] = at
    if p.get("open"):
        p["open"] = {**p["open"], "at": 0, "dur": 0.01}
    p.pop("hand", None)
    return p


def expand(spec: dict) -> dict:
    """The scene with every beat written out in full (carry formats build up beat by beat)."""
    if not (spec.get("carry") if "carry" in spec else get(spec)["carry"]):
        return spec
    out = copy.deepcopy(spec)
    carried: dict[str, dict] = {}
    order: list[str] = []
    last_set, last_opts = None, {}
    for b in out["beats"]:
        rm = b.pop("remove", None) or []
        if rm == "all" or "all" in rm:  # a fresh start (after a flash-forward opening)
            carried.clear()
            order.clear()
            rm = []
        for k in set(rm):
            carried.pop(k, None)
        own = b.get("props") or []
        own_ids = {p.get("id") for p in own if p.get("id")}
        kept = [carried[k] for k in order if k in carried and k not in own_ids]
        b["props"] = kept + own
        if not b.get("set") and last_set:
            b["set"] = last_set
        b["set_opts"] = {
            **(last_opts if b.get("set") == last_set else {}),
            **(b.get("set_opts") or {}),
        }
        last_set, last_opts = b["set"], b["set_opts"]
        for i, p in enumerate(own):
            key = p.get("id") or f"_auto{len(order)}_{i}"
            settled = _settle(p)
            if settled is None:
                carried.pop(key, None)
                continue
            if key not in carried:
                order.append(key)
            carried[key] = settled
    return out
