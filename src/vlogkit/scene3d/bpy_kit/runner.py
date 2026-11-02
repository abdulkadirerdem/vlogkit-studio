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
    framecheck,
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


def build_shot(plan: dict, shot: dict) -> int:
    fps = plan["fps"]
    n = int(shot["frames"])
    sc = bpy.context.scene
    sc.frame_start, sc.frame_end = 1, n
    info = sets.build(shot["set"], shot.get("set_opts") or {})
    for i, pr in enumerate(shot.get("props", [])):
        props.place(pr["kind"], f"prop{i}", pr)
    actors, scale_of = {}, {}
    for a in shot.get("actors", []):
        who = a["who"]
        spec = plan["cast"].get(who, {})
        if spec.get("style", "realistic") != "toon" and human.LIB:
            p = human.build(who, spec)
            actors[who] = p
            scale_of[who] = p.height / 1.7
            at = a.get("at", [0, 0])
            p.root.location = (at[0], at[1], at[2] if len(at) > 2 else 0)
            p.root.rotation_euler = (0, 0, R(a.get("facing", 0)))
            if a.get("size"):
                k = float(a["size"]) * p.root.scale.x
                p.root.scale = (k, k, k)
                scale_of[who] *= float(a["size"])
            p.root.keyframe_insert("location", frame=1)
            p.root.keyframe_insert("rotation_euler", frame=1)
            humanim.perform(p, a, fps, n)
            continue
        ch = character.build(who, spec)
        actors[who] = ch
        scale_of[who] = character.BODIES.get(ch.spec["body"], character.BODIES["adult"])[0]
        at = a.get("at", [0, 0])
        ch.root.location = (at[0], at[1], at[2] if len(at) > 2 else 0)
        ch.root.rotation_euler = (0, 0, R(a.get("facing", 0)))
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
            anim.act(ch, act["do"], f0, min(f1, n), fps, act.get("path"), act.get("heading"))
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
        anim.blinks(ch, 1, n, fps, seed=len(who) * 31 + n)
        anim.breathe(ch, 1, n, fps)
    cam = camera.make(shot.get("camera", {}).get("lens", 35))
    cspec = dict(shot.get("camera", {}))
    cspec.setdefault("_default_target", info.get("target", (0, 0, 1)))
    if "on" not in cspec and actors:
        cspec["on"] = next(iter(actors))
    camera.animate(cam, cspec, n, fps, actors, scale_of)
    return n


def render_shot(plan: dict, shot: dict, only: list[int] | None = None) -> None:
    out = Path(shot["out"])
    out.mkdir(parents=True, exist_ok=True)
    clear()
    n = build_shot(plan, shot)
    sc = bpy.context.scene
    frames = [f for f in (only or range(1, n + 1)) if 1 <= f <= n]
    # Cropped scene text is looked for on the frames a preview asks about, and on the middle of a
    # full shot (one check is enough: a sign does not move).
    checked = set(frames) if only else {frames[len(frames) // 2]} if frames else set()
    t = time.time()
    for f in frames:
        sc.frame_set(f)
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
