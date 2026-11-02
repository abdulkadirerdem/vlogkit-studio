"""Stylised characters: big head, big googly eyes, soft rounded body, a joint hierarchy that the
animation module poses (no armature: every part hangs off an empty, so posing is plain rotations).

A character is described by a small dict (the spec's `cast` entry):

    {"body": "adult|kid|big|old", "skin": "#e8b98a", "shirt": "#e25b45", "pants": "#3b5b8c",
     "shoes": "#f2f2f2", "hair": "short|long|bun|bald|hood|cap|curly", "hair_color": "#3a2a1e",
     "sleeves": "short|long", "beard": false, "glasses": false, "outfit": "casual|suit|chef|doctor|lab"}

The figure faces -Y, feet on z=0, origin between the feet.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import bpy

from . import look, shapes

BODIES = {  # proportions: (scale, head radius, torso w, torso h, leg length, arm length)
    "adult": (1.0, 0.27, 0.46, 0.55, 0.80, 0.58),
    "kid": (0.78, 0.30, 0.42, 0.46, 0.62, 0.50),
    "big": (1.05, 0.28, 0.62, 0.58, 0.78, 0.60),
    "old": (0.97, 0.27, 0.48, 0.52, 0.76, 0.56),
    "tall": (1.12, 0.26, 0.44, 0.60, 0.88, 0.62),
}
DEFAULT = {
    "body": "adult",
    "skin": "#e9b98f",
    "shirt": "#e25b45",
    "pants": "#3d5a8a",
    "shoes": "#f4f4f4",
    "hair": "short",
    "hair_color": "#3b2a20",
    "sleeves": "short",
    "beard": False,
    "glasses": False,
    "outfit": "casual",
}
JOINTS = (
    "root", "hips", "spine", "neck", "head",
    "shoulder.L", "elbow.L", "hand.L", "shoulder.R", "elbow.R", "hand.R",
    "hip.L", "knee.L", "foot.L", "hip.R", "knee.R", "foot.R",
)  # fmt: skip


@dataclass
class Character:
    name: str
    root: bpy.types.Object
    joints: dict[str, bpy.types.Object]
    face: dict[str, object] = field(default_factory=dict)  # eyes, pupils, brows, mouths
    height: float = 1.7
    spec: dict = field(default_factory=dict)


def _darker(hex_color: str, f: float = 0.8) -> str:
    c = hex_color.lstrip("#")
    r, g, b = (int(c[i : i + 2], 16) for i in (0, 2, 4))
    return "#{:02x}{:02x}{:02x}".format(*(max(0, min(255, round(x * f))) for x in (r, g, b)))


def build(name: str, spec: dict | None = None, collection=None) -> Character:
    s = {**DEFAULT, **(spec or {})}
    k, head_r, tw, th, leg, arm = BODIES.get(s["body"], BODIES["adult"])
    col = collection
    E = lambda n, loc, parent: shapes.empty(f"{name}.{n}", loc, parent, col)  # noqa: E731

    skin = look.mat(s["skin"], rough=0.5, sss=0.15)
    shirt = look.mat(s["shirt"], rough=0.7)
    pants = look.mat(s["pants"], rough=0.75)
    shoes = look.mat(s["shoes"], rough=0.45)
    hair_m = look.mat(s["hair_color"], rough=0.8)
    white = look.mat("#fbfbfb", rough=0.18, spec=0.6)
    black = look.mat("#121212", rough=0.15, spec=0.6)
    dark = look.mat("#3a1e1e", rough=0.6)
    shine = look.mat("#ffffff", emit=2.0)

    root = E("root", (0, 0, 0), None)
    root.scale = (k, k, k)
    hips = E("hips", (0, 0, leg), root)
    spine = E("spine", (0, 0, 0.02), hips)
    neck = E("neck", (0, 0, th + 0.02), spine)
    head = E("head", (0, 0, 0.06), neck)

    # --- body
    outfit = s["outfit"]
    top_color = shirt
    if outfit == "suit":
        top_color = look.mat(s.get("shirt", "#2d3340"), rough=0.6)
    shapes.rbox(
        f"{name}.torso",
        (tw, 0.29, th),
        top_color,
        (0, 0, th / 2 + 0.02),
        0.11,
        spine,
        collection=col,
    )
    shapes.rbox(
        f"{name}.pelvis", (tw * 0.96, 0.27, 0.16), pants, (0, 0, -0.02), 0.07, hips, collection=col
    )
    if outfit in ("chef", "doctor", "lab"):  # an apron / coat front panel
        coat = look.mat("#f7f7f2", rough=0.7)
        shapes.rbox(
            f"{name}.coat",
            (tw * 0.98, 0.3, th * 1.25),
            coat,
            (0, -0.002, th / 2 - 0.08),
            0.1,
            spine,
            collection=col,
        )
    if outfit == "suit":
        shapes.rbox(
            f"{name}.collar",
            (0.12, 0.04, 0.22),
            look.mat("#f4f4f4"),
            (0, -0.145, th - 0.1),
            0.02,
            spine,
            collection=col,
        )
        shapes.rbox(
            f"{name}.tie",
            (0.06, 0.03, 0.26),
            look.mat("#c0392b"),
            (0, -0.16, th - 0.17),
            0.015,
            spine,
            collection=col,
        )
    shapes.cylinder(
        f"{name}.neckmesh", 0.075, 0.1, skin, (0, 0, -0.02), parent=neck, collection=col
    )

    # --- head
    hr = head_r
    hz = hr * 0.95
    shapes.sphere(f"{name}.skull", hr, skin, (0, 0, hz), (1.0, 0.94, 1.02), head, collection=col)
    shapes.sphere(
        f"{name}.ear.L",
        hr * 0.2,
        skin,
        (hr * 0.98, 0.0, hz - 0.01),
        (0.55, 0.8, 1.0),
        head,
        collection=col,
    )
    shapes.sphere(
        f"{name}.ear.R",
        hr * 0.2,
        skin,
        (-hr * 0.98, 0.0, hz - 0.01),
        (0.55, 0.8, 1.0),
        head,
        collection=col,
    )
    shapes.sphere(
        f"{name}.nose",
        hr * 0.16,
        look.mat(_darker(s["skin"], 0.93), rough=0.5, sss=0.15),
        (0, -hr * 0.97, hz - hr * 0.12),
        (1, 0.9, 0.9),
        head,
        collection=col,
    )

    face: dict[str, object] = {}
    eye_r = hr * 0.31
    for side, sx in (("L", 1), ("R", -1)):
        ex = sx * hr * 0.36
        eye = E(f"eye.{side}", (ex, -hr * 0.8, hz + hr * 0.16), head)
        shapes.sphere(
            f"{name}.eyeball.{side}", eye_r, white, (0, 0, 0), (1, 0.75, 1.08), eye, collection=col
        )
        pupil = E(f"pupil.{side}", (0, -eye_r * 0.62, 0), eye)
        shapes.sphere(
            f"{name}.iris.{side}",
            eye_r * 0.52,
            black,
            (0, 0, 0),
            (1, 0.45, 1),
            pupil,
            collection=col,
        )
        shapes.sphere(
            f"{name}.glint.{side}",
            eye_r * 0.14,
            shine,
            (eye_r * 0.18, -eye_r * 0.2, eye_r * 0.22),
            parent=pupil,
            collection=col,
        )
        lid = shapes.cap(
            f"{name}.lid.{side}",
            eye_r * 1.06,
            skin,
            cut_z=eye_r * 0.15,
            loc=(0, 0, 0),
            scale=(1.02, 0.8, 1.1),
            parent=eye,
            collection=col,
        )
        lid.rotation_euler = (
            math.radians(-90),
            0,
            0,
        )  # rotate the cap so it closes downwards (blink)
        lid.hide_render = True
        lid.hide_viewport = True
        brow = E(f"brow.{side}", (ex, -hr * 0.86, hz + hr * 0.52), head)
        shapes.rbox(
            f"{name}.browmesh.{side}",
            (hr * 0.38, 0.03, 0.035),
            hair_m,
            (0, 0, 0),
            0.015,
            brow,
            collection=col,
        )
        face[f"eye.{side}"] = eye
        face[f"pupil.{side}"] = pupil
        face[f"lid.{side}"] = lid
        face[f"brow.{side}"] = brow

    mouth = E("mouth", (0, -hr * 0.9, hz - hr * 0.42), head)
    w = hr * 0.28
    shapes_m = {
        "smile": [
            (-w, 0, w * 0.35),
            (-w * 0.5, -0.01, -w * 0.15),
            (0, -0.012, -w * 0.25),
            (w * 0.5, -0.01, -w * 0.15),
            (w, 0, w * 0.35),
        ],
        "frown": [
            (-w, 0, -w * 0.25),
            (-w * 0.5, -0.01, w * 0.12),
            (0, -0.012, w * 0.2),
            (w * 0.5, -0.01, w * 0.12),
            (w, 0, -w * 0.25),
        ],
        "flat": [(-w * 0.8, 0, 0), (0, -0.01, -0.005), (w * 0.8, 0, 0)],
        "smirk": [(-w * 0.7, 0, 0), (0, -0.01, -w * 0.05), (w * 0.8, 0, w * 0.3)],
    }
    mouths = {}
    for key, pts in shapes_m.items():
        m = shapes.curve(
            f"{name}.mouth.{key}", pts, dark, bevel=hr * 0.035, parent=mouth, collection=col
        )
        mouths[key] = m
    mouths["open"] = shapes.sphere(
        f"{name}.mouth.open",
        w * 0.62,
        dark,
        (0, 0.0, -0.01),
        (1.0, 0.45, 0.85),
        mouth,
        collection=col,
    )
    mouths["shout"] = shapes.sphere(
        f"{name}.mouth.shout",
        w * 0.9,
        dark,
        (0, 0.0, -0.03),
        (1.0, 0.5, 1.25),
        mouth,
        collection=col,
    )
    mouths["grin"] = shapes.sphere(
        f"{name}.mouth.grin",
        w * 1.0,
        dark,
        (0, 0.0, 0.0),
        (1.15, 0.45, 0.45),
        mouth,
        collection=col,
    )
    face["mouth"] = mouth
    face["mouths"] = mouths

    # --- hair
    hair = s["hair"]
    if hair in ("short", "curly", "bun", "long"):
        shapes.cap(
            f"{name}.hair",
            hr * 1.06,
            hair_m,
            cut_z=hr * 0.05,
            loc=(0, hr * 0.03, hz),
            scale=(1.0, 0.97, 1.0),
            parent=head,
            front_cut=hr * 0.62,
            collection=col,
        )
        if hair == "curly":
            for i in range(9):
                a = i / 9 * math.tau
                shapes.sphere(
                    f"{name}.curl{i}",
                    hr * 0.24,
                    hair_m,
                    (math.cos(a) * hr * 0.75, math.sin(a) * hr * 0.6 + 0.03, hz + hr * 0.62),
                    parent=head,
                    collection=col,
                )
        if hair == "bun":
            shapes.sphere(
                f"{name}.bun",
                hr * 0.38,
                hair_m,
                (0, hr * 0.35, hz + hr * 0.95),
                parent=head,
                collection=col,
            )
        if hair == "long":
            shapes.rbox(
                f"{name}.longhair",
                (hr * 2.05, hr * 0.7, hr * 1.5),
                hair_m,
                (0, hr * 0.42, hz - hr * 0.35),
                0.1,
                head,
                collection=col,
            )
    elif hair == "hood":
        hood = look.mat(s.get("hood_color", s["shirt"]), rough=0.8)
        shapes.cap(
            f"{name}.hood",
            hr * 1.16,
            hood,
            cut_z=-hr * 0.55,
            loc=(0, hr * 0.08, hz),
            scale=(1.0, 1.0, 1.04),
            parent=head,
            front_cut=hr * 1.2,
            collection=col,
        )
    elif hair == "cap":
        capm = look.mat(s.get("cap_color", "#2b6cb0"), rough=0.6)
        shapes.cap(
            f"{name}.cap",
            hr * 1.07,
            capm,
            cut_z=hr * 0.25,
            loc=(0, 0, hz),
            parent=head,
            collection=col,
        )
        shapes.rbox(
            f"{name}.visor",
            (hr * 1.1, hr * 0.8, 0.025),
            capm,
            (0, -hr * 0.85, hz + hr * 0.32),
            0.012,
            head,
            collection=col,
        )
    if outfit == "chef":
        shapes.cylinder(
            f"{name}.chefhat",
            hr * 0.75,
            hr * 0.9,
            look.mat("#fafafa"),
            (0, 0, hz + hr * 1.2),
            parent=head,
            collection=col,
        )
        shapes.sphere(
            f"{name}.chefpuff",
            hr * 0.85,
            look.mat("#fafafa"),
            (0, 0, hz + hr * 1.6),
            (1, 1, 0.6),
            head,
            collection=col,
        )
    if s.get("beard"):
        shapes.cap(
            f"{name}.beard",
            hr * 1.0,
            hair_m,
            cut_z=-hr * 2,
            loc=(0, -0.01, hz - 0.02),
            scale=(1, 0.95, 1),
            parent=head,
            collection=col,
        ).rotation_euler = (math.radians(180), 0, 0)
    if s.get("mustache"):
        shapes.curve(
            f"{name}.mustache",
            [(-w * 1.2, 0, -0.01), (0, -0.015, 0.025), (w * 1.2, 0, -0.01)],
            hair_m,
            bevel=hr * 0.06,
            loc=(0, -hr * 0.95, hz - hr * 0.27),
            parent=head,
            collection=col,
        )
    if s.get("glasses"):
        frame = look.mat("#1c1c1c", rough=0.3)
        for sx in (1, -1):
            pts = [
                (math.cos(a) * eye_r * 1.25, 0, math.sin(a) * eye_r * 1.25)
                for a in [i / 12 * math.tau for i in range(12)]
            ]
            shapes.curve(
                f"{name}.lens{sx}",
                pts,
                frame,
                bevel=0.008,
                loc=(sx * hr * 0.36, -hr * 0.98, hz + hr * 0.16),
                parent=head,
                cyclic=True,
                collection=col,
            )

    # --- arms (hang down; elbows bend forward)
    up, lo = arm * 0.52, arm * 0.48
    sleeve = shirt
    joints = {"root": root, "hips": hips, "spine": spine, "neck": neck, "head": head}
    for side, sx in (("L", 1), ("R", -1)):
        sh = E(f"shoulder.{side}", (sx * (tw / 2 + 0.03), 0, th - 0.06), spine)
        shapes.sphere(f"{name}.deltoid.{side}", 0.085, sleeve, (0, 0, 0), parent=sh, collection=col)
        shapes.rbox(
            f"{name}.upperarm.{side}",
            (0.14, 0.14, up),
            sleeve,
            (0, 0, -up / 2),
            0.06,
            sh,
            collection=col,
        )
        el = E(f"elbow.{side}", (0, 0, -up), sh)
        fore = shirt if s["sleeves"] == "long" or outfit in ("suit", "doctor", "lab") else skin
        shapes.rbox(
            f"{name}.forearm.{side}",
            (0.12, 0.12, lo),
            fore,
            (0, 0, -lo / 2),
            0.055,
            el,
            collection=col,
        )
        hd = E(f"hand.{side}", (0, 0, -lo), el)
        shapes.sphere(
            f"{name}.palm.{side}", 0.072, skin, (0, 0, -0.045), (0.9, 0.75, 1.1), hd, collection=col
        )
        shapes.sphere(
            f"{name}.thumb.{side}",
            0.03,
            skin,
            (sx * -0.0, -0.05, -0.03),
            (1, 1, 1.3),
            hd,
            collection=col,
        )
        joints[f"shoulder.{side}"], joints[f"elbow.{side}"], joints[f"hand.{side}"] = sh, el, hd

    # --- legs
    th_len, sh_len = leg * 0.52, leg * 0.48 - 0.06
    for side, sx in (("L", 1), ("R", -1)):
        hp = E(f"hip.{side}", (sx * tw * 0.24, 0, -0.04), hips)
        shapes.rbox(
            f"{name}.thigh.{side}",
            (0.17, 0.18, th_len),
            pants,
            (0, 0, -th_len / 2),
            0.07,
            hp,
            collection=col,
        )
        kn = E(f"knee.{side}", (0, 0, -th_len), hp)
        shapes.rbox(
            f"{name}.shin.{side}",
            (0.155, 0.16, sh_len),
            pants,
            (0, 0, -sh_len / 2),
            0.065,
            kn,
            collection=col,
        )
        ft = E(f"foot.{side}", (0, 0, -sh_len), kn)
        shapes.rbox(
            f"{name}.shoe.{side}",
            (0.17, 0.29, 0.1),
            shoes,
            (0, -0.05, -0.02),
            0.045,
            ft,
            collection=col,
        )
        shapes.rbox(
            f"{name}.sole.{side}",
            (0.175, 0.295, 0.025),
            look.mat("#3b3b3b", rough=0.9),
            (0, -0.05, -0.07),
            0.01,
            ft,
            collection=col,
        )
        joints[f"hip.{side}"], joints[f"knee.{side}"], joints[f"foot.{side}"] = hp, kn, ft

    for j in joints.values():
        j.rotation_mode = "XYZ"
    height = (leg + th + 0.08 + hz + hr) * k
    ch = Character(name, root, joints, face, height, s)
    set_mouth(ch, "smile")
    return ch


# --------------------------------------------------------------------------- face
MOUTHS = ("smile", "frown", "flat", "smirk", "open", "shout", "grin")


def set_mouth(ch: Character, key: str, frame: int | None = None) -> None:
    """Show one mouth shape (keyframed when `frame` is given: constant interpolation)."""
    for k, ob in ch.face["mouths"].items():
        hidden = k != key
        ob.hide_render = hidden
        ob.hide_viewport = hidden
        if frame is not None:
            ob.keyframe_insert("hide_render", frame=frame)
            ob.keyframe_insert("hide_viewport", frame=frame)
