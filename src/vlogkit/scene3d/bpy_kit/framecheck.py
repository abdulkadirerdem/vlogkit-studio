"""Scene text that does not fit in the camera frame (signs, blackboards, labels on things).

A beat often puts its number on a prop, and a prop a hand's width too far to the side is cropped:
the viewer reads "0,6 g PROT". Only the frame is checked here, not what stands in front of the
text. Every 3D text in the kit is a FONT curve (`shapes.text`), so one pass over the scene's font
objects finds them all. Results are printed as `VKEDGE {json}` lines; the host (scene3d/framing.py)
turns them into warnings under the preview.

The geometry below is plain math and imports no bpy, so the host can test it.
"""

from __future__ import annotations

import json

MIN_VISIBLE = 0.97  # a text below this much inside the frame is reported
# Text the author asked for (a placed prop, the classroom board, the gym banner) must fit whole;
# a set's own dressing (shop signs down the street) is only reported when it is cut in half.
WANTED = ("prop", "set.boardtxt", "set.bannertxt")


def inside(lo: float, hi: float) -> float:
    """How much of the span [lo, hi] falls inside [0, 1] (camera frame coordinates)."""
    if hi <= lo:
        return 1.0 if 0.0 <= lo <= 1.0 else 0.0
    return max(0.0, min(hi, 1.0) - max(lo, 0.0)) / (hi - lo)


def visible(x0: float, x1: float, y0: float, y1: float) -> float:
    """The fraction of a text's box that the camera sees."""
    return inside(x0, x1) * inside(y0, y1)


def side(x0: float, x1: float, y0: float, y1: float) -> str:
    """Which edges it runs off, in Turkish ('sağ', 'alt sol'). Camera y grows upwards."""
    out = []
    if y1 > 1.0:
        out.append("üst")
    if y0 < 0.0:
        out.append("alt")
    if x0 < 0.0:
        out.append("sol")
    if x1 > 1.0:
        out.append("sağ")
    return " ".join(out)


def wanted(name: str) -> bool:
    return name.startswith(WANTED)


def box(scene, cam, ob) -> tuple[float, float, float, float] | None:
    """The object's bounding box in camera view coordinates, or None if it is behind the camera."""
    import bpy
    from bpy_extras.object_utils import world_to_camera_view
    from mathutils import Vector

    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg) if dg else ob
    xs, ys = [], []
    for corner in ev.bound_box:
        co = world_to_camera_view(scene, cam, ev.matrix_world @ Vector(corner))
        if co.z > 0:  # points behind the lens say nothing about the frame
            xs.append(co.x)
            ys.append(co.y)
    return (min(xs), max(xs), min(ys), max(ys)) if xs else None


def check(scene, shot_id: str, frame: int, min_visible: float = MIN_VISIBLE) -> list[dict]:
    """Report the frame's cropped text. Prints a `VKEDGE` line per finding and returns them."""
    cam = scene.camera
    if cam is None:
        return []
    found = []
    for ob in scene.objects:
        if ob.type != "FONT" or ob.hide_render:
            continue
        body = " ".join((ob.data.body or "").split())
        if not body:
            continue
        b = box(scene, cam, ob)
        if b is None:
            continue
        seen = visible(*b)
        if seen >= min_visible or (seen <= 0 and not wanted(ob.name)):
            continue
        found.append(
            {
                "shot": shot_id,
                "frame": frame,
                "text": body[:48],
                "visible": round(seen, 2),
                "side": side(*b),
            }
        )
    for f in found:
        print("VKEDGE " + json.dumps(f, ensure_ascii=False), flush=True)
    return found
