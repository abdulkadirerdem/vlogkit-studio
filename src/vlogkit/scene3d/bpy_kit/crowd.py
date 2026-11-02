"""Crowds: many people in a shot without many builds.

A handful of distinct people are built (random sex, skin, hair, clothes, height); everyone else is
a cheap copy of one of them (the meshes are shared, each copy has its own skeleton and its own
clip offset), so 40 people cost about as much as 6. Far crowds (`"cheap": true`, or more than 60
people) use the kit's simple low-detail people.

    {"count": 30, "area": [x0, y0, x1, y1], "do": "cheer", "facing": 0, "seed": 1, "at": "word"}
"""

from __future__ import annotations

import math
import random

import bpy

from . import human, humanim, props

SKINS = ("light", "light", "dark", "#c68b5e", "#e0ac83", "#8d5a3b")
COLORS = ("#d94f3d", "#2f6db5", "#f2b134", "#3a9d5d", "#7a4fb3", "#e7e3da", "#24282e", "#e58fb0",
          "#4fb3c9", "#9c6b3f")  # fmt: skip
HAIR_COLORS = ("#2b1d14", "#1a1410", "#5a3a22", "#a5753f", "#c9b18a", "#3b2a20")
UNIQUE = 6


def _spec(rng: random.Random) -> dict:
    sex = rng.choice(("male", "female"))
    return {
        "sex": sex,
        "skin": rng.choice(SKINS),
        "hair": rng.choice(("short", "buzzed", "long", "buns") if sex == "female" else ("short", "buzzed", "bald", "short")),
        "hair_color": rng.choice(HAIR_COLORS),
        "top": rng.choice(("tshirt", "longsleeve", "hoodie", "tshirt", "coat")),
        "shirt": rng.choice(COLORS),
        "bottom": rng.choice(("jeans", "trousers", "jeans", "shorts") if sex == "male" else ("jeans", "skirt", "trousers")),
        "pants": rng.choice(("#2f3e5c", "#3b3b3b", "#6b5b45", "#1f2a3a", "#8a8f99")),
        "shoes": rng.choice(("#f2f2f2", "#1b1b1b", "#c9302c")),
        "height": rng.uniform(0.94, 1.05) * (0.95 if sex == "female" else 1.0),
    }  # fmt: skip


def _copy(src: human.Human, name: str) -> human.Human:
    arm = src.root.copy()  # its own pose; the armature data is shared
    arm.name = f"{name}.rig"
    arm.animation_data_clear()
    bpy.context.collection.objects.link(arm)
    parts = []
    for o in src.parts:
        c = o.copy()  # the mesh is shared
        c.name = f"{name}.{o.name.split('.', 1)[-1]}"
        bpy.context.collection.objects.link(c)
        c.parent = arm
        for m in c.modifiers:
            if m.type == "ARMATURE":
                m.object = arm
        parts.append(c)
    body = next((p for p in parts if p.name.endswith(src.body.name.split(".", 1)[-1])), parts[0])
    return human.Human(name, arm, body, parts, src.spec, src.height)


def _spots(rng: random.Random, n: int, area, spread: float) -> list[tuple[float, float]]:
    """Positions inside the area, kept a body apart (a jittered grid, nearer rows first)."""
    x0, y0, x1, y1 = area
    w, d = max(0.5, x1 - x0), max(0.5, y1 - y0)
    cols = max(1, round(math.sqrt(n * w / d)))
    rows = math.ceil(n / cols)
    out = []
    for k in range(n):
        r, c = divmod(k, cols)
        x = x0 + (c + 0.5 + rng.uniform(-0.35, 0.35) * spread) * w / cols
        y = y0 + (r + 0.5 + rng.uniform(-0.35, 0.35) * spread) * d / rows
        out.append((x, y))
    return out


def build(c: dict, fps: float, span: int) -> list:
    rng = random.Random(int(c.get("seed", 1)))
    n = int(c.get("count", 12))
    area = c.get("area") or [-5, 3, 5, 10]
    do = c.get("do", "idle")
    f_at = max(1, 1 + round(float(c.get("t", 0)) * fps))
    spots = _spots(rng, n, area, float(c.get("spread", 1.0)))
    facing = c.get("facing", 0)
    if c.get("cheap") or n > 60 or not human.LIB:
        return _cheap(c, rng, spots, fps, span, f_at)
    uniq = [human.build(f"crowd{k}", _spec(rng)) for k in range(min(UNIQUE, n))]
    people = []
    for k, (x, y) in enumerate(spots):
        p = uniq[k] if k < len(uniq) else _copy(uniq[k % len(uniq)], f"crowd{k}")
        p.root.location = (x, y, 0)
        face = facing if isinstance(facing, (int, float)) else 0
        p.root.rotation_euler = (0, 0, math.radians(face + rng.uniform(-18, 18)))
        p.root.keyframe_insert("location", frame=1)
        p.root.keyframe_insert("rotation_euler", frame=1)
        _act(p, do, rng, fps, span, f_at, c)
        people.append(p)
    return people


def _act(p, do: str, rng: random.Random, fps: float, span: int, f_at: int, c: dict) -> None:
    pf = humanim.Performer(p, fps, span)
    delay = round(rng.uniform(0, 0.35) * fps)  # nobody reacts on the same frame
    start = min(span, f_at + delay)
    if start > 1:
        pf.clip("talk" if rng.random() < 0.4 else "idle", 1, start)
    end = span + 1
    if do in ("walk", "run", "panic"):
        h = p.root.rotation_euler.z
        speed = float(c.get("speed", {"walk": 1.3, "run": 4.5, "panic": 5.0}[do])) * rng.uniform(
            0.85, 1.15
        )
        dist = speed * (end - start) / fps
        x, y = p.root.location.x, p.root.location.y
        path = [[x, y], [x + math.sin(h) * dist, y - math.cos(h) * dist]]
        pf.move(path, start, end, "walk" if do == "walk" else "run")
        if do == "panic":
            pf.gesture("scared", start, end)
    elif do == "jump":
        f = start
        while f + round(0.9 * fps) < end:
            f = pf.jump(f, f + round(0.9 * fps), rng.uniform(0.3, 0.55)) + round(
                rng.uniform(0, 0.3) * fps
            )
    elif do in ("cheer", "shock", "point_up"):
        pf.clip("idle", start, end)
        pf.gesture(do, start, end)
    elif do == "dance":
        pf.clip("dance", start, end, rng.uniform(0.9, 1.1))
    elif do == "talk":
        pf.clip("talk", start, end, rng.uniform(0.9, 1.1))
    else:
        pf.clip("idle", start, end, rng.uniform(0.85, 1.1))
    pf.fill_idle()
    pf.bake_gestures()


def _cheap(c: dict, rng: random.Random, spots, fps: float, span: int, f_at: int) -> list:
    out = []
    do = c.get("do", "idle")
    for k, (x, y) in enumerate(spots):
        r = props.place(
            "crowd_person",
            f"crowdp{k}",
            {
                "at": [x, y],
                "color": rng.choice(COLORS),
                "skin": rng.choice(("#e9b98f", "#c68b5e", "#8d5a3b")),
            },
        )
        r.rotation_euler.z = math.radians(rng.uniform(-20, 20))
        if do in ("cheer", "jump", "panic", "shock"):
            amp = 0.35 if do == "jump" else 0.12
            period = rng.uniform(0.45, 0.7) * fps
            f = f_at + round(rng.uniform(0, 0.3) * fps)
            r.keyframe_insert("location", index=2, frame=max(1, f))
            while f < span:
                for df, z in ((period / 2, amp), (period, 0.0)):
                    r.location.z = z
                    r.keyframe_insert("location", index=2, frame=round(f + df))
                f += period
        out.append(r)
    return out
