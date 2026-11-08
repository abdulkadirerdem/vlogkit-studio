"""Camera: framings (how much of the subject is in frame) and moves (how the camera travels).

A shot's camera is {"frame": ..., "on": actor | [x, y, z], "move": ..., "angle": deg, "amount": n}.
Moves: static, push, pull, orbit, pan, rise, fall, zoom_out, dolly, follow, shake, dive (from
above the ground down into the cutaway, landing on `on`: the opening move of a build-up video).
Framings are tuned for a vertical 9:16 frame with a 35 mm lens. `angle` is the azimuth around the
target (0 = in front of a character facing -Y, 90 = from its left side), `tilt` raises (+) or
lowers (-) the camera.
"""

from __future__ import annotations

import math

import bpy
from mathutils import Vector

from . import shapes

R = math.radians

# framing -> (distance m, target height m (for a 1.7 m adult), camera height offset m)
FRAMES = {
    "face": (0.95, 1.52, 0.04),
    "close": (1.35, 1.42, 0.08),
    "medium": (2.1, 1.18, 0.18),
    "full": (3.1, 0.95, 0.35),
    "wide": (5.6, 1.0, 0.9),
    "far": (11.0, 1.2, 2.5),
    "aerial": (28.0, 0.0, 22.0),
    "top": (0.2, 0.0, 9.0),
    "low": (3.2, 1.05, -0.75),
    "hands": (0.9, 0.95, 0.15),
}


def make(lens: float = 35) -> bpy.types.Object:
    data = bpy.data.cameras.new("cam")
    data.lens = lens
    data.sensor_fit = "AUTO"
    data.clip_start = 0.05
    data.clip_end = 2000
    cam = bpy.data.objects.new("cam", data)
    bpy.context.collection.objects.link(cam)
    bpy.context.scene.camera = cam
    return cam


def _place(cam, target: Vector, dist: float, height: float, angle: float, tilt: float) -> None:
    a = R(angle)
    off = Vector((math.sin(a) * dist, -math.cos(a) * dist, height + tilt))
    cam.location = target + off
    shapes.look_at(cam, target)


def _group(on, actors: dict) -> list[str]:
    """`on` as a list of actor names (framing two or more people together)."""
    if isinstance(on, (list, tuple)) and on and all(isinstance(x, str) for x in on):
        return [x for x in on if x in actors and not getattr(actors[x], "is_prop", False)]
    return []


def _target_of(spec: dict, actors: dict, scale_of: dict) -> tuple[Vector, float]:
    on = spec.get("on")
    k = 1.0
    names = _group(on, actors)
    if names:
        pts = [actors[n].root.matrix_world.translation for n in names]
        mid = sum(pts, Vector()) / len(pts)
        return Vector((mid.x, mid.y, 0)), sum(scale_of.get(n, 1.0) for n in names) / len(names)
    if isinstance(on, str) and getattr(actors.get(on), "is_prop", False):
        return actors[on].center(), 1.0
    if isinstance(on, str) and on in actors:
        root = actors[on].root
        k = scale_of.get(on, 1.0)
        base = Vector((root.location.x, root.location.y, root.location.z))
    elif isinstance(on, (list, tuple)) and not names:
        base = Vector((on[0], on[1], on[2] if len(on) > 2 else 0))
    else:
        base = Vector(spec.get("_default_target", (0, 0, 1.0)))
        base.z = 0
    return base, k


def animate(
    cam, spec: dict, n: int, fps: float, actors: dict, scale_of: dict, start: int = 1
) -> None:
    """Keyframe the camera for a shot of n frames starting at frame `start`."""
    frame = spec.get("frame", "medium")
    dist, tz, hz = FRAMES.get(frame, FRAMES["medium"])
    bpy.context.scene.frame_set(start)  # where the subject is when this shot starts
    base, k = _target_of(spec, actors, scale_of)
    on = spec.get("on")
    if isinstance(on, str) and getattr(actors.get(on), "is_prop", False):
        # a thing: framed around its middle; the distance makes its width fill the frame
        w = actors[on].width()
        fill = {"face": 0.6, "close": 0.85, "hands": 0.85, "medium": 1.25, "full": 1.7,
                "wide": 2.8, "far": 5.5, "low": 1.5}.get(frame, 1.25)  # fmt: skip
        dist = 1.9 * w * fill * 35.0 / float(spec.get("lens", 35))
        tz, hz = 0.0, dist * 0.12
    elif _group(on, actors):
        # several people: aim between them, step back to take them all in
        names = _group(on, actors)
        pts = [actors[n].root.matrix_world.translation for n in names]
        spread = max((a - b).length for a in pts for b in pts)
        dist = max(dist, dist * 0.6 + spread * 1.6)
        tz *= k
    elif frame not in ("aerial", "top") and not isinstance(on, (list, tuple)):
        tz *= k
    # a set made at diorama scale (the cutaway yard) frames points and its centre further away
    is_actor = isinstance(on, str) and on in actors and not getattr(actors[on], "is_prop", False)
    if not is_actor and not (isinstance(on, str) and getattr(actors.get(on), "is_prop", False)):
        sc = float(spec.get("_scale", 1.0))
        dist *= sc
        hz *= sc
    elif isinstance(on, (list, tuple)) and len(on) > 2 and not _group(on, actors):
        tz = 0
    target = base + Vector((0, 0, tz)) + Vector(spec.get("offset", (0, 0, 0)))
    angle = float(spec.get("angle", 0))
    tilt = float(spec.get("tilt", 0))
    level = bool(spec.get("level"))  # eye level with the target: straight at a buried pipe
    dist *= float(spec.get("zoom", 1.0))
    hz += dist * float(spec.get("_lift", 0.0))  # a set may ask to be seen from a little above
    if level:  # looking up from below the lawn bent the house over the frame
        hz, tilt = 0.0, 0.0
    if spec.get("lens"):
        cam.data.lens = float(spec["lens"])
    move = spec.get("move", "push")
    amt = float(spec.get("amount", 0.0)) or {
        "push": 0.18,
        "pull": 0.25,
        "orbit": 25,
        "pan": 12,
        "rise": 1.5,
        "fall": 1.5,
        "zoom_out": 6.0,
        "shake": 0.03,
        "dolly": 1.2,
    }.get(move, 0)
    if move == "dive" and not spec.get("amount"):  # high enough to start over the ground
        amt = max(3.0, 2.5 - target.z)
    f0, f1 = start, start + max(1, n - 1)

    def at(f, d, h, ang, tgt):
        _place(cam, tgt, d, h, ang, tilt)
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)

    if move == "static":
        at(f0, dist, hz, angle, target)
    elif move == "push":
        at(f0, dist, hz, angle, target)
        at(f1, dist * (1 - amt), hz * (1 - amt * 0.5), angle, target)
    elif move == "pull":
        at(f0, dist * (1 - amt), hz, angle, target)
        at(f1, dist, hz, angle, target)
    elif move == "orbit":
        at(f0, dist, hz, angle - amt / 2, target)
        at((f0 + f1) // 2, dist, hz, angle, target)
        at(f1, dist, hz, angle + amt / 2, target)
    elif move == "pan":  # a sideways slide (truck) along the subject
        side = Vector((math.cos(R(angle)), math.sin(R(angle)), 0))
        at(f0, dist, hz, angle, target - side * amt * 0.05)
        at(f1, dist, hz, angle, target + side * amt * 0.05)
    elif move == "rise":  # crane up, ending higher and looking down a little
        at(f0, dist, hz, angle, target)
        at(f1, dist * 1.15, hz + amt, angle, target)
    elif move == "fall":
        at(f0, dist * 1.15, hz + amt, angle, target)
        at(f1, dist, hz, angle, target)
    elif move == "zoom_out":  # the scale reveal: from close to very far and high
        at(f0, dist, hz, angle, target)
        at(f1, dist * amt, hz + dist * amt * 0.55, angle, target)
    elif move == "dive":  # the hook move: from above the ground down through the cut, to land
        # on the target below (the water a well reaches); it starts looking at the surface
        # `from`: where it looks first (the working pump), else straight above the target
        first = Vector(spec["from"]) if spec.get("from") else target + Vector((0, 0, amt * 0.85))
        if spec.get("from_zoom"):  # start close on `from` (the pump at work), then dive
            d0 = dist * float(spec["from_zoom"])
            at(f0, d0, d0 * 0.45, angle, first)
        else:
            at(f0, dist * 1.15, hz + amt * 0.8, angle, first)
        at(f1, dist, hz, angle, target)
    elif move == "dolly":  # move forward along the view (walk-in)
        at(f0, dist + amt, hz, angle, target)
        at(f1, dist, hz, angle, target)
    elif move == "follow":  # keep framing an actor that moves: re-aim every 4 frames
        on = spec.get("on")
        root = actors[on].root if isinstance(on, str) and on in actors else None
        for f in [*range(f0, f1, 4), f1]:
            bpy.context.scene.frame_set(f)
            t = (
                Vector((root.matrix_world.translation.x, root.matrix_world.translation.y, tz))
                if root
                else target
            )
            at(f, dist, hz, angle, t)
        bpy.context.scene.frame_set(f0)
    else:
        at(f0, dist, hz, angle, target)
    if move == "shake" or spec.get("shake"):
        _shake(cam, float(spec.get("shake", amt or 0.03)), f0)
    _ease(cam, spec.get("ease", "ease"))
    # a set may ask for a shallow focus everywhere (`_dof`: the diorama look of the cutaway: the
    # subject sharp, the house behind soft); a shot can still turn it off with "dof": false
    set_dof = spec.get("_dof")
    if spec.get("dof", bool(set_dof) or frame in ("face", "close", "hands")):
        cam.data.dof.use_dof = True
        # focus on the target itself, so it stays sharp while the camera pushes or dives
        focus = shapes.empty("cam.focus", target)
        cam.data.dof.focus_object = focus
        cam.data.dof.aperture_fstop = float(spec.get("fstop", set_dof or 2.8))


def _shake(cam, strength: float, f0: int = 1, f1: int | None = None, blend: int = 0) -> None:
    """Hand-held / impact shake: noise on the rotation, optionally only from f0 to f1."""
    from .anim import _fcurves

    for idx in range(3):
        cam.keyframe_insert("rotation_euler", index=idx, frame=f0)
    for fc in _fcurves(cam.animation_data.action):
        if fc.data_path == "rotation_euler":
            m = fc.modifiers.new("NOISE")
            m.scale = 6 if f1 is None else 2.5
            m.strength = strength
            m.phase = fc.array_index * 7.0 + f0
            if f1 is not None:
                m.use_restricted_range = True
                m.frame_start, m.frame_end = f0, f1
                m.blend_in, m.blend_out = blend, max(blend, (f1 - f0) // 2)


def _ease(cam, mode: str) -> None:
    from .anim import _fcurves

    if not cam.animation_data or not cam.animation_data.action:
        return
    for fc in _fcurves(cam.animation_data.action):
        for kp in fc.keyframe_points:
            kp.interpolation = "LINEAR" if mode == "linear" else "BEZIER"
            if mode != "linear":
                kp.easing = "AUTO"
                kp.handle_left_type = kp.handle_right_type = "AUTO_CLAMPED"
