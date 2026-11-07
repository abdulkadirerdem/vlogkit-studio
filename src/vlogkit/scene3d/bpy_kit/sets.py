"""Sets: the place a shot happens in. Each builder dresses the stage, lights it and returns the
spots where actors usually stand plus a default camera framing.

Coordinates: the stage centre is (0, 0); the back wall of rooms is at +Y, the camera looks from -Y.
`opts` per set: "wall", "floor" colors, "night": true, "props": False to leave the dressing out.
"""

from __future__ import annotations

import math
import random

import bpy

from . import look, props, shapes

R = math.radians


def _room(
    o,
    wall="#e6eef2",
    floor="#c8925c",
    w=7.0,
    d=5.0,
    h=3.2,
    tiles=None,
    floor_tex="laminate_floor_02",
    floor_tile=2.0,
):
    wall_m = look.pbr("painted_plaster_wall", o.get("wall", wall), 2.5, fallback=wall)
    floor_m = look.pbr(floor_tex, o.get("floor_tint"), floor_tile, fallback=o.get("floor", floor))
    shapes.rbox("set.floor", (w, d + 6, 0.2), floor_m, (0, 0, -0.1), 0.01)
    shapes.rbox("set.back", (w, 0.2, h), wall_m, (0, d / 2, h / 2), 0.01)
    shapes.rbox("set.left", (0.2, d + 2, h), wall_m, (-w / 2, 0.5, h / 2), 0.01)
    shapes.rbox("set.right", (0.2, d + 2, h), wall_m, (w / 2, 0.5, h / 2), 0.01)
    shapes.rbox("set.skirting", (w, 0.05, 0.12), look.mat("#ffffff"), (0, d / 2 - 0.12, 0.06), 0.01)
    if tiles:  # a tiled lower wall (bathroom, kitchen): a grid of slightly raised tiles
        tm = look.mat(tiles, rough=0.25, spec=0.6)
        grout = look.mat("#d4dade", rough=0.8)
        shapes.rbox("set.grout", (w, 0.05, 1.6), grout, (0, d / 2 - 0.11, 0.8), 0.0)
        for i in range(int(w / 0.3)):
            for j in range(5):
                shapes.rbox(
                    f"set.tile{i}_{j}",
                    (0.28, 0.03, 0.3),
                    tm,
                    (-w / 2 + 0.15 + i * 0.3, d / 2 - 0.14, 0.16 + j * 0.32),
                    0.01,
                )
    if o.get("night"):
        if not look.env("dusk", 0.25, visible=False):
            look.world("#1b2340", "#2b3150", 0.35)
        look.point((0, 0, h - 0.3), 250, "#ffd59e", 0.3, "ceiling")
    else:
        if not look.env("interior", 0.9, visible=False):
            look.world("#d8ecf8", "#fff4e8", 0.85)
        look.sun(3.5, 10, (55, 5, 25))
        look.area((-2.0, -3.5, 3.0), (0, 0.5, 1.2), 380, 5, "#ffffff", "fill")
    look.area((2.5, 1.5, 2.8), (0, 0, 1.0), 120, 2, "#ffe1c0", "rim")


def room(o):
    _room(o)
    if o.get("props", True):
        props.place("bed", "bed", {"at": (-1.9, 1.3), "color": o.get("accent", "#3f6db3")})
        props.place("window", "win", {"at": (0.6, 2.38)})
        props.place("desk", "desk", {"at": (2.3, 2.0)})
        props.place("chair", "chair", {"at": (2.3, 1.35), "rot": 180})
        props.place("plant", "plant", {"at": (3.1, 2.1)})
        props.place("laptop", "lap", {"at": (2.3, 2.0, 0.79)})
        props.place("bookshelf", "shelf", {"at": (-0.3, 2.2)})
    return {
        "spots": {
            "center": (0, 0),
            "left": (-1.2, 0.2),
            "right": (1.2, 0.2),
            "bed": (-1.9, 1.0),
            "desk": (2.3, 1.0),
        },
        "target": (0, 0.3, 1.1),
    }


def bedroom_night(o):
    return room({**o, "night": True})


def bathroom(o):
    _room(
        o,
        wall="#f1f4f6",
        floor="#d9dfe4",
        w=5.0,
        d=4.0,
        tiles=o.get("tiles", "#9fd0c7"),
        floor_tex="floor_tiles_06",
        floor_tile=1.2,
    )
    if o.get("props", True):
        props.place("toilet", "toilet", {"at": (0.9, 1.45)})
        props.place("sink", "sink", {"at": (-0.9, 1.72)})
        shapes.rbox(
            "set.mirror",
            (0.7, 0.03, 0.9),
            look.mat("#cfe6f0", rough=0.03, metal=0.9),
            (-0.9, 1.98, 1.65),
            0.02,
        )
        props.place("plant", "plant", {"at": (-2.0, 1.6), "scale": 0.8})
    return {
        "spots": {"center": (0, 0.3), "toilet": (0.9, 0.9), "sink": (-0.9, 1.1)},
        "target": (0, 0.8, 1.0),
    }


def classroom(o):
    _room(o, wall="#efe5d2", floor="#c9a27a", w=9.0, d=6.0)
    board = look.mat("#2f5a46", rough=0.85)
    shapes.rbox("set.board", (4.0, 0.06, 1.5), board, (0, 2.9, 1.75), 0.02)
    shapes.rbox("set.boardframe", (4.12, 0.05, 1.62), look.mat("#a8784e"), (0, 2.92, 1.75), 0.02)
    if o.get("text"):
        shapes.text(
            "set.boardtxt",
            o["text"],
            look.mat("#f4f4f0", rough=0.9),
            0.32,
            (0, 2.86, 1.8),
            font_path=props.FONT,
        )
    if o.get("props", True):
        for i, x in enumerate((-2.6, -0.9, 0.9, 2.6)):
            for j, y in enumerate((-0.4, -1.8)):
                props.place("school_desk", f"d{i}{j}", {"at": (x, y), "rot": 180})
                props.place("chair", f"c{i}{j}", {"at": (x, y - 0.45), "rot": 180})
        props.place("clock", "clock", {"at": (3.0, 2.88), "z": 2.6})
    return {
        "spots": {"teacher": (1.5, 2.0), "front": (0, 1.4), "student": (-0.9, -0.95)},
        "target": (0, 1.0, 1.3),
    }


def kitchen(o):
    _room(
        o,
        wall="#f4efe6",
        floor="#d5c4ad",
        w=7.0,
        d=5.0,
        tiles="#f2f2f2",
        floor_tex="floor_tiles_06",
        floor_tile=1.5,
    )
    if o.get("props", True):
        props.place("counter", "cnt", {"at": (-0.7, 2.1), "w": 3.0})
        props.place("stove", "stove", {"at": (1.3, 2.15)})
        props.place("fridge", "fridge", {"at": (2.6, 2.1)})
        props.place("plant", "plant", {"at": (-1.9, 2.1, 0.91), "scale": 0.6})
    return {
        "spots": {"center": (0, 0.6), "stove": (1.3, 1.4), "fridge": (2.3, 1.3)},
        "target": (0.4, 1.0, 1.1),
    }


def office(o):
    _room(
        o,
        wall="#e9edf1",
        floor="#8f9aa6",
        w=9.0,
        d=6.0,
        floor_tex="concrete_floor_02",
        floor_tile=3.0,
    )
    if o.get("props", True):
        for i, x in enumerate((-2.4, 0, 2.4)):
            props.place("desk", f"desk{i}", {"at": (x, 1.2), "color": "#e7e1d8"})
            props.place("laptop", f"lap{i}", {"at": (x, 1.2, 0.79)})
            props.place("armchair", f"ch{i}", {"at": (x, 0.45), "rot": 180, "scale": 0.85})
        props.place("bookshelf", "shelf", {"at": (-3.8, 2.6)})
        props.place("plant", "plant", {"at": (3.8, 2.4)})
        props.place("window", "win", {"at": (0, 2.98), "w": 3.0})
    return {"spots": {"center": (0, 0), "desk": (0, 0.6)}, "target": (0, 1.0, 1.1)}


def gym(o):
    _room(
        o,
        wall="#d8dde2",
        floor="#3a3f45",
        w=10.0,
        d=7.0,
        floor_tex="concrete_floor_02",
        floor_tile=3.0,
    )
    shapes.rbox("set.mat", (6, 4, 0.03), look.mat("#2b2f33", rough=0.9), (0, 0.5, 0.015), 0.005)
    if o.get("text", "GÜÇ SALONU"):
        shapes.rbox("set.banner", (3.6, 0.05, 0.7), look.mat("#d9483b"), (0, 3.4, 2.4), 0.02)
        shapes.text(
            "set.bannertxt",
            o.get("text", "GÜÇ SALONU"),
            look.mat("#ffffff"),
            0.36,
            (0, 3.36, 2.4),
            font_path=props.FONT,
        )
    if o.get("props", True):
        props.place("weight_bench", "bench", {"at": (0, 1.2)})
        props.place("barbell", "bar", {"at": (0, 1.75), "z": 1.08})
        props.place("barbell", "bar2", {"at": (-3.2, 2.2), "z": 0.25})
        shapes.rbox(
            "set.mirror",
            (4, 0.03, 1.8),
            look.mat("#cfe6f0", rough=0.03, metal=0.9),
            (3.2, 3.38, 1.4),
            0.02,
        )
    return {
        "spots": {"center": (0, 0), "bench": (0, 1.2), "side": (1.3, 1.0)},
        "target": (0, 1.0, 1.1),
    }


def elevator(o):
    """A lift cabin, open towards the camera: steel walls, the doors and the floor indicator at the
    back, a button panel, a handrail. `opts`: "floor" (the number on the indicator), "open" (doors
    apart), "ceiling": False (for shots from above), "shaft" (the hoistway over the cabin: concrete,
    guide rails, suspension cables; implies no ceiling), "emergency" (red light, no cabin lamp)."""
    w, d, h = 1.9, 1.7, 2.35
    shaft = bool(o.get("shaft"))
    steel = look.mat(o.get("wall", "#b9bfc6"), rough=0.3, spec=0.7, metal=0.6)
    # "floor" is the number on the indicator here, so the ground's color is "floor_color"
    floor_m = look.pbr("floor_tiles_06", None, 0.8, fallback=o.get("floor_color", "#4a4f55"))
    shapes.rbox("set.floor", (w, d, 0.12), floor_m, (0, 0, -0.06), 0.01)
    shapes.rbox("set.back", (w, 0.1, h), steel, (0, d / 2, h / 2), 0.01)
    for s in (-1, 1):
        shapes.rbox(f"set.side{s}", (0.1, d, h), steel, (s * w / 2, 0, h / 2), 0.01)
    dm = look.mat("#d7dde2", rough=0.2, spec=0.8, metal=0.5)
    dw, dx = (0.3, w / 2 - 0.22) if o.get("open") else (0.78, 0.4)
    for s in (-1, 1):
        shapes.rbox(f"set.door{s}", (dw, 0.06, 2.05), dm, (s * dx, d / 2 - 0.09, 1.02), 0.01)
    shapes.rbox("set.indbox", (0.62, 0.05, 0.22), look.mat("#15181c", rough=0.4), (0, 0.75, 2.18), 0.01)  # fmt: skip
    shapes.text("set.indtxt", str(o.get("floor", "20")), look.mat("#ff9b2f", emit=3.0), 0.15,
                (0, 0.70, 2.18), font_path=props.FONT)  # fmt: skip
    shapes.rbox("set.panel", (0.05, 0.22, 0.62), look.mat("#2a2f35", rough=0.5), (w / 2 - 0.07, 0.42, 1.25), 0.01)  # fmt: skip
    btn = look.mat("#e8e2d8", emit=0.6)
    for i in range(6):
        shapes.cylinder(f"set.btn{i}", 0.022, 0.012, btn,
                        (w / 2 - 0.1, 0.36 + (i % 2) * 0.11, 1.46 - (i // 2) * 0.12), (0, 90, 0), segments=12)  # fmt: skip
    shapes.cylinder("set.handrail", 0.022, d - 0.3, look.mat("#8d949b", rough=0.25, metal=0.8),
                    (-w / 2 + 0.08, 0, 0.95), (90, 0, 0), segments=12)  # fmt: skip
    roofed = o.get("ceiling", True) and not shaft
    if roofed:
        shapes.rbox("set.ceil", (w, d, 0.08), steel, (0, 0, h + 0.04), 0.01)
    if shaft:
        conc = look.pbr("concrete_floor_02", None, 2.5, fallback="#5b5f64")
        rail_m = look.mat("#777d84", rough=0.25, metal=0.9)
        for s in (-1, 1):
            shapes.rbox(f"set.shaftside{s}", (0.3, d + 1.8, 26), conc, (s * (w / 2 + 0.5), 0.2, 13.0), 0.0)  # fmt: skip
            shapes.rbox(f"set.guide{s}", (0.09, 0.14, 26), rail_m, (s * (w / 2 + 0.24), 0, 13.0), 0.01)  # fmt: skip
        shapes.rbox("set.shaftback", (w + 1.6, 0.3, 26), conc, (0, d / 2 + 0.95, 13.0), 0.0)
        cable = look.mat("#3c4044", rough=0.4, metal=0.7)
        for i in range(8):
            shapes.cylinder(f"set.cable{i}", 0.018, 24, cable, (-0.35 + i * 0.1, 0.15, h + 12.3), segments=8)  # fmt: skip
        look.point((0, 0, 8.0), 600, "#9fb6c8", 1.2, "shaft")
    if o.get("emergency"):
        look.world("#0a0c10", "#141820", 0.15)
        look.point((0, 0.2, h - 0.25), 140, "#ff5a4a", 0.25, "emergency")
    else:
        if not look.env("interior", 0.5, visible=False):
            look.world("#20242b", "#2c323a", 0.4)
        if roofed:  # a loose light panel would hang in mid-air once the ceiling is off
            shapes.rbox("set.lamp", (0.9, 0.7, 0.03), look.mat("#fff6e2", emit=4.0), (0, -0.05, h - 0.03), 0.005)  # fmt: skip
        look.point((0, -0.05, h - 0.2), 180, "#ffe9c6", 0.35, "cabin")
    look.area((0, -2.6, 1.8), (0, 0.3, 1.2), 180, 2.2, "#ffffff", "fill")
    return {
        "spots": {"center": (0, -0.1), "left": (-0.5, -0.1), "right": (0.5, -0.1), "door": (0, 0.35)},
        "target": (0, 0.2, 1.2),
    }  # fmt: skip


def street(o):
    rng = random.Random(o.get("seed", 3))
    if o.get("night"):
        if not look.env("dusk", 0.6, 160):
            look.world("#121933", "#28304f", 0.35)
    else:
        if not look.env("outdoor", 1.0, 160):
            look.world("#9fd2f5", "#fbf3e7", 1.0)
        look.sun(3.2, 4, (48, 10, 35))
    asphalt = look.pbr("asphalt_02", None, 4.0, fallback="#4a4f57")
    walk = look.pbr("large_square_pattern_01", None, 1.5, fallback="#cfcac2")
    shapes.rbox("set.road", (8, 160, 0.1), asphalt, (0, 40, -0.05), 0.0)
    for i in range(36):
        shapes.rbox(
            f"set.line{i}", (0.15, 2.0, 0.01), look.mat("#f4f1e6"), (0, -20 + i * 5, 0.005), 0.0
        )
    for sx in (-1, 1):
        shapes.rbox(f"set.walk{sx}", (5, 160, 0.25), walk, (sx * 6.5, 40, 0.125), 0.03)
        shapes.rbox(
            f"set.curb{sx}", (0.25, 160, 0.27), look.mat("#e8e4dd"), (sx * 4.1, 40, 0.135), 0.02
        )
    names = o.get(
        "shops", ["MARKET", "FIRIN", "KAFE", "NALBUR", "BERBER", "ECZANE", "KEBAP", "TERZİ"]
    )
    real = props.load_world()
    k = 0
    for sx in (-1, 1):
        y = -12.0
        while y < 110:
            if real:
                b = props.place("building", f"bld{k}", {"at": (0, 0), "rot": 90 if sx < 0 else -90})
                w, d, _ = props.kit_size(b) or (16.0, 14.0, 20.0)
                front = 9.2  # the sidewalk's outer edge
                b.location = (
                    sx * (front + d / 2),
                    y + w / 2,
                    0,
                )  # turned: its width runs along the street
                sign = props.place("sign", f"sign{k}", {"at": (sx * (front - 0.06), y + w / 2, 0), "rot": 90 if sx < 0 else -90,
                                                       "text": names[k % len(names)], "color": rng.choice(["#c0392b", "#1f6fb2", "#2e8b57", "#d4a017", "#2b2b2b"]),
                                                       "text_color": "#ffffff", "size": 0.55, "stand": False, "z": 3.4})  # fmt: skip
                del sign
                step_w = w + 0.4
            else:
                props.place(
                    "shop",
                    f"shop{k}",
                    {
                        "at": (sx * 8.1, y + 2.6),
                        "rot": -90 * sx,
                        "w": 5.2,
                        "text": names[k % len(names)],
                    },
                )
                step_w = 5.5
            k += 1
            y += step_w
    for i in range(14):
        for sx in (-1, 1):
            yy = -6 + i * 8
            props.place(
                "tree", f"tree{i}{sx}", {"at": (sx * 5.4, yy), "rot": rng.uniform(0, 360), "h": 3.2}
            )
            props.place(
                "lamp_post",
                f"lamp{i}{sx}",
                {"at": (sx * 4.6, yy + 4), "rot": -90 * sx, "on": bool(o.get("night"))},
            )
            if i % 3 == 0:
                props.place(
                    "fire_hydrant" if sx > 0 else "trash_can",
                    f"str{i}{sx}",
                    {"at": (sx * 5.0, yy + 2), "rot": -90 * sx, "scale": 0.8},
                )
    if o.get("cars", True):
        for i in range(10):
            side = rng.choice((-1, 1))
            props.place(
                "taxi" if i % 4 == 1 else "car",
                f"car{i}",
                {
                    "at": (side * 3.0, 6 + i * 9.5),
                    "rot": 0 if side > 0 else 180,
                    "color": rng.choice(["#e04f3f", "#3f7fe0", "#f2c12e", "#eeeeee"]),
                },
            )
    return {
        "spots": {"center": (0, 0), "left": (-5.5, 1), "right": (5.5, 1), "road": (0, 2)},
        "target": (0, 2, 1.2),
    }


def city(o):
    """A city from above: blocks of buildings on a grid (for wide and aerial shots)."""
    rng = random.Random(o.get("seed", 9))
    if not look.env("outdoor", 1.0, 120):
        look.world("#9fd2f5", "#fbf3e7", 1.0)
    look.sun(4.0, 4, (40, 5, 40))
    shapes.rbox(
        "set.ground",
        (400, 400, 0.2),
        look.pbr("aerial_grass_rock", None, 12.0, fallback="#8fbf7a"),
        (0, 0, -0.1),
        0.0,
    )
    road = look.pbr("asphalt_02", None, 6.0, fallback="#5b6068")
    span, step = int(o.get("size", 6)), 22
    for i in range(-span, span + 1):
        shapes.rbox(
            f"set.rx{i}", (span * 2 * step + 20, 5, 0.05), road, (0, i * step + step / 2, 0.02), 0.0
        )
        shapes.rbox(
            f"set.ry{i}",
            (5, span * 2 * step + 20, 0.05),
            road,
            (i * step + step / 2, 0, 0.025),
            0.0,
        )
    colors = ["#e9e2d6", "#d9cfc1", "#cfd8e0", "#f0dcc4", "#d6e2d3", "#e6d3d9"]
    real = props.load_world()
    for i in range(-span, span):
        for j in range(-span, span):
            cx, cy = i * step + 11, j * step + 11
            if rng.random() < 0.12:
                for t in range(5):
                    props.place(
                        "tree",
                        f"pk{i}{j}{t}",
                        {
                            "at": (cx + rng.uniform(-6, 6), cy + rng.uniform(-6, 6)),
                            "h": 4,
                            "rot": rng.uniform(0, 360),
                        },
                    )
                continue
            if real:
                props.place("building", f"b{i}_{j}", {"at": (cx, cy), "rot": rng.choice((0, 90, 180, 270)),
                                                      "scale": rng.uniform(0.75, 1.0) * (1.25 if abs(i) < 2 and abs(j) < 2 else 1.0)})  # fmt: skip
                continue
            for q in range(rng.randint(1, 3)):
                h = rng.choice((8, 12, 16, 22, 30, 45)) * (
                    1.4 if abs(i) < 2 and abs(j) < 2 else 1.0
                )
                props.place(
                    "building",
                    f"b{i}_{j}_{q}",
                    {
                        "at": (cx + rng.uniform(-4, 4), cy + rng.uniform(-4, 4)),
                        "w": rng.uniform(6, 9),
                        "d": rng.uniform(6, 9),
                        "h": h,
                        "color": rng.choice(colors),
                        "procedural": True,
                    },
                )
    if real:
        for c in range(16):
            props.place(
                "car",
                f"ccar{c}",
                {
                    "at": (
                        rng.choice((-1, 1)) * rng.randint(0, span) * step
                        + step / 2
                        + rng.choice((-1.5, 1.5)),
                        rng.uniform(-span, span) * step,
                    ),
                    "rot": 0,
                },
            )
    return {"spots": {"center": (0, 0)}, "target": (0, 0, 10)}


def park(o):
    if not look.env("outdoor", 1.0, 200):
        look.world("#a6d8f7", "#fbf5e9", 1.0)
    look.sun(3.5, 7, (50, 8, 30))
    shapes.rbox(
        "set.grass",
        (90, 90, 0.2),
        look.pbr("aerial_grass_rock", None, 5.0, fallback="#86c06c"),
        (0, 20, -0.1),
        0.0,
    )
    shapes.rbox(
        "set.path",
        (2.6, 90, 0.03),
        look.pbr("large_square_pattern_01", "#d9cdb4", 1.2, fallback="#e3d4b4"),
        (0, 20, 0.0),
        0.0,
    )
    rng = random.Random(5)
    for i in range(26):
        x = rng.choice((-1, 1)) * rng.uniform(3.5, 22)
        props.place(
            rng.choice(("tree", "tree", "pine")),
            f"t{i}",
            {"at": (x, rng.uniform(-2, 45)), "h": rng.uniform(3, 5), "rot": rng.uniform(0, 360)},
        )
    for i in range(30):
        x = rng.choice((-1, 1)) * rng.uniform(1.8, 14)
        props.place(
            rng.choice(("bush", "flowers", "grass", "grass", "rock")),
            f"g{i}",
            {
                "at": (x, rng.uniform(-2, 30)),
                "rot": rng.uniform(0, 360),
                "scale": rng.uniform(0.5, 0.9),
            },
        )
    props.place("bench", "bench", {"at": (2.2, 1.6), "rot": -90})
    props.place("lamp_post", "lamp", {"at": (-1.8, 2.5)})
    props.place("trash_can", "bin", {"at": (2.3, 3.6), "rot": -90, "scale": 0.6})
    return {"spots": {"center": (0, 0), "bench": (2.2, 1.6)}, "target": (0, 1.5, 1.2)}


def space(o):
    """Stars, the Earth below, the Moon far away (for 'it goes into space' moments)."""
    look.world("#04050c", "#0b1024", 0.25)
    look.sun(5.0, 1, (30, -20, 60), "#ffffff")
    rng = random.Random(1)
    star = look.mat("#ffffff", emit=6.0)
    for i in range(260):
        th, ph = rng.uniform(0, math.tau), rng.uniform(-1.2, 1.5)
        rad = 400
        shapes.sphere(
            f"set.star{i}",
            rng.uniform(0.25, 0.8),
            star,
            (
                math.cos(ph) * math.cos(th) * rad,
                math.cos(ph) * math.sin(th) * rad,
                math.sin(ph) * rad,
            ),
            segments=6,
            rings=4,
        )
    props.place("globe", "earth", {"at": (0, 40, -125), "r": 60})
    props.place("moon", "moon", {"at": (-60, 160, 40), "r": 8})
    return {"spots": {"center": (0, 0, 2)}, "target": (0, 0, 1.0)}


def studio(o):
    """An infinite colored backdrop (a curved cyclorama): for explainers, item close-ups, lists."""
    color = o.get("color", "#f3d9a4")
    m = look.mat(color, rough=0.9)
    shapes.rbox("set.floor", (40, 40, 0.2), m, (0, 0, -0.1), 0.0)
    cyc = shapes.cylinder("set.cyc", 6, 40, m, (0, 6, 6), (0, 90, 0), segments=48)
    cyc.scale = (1, 1, 1)
    shapes.rbox("set.back", (40, 0.2, 30), m, (0, 12, 15), 0.0)
    if not look.env("studio", 0.8, visible=False):
        look.world(o.get("sky", color), o.get("sky", color), 0.7)
    look.sun(2.8, 14, (50, 0, 30))
    look.area((-3, -4, 4), (0, 0, 1), 450, 5, "#ffffff", "key")
    look.area((3.5, 1, 3), (0, 0, 1), 200, 3, "#fff0d8", "rim")
    return {
        "spots": {"center": (0, 0), "left": (-1.0, 0), "right": (1.0, 0)},
        "target": (0, 0, 1.0),
    }


def world_view(o):
    """The whole planet in frame (for 'everyone on Earth' moments)."""
    look.world("#04050c", "#0a0f22", 0.2)
    look.sun(4.5, 1, (20, -30, 70))
    rng = random.Random(2)
    star = look.mat("#ffffff", emit=5.0)
    for i in range(160):
        th, ph = rng.uniform(0, math.tau), rng.uniform(-1.3, 1.3)
        shapes.sphere(
            f"set.star{i}",
            rng.uniform(0.3, 0.7),
            star,
            (
                math.cos(ph) * math.cos(th) * 300,
                math.cos(ph) * math.sin(th) * 300 + 100,
                math.sin(ph) * 300,
            ),
            segments=6,
            rings=4,
        )
    props.place("globe", "earth", {"at": (0, 0, -3), "r": 3})
    return {"spots": {"center": (0, -3.5, 0)}, "target": (0, 0, 0)}


# --------------------------------------------------------------------------- cutaway (kesit)
CUT_W, CUT_D, CUT_H = 14.0, 15.0, 16.0  # the diorama block: width (x), depth (y), soil depth (z)
STRATA_DEPTH = 5.0  # the layers are drawn over the top 5 m; below that it is all bedrock


def _strata_material(name: str = "set.strata"):
    """Soil cut open: dark topsoil, brown earth, an orange clay band, grey bedrock; noisy borders,
    pebbles and cracks in the bump (the side of a cake, read in a second)."""
    have = bpy.data.materials.get(name)
    if have is not None:
        return have
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs["Roughness"].default_value = 0.95
    # world position: the block and every pit wall dug into it share one set of layers
    coord = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Position"], sep.inputs[0])
    wob = nt.nodes.new("ShaderNodeTexNoise")  # wavy layer borders
    wob.inputs["Scale"].default_value = 0.9
    nt.links.new(coord.outputs["Position"], wob.inputs["Vector"])
    mix = nt.nodes.new("ShaderNodeMath")
    mix.operation = "MULTIPLY_ADD"
    mix.inputs[1].default_value = 0.45
    nt.links.new(wob.outputs["Fac"], mix.inputs[0])
    nt.links.new(sep.outputs["Z"], mix.inputs[2])
    ramp = nt.nodes.new("ShaderNodeValToRGB")  # z (m, negative below the lawn) -> colour
    els = ramp.color_ramp.elements
    stops = [(0.0, "#433a33"), (0.30, "#524438"), (0.40, "#6c4a31"), (0.47, "#674530"),
             (0.56, "#5a3c27"), (0.84, "#4d321f"), (0.94, "#3a2517"), (1.0, "#2e1f14")]  # fmt: skip
    els[0].position, els[0].color = stops[0][0], look.hex_rgba(stops[0][1])
    els[1].position, els[1].color = stops[-1][0], look.hex_rgba(stops[-1][1])
    for pos, col in stops[1:-1]:
        e = els.new(pos)
        e.color = look.hex_rgba(col)
    to01 = nt.nodes.new("ShaderNodeMapRange")  # -5..0 m -> 0..1
    to01.inputs["From Min"].default_value = -STRATA_DEPTH
    to01.inputs["From Max"].default_value = 0.2
    nt.links.new(mix.outputs["Value"], to01.inputs["Value"])
    nt.links.new(to01.outputs["Result"], ramp.inputs["Fac"])
    grain = nt.nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 9.0
    grain.inputs["Detail"].default_value = 6.0
    nt.links.new(coord.outputs["Position"], grain.inputs["Vector"])
    tint = nt.nodes.new("ShaderNodeMix")
    tint.data_type = "RGBA"
    tint.blend_type = "MULTIPLY"
    tint.inputs["Factor"].default_value = 0.35
    nt.links.new(ramp.outputs["Color"], tint.inputs["A"])
    nt.links.new(grain.outputs["Color"], tint.inputs["B"])
    cracks = nt.nodes.new("ShaderNodeTexVoronoi")  # dry cracks: dark lines between clods
    cracks.feature = "DISTANCE_TO_EDGE"
    cracks.inputs["Scale"].default_value = 1.9
    if "Randomness" in cracks.inputs:
        cracks.inputs["Randomness"].default_value = 1.0
    warp = nt.nodes.new("ShaderNodeTexNoise")  # bend the cells: clods, not paving stones
    warp.inputs["Scale"].default_value = 1.4
    warp.inputs["Detail"].default_value = 4.0
    nt.links.new(coord.outputs["Position"], warp.inputs["Vector"])
    bent = nt.nodes.new("ShaderNodeVectorMath")
    bent.operation = "MULTIPLY_ADD"
    bent.inputs[1].default_value = (0.55, 0.55, 0.55)
    nt.links.new(warp.outputs["Color"], bent.inputs[0])
    nt.links.new(coord.outputs["Position"], bent.inputs[2])
    nt.links.new(bent.outputs["Vector"], cracks.inputs["Vector"])
    edge = nt.nodes.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value = 0.0
    edge.inputs["From Max"].default_value = 0.035
    edge.inputs["To Min"].default_value = 0.62
    edge.inputs["To Max"].default_value = 1.0
    nt.links.new(cracks.outputs["Distance"], edge.inputs["Value"])
    dark = nt.nodes.new("ShaderNodeMix")
    dark.data_type = "RGBA"
    dark.blend_type = "MULTIPLY"
    dark.inputs["Factor"].default_value = 1.0
    nt.links.new(tint.outputs["Result"], dark.inputs["A"])
    nt.links.new(edge.outputs["Result"], dark.inputs["B"])
    nt.links.new(dark.outputs["Result"], p.inputs["Base Color"])
    pebbles = nt.nodes.new("ShaderNodeTexVoronoi")
    pebbles.inputs["Scale"].default_value = 7.0
    nt.links.new(coord.outputs["Position"], pebbles.inputs["Vector"])
    bump_in = nt.nodes.new("ShaderNodeMath")
    bump_in.operation = "ADD"
    nt.links.new(pebbles.outputs["Distance"], bump_in.inputs[0])
    nt.links.new(grain.outputs["Fac"], bump_in.inputs[1])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.55
    nt.links.new(bump_in.outputs["Value"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    m.diffuse_color = look.hex_rgba("#5a3b24")
    return m


def _lawn_material(winter: bool):
    if winter:
        return look.mat("#dfe7ee", rough=0.9)
    m = bpy.data.materials.get("set.lawn")
    if m is not None:
        return m
    m = bpy.data.materials.new("set.lawn")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    p.inputs["Roughness"].default_value = 0.9
    coord = nt.nodes.new("ShaderNodeTexCoord")
    stripes = nt.nodes.new("ShaderNodeTexWave")  # mowing stripes
    stripes.inputs["Scale"].default_value = 0.35
    nt.links.new(coord.outputs["Object"], stripes.inputs["Vector"])
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 30.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = look.hex_rgba("#4f8f2f")
    ramp.color_ramp.elements[1].color = look.hex_rgba("#6fae3c")
    add = nt.nodes.new("ShaderNodeMath")
    add.operation = "MULTIPLY_ADD"
    add.inputs[1].default_value = 0.25
    nt.links.new(noise.outputs["Fac"], add.inputs[0])
    nt.links.new(stripes.outputs["Fac"], add.inputs[2])
    nt.links.new(add.outputs["Value"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.3
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    m.diffuse_color = look.hex_rgba("#5f9e35")
    return m


def _villa(at, winter: bool, color: str = "#e9e4da") -> None:
    """A two-storey family house: plaster walls, white-framed windows with shutters, a tiled
    gable roof, a chimney, a front door and a porch light."""
    x0, y0 = at
    w, d, h = 10.0, 5.0, 6.0
    wall = look.pbr("painted_plaster_wall", color, 2.0, fallback=color)
    shapes.rbox("set.house", (w, d, h), wall, (x0, y0, h / 2), 0.02)
    shapes.rbox("set.plinth", (w + 0.1, d + 0.1, 0.45), look.mat("#8d8a84", rough=0.9), (x0, y0, 0.22), 0.01)  # fmt: skip
    roof_m = look.mat("#f2f4f6" if winter else "#a94a32", rough=0.75)
    for side in (-1, 1):  # two roof planes meeting at the ridge
        pl = shapes.rbox(f"set.roof{side}", (w + 0.6, d * 0.62, 0.16), roof_m,
                         (x0, y0 + side * d * 0.25, h + 1.05), 0.02)  # fmt: skip
        pl.rotation_euler = (R(-38 * side), 0, 0)
    gable = look.pbr("painted_plaster_wall", color, 2.0, fallback=color)
    for sx in (-1, 1):  # the triangles under the roof at both ends
        tri = shapes.cylinder(f"set.gable{sx}", d * 0.58, 0.2, gable,
                              (x0 + sx * (w / 2 - 0.1), y0, h + 0.05), (0, 90, 0), segments=3)  # fmt: skip
        tri.rotation_euler = (R(90), R(90), 0)
        tri.scale = (1.0, 0.62, 1.0)
    shapes.rbox("set.chimney", (0.7, 0.7, 2.2), look.mat("#8a4a3a", rough=0.85), (x0 + w * 0.3, y0 + 0.6, h + 1.4), 0.02)  # fmt: skip
    glass = look.mat("#2c3a46", rough=0.08, spec=0.9)
    frame = look.mat("#fbfbfa", rough=0.5)
    shutter = look.mat("#2f4a63", rough=0.6)
    for row, z in enumerate((1.8, 4.4)):
        for col in range(5):
            if row == 0 and col == 2:
                continue  # the door goes there
            x = x0 - w / 2 + 1.0 + col * (w - 2.0) / 4
            shapes.rbox(
                f"set.wf{row}{col}", (1.0, 0.08, 1.4), frame, (x, y0 - d / 2 - 0.02, z), 0.01
            )
            shapes.rbox(
                f"set.wg{row}{col}", (0.84, 0.06, 1.24), glass, (x, y0 - d / 2 - 0.05, z), 0.0
            )
            for sx in (-1, 1):
                shapes.rbox(f"set.sh{row}{col}{sx}", (0.36, 0.06, 1.4), shutter,
                            (x + sx * 0.72, y0 - d / 2 - 0.04, z), 0.01)  # fmt: skip
    shapes.rbox("set.door", (1.3, 0.1, 2.4), look.mat("#f7f7f5", rough=0.4), (x0, y0 - d / 2 - 0.03, 1.2), 0.02)  # fmt: skip
    shapes.rbox("set.doorglass", (1.0, 0.08, 1.9), glass, (x0, y0 - d / 2 - 0.07, 1.25), 0.0)
    shapes.rbox("set.step", (2.0, 0.8, 0.22), look.mat("#a8a49c", rough=0.9), (x0, y0 - d / 2 - 0.4, 0.11), 0.02)  # fmt: skip


def cutaway(o):
    """The yard cut open like a cake: a block of lawn and soil whose front face is the cut, a
    two-storey house at the back, a fence, a tree. Pits (`pit` props) are dug into the block and
    cut in half by the front face; `layer` props fill them (water, gravel, concrete...).
    `opts`: "season" summer | autumn | winter, "house" false, "w"/"d" block size."""
    winter = o.get("season") == "winter"
    w, d, hh = float(o.get("w", CUT_W)), float(o.get("d", CUT_D)), CUT_H
    if winter:  # a cold blue sky and a low sun: snow must not wash the frame out
        look.world("#7f97ad", "#c4d0db", 0.75)
        look.sun(2.0, 5, (32, 10, 25), "#dfe8f2")
    else:
        if not look.env("outdoor", 1.0, 150):
            look.world("#a6d8f7", "#fbf5e9", 1.0)
        look.sun(3.6, 6, (48, 6, 35))
    # a soft fill from the camera side: the cut face looks at the camera, away from the sun
    look.area((0, -16, 1.0), (0, 0, -2.5), 2600 if not winter else 2000, 24, "#fff3e6")
    strata = _strata_material()
    lawn = _lawn_material(winter)
    # the block: one mesh, lawn on top, the strata everywhere else (pits dug later inherit strata)
    soil = shapes.rbox("set.soil", (w, d, hh), strata, (0, d / 2, -hh / 2), 0.0)
    soil.data.materials.append(lawn)
    for poly in soil.data.polygons:
        if poly.normal.z > 0.9:
            poly.material_index = 1
    if o.get("house", True):
        _villa((0, d - 4.2), winter, o.get("house_color", "#e9e4da"))
    fence = look.mat("#f1efe9" if not winter else "#e8e8e6", rough=0.7)
    for i in range(int(w / 0.6) + 1):  # a picket fence along the back edge
        shapes.rbox(
            f"set.picket{i}", (0.09, 0.05, 1.1), fence, (-w / 2 + i * 0.6, d - 0.3, 0.55), 0.01
        )
    shapes.rbox("set.rail", (w, 0.05, 0.08), fence, (0, d - 0.32, 0.8), 0.0)
    rng = random.Random(3)
    for i, (x, y) in enumerate(((-w / 2 + 1.2, d - 2.0), (w / 2 - 1.3, d - 1.6))):
        props.place(
            "tree",
            f"set.tree{i}",
            {"at": (x, y), "h": rng.uniform(4.0, 5.5), "rot": rng.uniform(0, 360)},
        )
    for i in range(6):
        props.place(rng.choice(("bush", "flowers", "shrub")), f"set.bush{i}",
                    {"at": (rng.uniform(-w / 2 + 0.6, w / 2 - 0.6), d - 0.9 - rng.uniform(0, 0.5)),
                     "scale": rng.uniform(0.6, 0.9), "rot": rng.uniform(0, 360)})  # fmt: skip
    # diorama scale: "medium" on a point is three times as far as on a person; seen from above
    return {"spots": {"center": (0, 1.5), "cut": (0, 0)}, "target": (0, 0.0, -1.2),
            "camera_scale": 3.0, "camera_lift": 0.22}  # fmt: skip


SETS = {
    "room": room,
    "bedroom_night": bedroom_night,
    "bathroom": bathroom,
    "classroom": classroom,
    "kitchen": kitchen,
    "office": office,
    "gym": gym,
    "elevator": elevator,
    "cutaway": cutaway,
    "street": street,
    "city": city,
    "park": park,
    "space": space,
    "studio": studio,
    "world": world_view,
}


def build(kind: str, opts: dict | None = None) -> dict:
    if kind not in SETS:
        raise ValueError(f"bilinmeyen mekân: {kind} (var olanlar: {', '.join(sorted(SETS))})")
    return SETS[kind](opts or {})
