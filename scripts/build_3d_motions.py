"""Add Mesh2Motion's CC0 human animations to the 3D library file. Developer tool.

    blender -b --factory-startup -P scripts/build_3d_motions.py -- HUMANS.blend M2M_DIR OUT.blend

M2M_DIR holds the `static/assets/human/animations/*.glb` files of github.com/Mesh2Motion/
mesh2motion-app at a pinned commit (written in M2M_DIR/COMMIT), with its LICENSE-CC0.MD. Root-motion
variants (`*-rm.glb`) are skipped: the kit moves people itself.

The Mesh2Motion skeleton has the same bone names as Quaternius' (`head` is `Head`), with rest
orientations a few degrees apart. Every clip is retargeted once onto the library's male armature,
bone by bone: q_target = (Rt^-1 Rs) q_source (Rs^-1 Rt), Rs / Rt the bones' rest rotations in
armature space; the pelvis translation is turned the same way and scaled by the hip heights. The
result is an action "m2m_<clip>" with a fake user, next to the "ual_" ones.

Sitting and lying clips also get where the body rests: `vk_seat_z` (the lowest point of the
buttocks above the floor, the rig origin at the feet) and `vk_seat_y` (how far behind the origin),
measured on the posed body mesh, so the runtime can put the hips on a seat of any height.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retarget as rt

RENAME = {"head": "Head"}
SKIP = {"head_leaf"}
SEATED = ("sitting-", "sit-ground", "sleeping", "laytoidle", "meditate", "tired-kneeling")


def _paths(bone: str) -> tuple[str, str]:
    return f'pose.bones["{bone}"].rotation_quaternion', f'pose.bones["{bone}"].location'


def _fcurves(action):
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


def retarget(src_arm, src_act, dst_arm, name: str):
    rest_s = {b.name: b.matrix_local.to_quaternion() for b in src_arm.data.bones}
    rest_t = {b.name: b.matrix_local.to_quaternion() for b in dst_arm.data.bones}
    hip = dst_arm.data.bones["pelvis"].head_local.z / max(
        1e-6, src_arm.data.bones["pelvis"].head_local.z
    )
    curves: dict[tuple[str, int], object] = {}
    for fc in _fcurves(src_act):
        curves[(fc.data_path, fc.array_index)] = fc
    f0, f1 = (round(x) for x in src_act.frame_range)
    frames = list(range(f0, f1 + 1))
    act = bpy.data.actions.new("m2m_" + name)
    act.use_fake_user = True
    dst_arm.animation_data_create()
    dst_arm.animation_data.action = act
    for sb in src_arm.data.bones:
        if sb.name in SKIP:
            continue
        tb = RENAME.get(sb.name, sb.name)
        if tb not in rest_t:
            continue
        rq, rl = _paths(sb.name)
        has_rot = any((rq, i) in curves for i in range(4))
        has_loc = sb.name in ("pelvis", "root") and any((rl, i) in curves for i in range(3))
        if not (has_rot or has_loc):
            continue
        a = rest_t[tb].inverted() @ rest_s[sb.name]  # source bone frame -> target bone frame
        b = rest_s[sb.name].inverted() @ rest_t[tb]
        tq, tl = _paths(tb)
        rows_q: list[list[float]] = [[] for _ in range(4)]
        rows_l: list[list[float]] = [[] for _ in range(3)]
        prev_q = None
        for f in frames:
            if has_rot:
                q = Quaternion([
                    curves[(rq, i)].evaluate(f) if (rq, i) in curves else (1.0 if i == 0 else 0.0)
                    for i in range(4)
                ])  # fmt: skip
                q = rt.steady(a @ q @ b, prev_q)
                prev_q = q
                for i in range(4):
                    rows_q[i] += [f, q[i]]
            if has_loc:
                v = Vector(
                    [curves[(rl, i)].evaluate(f) if (rl, i) in curves else 0.0 for i in range(3)]
                )
                v = (a.to_matrix() @ v) * hip
                for i in range(3):
                    rows_l[i] += [f, v[i]]
        for path, rows in ((tq, rows_q if has_rot else None), (tl, rows_l if has_loc else None)):
            if rows is None:
                continue
            for i, co in enumerate(rows):
                fc = act.fcurve_ensure_for_datablock(dst_arm, path, index=i)
                fc.keyframe_points.add(len(co) // 2)
                fc.keyframe_points.foreach_set("co", co)
                fc.update()
    return act


def seat(arm, body, act) -> tuple[float, float]:
    """Where the posed body rests: the lowest point near the hips, its height and depth."""
    arm.animation_data.action = act
    f0, f1 = act.frame_range
    bpy.context.scene.frame_set(round((f0 + f1) / 2))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    pelvis = arm.matrix_world @ arm.pose.bones["pelvis"].head
    pts = [body.matrix_world @ v.co for v in me.vertices]
    near = [
        p
        for p in pts
        if abs(p.x - pelvis.x) < 0.2 and abs(p.y - pelvis.y) < 0.25 and p.z < pelvis.z
    ]
    ev.to_mesh_clear()
    if not near:
        return pelvis.z - 0.12, pelvis.y
    low = min(near, key=lambda p: p.z)
    return low.z, pelvis.y


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    lib, m2m, out = Path(args[0]), Path(args[1]), Path(args[2])
    bpy.ops.wm.open_mainfile(filepath=str(lib))
    dst = bpy.data.objects["male_Armature"]
    body = next(o for o in bpy.data.objects if o.name == "male_SuperHero_Male")
    for a in [a for a in bpy.data.actions if a.name.startswith("m2m_")]:
        bpy.data.actions.remove(a)
    done = 0
    for glb in sorted(m2m.glob("*.glb")):
        if glb.stem.endswith("-rm"):
            continue
        before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
        bpy.ops.import_scene.gltf(filepath=str(glb))
        new_o = [o for o in bpy.data.objects if o not in before_o]
        new_a = [a for a in bpy.data.actions if a not in before_a]
        src = next((o for o in new_o if o.type == "ARMATURE"), None)
        if src is None or not new_a:
            print("VKSKIPCLIP", glb.name)
        else:
            act = retarget(src, new_a[0], dst, glb.stem)
            if glb.stem.startswith(SEATED):
                z, y = seat(dst, body, act)
                act["vk_seat_z"], act["vk_seat_y"] = round(z, 4), round(y, 4)
            done += 1
        for o in new_o:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in new_a:
            bpy.data.actions.remove(a)
    dst.animation_data.action = None
    # every clip on one quaternion side (blending clips of opposite signs spun the arms)
    flips = sum(rt.canonical(a) for a in bpy.data.actions if a.name.startswith(("ual_", "m2m_")))
    print("VKCANON", flips, "keys flipped", flush=True)
    # the pose stays where the last measured clip left it unless cleared, and the runtime builds
    # shoes and clothes on whatever pose the library armature is saved in
    for pb in dst.pose.bones:
        pb.location = (0, 0, 0)
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.rotation_euler = (0, 0, 0)
        pb.scale = (1, 1, 1)
    for blk in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images):
        for x in list(blk):
            if x.users == 0:
                blk.remove(x)
    commit = (m2m / "COMMIT").read_text().strip() if (m2m / "COMMIT").exists() else "?"
    bpy.context.scene["vk_m2m_commit"] = commit
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print("VKMOTIONS", done, "clips", commit)


if __name__ == "__main__":
    main()
