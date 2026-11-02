"""Acting: poses, actions (walk, run, jump, wave, point, shock, cheer, fall, sit...), expressions,
blinks, talking mouths and moves through the set. Keyframes only; no armature or NLA.

Angles are degrees (x = bend forward/back, y = sideways, z = twist). Arms hang down at rest; a
positive shoulder x swings the arm forward, a negative shoulder y on the left arm lifts it out
sideways (mirrored for the right arm).
"""

from __future__ import annotations

import itertools
import math
import random

from .character import Character, set_mouth

R = math.radians

# Poses: joint -> (x, y, z) degrees. Missing joints go back to rest.
POSES: dict[str, dict[str, tuple[float, float, float]]] = {
    "rest": {},
    "idle": {
        "shoulder.L": (0, -6, 0),
        "shoulder.R": (0, 6, 0),
        "elbow.L": (-12, 0, 0),
        "elbow.R": (-12, 0, 0),
    },
    "arms_up": {
        "shoulder.L": (0, -165, 0),
        "shoulder.R": (0, 165, 0),
        "elbow.L": (0, -10, 0),
        "elbow.R": (0, 10, 0),
        "head": (-8, 0, 0),
    },
    "shock": {
        "shoulder.L": (25, -120, 0),
        "shoulder.R": (25, 120, 0),
        "elbow.L": (-70, 0, 0),
        "elbow.R": (-70, 0, 0),
        "spine": (-8, 0, 0),
        "head": (-6, 0, 0),
    },
    "point": {
        "shoulder.R": (85, 10, 0),
        "elbow.R": (-5, 0, 0),
        "shoulder.L": (0, -6, 0),
        "elbow.L": (-12, 0, 0),
    },
    "point_up": {"shoulder.R": (0, 160, 0), "elbow.R": (0, 0, 0), "head": (-15, 0, 0)},
    "wave_a": {"shoulder.R": (0, 95, 0), "elbow.R": (0, 70, 0), "shoulder.L": (0, -6, 0)},
    "wave_b": {"shoulder.R": (0, 95, 0), "elbow.R": (0, 35, 0), "shoulder.L": (0, -6, 0)},
    "think": {
        "shoulder.R": (60, 20, 0),
        "elbow.R": (-125, 0, 0),
        "head": (6, 8, -10),
        "shoulder.L": (25, -10, 0),
        "elbow.L": (-80, 0, 0),
    },
    "facepalm": {
        "shoulder.R": (75, 25, 0),
        "elbow.R": (-130, 0, 0),
        "head": (22, 0, 0),
        "spine": (8, 0, 0),
    },
    "shrug": {
        "shoulder.L": (10, -30, 0),
        "shoulder.R": (10, 30, 0),
        "elbow.L": (-90, -20, 0),
        "elbow.R": (-90, 20, 0),
        "head": (0, 10, 0),
        "spine": (0, 0, 0),
    },
    "cheer": {
        "shoulder.L": (0, -150, 0),
        "shoulder.R": (0, 150, 0),
        "elbow.L": (0, -25, 0),
        "elbow.R": (0, 25, 0),
        "head": (-12, 0, 0),
    },
    "hands_hips": {
        "shoulder.L": (0, -40, 0),
        "shoulder.R": (0, 40, 0),
        "elbow.L": (0, 95, 0),
        "elbow.R": (0, -95, 0),
    },
    "scared": {
        "shoulder.L": (70, -20, 0),
        "shoulder.R": (70, 20, 0),
        "elbow.L": (-120, 0, 0),
        "elbow.R": (-120, 0, 0),
        "spine": (14, 0, 0),
        "head": (10, 0, 0),
        "hip.L": (10, 0, 0),
        "hip.R": (10, 0, 0),
        "knee.L": (-25, 0, 0),
        "knee.R": (-25, 0, 0),
    },
    "sit": {
        "hip.L": (90, 0, 0),
        "hip.R": (90, 0, 0),
        "knee.L": (-90, 0, 0),
        "knee.R": (-90, 0, 0),
        "shoulder.L": (25, -5, 0),
        "shoulder.R": (25, 5, 0),
        "elbow.L": (-50, 0, 0),
        "elbow.R": (-50, 0, 0),
    },
    "lie": {"root": (-90, 0, 0), "shoulder.L": (0, -10, 0), "shoulder.R": (0, 10, 0)},
    "crouch": {
        "hip.L": (70, 0, 0),
        "hip.R": (70, 0, 0),
        "knee.L": (-120, 0, 0),
        "knee.R": (-120, 0, 0),
        "spine": (25, 0, 0),
        "shoulder.L": (40, 0, 0),
        "shoulder.R": (40, 0, 0),
    },
    "flex": {
        "shoulder.L": (0, -90, 0),
        "shoulder.R": (0, 90, 0),
        "elbow.L": (0, -110, 0),
        "elbow.R": (0, 110, 0),
        "head": (-5, 0, 0),
    },
    "hold": {
        "shoulder.L": (55, -10, 0),
        "shoulder.R": (55, 10, 0),
        "elbow.L": (-55, 0, 0),
        "elbow.R": (-55, 0, 0),
    },
    "phone": {
        "shoulder.R": (50, 15, 0),
        "elbow.R": (-110, 0, 0),
        "head": (18, 0, 0),
        "shoulder.L": (40, -5, 0),
        "elbow.L": (-90, 0, 0),
    },
    "sad": {
        "head": (20, 0, 0),
        "spine": (12, 0, 0),
        "shoulder.L": (5, -3, 0),
        "shoulder.R": (5, 3, 0),
    },
    "run_reach": {"shoulder.L": (70, -10, 0), "shoulder.R": (70, 10, 0), "spine": (12, 0, 0)},
}

# Faces: brows (raise m, tilt deg), pupils (scale), eye scale, mouth
FACES = {
    "neutral": {"brow": (0.0, 0), "pupil": 1.0, "eye": 1.0, "mouth": "flat"},
    "happy": {"brow": (0.01, -6), "pupil": 1.0, "eye": 1.0, "mouth": "smile"},
    "grin": {"brow": (0.015, -8), "pupil": 1.0, "eye": 0.95, "mouth": "grin"},
    "shock": {"brow": (0.05, 6), "pupil": 0.6, "eye": 1.25, "mouth": "shout"},
    "surprised": {"brow": (0.04, 4), "pupil": 0.8, "eye": 1.15, "mouth": "open"},
    "angry": {"brow": (-0.02, 22), "pupil": 1.0, "eye": 0.9, "mouth": "frown"},
    "sad": {"brow": (0.02, -18), "pupil": 1.1, "eye": 0.95, "mouth": "frown"},
    "scared": {"brow": (0.04, -14), "pupil": 0.55, "eye": 1.2, "mouth": "open"},
    "smug": {"brow": (0.0, 10), "pupil": 1.0, "eye": 0.88, "mouth": "smirk"},
    "confused": {"brow": (0.03, -10), "pupil": 1.0, "eye": 1.05, "mouth": "smirk"},
    "talk": {"brow": (0.01, 0), "pupil": 1.0, "eye": 1.0, "mouth": "smile"},
}


def key_pose(
    ch: Character, pose: str | dict, frame: int, joints: tuple[str, ...] | None = None
) -> None:
    """Set every joint (or `joints`) to the pose and keyframe it."""
    p = POSES.get(pose, {}) if isinstance(pose, str) else pose
    for name, ob in ch.joints.items():
        if joints and name not in joints:
            continue
        if name == "root":
            continue  # the root belongs to moves (location/heading), see below
        x, y, z = p.get(name, (0, 0, 0))
        ob.rotation_euler = (R(x), R(y), R(z))
        ob.keyframe_insert("rotation_euler", frame=frame)


def key_root(
    ch: Character, frame: int, loc=None, heading: float | None = None, lift: float | None = None
) -> None:
    root = ch.root
    if loc is not None:
        root.location.x, root.location.y = loc[0], loc[1]
    if lift is not None:
        root.location.z = lift
    if loc is not None or lift is not None:
        root.keyframe_insert("location", frame=frame)
    if heading is not None:
        root.rotation_euler.z = R(heading)
        root.keyframe_insert("rotation_euler", index=2, frame=frame)


def key_face(ch: Character, face: str, frame: int) -> None:
    f = FACES.get(face, FACES["neutral"])
    up, tilt = f["brow"]
    for side, sx in (("L", 1), ("R", -1)):
        brow = ch.face[f"brow.{side}"]
        if "_rest_z" not in brow:
            brow["_rest_z"] = brow.location.z
        brow.location.z = brow["_rest_z"] + up
        brow.rotation_euler = (0, R(-tilt * sx), 0)
        brow.keyframe_insert("location", index=2, frame=frame)
        brow.keyframe_insert("rotation_euler", frame=frame)
        eye = ch.face[f"eye.{side}"]
        eye.scale = (f["eye"],) * 3
        eye.keyframe_insert("scale", frame=frame)
        pupil = ch.face[f"pupil.{side}"]
        pupil.scale = (f["pupil"],) * 3
        pupil.keyframe_insert("scale", frame=frame)
    set_mouth(ch, f["mouth"], frame)


def look(ch: Character, frame: int, x: float = 0.0, z: float = 0.0) -> None:
    """Move the pupils: x -1..1 (screen left..right from the character's view), z -1..1 down..up."""
    for side in ("L", "R"):
        p = ch.face[f"pupil.{side}"]
        if "_rest" not in p:
            p["_rest"] = tuple(p.location)
        rx, ry, rz = p["_rest"]
        p.location = (rx + x * 0.035, ry, rz + z * 0.03)
        p.keyframe_insert("location", frame=frame)


def blinks(ch: Character, f0: int, f1: int, fps: float, seed: int = 0) -> None:
    """Blink every 2.5-5 s: lids show for ~4 frames."""
    rng = random.Random(seed or hash(ch.name) & 0xFFFF)
    f = f0 + int(rng.uniform(0.6, 2.0) * fps)
    lids = [ch.face["lid.L"], ch.face["lid.R"]]
    while f < f1 - 4:
        for lid in lids:
            for fr, hide in ((f - 1, True), (f, False), (f + 3, True)):
                lid.hide_render = hide
                lid.hide_viewport = hide
                lid.keyframe_insert("hide_render", frame=fr)
                lid.keyframe_insert("hide_viewport", frame=fr)
        f += int(rng.uniform(2.5, 5.0) * fps)


def talk(ch: Character, f0: int, f1: int, fps: float, rest: str = "smile", seed: int = 0) -> None:
    """Flap the mouth while the narration speaks for this character (open/closed ~6 per s)."""
    rng = random.Random(seed or 7)
    f = f0
    while f < f1:
        set_mouth(
            ch, rng.choice(("open", "grin", "open", "shout")) if rng.random() < 0.85 else rest, f
        )
        f += max(2, int(fps / rng.uniform(5.0, 7.5)))
        set_mouth(ch, rest, f)
        f += max(1, int(fps / rng.uniform(9, 14)))
    set_mouth(ch, rest, f1)


def breathe(ch: Character, f0: int, f1: int, fps: float) -> None:
    """A slow rise of the spine and head: still characters never look frozen."""
    sp = ch.joints["spine"]
    period = int(fps * 3.2)
    f = f0
    up = False
    while f <= f1:
        sp.scale = (1.0, 1.0, 1.015 if up else 1.0)
        sp.keyframe_insert("scale", frame=f)
        up = not up
        f += period // 2


def _ease_all(ch: Character, f0: int, f1: int, mode: str = "BEZIER") -> None:
    for ob in [ch.root, *ch.joints.values()]:
        ad = ob.animation_data
        if not ad or not ad.action:
            continue
        for fc in _fcurves(ad.action):
            for kp in fc.keyframe_points:
                if f0 <= kp.co.x <= f1 and kp.interpolation != "CONSTANT":
                    kp.interpolation = mode


def _fcurves(action):
    """Blender 4.4+ layered actions keep curves in channelbags; older ones in action.fcurves."""
    if hasattr(action, "fcurves") and action.fcurves is not None:
        try:
            return list(action.fcurves)
        except (AttributeError, TypeError):
            pass
    out = []
    for layer in getattr(action, "layers", []):
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []):
                out.extend(bag.fcurves)
    return out


# --------------------------------------------------------------------------- actions
def act(
    ch: Character,
    action: str,
    f0: int,
    f1: int,
    fps: float,
    path: list | None = None,
    heading: float | None = None,
) -> None:
    """Play `action` between frames f0 and f1. `path` = [(x, y), ...] for moves (walk, run)."""
    n = max(1, f1 - f0)
    if action in ("walk", "run", "sneak"):
        _locomotion(ch, action, f0, f1, fps, path or [], heading)
        return
    if action == "jump":
        _jump(ch, f0, f1, fps)
        return
    if action in ("wave",):
        f = f0
        key_pose(ch, "wave_a", f)
        while f < f1:
            f += int(fps * 0.25)
            key_pose(ch, "wave_b" if ((f - f0) // int(fps * 0.25)) % 2 else "wave_a", min(f, f1))
        return
    if action == "fall":
        key_pose(ch, "shock", f0)
        key_root(ch, f0, lift=0)
        mid = f0 + min(n, int(fps * 0.35))
        ch.root.rotation_euler.x = R(-85)
        key_root(ch, mid, lift=0.12)
        ch.root.keyframe_insert("rotation_euler", index=0, frame=mid)
        ch.root.rotation_euler.x = 0
        ch.root.keyframe_insert("rotation_euler", index=0, frame=f0)
        key_pose(ch, "arms_up", mid)
        return
    if action == "shake":  # trembling (fear, cold)
        key_pose(ch, "scared", f0)
        f, s = f0, 1
        while f < f1:
            ch.joints["spine"].rotation_euler.z = R(3 * s)
            ch.joints["spine"].keyframe_insert("rotation_euler", index=2, frame=f)
            s, f = -s, f + 2
        return
    if action == "nod":
        for i, f in enumerate(range(f0, f1, max(2, int(fps * 0.22)))):
            ch.joints["head"].rotation_euler.x = R(14 if i % 2 else -4)
            ch.joints["head"].keyframe_insert("rotation_euler", index=0, frame=f)
        return
    if action == "spin":
        ch.root.rotation_euler.z = R(heading or 0)
        ch.root.keyframe_insert("rotation_euler", index=2, frame=f0)
        ch.root.rotation_euler.z = R((heading or 0) + 360 * max(1, round(n / fps)))
        ch.root.keyframe_insert("rotation_euler", index=2, frame=f1)
        return
    # a held pose with a small settle and a bit of life
    pose = action if action in POSES else "idle"
    key_pose(ch, "idle", f0)
    key_pose(ch, pose, f0 + min(n // 3, int(fps * 0.25)))
    if pose in ("cheer", "flex"):  # bounce
        for i, f in enumerate(range(f0 + int(fps * 0.3), f1, int(fps * 0.3))):
            key_root(ch, f, lift=0.08 if i % 2 == 0 else 0.0)
    key_pose(ch, pose, f1)


def _locomotion(
    ch: Character, kind: str, f0: int, f1: int, fps: float, path: list, heading
) -> None:
    if len(path) < 2:
        x, y = ch.root.location.x, ch.root.location.y
        path = [(x, y), (x, y - 1.0)]
    seg = [math.dist(a, b) for a, b in itertools.pairwise(path)]
    total = sum(seg) or 1.0
    n = f1 - f0
    # heading and position along the path
    acc = 0.0
    for (a, b), d in zip(itertools.pairwise(path), seg, strict=True):
        fa = f0 + round(n * acc / total)
        acc += d
        fb = f0 + round(n * acc / total)
        h = math.degrees(math.atan2(b[0] - a[0], -(b[1] - a[1])))
        key_root(ch, fa, loc=a, heading=h)
        key_root(ch, fb, loc=b, heading=h)
    stride = {"walk": 0.55, "run": 0.4, "sneak": 0.8}[kind]  # seconds per step
    swing = {"walk": 28, "run": 50, "sneak": 18}[kind]
    knee = {"walk": 35, "run": 80, "sneak": 50}[kind]
    lean = {"walk": 3, "run": 14, "sneak": 18}[kind]
    step = max(2, int(fps * stride / 2))
    f, s = f0, 1
    while f <= f1:
        pose = {
            "hip.L": (swing * s, 0, 0), "hip.R": (-swing * s, 0, 0),
            "knee.L": (-knee * (s < 0), 0, 0), "knee.R": (-knee * (s > 0), 0, 0),
            "shoulder.L": (-swing * 0.9 * s, -6, 0), "shoulder.R": (swing * 0.9 * s, 6, 0),
            "elbow.L": (-25 - (40 if kind == "run" else 0), 0, 0), "elbow.R": (-25 - (40 if kind == "run" else 0), 0, 0),
            "spine": (lean, 0, 0),
        }  # fmt: skip
        key_pose(ch, pose, f)
        mid = f + step // 2
        if mid <= f1:
            ch.root.location.z = 0.05 if kind == "run" else 0.025
            ch.root.keyframe_insert("location", index=2, frame=mid)
        ch.root.location.z = 0
        ch.root.keyframe_insert("location", index=2, frame=f)
        f += step
        s = -s
    key_pose(ch, "idle", f1 + int(fps * 0.2))


def _jump(ch: Character, f0: int, f1: int, fps: float) -> None:
    n = max(int(fps * 0.6), f1 - f0)
    crouch = f0 + int(n * 0.2)
    top = f0 + int(n * 0.5)
    land = f0 + int(n * 0.8)
    key_pose(ch, "idle", f0)
    key_pose(ch, "crouch", crouch)
    key_pose(ch, "cheer", top)
    key_pose(ch, "crouch", land)
    key_pose(ch, "idle", f0 + n)
    for f, z in ((f0, 0), (crouch, 0), (top, 0.6), (land, 0), (f0 + n, 0)):
        key_root(ch, f, lift=z)
