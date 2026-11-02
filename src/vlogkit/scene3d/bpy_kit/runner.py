"""Entry point inside Blender: build and render the shots of a plan.

    blender -b --factory-startup --python-exit-code 1 -P runner.py -- plan.json

The plan (written by vlogkit.scene3d.plan) is fully resolved: frame counts, positions, actions
with shot-local times, a camera per shot. Each shot is built from an empty scene, so shots are
independent: a cached shot is skipped, a changed one renders again. Frames go to
<shot.out>/#####.png; a `done.json` marks a complete shot. Progress lines on stdout:
`VKFRAME <shot> <frame> <of>` (the host shows them).
"""

from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE.parent) not in sys.path:
    sys.path.insert(0, str(HERE.parent))

import os  # noqa: E402

import bpy  # noqa: E402
from bpy_kit import (  # noqa: E402
    anim,
    camera,
    character,
    crowd,
    framecheck,
    fx,
    human,
    humanim,
    look,
    props,
    sets,
)

R = math.radians


def clear() -> None:
    """An empty stage for the next shot; the appended 3D library stays loaded."""
    for coll in (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.lights,
        bpy.data.cameras,
        bpy.data.materials,
        bpy.data.actions,
        bpy.data.armatures,
    ):
        for item in list(coll):
            key = (type(item).__name__, item.name)
            if key not in human.KEEP_NAMES and key not in props.WORLD_KEEP:
                coll.remove(item)
    look.reset_cache()


def _heading(frm, to) -> float:
    """The turn (radians) that makes something at `frm` face `to` (0 = facing the camera, -Y)."""
    return math.atan2(to[0] - frm[0], -(to[1] - frm[1]))


def _hide(root, f: int, hidden: bool) -> None:
    for ob in [root, *root.children_recursive]:
        ob.hide_render = ob.hide_viewport = hidden
        ob.keyframe_insert("hide_render", frame=f)
        ob.keyframe_insert("hide_viewport", frame=f)


def _prop_moves(pr: dict, placed: props.Placed, fps: float, span: int) -> None:
    """A prop's `anim` (moves, turns, growth, appearing and disappearing) and a door's `open`."""
    root = placed.root

    def frame(t):
        return max(1, min(span, 1 + round(t * fps)))

    base_rot = root.rotation_euler.z - R(pr.get("rot", 0))
    shown_from = None
    for m in sorted(pr.get("anim") or [], key=lambda x: x["t"]):
        f0 = frame(m["t"])
        f1 = max(f0 + 1, min(span, f0 + round(float(m.get("dur", 0.6)) * fps)))
        if m.get("show"):
            shown_from = f0
            continue
        root.keyframe_insert("location", frame=f0)
        root.keyframe_insert("rotation_euler", frame=f0)
        root.keyframe_insert("scale", frame=f0)
        if m.get("to") is not None:
            to = m["to"]
            root.location = (to[0], to[1], to[2] if len(to) > 2 else root.location.z)
        if m.get("by") is not None:
            by = m["by"]
            root.location = (root.location.x + by[0], root.location.y + by[1],
                             root.location.z + (by[2] if len(by) > 2 else 0))  # fmt: skip
        if m.get("rot") is not None:
            root.rotation_euler.z = base_rot + R(m["rot"])
        if m.get("spin"):
            root.rotation_euler.z += R(m["spin"])
        if m.get("tilt") is not None:
            root.rotation_euler.x = R(m["tilt"])
        if m.get("scale") is not None:
            k = m["scale"]
            root.scale = (k, k, k) if isinstance(k, (int, float)) else k
        root.keyframe_insert("location", frame=f1)
        root.keyframe_insert("rotation_euler", frame=f1)
        root.keyframe_insert("scale", frame=f1)
        from bpy_kit import fx

        fx._ease(root, m.get("ease", "inout"))
        if m.get("hide"):
            _hide(root, f1 - 1, False)
            _hide(root, f1, True)
    if shown_from is not None and shown_from > 1:
        _hide(root, 1, True)
        _hide(root, shown_from, False)
    op = pr.get("open")
    hinge = next((o for o in root.children_recursive if o.name.endswith(".hinge")), None)
    if op and hinge is not None:
        f0 = frame(op["t"])
        f1 = min(span, f0 + round(float(op.get("dur", 0.7)) * fps))
        for f, ang in ((f0, 0.0), (f1, float(op.get("angle", 100)))):
            hinge.rotation_euler.z = R(ang)
            hinge.keyframe_insert("rotation_euler", index=2, frame=f)
        from bpy_kit import fx

        fx._ease(hinge, "out")


def _hands(pr: dict, placed: props.Placed, actors: dict, fps: float, frames) -> None:
    """A held prop follows the hand of whoever holds it; `hand` steps pass it on."""
    from mathutils import Matrix, Vector

    steps = sorted(pr["hand"], key=lambda x: x["t"])
    root = placed.root
    rest = root.matrix_world.copy()
    grip = Vector(pr.get("grip", (0.0, 0.0, 0.0)))
    mode = pr.get("grip_mode") or (
        "palm" if pr["kind"] in ("phone", "money", "newspaper") else "upright"
    )
    sc = bpy.context.scene
    last = None
    prev_owner = None
    hand_from, switch_f = None, 0
    pass_frames = max(2, round(0.3 * fps))
    for f in range(max(1, frames.start - pass_frames), frames.stop):
        t = (f - 1) / fps
        cur = None
        for st in steps:
            if st["t"] <= t + 1e-6:
                cur = st
        who = cur and cur.get("who")
        if who in actors and hasattr(actors[who], "body"):
            arm = actors[who].root
            sc.frame_set(f)
            side = cur.get("side", "r")
            pb = arm.pose.bones.get(f"hand_{side}")
            if pb is None:
                continue
            hm = arm.matrix_world @ pb.matrix
            rot3 = hm.to_3x3().normalized()
            fingers = rot3.col[1].normalized()
            # the palm faces out of the bone's -X on the right hand, +X on the left (T-pose rest:
            # palms down); the thumb is on +Z
            palm = (rot3.col[0] * (-1 if side == "r" else 1)).normalized()
            centre = hm.translation + fingers * 0.06
            if mode == "palm":  # a phone, a card: lies in the palm, its face towards the face
                up = fingers
                back = -palm  # the prop faces -Y: its +Y rests on the palm
                x = back.cross(up).normalized()
                basis = Matrix((x, back, up)).transposed().to_4x4()
                basis.translation = centre + palm * 0.012 - fingers * 0.05 + grip
                root.matrix_world = basis
            else:  # a box, a cup: upright in the hand, turned with the body
                heading = arm.matrix_world.to_euler().z
                root.location = centre + palm * 0.03 + grip
                root.rotation_euler = (R(pr.get("tilt", 0)), 0, heading + R(pr.get("rot", 0)))
            last = root.matrix_world.copy()
        elif last is not None:  # let go: it stays where it was
            root.matrix_world = last
        else:
            root.matrix_world = rest
        # a hand-off: for a moment the phone travels from the giving hand to the taking one
        if cur is not None and prev_owner is not None and cur.get("who") != prev_owner[0]:
            hand_from = prev_owner[1]
            switch_f = f
        prev_owner = (cur.get("who") if cur else None, root.matrix_world.copy())
        if hand_from is not None and f - switch_f < pass_frames:
            k = (f - switch_f + 1) / (pass_frames + 1)
            k = k * k * (3 - 2 * k)
            loc = hand_from.translation.lerp(root.matrix_world.translation, k)
            q = hand_from.to_quaternion().slerp(root.matrix_world.to_quaternion(), k)
            root.matrix_world = Matrix.LocRotScale(loc, q, root.matrix_world.to_scale())
        root.keyframe_insert("location", frame=f)
        root.keyframe_insert("rotation_euler", frame=f)


def build_shot(plan: dict, shot: dict) -> int:
    """Build the beat's world (all of its timeline) for one shot; returns the beat's length."""
    fps = plan["fps"]
    span = int(shot.get("span", shot["frames"]))
    start = int(shot.get("start", 1))
    n_shot = int(shot["frames"])
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, span
    info = sets.build(shot["set"], shot.get("set_opts") or {})
    placed: dict[str, props.Placed] = {}
    for i, pr in enumerate(shot.get("props", [])):
        ob = props.place(pr["kind"], f"prop{i}", pr)
        placed[pr.get("id") or f"prop{i}"] = props.Placed(ob)
    actors, scale_of = {}, {}
    real = []
    for a in shot.get("actors", []):
        who = a["who"]
        spec = plan["cast"].get(who, {})
        at = a.get("at", [0, 0])
        if spec.get("style", "realistic") != "toon" and human.LIB:
            p = human.build(who, spec)
            actors[who] = p
            scale_of[who] = p.height / 1.7
            p.root.location = (at[0], at[1], at[2] if len(at) > 2 else 0)
            if a.get("size"):
                k = float(a["size"]) * p.root.scale.x
                p.root.scale = (k, k, k)
                scale_of[who] *= float(a["size"])
            real.append((p, a))
            continue
        ch = character.build(who, spec)
        actors[who] = ch
        scale_of[who] = character.BODIES.get(ch.spec["body"], character.BODIES["adult"])[0]
        ch.root.location = (at[0], at[1], at[2] if len(at) > 2 else 0)
        ch.root.rotation_euler = (
            0,
            0,
            R(a.get("facing", 0)) if not isinstance(a.get("facing"), str) else 0,
        )
        if a.get("size"):
            s = scale_of[who] * float(a["size"])
            ch.root.scale = (s, s, s)
            scale_of[who] = s
        ch.root.keyframe_insert("location", frame=1)
        ch.root.keyframe_insert("rotation_euler", frame=1)
        anim.key_pose(ch, "idle", 1)
        anim.key_face(ch, a.get("face", "happy"), 1)
        lx, lz = a.get("look", [0, 0])
        anim.look(ch, 1, lx, lz)
        for act in a.get("acts", []):
            f0 = 1 + round(act["t0"] * fps)
            f1 = max(f0 + 1, 1 + round(act["t1"] * fps))
            anim.act(ch, act["do"], f0, min(f1, span), fps, act.get("path"), act.get("heading"))
            if act.get("face"):
                anim.key_face(ch, act["face"], f0)
        for fc in a.get("faces", []):
            anim.key_face(ch, fc["face"], 1 + round(fc["t"] * fps))
        for t0, t1 in a.get("talk", []):
            anim.talk(
                ch,
                1 + round(t0 * fps),
                1 + round(t1 * fps),
                fps,
                rest=anim.FACES.get(a.get("face", "happy"), {}).get("mouth", "smile"),
            )
        anim.blinks(ch, 1, span, fps, seed=len(who) * 31 + span)
        anim.breathe(ch, 1, span, fps)
    # where everyone stands is known: now people can face each other and act
    spots = {who: tuple(a.get("at", [0, 0])) for p, a in real for who in [p.name]}
    for key, pl in placed.items():
        c = pl.center()
        spots[key] = (c.x, c.y)
    for p, a in real:
        facing = a.get("facing", 0)
        if isinstance(facing, str) and facing in spots:
            p.root.rotation_euler = (0, 0, _heading(a.get("at", [0, 0]), spots[facing]))
        else:
            p.root.rotation_euler = (0, 0, R(facing if not isinstance(facing, str) else 0))
        p.root.keyframe_insert("location", frame=1)
        p.root.keyframe_insert("rotation_euler", frame=1)
        humanim.perform(p, a, fps, span)
    crowd_people = crowd.build(shot["crowd"], fps, span) if shot.get("crowd") else []
    del crowd_people
    frames = range(start, start + n_shot)
    for i, pr in enumerate(shot.get("props", [])):
        pl = placed[pr.get("id") or f"prop{i}"]
        _prop_moves(pr, pl, fps, span)
        if pr.get("hand"):
            _hands(pr, pl, actors, fps, frames)
    cam = camera.make(shot.get("camera", {}).get("lens", 35))
    cspec = dict(shot.get("camera", {}))
    cspec.setdefault("_default_target", info.get("target", (0, 0, 1)))
    if "on" not in cspec and actors:
        cspec["on"] = next(iter(actors))
    targets = {**placed, **actors}
    camera.animate(cam, cspec, n_shot, fps, targets, scale_of, start)
    if shot.get("fx"):
        seed = sum(ord(ch) for ch in shot["id"])
        ctx = fx.Ctx(fps, span, cam, actors, placed, seed)
        ctx.gravity = 0.0 if shot["set"] in ("space", "world") else fx.G  # nothing falls in space
        fx.apply(ctx, shot["fx"])
    sc.frame_set(start)
    return span


def render_shot(plan: dict, shot: dict, only: list[int] | None = None) -> None:
    """Render the shot's frames (its part of the beat) as 00001.png, 00002.png..."""
    out = Path(shot["out"])
    out.mkdir(parents=True, exist_ok=True)
    clear()
    build_shot(plan, shot)
    start, n = int(shot.get("start", 1)), int(shot["frames"])
    sc = bpy.context.scene
    local = [f for f in (only or range(1, n + 1)) if 1 <= f <= n]
    # Cropped scene text is looked for on the frames a preview asks about, and on the middle of a
    # full shot (one check is enough: a sign does not move).
    checked = set(local) if only else {local[len(local) // 2]} if local else set()
    t = time.time()
    for f in local:
        sc.frame_set(start + f - 1)
        if f in checked:
            framecheck.check(sc, shot["id"], f)
        sc.render.filepath = str(out / f"{f:05d}.png")
        bpy.ops.render.render(write_still=True)
        print(f"VKFRAME {shot['id']} {f} {n}", flush=True)
    if not only:
        (out / "done.json").write_text(
            json.dumps({"key": shot["key"], "frames": n, "seconds": round(time.time() - t, 1)})
        )


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    plan = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    props.FONT = plan.get("font")
    human.LIB = plan.get("library") or os.environ.get("VK3D_LIB", "")
    props.WORLD = plan.get("world") or os.environ.get("VK3D_WORLD", "")
    props.MOON_DIR = plan.get("moon_dir") or ""
    if plan.get("hdri_dir"):
        look.HDRI_DIR = plan["hdri_dir"]
        look.TEX_DIR = str(Path(plan["hdri_dir"]).parent / "tex")
    look.setup_render(
        plan["size"][0],
        plan["size"][1],
        plan["fps"],
        plan.get("engine", "eevee"),
        plan.get("samples", 32),
        plan.get("motion_blur", True),
    )
    pct = round(100 * float(plan.get("resolution_scale", 1.0)))  # drafts, machines without a GPU
    bpy.context.scene.render.resolution_percentage = pct
    if plan.get("view"):  # "standard" for flat, poster-like color
        bpy.context.scene.view_settings.view_transform = "Standard"
    only = plan.get("only")  # {"shot_id": [frames]} for previews
    for shot in plan["shots"]:
        if only is not None and shot["id"] not in only:
            continue
        done = Path(shot["out"]) / "done.json"
        if only is None and done.exists():
            try:
                if json.loads(done.read_text())["key"] == shot["key"]:
                    print(f"VKSKIP {shot['id']}", flush=True)
                    continue
            except (ValueError, KeyError):
                pass
        look.setup_render(
            plan["size"][0],
            plan["size"][1],
            plan["fps"],
            plan.get("engine", "eevee"),
            plan.get("samples", 32),
            plan.get("motion_blur", True),
        )
        bpy.context.scene.render.resolution_percentage = pct
        render_shot(plan, shot, only.get(shot["id"]) if only else None)
    print("VKDONE", flush=True)


if __name__ == "__main__":
    main()
