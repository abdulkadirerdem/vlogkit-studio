"""Props: small procedural objects placed by name in a shot (`{"kind": "toilet", "at": [x, y]}`).

Every builder takes (name, opts, parent) and returns the root object; the object stands on z=0 and
faces -Y. `opts` may carry "color" and, for things with writing, "text".
"""

from __future__ import annotations

import math

import bpy

from . import look, shapes

R = math.radians
FONT: str | None = None  # set by the runner: the kit's bold font for 3D text


def _root(name, parent):
    return shapes.empty(name, (0, 0, 0), parent)


def bed(name, o, p):
    r = _root(name, p)
    c = o.get("color", "#3f6db3")
    shapes.rbox(f"{name}.frame", (1.1, 2.1, 0.35), look.mat("#f1ece4"), (0, 0, 0.18), 0.05, r)
    shapes.rbox(f"{name}.mattress", (1.04, 2.0, 0.2), look.mat("#fafafa"), (0, 0, 0.44), 0.08, r)
    shapes.rbox(
        f"{name}.blanket", (1.08, 1.4, 0.08), look.mat(c, rough=0.9), (0, -0.28, 0.55), 0.04, r
    )
    shapes.rbox(
        f"{name}.pillow",
        (0.75, 0.38, 0.14),
        look.mat("#ffffff", rough=0.9),
        (0, 0.72, 0.6),
        0.07,
        r,
    )
    shapes.rbox(f"{name}.head", (1.1, 0.1, 0.95), look.mat("#d9cbb8"), (0, 1.02, 0.48), 0.04, r)
    return r


def toilet(name, o, p):
    r = _root(name, p)
    w = look.mat("#f7f8fa", rough=0.25, spec=0.6)
    shapes.cylinder(f"{name}.base", 0.17, 0.4, w, (0, 0, 0.2), bevel=0.03, radius2=0.2, parent=r)
    shapes.sphere(f"{name}.bowl", 0.26, w, (0, -0.08, 0.42), (1, 1.25, 0.45), r)
    shapes.cylinder(
        f"{name}.seat",
        0.25,
        0.04,
        look.mat("#ffffff", rough=0.3),
        (0, -0.08, 0.53),
        bevel=0.015,
        parent=r,
    ).scale = (1, 1.22, 1)
    shapes.rbox(f"{name}.tank", (0.46, 0.2, 0.42), w, (0, 0.24, 0.72), 0.05, r)
    shapes.rbox(f"{name}.lid", (0.48, 0.22, 0.04), w, (0, 0.24, 0.94), 0.02, r)
    shapes.cylinder(
        f"{name}.flush",
        0.03,
        0.02,
        look.mat("#c0c4c8", metal=1, rough=0.2),
        (0, 0.24, 0.965),
        parent=r,
    )
    return r


def sink(name, o, p):
    r = _root(name, p)
    w = look.mat("#f7f8fa", rough=0.25)
    shapes.cylinder(f"{name}.ped", 0.09, 0.75, w, (0, 0.05, 0.37), parent=r)
    shapes.rbox(f"{name}.basin", (0.6, 0.45, 0.16), w, (0, 0, 0.82), 0.07, r)
    shapes.cylinder(
        f"{name}.tap",
        0.02,
        0.18,
        look.mat("#c8ccd0", metal=1, rough=0.15),
        (0, 0.17, 0.95),
        parent=r,
    )
    return r


def desk(name, o, p):
    r = _root(name, p)
    wood = look.mat(o.get("color", "#c9935e"), rough=0.6)
    shapes.rbox(f"{name}.top", (1.3, 0.65, 0.05), wood, (0, 0, 0.75), 0.015, r)
    for i, (x, y) in enumerate(((-0.6, -0.27), (0.6, -0.27), (-0.6, 0.27), (0.6, 0.27))):
        shapes.rbox(f"{name}.leg{i}", (0.05, 0.05, 0.73), wood, (x, y, 0.365), 0.01, r)
    return r


def school_desk(name, o, p):
    r = desk(name, {"color": o.get("color", "#d7a46b")}, p)
    r.scale = (0.7, 0.85, 0.95)
    return r


def chair(name, o, p):
    r = _root(name, p)
    m = look.mat(o.get("color", "#3b4b5e"), rough=0.6)
    shapes.rbox(f"{name}.seat", (0.45, 0.45, 0.06), m, (0, 0, 0.46), 0.02, r)
    shapes.rbox(f"{name}.back", (0.45, 0.05, 0.45), m, (0, 0.21, 0.72), 0.02, r)
    for i, (x, y) in enumerate(((-0.2, -0.2), (0.2, -0.2), (-0.2, 0.2), (0.2, 0.2))):
        shapes.cylinder(
            f"{name}.leg{i}",
            0.018,
            0.44,
            look.mat("#9aa3ad", metal=1, rough=0.3),
            (x, y, 0.22),
            parent=r,
        )
    return r


def sofa(name, o, p):
    r = _root(name, p)
    m = look.mat(o.get("color", "#6c8fb3"), rough=0.85)
    shapes.rbox(f"{name}.base", (2.0, 0.85, 0.42), m, (0, 0, 0.25), 0.1, r)
    shapes.rbox(f"{name}.back", (2.0, 0.25, 0.55), m, (0, 0.32, 0.65), 0.1, r)
    for sx in (-1, 1):
        shapes.rbox(f"{name}.arm{sx}", (0.22, 0.85, 0.6), m, (sx * 0.95, 0, 0.36), 0.1, r)
    return r


def tv(name, o, p):
    r = _root(name, p)
    shapes.rbox(
        f"{name}.body", (1.3, 0.06, 0.75), look.mat("#151515", rough=0.3), (0, 0, 1.2), 0.02, r
    )
    shapes.plane(
        f"{name}.screen",
        (1.22, 0.68),
        look.mat(o.get("color", "#3aa0ff"), emit=1.5),
        (0, -0.032, 1.2),
        (90, 0, 0),
        r,
    )
    if o.get("news"):  # a breaking-news broadcast: red tag, headline bar, ticker
        shapes.plane(
            f"{name}.bar",
            (1.22, 0.16),
            look.mat("#ffffff", emit=1.2),
            (0, -0.034, 1.0),
            (90, 0, 0),
            r,
        )
        shapes.plane(
            f"{name}.tag",
            (0.36, 0.1),
            look.mat("#d7261e", emit=2.0),
            (-0.4, -0.036, 1.12),
            (90, 0, 0),
            r,
        )
        shapes.text(
            f"{name}.tagt",
            o.get("tag", "SON DAKİKA"),
            look.mat("#ffffff", emit=3),
            0.05,
            (-0.4, -0.04, 1.12),
            font_path=FONT,
            parent=r,
        )
        shapes.text(
            f"{name}.head",
            o.get("text", ""),
            look.mat("#111111"),
            0.07,
            (0, -0.04, 1.0),
            font_path=FONT,
            parent=r,
        )
        shapes.plane(
            f"{name}.tick",
            (1.22, 0.06),
            look.mat("#14213d", emit=1.0),
            (0, -0.034, 0.89),
            (90, 0, 0),
            r,
        )
        shapes.text(
            f"{name}.tickt",
            o.get("ticker", ""),
            look.mat("#ffd23f", emit=2),
            0.035,
            (0, -0.04, 0.89),
            font_path=FONT,
            parent=r,
        )
    elif o.get("text"):
        shapes.text(
            f"{name}.txt",
            o["text"],
            look.mat("#ffffff", emit=3),
            0.12,
            (0, -0.04, 1.2),
            font_path=FONT,
            parent=r,
        )
    return r


def laptop(name, o, p):
    r = _root(name, p)
    m = look.mat("#c4c8cc", metal=0.6, rough=0.3)
    shapes.rbox(f"{name}.base", (0.34, 0.24, 0.015), m, (0, 0, 0.008), 0.004, r)
    lid = shapes.rbox(f"{name}.lid", (0.34, 0.012, 0.23), m, (0, 0.12, 0.115), 0.004, r)
    lid.rotation_euler = (R(-12), 0, 0)
    shapes.plane(
        f"{name}.scr", (0.31, 0.2), look.mat("#79c2ff", emit=1.2), (0, 0.11, 0.115), (78, 0, 0), r
    )
    return r


def phone(name, o, p):
    """A phone standing on its bottom edge, the screen towards -Y, an app on it."""
    r = _root(name, p)
    shapes.rbox(
        f"{name}.body",
        (0.075, 0.009, 0.155),
        look.mat("#1b1b1f", rough=0.25, metal=0.3),
        (0, 0, 0.0775),
        0.008,
        r,
    )
    shapes.plane(
        f"{name}.scr",
        (0.068, 0.146),
        look.mat(o.get("color", "#0f1115"), emit=1.0),
        (0, -0.0047, 0.0775),
        (90, 0, 0),
        r,
    )
    # a social app: a picture, a red like, lines of text (reads as "a video on a phone")
    shapes.plane(f"{name}.pic", (0.062, 0.07), look.mat(o.get("accent", "#3aa0ff"), emit=2.2),
                 (0, -0.0049, 0.092), (90, 0, 0), r)  # fmt: skip
    shapes.plane(f"{name}.like", (0.012, 0.012), look.mat("#ff3054", emit=3.0),
                 (0.022, -0.005, 0.042), (90, 0, 0), r)  # fmt: skip
    for i, w in enumerate((0.05, 0.036)):
        shapes.plane(f"{name}.ln{i}", (w, 0.005), look.mat("#e8e8e8", emit=1.6),
                     (-0.006 - (0.05 - w) / 2, -0.005, 0.048 - i * 0.012), (90, 0, 0), r)  # fmt: skip
    return r


def fridge(name, o, p):
    r = _root(name, p)
    m = look.mat(o.get("color", "#eef1f4"), rough=0.3)
    shapes.rbox(f"{name}.body", (0.75, 0.7, 1.85), m, (0, 0, 0.925), 0.06, r)
    for z, h in ((1.45, 0.75), (0.55, 1.0)):
        shapes.rbox(
            f"{name}.handle{z}",
            (0.03, 0.04, h * 0.4),
            look.mat("#9aa3ad", metal=1),
            (0.3, -0.37, z),
            0.01,
            r,
        )
    shapes.rbox(f"{name}.gap", (0.74, 0.02, 0.012), look.mat("#c3c8cd"), (0, -0.35, 1.05), 0.003, r)
    return r


def stove(name, o, p):
    r = _root(name, p)
    shapes.rbox(
        f"{name}.body", (0.75, 0.65, 0.9), look.mat("#e9ecef", rough=0.35), (0, 0, 0.45), 0.03, r
    )
    shapes.rbox(
        f"{name}.top", (0.75, 0.65, 0.02), look.mat("#222", rough=0.2), (0, 0, 0.91), 0.005, r
    )
    for i, (x, y) in enumerate(((-0.17, -0.15), (0.17, -0.15), (-0.17, 0.15), (0.17, 0.15))):
        shapes.cylinder(f"{name}.ring{i}", 0.1, 0.01, look.mat("#444"), (x, y, 0.925), parent=r)
    shapes.cylinder(
        f"{name}.pot",
        0.14,
        0.18,
        look.mat("#b8bfc6", metal=1, rough=0.25),
        (-0.17, -0.15, 1.02),
        parent=r,
    )
    return r


def counter(name, o, p):
    r = _root(name, p)
    w = o.get("w", 2.4)
    shapes.rbox(
        f"{name}.cab",
        (w, 0.6, 0.86),
        look.mat(o.get("color", "#f1ede6"), rough=0.6),
        (0, 0, 0.43),
        0.02,
        r,
    )
    shapes.rbox(
        f"{name}.top",
        (w + 0.04, 0.64, 0.05),
        look.mat("#c9b8a3", rough=0.4),
        (0, 0, 0.885),
        0.01,
        r,
    )
    return r


def car(name, o, p):
    r = _root(name, p)
    c = look.mat(o.get("color", "#e04f3f"), rough=0.3, spec=0.6)
    shapes.rbox(f"{name}.body", (1.7, 3.8, 0.7), c, (0, 0, 0.6), 0.2, r)
    shapes.rbox(f"{name}.cabin", (1.5, 2.0, 0.6), c, (0, 0.2, 1.15), 0.22, r)
    glass = look.mat("#9fd3f0", rough=0.05, spec=0.8)
    shapes.rbox(f"{name}.wind", (1.42, 2.05, 0.45), glass, (0, 0.2, 1.17), 0.18, r)
    for i, (x, y) in enumerate(((-0.82, -1.2), (0.82, -1.2), (-0.82, 1.25), (0.82, 1.25))):
        shapes.cylinder(
            f"{name}.wheel{i}",
            0.34,
            0.24,
            look.mat("#1d1d1d", rough=0.7),
            (x, y, 0.34),
            (0, 90, 0),
            r,
        )
        shapes.cylinder(
            f"{name}.hub{i}",
            0.17,
            0.25,
            look.mat("#c7ccd1", metal=1, rough=0.2),
            (x, y, 0.34),
            (0, 90, 0),
            r,
        )
    for sx in (-1, 1):
        shapes.sphere(
            f"{name}.light{sx}",
            0.1,
            look.mat("#fff7d6", emit=2.5),
            (sx * 0.55, -1.9, 0.68),
            (1, 0.4, 0.7),
            r,
        )
    return r


def bus(name, o, p):
    r = _root(name, p)
    c = look.mat(o.get("color", "#f2b134"), rough=0.4)
    shapes.rbox(f"{name}.body", (2.4, 9.0, 2.6), c, (0, 0, 1.6), 0.3, r)
    glass = look.mat("#9fd3f0", rough=0.05)
    shapes.rbox(f"{name}.win", (2.44, 8.0, 0.9), glass, (0, 0.2, 2.1), 0.1, r)
    for i, y in enumerate((-3.0, 3.0)):
        for sx in (-1, 1):
            shapes.cylinder(
                f"{name}.w{i}{sx}", 0.5, 0.3, look.mat("#1d1d1d"), (sx * 1.1, y, 0.5), (0, 90, 0), r
            )
    return r


def tree(name, o, p):
    r = _root(name, p)
    h = o.get("h", 3.0)
    shapes.cylinder(
        f"{name}.trunk",
        0.14,
        h * 0.45,
        look.mat("#8a5a3b", rough=0.9),
        (0, 0, h * 0.22),
        radius2=0.1,
        parent=r,
    )
    leaf = look.mat(o.get("color", "#5fae5a"), rough=0.8)
    for i, (x, y, z, s) in enumerate(
        (
            (0, 0, 0.62, 0.42),
            (0.25, 0.1, 0.52, 0.3),
            (-0.24, -0.08, 0.55, 0.32),
            (0.05, -0.2, 0.75, 0.28),
        )
    ):
        shapes.sphere(
            f"{name}.leaf{i}", h * s, leaf, (x * h, y * h, z * h), parent=r, segments=16, rings=10
        )
    return r


def pine(name, o, p):
    r = _root(name, p)
    h = o.get("h", 4.0)
    shapes.cylinder(f"{name}.trunk", 0.12, h * 0.3, look.mat("#7a4e33"), (0, 0, h * 0.15), parent=r)
    m = look.mat(o.get("color", "#3f8c5a"), rough=0.8)
    for i in range(3):
        shapes.cylinder(
            f"{name}.cone{i}",
            h * (0.32 - i * 0.07),
            h * 0.35,
            m,
            (0, 0, h * (0.38 + i * 0.2)),
            radius2=0.0,
            segments=16,
            parent=r,
        )
    return r


def bench(name, o, p):
    r = _root(name, p)
    wood = look.mat("#b9814e", rough=0.6)
    for i, z in enumerate((0.45, 0.47)):
        shapes.rbox(f"{name}.slat{i}", (1.6, 0.16, 0.04), wood, (0, -0.12 + i * 0.2, z), 0.01, r)
    shapes.rbox(f"{name}.back", (1.6, 0.04, 0.3), wood, (0, 0.2, 0.75), 0.01, r)
    for sx in (-1, 1):
        shapes.rbox(
            f"{name}.leg{sx}", (0.06, 0.45, 0.45), look.mat("#333"), (sx * 0.7, 0, 0.225), 0.01, r
        )
    return r


def lamp_post(name, o, p):
    r = _root(name, p)
    m = look.mat("#2f3a44", metal=0.5, rough=0.4)
    shapes.cylinder(f"{name}.pole", 0.06, 4.0, m, (0, 0, 2.0), parent=r)
    shapes.rbox(f"{name}.arm", (0.08, 0.7, 0.08), m, (0, -0.32, 3.95), 0.02, r)
    shapes.sphere(
        f"{name}.bulb",
        0.14,
        look.mat("#fff2c4", emit=3.0 if o.get("on") else 0.3),
        (0, -0.65, 3.85),
        (1, 1, 0.6),
        r,
    )
    return r


def box(name, o, p):
    r = _root(name, p)
    s = o.get("size", (0.5, 0.5, 0.5))
    shapes.rbox(
        f"{name}.b", s, look.mat(o.get("color", "#c89b6d"), rough=0.8), (0, 0, s[2] / 2), 0.03, r
    )
    return r


def ball(name, o, p):
    r = _root(name, p)
    d = o.get("d", 0.3)
    shapes.sphere(
        f"{name}.b", d / 2, look.mat(o.get("color", "#ff7a3d"), rough=0.4), (0, 0, d / 2), parent=r
    )
    return r


def barbell(name, o, p):
    r = _root(name, p)
    steel = look.mat("#c3c8cd", metal=1, rough=0.25)
    shapes.cylinder(f"{name}.bar", 0.025, 2.0, steel, (0, 0, o.get("z", 0.25)), (0, 90, 0), r)
    for sx in (-1, 1):
        for i, (rad, col) in enumerate(((0.25, "#d23c3c"), (0.22, "#2d6cdf"), (0.18, "#f2c12e"))):
            shapes.cylinder(
                f"{name}.plate{sx}{i}",
                rad,
                0.06,
                look.mat(col, rough=0.5),
                (sx * (0.75 - i * 0.07), 0, o.get("z", 0.25)),
                (0, 90, 0),
                r,
            )
    return r


def weight_bench(name, o, p):
    r = _root(name, p)
    shapes.rbox(
        f"{name}.pad", (0.35, 1.3, 0.12), look.mat("#222", rough=0.6), (0, 0, 0.45), 0.04, r
    )
    for sx in (-1, 1):
        shapes.rbox(
            f"{name}.rack{sx}",
            (0.06, 0.06, 1.2),
            look.mat("#555", metal=0.7),
            (sx * 0.55, 0.55, 0.6),
            0.01,
            r,
        )
    shapes.rbox(
        f"{name}.foot", (0.08, 1.2, 0.36), look.mat("#555", metal=0.7), (0, 0, 0.2), 0.02, r
    )
    return r


def door(name, o, p):
    """A door in its frame; the leaf turns on `{name}.hinge` (the "open" key of a prop)."""
    r = _root(name, p)
    shapes.rbox(f"{name}.frame", (1.05, 0.12, 2.2), look.mat("#efe7da"), (0, 0, 1.1), 0.02, r)
    shapes.rbox(
        f"{name}.void", (0.94, 0.02, 2.1), look.mat("#15120f", rough=1), (0, 0.04, 1.05), 0.0, r
    )
    hinge = shapes.empty(f"{name}.hinge", (-0.46, -0.03, 0), r)
    shapes.rbox(
        f"{name}.leaf",
        (0.92, 0.08, 2.08),
        look.mat(o.get("color", "#a8744a"), rough=0.6),
        (0.46, 0, 1.05),
        0.02,
        hinge,
    )
    shapes.sphere(
        f"{name}.knob",
        0.04,
        look.mat("#d4b05a", metal=1, rough=0.2),
        (0.82, -0.07, 1.0),
        parent=hinge,
    )
    if o.get("text"):
        shapes.rbox(
            f"{name}.plate",
            (0.5, 0.02, 0.22),
            look.mat("#ffffff"),
            (0.46, -0.05, 1.75),
            0.01,
            hinge,
        )
        shapes.text(
            f"{name}.txt",
            o["text"],
            look.mat("#c0392b"),
            0.11,
            (0.46, -0.065, 1.75),
            font_path=FONT,
            parent=hinge,
        )
    return r


def window(name, o, p):
    r = _root(name, p)
    w, h = o.get("w", 1.3), o.get("h", 1.3)
    shapes.rbox(f"{name}.frame", (w + 0.1, 0.1, h + 0.1), look.mat("#ffffff"), (0, 0, 1.5), 0.02, r)
    shapes.plane(
        f"{name}.sky",
        (w, h),
        look.mat(o.get("color", "#a9d8ff"), emit=1.2),
        (0, -0.051, 1.5),
        (90, 0, 0),
        r,
    )
    shapes.rbox(f"{name}.mullion", (0.04, 0.12, h), look.mat("#ffffff"), (0, 0, 1.5), 0.01, r)
    shapes.rbox(f"{name}.transom", (w, 0.12, 0.04), look.mat("#ffffff"), (0, 0, 1.5), 0.01, r)
    return r


def plant(name, o, p):
    r = _root(name, p)
    shapes.cylinder(
        f"{name}.pot",
        0.17,
        0.32,
        look.mat("#c86f4b", rough=0.7),
        (0, 0, 0.16),
        radius2=0.13,
        parent=r,
    )
    leaf = look.mat("#4f9a57", rough=0.8)
    for i in range(6):
        a = i / 6 * math.tau
        lf = shapes.sphere(
            f"{name}.leaf{i}",
            0.16,
            leaf,
            (math.cos(a) * 0.12, math.sin(a) * 0.12, 0.55),
            (0.4, 1.0, 0.12),
            r,
            segments=12,
            rings=8,
        )
        lf.rotation_euler = (R(35), 0, a)
    return r


def cup(name, o, p):
    r = _root(name, p)
    shapes.cylinder(
        f"{name}.c",
        0.045,
        0.11,
        look.mat(o.get("color", "#ffffff"), rough=0.3),
        (0, 0, 0.055),
        parent=r,
    )
    return r


def burger(name, o, p):
    r = _root(name, p)
    s = o.get("s", 1.0)
    for i, (h, c, rad) in enumerate(
        (
            (0.05, "#d9963f", 0.12),
            (0.035, "#5a3524", 0.125),
            (0.015, "#f5c242", 0.13),
            (0.015, "#69b34c", 0.13),
            (0.07, "#e0a24c", 0.12),
        )
    ):
        shapes.cylinder(
            f"{name}.l{i}",
            rad * s,
            h * s,
            look.mat(c, rough=0.6),
            (0, 0, (0.03 + i * 0.045) * s),
            bevel=0.01 * s,
            parent=r,
        )
    return r


def money(name, o, p):
    r = _root(name, p)
    n = int(o.get("n", 5))
    g = look.mat("#78c26a", rough=0.7)
    for i in range(n):
        shapes.rbox(f"{name}.s{i}", (0.16, 0.07, 0.02), g, (0, 0, 0.01 + i * 0.022), 0.003, r)
    return r


def rocket(name, o, p):
    r = _root(name, p)
    body = look.mat("#f2f2f2", rough=0.35)
    red = look.mat("#d6453d", rough=0.4)
    shapes.cylinder(f"{name}.body", 0.5, 3.0, body, (0, 0, 2.0), parent=r)
    shapes.cylinder(f"{name}.nose", 0.5, 1.0, red, (0, 0, 4.0), radius2=0.0, parent=r)
    for i in range(3):
        a = i / 3 * math.tau
        fin = shapes.rbox(
            f"{name}.fin{i}",
            (0.06, 0.7, 0.9),
            red,
            (math.cos(a) * 0.55, math.sin(a) * 0.55, 0.8),
            0.02,
            r,
        )
        fin.rotation_euler = (0, 0, a + R(90))
    shapes.cylinder(
        f"{name}.win", 0.18, 0.05, look.mat("#7fc8ff", emit=0.8), (0, -0.5, 2.8), (90, 0, 0), r
    )
    if o.get("fire", True):
        shapes.cylinder(
            f"{name}.fire",
            0.4,
            1.4,
            look.mat("#ffb43a", emit=6),
            (0, 0, -0.2),
            radius2=0.05,
            parent=r,
        ).rotation_euler = (R(180), 0, 0)
    return r


def house(name, o, p):
    r = _root(name, p)
    shapes.rbox(
        f"{name}.walls",
        (4, 4, 3),
        look.mat(o.get("color", "#f3e2c3"), rough=0.8),
        (0, 0, 1.5),
        0.05,
        r,
    )
    roof = shapes.cylinder(
        f"{name}.roof",
        3.2,
        4.4,
        look.mat("#c1503e", rough=0.7),
        (0, 0, 3.6),
        (90, 0, 0),
        r,
        segments=3,
    )
    roof.rotation_euler = (R(90), 0, R(90))
    roof.scale = (1, 0.55, 1)
    door(f"{name}.door", {}, r).location = (0, -2.02, 0)
    return r


def building(name, o, p):
    """A city block: a box with rows of lit windows (the window grid is one emissive pattern)."""
    r = _root(name, p)
    w, d, h = o.get("w", 6), o.get("d", 6), o.get("h", 14)
    shapes.rbox(
        f"{name}.mass",
        (w, d, h),
        look.mat(o.get("color", "#d9d2c7"), rough=0.8),
        (0, 0, h / 2),
        0.08,
        r,
    )
    win = look.mat("#9cc9ef", rough=0.1, spec=0.7)
    cols, rows = max(1, int(w / 1.6)), max(1, int(h / 2.6))
    for i in range(cols):
        for j in range(rows):
            x = -w / 2 + (i + 0.5) * w / cols
            z = 1.6 + j * (h - 1.0) / rows
            shapes.plane(
                f"{name}.w{i}_{j}",
                (w / cols * 0.55, 1.2),
                win,
                (x, -d / 2 - 0.01, z),
                (90, 0, 0),
                r,
            )
    if o.get("text"):
        sign_c = look.mat(o.get("sign_color", "#d9483b"), rough=0.5)
        shapes.rbox(f"{name}.sign", (w * 0.85, 0.15, 0.9), sign_c, (0, -d / 2 - 0.1, 3.4), 0.04, r)
        shapes.text(
            f"{name}.signtxt",
            o["text"],
            look.mat("#ffffff"),
            0.5,
            (0, -d / 2 - 0.19, 3.4),
            font_path=FONT,
            parent=r,
        )
    return r


def shop(name, o, p):
    """A street shop: front with an awning, a sign and a door."""
    r = _root(name, p)
    w = o.get("w", 4.5)
    color = o.get("color", "#f0e2cf")
    shapes.rbox(f"{name}.mass", (w, 4, 6.5), look.mat(color, rough=0.8), (0, 2, 3.25), 0.05, r)
    shapes.plane(
        f"{name}.glass",
        (w * 0.55, 1.8),
        look.mat("#a8d4f2", rough=0.05, spec=0.8),
        (-w * 0.15, -0.01, 1.4),
        (90, 0, 0),
        r,
    )
    door(f"{name}.door", {"color": "#7b5134"}, r).location = (w * 0.3, -0.02, 0)
    aw = look.mat(o.get("awning", "#d9483b"), rough=0.7)
    a = shapes.rbox(f"{name}.awning", (w, 1.1, 0.08), aw, (0, -0.5, 2.75), 0.03, r)
    a.rotation_euler = (R(-14), 0, 0)
    if o.get("text"):
        shapes.rbox(
            f"{name}.board",
            (w * 0.9, 0.12, 0.7),
            look.mat(o.get("sign_color", "#ffffff")),
            (0, -0.07, 3.5),
            0.03,
            r,
        )
        shapes.text(
            f"{name}.txt",
            o["text"],
            look.mat(o.get("text_color", "#c0392b")),
            0.42,
            (0, -0.15, 3.5),
            font_path=FONT,
            parent=r,
        )
    for i in range(int(w / 1.5)):
        shapes.plane(
            f"{name}.up{i}",
            (0.8, 1.1),
            look.mat("#a8d4f2", rough=0.05),
            (-w / 2 + 0.75 + i * 1.5, -0.01, 5.0),
            (90, 0, 0),
            r,
        )
    return r


def sign(name, o, p):
    """A board with big text on a stand (labels, warnings, prices)."""
    r = _root(name, p)
    t = o.get("text", "")
    w = max(1.0, 0.36 * len(t) * o.get("size", 0.4) / 0.4)
    shapes.rbox(
        f"{name}.board",
        (w, 0.08, 0.7),
        look.mat(o.get("color", "#ffffff")),
        (0, 0, o.get("z", 1.8)),
        0.03,
        r,
    )
    shapes.text(
        f"{name}.txt",
        t,
        look.mat(o.get("text_color", "#1b1b1b")),
        o.get("size", 0.4),
        (0, -0.05, o.get("z", 1.8)),
        font_path=FONT,
        parent=r,
    )
    if o.get("stand", True):
        shapes.cylinder(
            f"{name}.pole",
            0.04,
            o.get("z", 1.8) - 0.3,
            look.mat("#666"),
            (0, 0.02, (o.get("z", 1.8) - 0.3) / 2),
            parent=r,
        )
    return r


def newspaper(name, o, p):
    """A big newspaper held up or lying flat; `text` is the headline (use \\n for two lines)."""
    r = _root(name, p)
    paper = look.mat("#f3efe6", rough=0.9)
    shapes.rbox(f"{name}.sheet", (0.9, 0.01, 1.2), paper, (0, 0, 0.6), 0.004, r)
    ink = look.mat("#1d1d1d")
    shapes.text(
        f"{name}.mast",
        o.get("masthead", "GÜNDEM"),
        ink,
        0.12,
        (0, -0.008, 1.08),
        font_path=FONT,
        parent=r,
    )
    shapes.text(
        f"{name}.head",
        o.get("text", "SON DAKİKA"),
        look.mat("#b8322a"),
        0.1,
        (0, -0.008, 0.88),
        font_path=FONT,
        parent=r,
    )
    for i in range(7):
        shapes.rbox(
            f"{name}.col{i}",
            (0.78 if i % 3 else 0.5, 0.004, 0.02),
            look.mat("#9a958c"),
            (0.0, -0.008, 0.62 - i * 0.07),
            0.002,
            r,
        )
    return r


def screen(name, o, p):
    """A wall screen / security monitor with a colored glow and optional text."""
    r = _root(name, p)
    w, h = o.get("w", 1.6), o.get("h", 0.9)
    shapes.rbox(
        f"{name}.bezel",
        (w + 0.08, 0.06, h + 0.08),
        look.mat("#1a1a1a"),
        (0, 0, o.get("z", 1.6)),
        0.02,
        r,
    )
    shapes.plane(
        f"{name}.s",
        (w, h),
        look.mat(o.get("color", "#2a3b4a"), emit=1.0),
        (0, -0.032, o.get("z", 1.6)),
        (90, 0, 0),
        r,
    )
    if o.get("text"):
        shapes.text(
            f"{name}.t",
            o["text"],
            look.mat("#e8f6ff", emit=2.0),
            o.get("size", 0.14),
            (0, -0.04, o.get("z", 1.6)),
            font_path=FONT,
            parent=r,
        )
    return r


def calendar(name, o, p):
    r = _root(name, p)
    z = o.get("z", 1.7)
    shapes.rbox(f"{name}.page", (0.6, 0.03, 0.7), look.mat("#ffffff"), (0, 0, z), 0.02, r)
    shapes.rbox(
        f"{name}.top", (0.6, 0.035, 0.18), look.mat("#d23f37"), (0, -0.003, z + 0.26), 0.02, r
    )
    shapes.text(
        f"{name}.month",
        o.get("month", "KASIM"),
        look.mat("#ffffff"),
        0.1,
        (0, -0.025, z + 0.26),
        font_path=FONT,
        parent=r,
    )
    shapes.text(
        f"{name}.day",
        str(o.get("text", "1")),
        look.mat("#1d1d1d"),
        0.3,
        (0, -0.02, z - 0.05),
        font_path=FONT,
        parent=r,
    )
    return r


def clock(name, o, p):
    """A wall clock; `hours` (e.g. 10.25 = 10:15) sets the hands."""
    r = _root(name, p)
    z = o.get("z", 2.2)
    shapes.cylinder(f"{name}.rim", 0.32, 0.05, look.mat("#2b2b2b"), (0, 0.02, z), (90, 0, 0), r)
    shapes.cylinder(f"{name}.face", 0.29, 0.05, look.mat("#ffffff"), (0, 0, z), (90, 0, 0), r)
    hours = float(o.get("hours", 10.1))
    for hand, length, width, ang in (
        ("hour", 0.15, 0.03, hours / 12 * 360),
        ("min", 0.23, 0.02, (hours % 1) * 360),
    ):
        pivot = shapes.empty(f"{name}.{hand}p", (0, -0.035, z), r)
        shapes.rbox(
            f"{name}.{hand}",
            (width, 0.01, length),
            look.mat("#111111"),
            (0, 0, length / 2),
            0.005,
            pivot,
        )
        pivot.rotation_euler = (0, R(ang), 0)
    return r


def arrow(name, o, p):
    """A big 3D arrow pointing down at something (place it above the target)."""
    r = _root(name, p)
    m = look.mat(o.get("color", "#e8372b"), rough=0.4, emit=0.4)
    shapes.rbox(f"{name}.shaft", (0.18, 0.18, 0.7), m, (0, 0, 0.75), 0.06, r)
    shapes.cylinder(
        f"{name}.head", 0.32, 0.4, m, (0, 0, 0.2), radius2=0.0, parent=r
    ).rotation_euler = (R(180), 0, 0)
    return r


def _earth_material():
    m = bpy.data.materials.get("vk_earth")
    if m:
        return m
    img = bpy.data.images.get("earth_bluemarble")
    if img is None:
        return None
    m = bpy.data.materials.new("vk_earth")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.projection = "SPHERE"
    nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
    nt.links.new(tex.outputs["Color"], p.inputs["Base Color"])
    p.inputs["Roughness"].default_value = 0.55
    p.inputs["Specular IOR Level"].default_value = 0.3
    return m


def _atmosphere():
    m = bpy.data.materials.get("vk_atmo")
    if m:
        return m
    m = bpy.data.materials.new("vk_atmo")
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    pw = nt.nodes.new("ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 2.5
    em = nt.nodes.new("ShaderNodeEmission")
    em.inputs["Color"].default_value = look.hex_rgba("#7cc4ff")
    em.inputs["Strength"].default_value = 3.0
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    nt.links.new(pw.outputs[0], mix.inputs["Fac"])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs["Surface"])
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED"
    return m


def globe(name, o, p):
    """The Earth: NASA Blue Marble (public domain) with a glowing atmosphere; stylised blobs
    when the world library is not installed."""
    r = _root(name, p)
    rad = o.get("r", 3.0)
    load_world()
    em = _earth_material()
    if em is not None:
        e = shapes.sphere(f"{name}.earth", rad, em, (0, 0, rad), parent=r, segments=128, rings=64)
        e.rotation_euler = (R(o.get("axis", 0)), 0, R(o.get("spin", 200)))
        shapes.sphere(
            f"{name}.atmo", rad * 1.025, _atmosphere(), (0, 0, rad), parent=r, segments=96, rings=48
        )
        return r
    shapes.sphere(
        f"{name}.ocean",
        rad,
        look.mat("#3c8fd8", rough=0.4),
        (0, 0, rad),
        parent=r,
        segments=64,
        rings=32,
    )
    land = look.mat("#68b85a", rough=0.8)
    import random

    rng = random.Random(4)
    for i in range(16):
        th, ph = rng.uniform(0, math.tau), rng.uniform(-1.1, 1.1)
        v = (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph))
        s = shapes.sphere(
            f"{name}.land{i}",
            rad * rng.uniform(0.18, 0.35),
            land,
            (v[0] * rad * 0.9, v[1] * rad * 0.9, rad + v[2] * rad * 0.9),
            (1, 1, 0.35),
            r,
            segments=16,
            rings=8,
        )
        s.rotation_euler = (0, math.acos(max(-1, min(1, v[2]))), th)
    clouds = look.mat("#ffffff", rough=0.9)
    for i in range(10):
        th, ph = rng.uniform(0, math.tau), rng.uniform(-1.2, 1.2)
        v = (math.cos(ph) * math.cos(th), math.cos(ph) * math.sin(th), math.sin(ph))
        shapes.sphere(
            f"{name}.cloud{i}",
            rad * 0.1,
            clouds,
            (v[0] * rad * 1.05, v[1] * rad * 1.05, rad + v[2] * rad * 1.05),
            (2.2, 1.0, 0.5),
            r,
            segments=12,
            rings=6,
        )
    return r


MOON_DIR = ""  # assets/moon (NASA CGI Moon Kit), set by the runner


def _moon_material():
    """The Moon: NASA's LRO colour mosaic and height map (public domain); a procedural
    stand-in when the files are not there."""
    import os

    have = bpy.data.materials.get("moon_surface")  # shots clear materials: look it up by name
    if have is not None:
        return have
    m = bpy.data.materials.new("moon_surface")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.97
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.1
    color = os.path.join(MOON_DIR, "moon_color_2k.jpg") if MOON_DIR else ""
    height = os.path.join(MOON_DIR, "moon_height_1k.jpg") if MOON_DIR else ""
    coord = nt.nodes.new("ShaderNodeTexCoord")
    if color and os.path.exists(color):
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(color, check_existing=True)
        tex.projection = "SPHERE"
        nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        bright = nt.nodes.new("ShaderNodeBrightContrast")
        bright.inputs["Contrast"].default_value = 0.25
        nt.links.new(tex.outputs["Color"], bright.inputs["Color"])
        nt.links.new(bright.outputs["Color"], bsdf.inputs["Base Color"])
        hsrc = None
        if height and os.path.exists(height):
            hsrc = nt.nodes.new("ShaderNodeTexImage")
            hsrc.image = bpy.data.images.load(height, check_existing=True)
            hsrc.image.colorspace_settings.name = "Non-Color"
            hsrc.projection = "SPHERE"
            nt.links.new(coord.outputs["Object"], hsrc.inputs["Vector"])
        craters = nt.nodes.new("ShaderNodeTexVoronoi")  # small craters the map is too coarse for
        craters.inputs["Scale"].default_value = 60.0
        nt.links.new(coord.outputs["Object"], craters.inputs["Vector"])
        add = nt.nodes.new("ShaderNodeMath")
        add.operation = "MULTIPLY_ADD"
        add.inputs[1].default_value = 0.15
        nt.links.new(craters.outputs["Distance"], add.inputs[0])
        if hsrc is not None:
            nt.links.new(hsrc.outputs["Color"], add.inputs[2])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.6
        nt.links.new(add.outputs["Value"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        m.diffuse_color = look.hex_rgba("#a9a7a2")
        return m
    seas = nt.nodes.new("ShaderNodeTexNoise")
    seas.inputs["Scale"].default_value = 1.6
    seas.inputs["Detail"].default_value = 3.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = look.hex_rgba("#5f5d58")
    ramp.color_ramp.elements[1].position = 0.6
    ramp.color_ramp.elements[1].color = look.hex_rgba("#d3d1ca")
    nt.links.new(seas.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    craters = nt.nodes.new("ShaderNodeTexVoronoi")
    craters.inputs["Scale"].default_value = 14.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.45
    nt.links.new(craters.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    m.diffuse_color = look.hex_rgba("#bdbbb4")
    return m


def moon(name, o, p):
    r = _root(name, p)
    rad = o.get("r", 1.0)
    shapes.sphere(f"{name}.m", rad, _moon_material(), (0, 0, rad), parent=r, segments=64, rings=32)
    return r


def cloud(name, o, p):
    r = _root(name, p)
    m = look.mat("#ffffff", rough=0.95)
    for i, (x, z, s) in enumerate(
        ((0, 0, 1), (0.8, -0.1, 0.75), (-0.8, -0.15, 0.7), (0.3, 0.35, 0.65))
    ):
        shapes.sphere(
            f"{name}.p{i}",
            0.7 * s,
            m,
            (x, 0, z + o.get("z", 6)),
            (1, 0.7, 0.8),
            r,
            segments=16,
            rings=8,
        )
    return r


def water_jet(name, o, p):
    """A straight jet/beam (urine, water, laser) from the root upwards, `len` long."""
    r = _root(name, p)
    ln = o.get("len", 3.0)
    shapes.cylinder(
        f"{name}.jet",
        o.get("r", 0.04),
        ln,
        look.mat(o.get("color", "#f2d64b"), rough=0.2, emit=o.get("emit", 0.6)),
        (0, 0, ln / 2),
        parent=r,
    )
    return r


def crowd_person(name, o, p):
    """A tiny low-detail person for crowds and far shots (cheap: 3 parts)."""
    r = _root(name, p)
    shirt = look.mat(o.get("color", "#e25b45"))
    shapes.rbox(f"{name}.b", (0.45, 0.3, 0.8), shirt, (0, 0, 0.95), 0.12, r)
    shapes.rbox(f"{name}.l", (0.4, 0.28, 0.55), look.mat("#3d5a8a"), (0, 0, 0.3), 0.08, r)
    shapes.sphere(
        f"{name}.h",
        0.25,
        look.mat(o.get("skin", "#e9b98f")),
        (0, 0, 1.6),
        parent=r,
        segments=16,
        rings=8,
    )
    return r


def wanted(name, o, p):
    """An ARANIYOR poster on a wall: a face silhouette, the name and the reward."""
    r = _root(name, p)
    z = o.get("z", 1.6)
    shapes.rbox(
        f"{name}.paper", (0.62, 0.01, 0.86), look.mat("#e9dcc0", rough=0.95), (0, 0, z), 0.003, r
    )
    shapes.text(
        f"{name}.head",
        o.get("title", "ARANIYOR"),
        look.mat("#7a1d14"),
        0.12,
        (0, -0.008, z + 0.32),
        font_path=FONT,
        parent=r,
    )
    shapes.rbox(
        f"{name}.photo", (0.36, 0.004, 0.36), look.mat("#c9b994"), (0, -0.006, z + 0.04), 0.002, r
    )
    ink = look.mat("#2b241c")
    shapes.sphere(
        f"{name}.headsil",
        0.075,
        ink,
        (0, -0.01, z + 0.1),
        scale=(1, 0.1, 1.2),
        parent=r,
        segments=16,
        rings=8,
    )
    shapes.sphere(
        f"{name}.shoulders",
        0.15,
        ink,
        (0, -0.01, z - 0.1),
        scale=(1, 0.1, 0.5),
        parent=r,
        segments=16,
        rings=8,
    )
    shapes.text(
        f"{name}.name",
        o.get("text", ""),
        ink,
        0.06,
        (0, -0.008, z - 0.22),
        font_path=FONT,
        parent=r,
    )
    shapes.text(
        f"{name}.reward",
        o.get("reward", "ÖDÜL"),
        look.mat("#7a1d14"),
        0.05,
        (0, -0.008, z - 0.33),
        font_path=FONT,
        parent=r,
    )
    return r


def map(name, o, p):  # shadows the builtin on purpose: the kind is "map"
    """A wall map: land and sea, a title and red pins (`pins` in -1..1 of the map)."""
    r = _root(name, p)
    z, w, h = o.get("z", 1.6), o.get("w", 1.6), o.get("h", 1.0)
    shapes.rbox(
        f"{name}.board", (w + 0.06, 0.03, h + 0.06), look.mat("#6b4b2e"), (0, 0, z), 0.01, r
    )
    shapes.plane(
        f"{name}.sea", (w, h), look.mat("#8fc6db", rough=0.9), (0, -0.017, z), (90, 0, 0), r
    )
    rng = __import__("random").Random(len(o.get("text", "")) + 7)
    land = look.mat("#d8cf9e", rough=0.95)
    for k in range(7):
        sx, sz = rng.uniform(0.12, 0.38) * w, rng.uniform(0.08, 0.3) * h
        shapes.sphere(
            f"{name}.land{k}",
            1.0,
            land,
            (rng.uniform(-0.35, 0.35) * w, -0.019, z + rng.uniform(-0.3, 0.3) * h),
            scale=(sx, 0.004, sz),
            parent=r,
            segments=12,
            rings=6,
        )
    pin = look.mat("#d7261e", rough=0.3)
    for k, (u, v) in enumerate(o.get("pins", [[0.1, 0.05]])):
        shapes.sphere(
            f"{name}.pin{k}",
            0.03,
            pin,
            (u * w / 2, -0.05, z + v * h / 2),
            parent=r,
            segments=12,
            rings=6,
        )
    if o.get("text"):
        shapes.text(
            f"{name}.title",
            o["text"],
            look.mat("#1d1d1d"),
            0.08,
            (0, -0.025, z + h / 2 - 0.08),
            font_path=FONT,
            parent=r,
        )
    return r


def phone_big(name, o, p):
    """A phone the size of a door: a social post on its screen (#tag, likes, user)."""
    r = _root(name, p)
    z = o.get("z", 1.3)
    shapes.rbox(
        f"{name}.body", (1.0, 0.08, 2.0), look.mat("#111216", rough=0.25), (0, 0, z), 0.12, r
    )
    shapes.plane(
        f"{name}.scr", (0.9, 1.86), look.mat("#ffffff", emit=0.9), (0, -0.042, z), (90, 0, 0), r
    )
    shapes.plane(
        f"{name}.img",
        (0.9, 0.9),
        look.mat(o.get("color", "#3aa0ff"), emit=1.0),
        (0, -0.044, z + 0.1),
        (90, 0, 0),
        r,
    )
    shapes.sphere(
        f"{name}.avatar",
        0.05,
        look.mat("#ff7a59"),
        (-0.36, -0.046, z + 0.72),
        scale=(1, 0.2, 1),
        parent=r,
        segments=16,
        rings=8,
    )
    shapes.text(
        f"{name}.user",
        o.get("user", "@pekiya"),
        look.mat("#111111"),
        0.05,
        (-0.28, -0.046, z + 0.72),
        align="LEFT",
        font_path=FONT,
        parent=r,
    )
    shapes.text(
        f"{name}.tag",
        o.get("text", "#pekiya"),
        look.mat("#1d6fd1"),
        0.07,
        (0, -0.046, z - 0.52),
        font_path=FONT,
        parent=r,
    )
    shapes.text(
        f"{name}.likes",
        f"♥ {o.get('likes', '1,2 M')}",
        look.mat("#e0245e"),
        0.065,
        (-0.2, -0.046, z - 0.7),
        font_path=FONT,
        parent=r,
    )
    return r


# --------------------------------------------------------------------------- cutaway (kesit)
PITS: dict[str, list] = {}  # pit id -> its cutter objects (reset per shot by the runner)
LAYER_MATS = {  # material -> (colour, roughness, alpha, emit)
    "water": ("#4fb3d4", 0.05, 0.55, 0.0), "green_water": ("#6f9b3c", 0.1, 0.8, 0.0),
    "murky": ("#5d5a3e", 0.2, 0.9, 0.0), "sand": ("#d9bf86", 0.95, 1.0, 0.0),
    "gravel": ("#9b958b", 0.9, 1.0, 0.0), "concrete": ("#a6a39d", 0.85, 1.0, 0.0),
    "asphalt": ("#3a3b3d", 0.8, 1.0, 0.0), "soil": ("#5a3b24", 0.95, 1.0, 0.0),
    "clay": ("#b06a3c", 0.9, 1.0, 0.0), "liner": ("#1b1c1e", 0.45, 1.0, 0.0),
    "ice": ("#dff3fb", 0.08, 0.75, 0.0), "snow": ("#f7f9fb", 0.9, 1.0, 0.0),
    "sludge": ("#4a3d2a", 0.6, 1.0, 0.0), "oil": ("#121212", 0.05, 1.0, 0.0),
    "lava": ("#ff5a14", 0.6, 1.0, 6.0), "foam": ("#f2e9d8", 0.9, 1.0, 0.0),
    "stone": ("#8d857a", 0.85, 1.0, 0.0),
}  # fmt: skip


def _layer_material(kind: str, color: str | None = None):
    col, rough, alpha, emit = LAYER_MATS.get(kind, LAYER_MATS["soil"])
    col = color or col
    if alpha >= 1.0 and kind not in ("gravel", "asphalt", "concrete", "stone"):
        return look.mat(col, rough=rough, emit=emit)
    m = bpy.data.materials.new(f"layer_{kind}")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Base Color"].default_value = look.hex_rgba(col)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Alpha"].default_value = alpha
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.8 if alpha < 1 else 0.3
    if hasattr(m, "surface_render_method") and alpha < 1:
        m.surface_render_method = "BLENDED"
    coord = nt.nodes.new("ShaderNodeTexCoord")
    if kind in ("gravel", "asphalt", "concrete", "stone"):  # stones / aggregate in the bump
        vor = nt.nodes.new("ShaderNodeTexVoronoi")
        vor.inputs["Scale"].default_value = {
            "gravel": 28.0,
            "asphalt": 60.0,
            "concrete": 90.0,
            "stone": 7.0,
        }[kind]
        nt.links.new(coord.outputs["Object"], vor.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.7 if kind in ("gravel", "stone") else 0.25
        nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    else:  # water: small ripples
        noise = nt.nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 4.0
        nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.12
        nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    m.diffuse_color = look.hex_rgba(col)
    return m


def pit(name, o, p):
    """A hole dug into the cutaway block, cut in half by its front face (`at` y = 0 puts the
    middle of the pit on the cut). `shape`: bowl | box | shelf (a pond with a planting shelf) |
    trench | tunnel; `size` [w, d, depth] m. The soil it removes keeps the strata."""
    r = _root(name, p)
    shape = o.get("shape", "bowl")
    w, d, depth = ([*list(o.get("size", (3.0, 2.6, 1.2))), 1.2])[:3]
    x, y = ([*list(o.get("at", (0, 0))), 0])[:2]
    strata = bpy.data.materials.get("set.strata") or look.mat("#5a3b24", rough=0.95)
    cutters = []
    if shape == "bowl":
        c = shapes.sphere(
            f"{name}.cut", 1.0, strata, (x, y, 0.0), (w / 2, d / 2, depth), segments=48, rings=24
        )
        cutters.append(c)
    elif shape == "shelf":
        cutters.append(
            shapes.rbox(
                f"{name}.cut0", (w, d, depth * 0.4 + 0.4), strata, (x, y, -depth * 0.2 + 0.2), 0.08
            )
        )
        cutters.append(
            shapes.rbox(
                f"{name}.cut1",
                (w * 0.55, d * 0.6, depth + 0.4),
                strata,
                (x, y, -depth / 2 + 0.2),
                0.08,
            )
        )
    elif shape == "tunnel":
        z = -float(o.get("z", depth))
        c = shapes.cylinder(f"{name}.cut", d / 2, w, strata, (x, y, z), (0, 90, 0), segments=32)
        cutters.append(c)
    else:  # box, trench; `top` m below the lawn keeps the ground over it (a buried band)
        top = float(o.get("top", 0.0))
        if top > 0:
            box = (w, d, depth)
            centre = (x, y, -top - depth / 2)
        else:
            box = (w, d, depth + 0.4)
            centre = (x, y, -depth / 2 + 0.2)
        cutters.append(shapes.rbox(f"{name}.cut", box, strata, centre, 0.04 if top <= 0 else 0.0))
    soil = bpy.data.objects.get("set.soil")
    for c in cutters:
        c.parent = r  # the pit's size is its cutters' (the camera frames a pit by them)
        c.hide_render = True
        c.display_type = "WIRE"
        if soil is not None:
            mod = soil.modifiers.new(f"dig.{c.name}", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.object = c
            mod.solver = "EXACT"
            if hasattr(mod, "material_mode"):
                mod.material_mode = "TRANSFER"
    PITS[o.get("id") or name] = cutters
    o["at"] = (0, 0)  # the cutters are placed in world space already
    return r


def bake_ground() -> None:
    """Dig the pits for good: the soil's boolean cuts become plain geometry once, instead of
    being recomputed on every frame (several exact booleans per frame made renders 5x slower)."""
    soil = bpy.data.objects.get("set.soil")
    if soil is None or not any(m.type == "BOOLEAN" for m in soil.modifiers):
        return
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(soil.evaluated_get(dg))
    old = soil.data
    soil.modifiers.clear()
    soil.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)


def layer(name, o, p):
    """What fills a pit between two depths (`from`, `to`: metres, negative below the lawn):
    water, gravel, concrete, sand... Only the half behind the cut exists, so the cut shows it in
    section. `shell` (or material "liner") makes a skin `t` thick on the pit's walls. Its origin
    is at its bottom: a scale of [1, 1, 0] grows it upward (water filling up)."""
    from mathutils import Matrix, Vector

    r = _root(name, p)
    cutters = PITS.get(o.get("pit", ""))
    if not cutters:
        raise ValueError(f"layer: '{o.get('pit')}' adında bir pit yok (pit önce gelmeli)")
    kind = o.get("material", "water")
    z0, z1 = float(o.get("from", -1.2)), float(o.get("to", 0.0))
    shell = bool(o.get("shell")) or kind == "liner"
    m = _layer_material(kind, o.get("color"))
    sc = bpy.context.scene
    parts = []
    for c in cutters:
        dup = c.copy()
        dup.data = c.data.copy()
        sc.collection.objects.link(dup)
        dup.hide_render = False
        dup.data.materials.clear()
        dup.data.materials.append(m)
        for mod in list(dup.modifiers):
            dup.modifiers.remove(mod)
        if shell:
            so = dup.modifiers.new("skin", "SOLIDIFY")
            so.thickness = float(o.get("t", 0.05))
            so.offset = -1.0
        slab = shapes.rbox(
            f"{name}.slab", (80, 40, max(0.01, z1 - z0)), m, (0, 20.0, (z0 + z1) / 2), 0.0
        )
        bo = dup.modifiers.new("slab", "BOOLEAN")
        bo.operation = "INTERSECT"
        bo.object = slab
        bo.solver = "EXACT"
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        me = bpy.data.meshes.new_from_object(dup.evaluated_get(dg))
        me.transform(dup.matrix_world)
        bpy.data.objects.remove(dup)
        bpy.data.objects.remove(slab)
        if len(me.vertices) == 0:
            continue
        ob = bpy.data.objects.new(f"{name}.part{len(parts)}", me)
        sc.collection.objects.link(ob)
        parts.append(ob)
    if parts:
        xs = [ob.matrix_world @ v.co for ob in parts for v in ob.data.vertices]
        origin = Vector(((min(v.x for v in xs) + max(v.x for v in xs)) / 2, 0.0, z0))
        for ob in parts:
            ob.data.transform(Matrix.Translation(-origin))
            ob.parent = r
            for poly in ob.data.polygons:
                poly.use_smooth = kind in ("water", "green_water", "murky", "oil", "ice")
        o["at"] = (origin.x, origin.y, origin.z)
    return r


def pipe(name, o, p):
    """A pipe or a cable through `path` [[x, y, z], ...] (`r` radius, `color`)."""
    r = _root(name, p)
    pts = o.get("path") or [[0, 0, 0], [0, 0, 1]]
    cu = bpy.data.curves.new(f"{name}.c", "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = float(o.get("r", 0.06))
    cu.bevel_resolution = 6
    cu.use_fill_caps = True
    sp = cu.splines.new("POLY")
    sp.points.add(len(pts) - 1)
    for pt, co in zip(sp.points, pts, strict=True):
        pt.co = (co[0], co[1], co[2] if len(co) > 2 else 0.0, 1.0)
    ob = bpy.data.objects.new(f"{name}.pipe", cu)
    ob.data.materials.append(look.mat(o.get("color", "#2f3338"), rough=0.4, metal=0.2))
    bpy.context.collection.objects.link(ob)
    ob.parent = r
    o["at"] = (0, 0)
    return r


def fish(name, o, p):
    """A small pond fish (koi orange by default), nose towards -X; `size` in metres."""
    r = _root(name, p)
    k = float(o.get("size", 0.3)) / 0.3
    body = look.mat(o.get("color", "#f07d22"), rough=0.35, sss=0.1)
    shapes.sphere(
        f"{name}.body", 0.15 * k, body, (0, 0, 0), (1.0, 0.36, 0.42), r, segments=20, rings=12
    )
    tail = shapes.cylinder(
        f"{name}.tail",
        0.07 * k,
        0.12 * k,
        body,
        (0.17 * k, 0, 0),
        (0, 90, 0),
        r,
        segments=12,
        radius2=0.0,
    )
    tail.scale = (1.0, 0.25, 1.0)
    patch = look.mat("#fbf7f0", rough=0.4)
    shapes.sphere(
        f"{name}.patch",
        0.06 * k,
        patch,
        (-0.02 * k, 0, 0.045 * k),
        (1.3, 0.5, 0.5),
        r,
        segments=12,
        rings=8,
    )
    for sy in (-1, 1):
        shapes.sphere(f"{name}.eye{sy}", 0.012 * k, look.mat("#111111", rough=0.2),
                      (-0.12 * k, sy * 0.045 * k, 0.015 * k), parent=r, segments=8, rings=6)  # fmt: skip
    return r


def lily_pad(name, o, p):
    """A water-lily leaf floating on the surface, with a flower if `flower` is true."""
    r = _root(name, p)
    k = float(o.get("size", 0.5)) / 0.5
    shapes.cylinder(
        f"{name}.leaf",
        0.25 * k,
        0.012,
        look.mat("#3d8b3a", rough=0.5),
        (0, 0, 0),
        parent=r,
        segments=24,
    )
    if o.get("flower"):
        petal = look.mat(o.get("color", "#f5a3c0"), rough=0.5, sss=0.2)
        for i in range(6):
            a = R(60 * i)
            shapes.sphere(f"{name}.petal{i}", 0.045 * k, petal,
                          (math.cos(a) * 0.04 * k, math.sin(a) * 0.04 * k, 0.04 * k), (1.0, 0.5, 0.35),
                          r, segments=10, rings=6)  # fmt: skip
        shapes.sphere(
            f"{name}.core",
            0.02 * k,
            look.mat("#ffd23f", emit=0.4),
            (0, 0, 0.05 * k),
            parent=r,
            segments=8,
            rings=6,
        )
    return r


def tank(name, o, p):
    """A buried or standing box / drum (a filter, a septic tank, a water tank) with a label."""
    r = _root(name, p)
    w, d, h = ([*list(o.get("size", (0.8, 0.6, 0.6))), 0.6])[:3]
    m = look.mat(o.get("color", "#3f6b4a"), rough=0.5)
    if o.get("shape", "box") == "drum":
        shapes.cylinder(f"{name}.body", w / 2, h, m, (0, 0, h / 2), segments=32, parent=r)
    else:
        shapes.rbox(f"{name}.body", (w, d, h), m, (0, 0, h / 2), 0.04, r)
    if o.get("text"):
        shapes.text(f"{name}.label", o["text"], look.mat("#ffffff", emit=0.3), min(0.14, h * 0.22),
                    (0, -d / 2 - 0.01, h * 0.55), font_path=FONT, parent=r)  # fmt: skip
    return r


def hand_pump(name, o, p):
    """A cast-iron hand pump: a column, a spout towards -X, a lever on top (`color`)."""
    r = _root(name, p)
    iron = look.mat(o.get("color", "#2f5d3a"), rough=0.45, metal=0.4)
    shapes.cylinder(f"{name}.base", 0.16, 0.08, iron, (0, 0, 0.04), parent=r, segments=24)
    shapes.cylinder(f"{name}.col", 0.09, 0.95, iron, (0, 0, 0.5), parent=r, segments=24)
    shapes.sphere(f"{name}.cap", 0.11, iron, (0, 0, 0.98), (1, 1, 0.6), r, segments=16, rings=8)
    spout = shapes.cylinder(
        f"{name}.spout", 0.04, 0.32, iron, (-0.2, 0, 0.78), (0, 90, 0), r, segments=12
    )
    spout.rotation_euler = (0, math.radians(100), 0)
    lever = shapes.rbox(f"{name}.lever", (0.75, 0.05, 0.05), look.mat("#1d1f22", rough=0.4, metal=0.6),
                        (0.32, 0, 1.08), 0.02, r)  # fmt: skip
    lever.rotation_euler = (0, math.radians(-14), 0)
    return r


KIT_ROT: dict[str, float] = {}  # per-kind turn so library models face -Y like the kit's own

BUILDERS = {
    f.__name__: f
    for f in (
        bed, toilet, sink, desk, school_desk, chair, sofa, tv, laptop, phone, fridge, stove, counter,
        car, bus, tree, pine, bench, lamp_post, box, ball, barbell, weight_bench, door, window,
        plant, cup, burger, money, rocket, house, building, shop, sign, newspaper, screen, calendar,
        clock, arrow, globe, moon, cloud, water_jet, crowd_person, wanted, map, phone_big,
        pit, layer, pipe, fish, lily_pad, tank, hand_pump,
    )
}  # fmt: skip


# --------------------------------------------------------------------------- the world library
WORLD = ""  # path of vk3d_world.blend (set by the runner); empty = procedural props only
KIT = {  # kind -> library assets (one is picked per placement, the same one for the same name)
    "car": ["NormalCar1", "NormalCar2", "SUV", "SportsCar", "SportsCar2"],
    "taxi": ["Taxi"], "police_car": ["Cop"], "sports_car": ["SportsCar", "SportsCar2"], "suv": ["SUV"],
    "tree": [f"CommonTree_{i}" for i in range(1, 6)], "pine": [f"Pine_{i}" for i in range(1, 6)],
    "big_tree": [f"TwistedTree_{i}" for i in range(1, 4)], "bush": ["Bush_Common", "Bush_Common_Flowers"],
    "flowers": ["Flower_3_Group", "Flower_4_Group"], "grass": ["Grass_Common_Tall", "Grass_Wispy_Tall"],
    "rock": ["Rock_Medium_1", "Rock_Medium_2", "Rock_Medium_3"], "fern": ["Fern_1"], "shrub": ["shrub_02", "Plant_1_Big"],
    "building": ["Building_Large_2", "Building_Medium_2_001", "Building_Small_1"],
    "school_desk": ["SchoolDesk_01"], "chair": ["SchoolChair_01"], "armchair": ["ArmChair_01"], "sofa": ["Sofa_01"],
    "coffee_table": ["CoffeeTable_01"], "desk": ["metal_office_desk"], "dining_table": ["dining_table"],
    "plant": ["potted_plant_01", "potted_plant_02"], "lamp_post": ["street_lamp_01"], "fire_hydrant": ["fire_hydrant"],
    "trash_can": ["metal_trash_can"], "bench": ["painted_wooden_bench"], "box": ["cardboard_box_01"],
    "bookshelf": ["wooden_bookshelf_worn"], "laptop": ["classic_laptop"], "desk_lamp": ["desk_lamp_arm_01"],
    "cctv_camera": ["security_camera_01"], "bollard": ["Prop_Bollard"], "ac_unit": ["Prop_ACUnit"],
    "planter": ["Prop_Planter_Single", "Sidewalk_Planter"], "manhole": ["Prop_ManholeCover"],
}  # fmt: skip
FALLBACK = {  # without the library, a library-only kind is drawn as its nearest own build
    "taxi": "car", "police_car": "car", "sports_car": "car", "suv": "car", "big_tree": "tree",
    "bush": "plant", "shrub": "plant", "flowers": "plant", "grass": "plant", "fern": "plant",
    "rock": "box", "armchair": "chair", "coffee_table": "desk", "dining_table": "desk", "bookshelf": "box",
    "fire_hydrant": "box", "trash_can": "box", "bollard": "box", "ac_unit": "box", "planter": "plant",
    "manhole": "box", "desk_lamp": "cup", "cctv_camera": "box",
}  # fmt: skip
TEXT_KEYS = ("text", "hours", "masthead", "month")  # a prop with writing stays the kit's own build
_world_loaded = False
WORLD_KEEP: set[tuple[str, str]] = set()


def load_world() -> bool:
    global _world_loaded
    if _world_loaded:
        return True
    import os

    if not WORLD or not os.path.exists(WORLD):
        return False
    colls = (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.collections,
        bpy.data.images,
        bpy.data.textures,
    )
    before = {(type(x).__name__, x.name) for c in colls for x in c}
    with bpy.data.libraries.load(WORLD, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c.startswith("kit_")]
        dst.images = [i for i in src.images if i.startswith("earth_")]
    WORLD_KEEP.update({(type(x).__name__, x.name) for c in colls for x in c} - before)
    _world_loaded = True
    return True


def kit_asset(kind: str, name: str, opts: dict) -> bpy.types.Object | None:
    """An instance of a library model for `kind`, or None (no library, or a prop with text)."""
    if (
        kind not in KIT
        or any(k in opts for k in TEXT_KEYS)
        or opts.get("procedural")
        or not load_world()
    ):
        return None
    choices = [c for c in KIT[kind] if bpy.data.collections.get(f"kit_{c}")]
    if opts.get("model") in KIT[kind]:
        choices = [opts["model"]]
    if not choices:
        return None
    import zlib

    pick = choices[zlib.crc32(name.encode()) % len(choices)]
    ob = bpy.data.objects.new(name, None)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = bpy.data.collections[f"kit_{pick}"]
    bpy.context.collection.objects.link(ob)
    return ob


def kit_size(ob: bpy.types.Object) -> tuple[float, float, float] | None:
    """Width (x), depth (y), height (z) of a library instance, unscaled and unturned."""
    coll = ob.instance_collection if ob.instance_type == "COLLECTION" else None
    if coll is None:
        return None
    from mathutils import Vector

    pts = [
        o.matrix_world @ Vector(c)
        for o in coll.all_objects
        if o.type == "MESH"
        for c in o.bound_box
    ]
    if not pts:
        return None
    return (
        max(p.x for p in pts) - min(p.x for p in pts),
        max(p.y for p in pts) - min(p.y for p in pts),
        max(p.z for p in pts) - min(p.z for p in pts),
    )


class Placed:
    """A prop in the shot: what effects, hands and the camera need to know about it."""

    is_prop = True

    def __init__(self, root: bpy.types.Object):
        self.root = root

    def _box(self):
        from mathutils import Vector

        bpy.context.view_layer.update()
        pts = []
        for ob in [self.root, *self.root.children_recursive]:
            if ob.type in ("MESH", "CURVE", "FONT") or ob.instance_type == "COLLECTION":
                corners = (
                    [ob.matrix_world @ Vector(c) for c in ob.bound_box]
                    if ob.type != "EMPTY"
                    else []
                )
                if ob.instance_type == "COLLECTION" and ob.instance_collection:
                    for src in ob.instance_collection.all_objects:
                        corners += [
                            ob.matrix_world @ src.matrix_world @ Vector(c) for c in src.bound_box
                        ]
                pts += corners
        if not pts:
            p = self.root.matrix_world.translation
            return p, p
        lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
        hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
        return lo, hi

    def center(self):
        lo, hi = self._box()
        return (lo + hi) / 2

    def width(self) -> float:
        """How wide it looks from the front (or how tall, for a tall thing in a tall frame)."""
        lo, hi = self._box()
        d = hi - lo
        return max(0.1, max(d.x, d.y * 0.5), d.z * 0.56)

    def size(self) -> float:
        lo, hi = self._box()
        return max(0.1, (hi - lo).length)


def place(kind: str, name: str, opts: dict | None = None, parent=None) -> bpy.types.Object:
    o = opts or {}
    ob = kit_asset(kind, name, o)
    if ob is not None:
        if parent is not None:
            ob.parent = parent
        at = o.get("at", (0, 0))
        ob.location = (
            at[0],
            at[1],
            at[2] if len(at) > 2 else o.get("z", 0) if kind in ("clock", "cctv_camera") else 0,
        )
        ob.rotation_euler = (R(o.get("tilt", 0)), 0, R(o.get("rot", 0) + KIT_ROT.get(kind, 0)))
        sc = o.get("scale", 1)
        ob.scale = (sc, sc, sc) if isinstance(sc, (int, float)) else sc
        return ob
    kind = FALLBACK.get(kind, kind) if kind not in BUILDERS else kind
    if kind not in BUILDERS:
        raise ValueError(f"bilinmeyen eşya: {kind} (var olanlar: {', '.join(sorted(BUILDERS))})")
    ob = BUILDERS[kind](name, o, parent)
    at = o.get("at", (0, 0))
    ob.location = (at[0], at[1], at[2] if len(at) > 2 else 0)
    ob.rotation_euler = (R(o.get("tilt", 0)), 0, R(o.get("rot", 0)))
    s = o.get("scale", 1)
    ob.scale = (s, s, s) if isinstance(s, (int, float)) else s
    return ob
