"""Retarget an action from one armature to another with the same bone names. Developer tool,
imported by the library build scripts (runs inside Blender).

Each target bone is made to point where the source bone points, frame by frame, in armature
space; only the difference in how the two rigs roll their bones (the twist about the bone's own
axis) is kept as a constant offset. So it works between rigs whose rest poses differ (a T-pose
clip on an A-pose body: the arms come out where the clip has them, not 45 degrees lower), and
between rigs whose bones are rolled differently.

    Ms = Ms_parent @ (Rs_parent^-1 @ Rs) @ basis_s        (source, posed, armature space)
    Mt = Ms @ twist_y(Rs^-1 @ Rt)                          (arms: same direction, target's roll)
    Mt = Ms @ (Rs^-1 @ Rt)                                 (others: same turn away from rest)
    basis_t = (Mt_parent @ Rt_parent^-1 @ Rt)^-1 @ Mt

R = a bone's rest rotation in armature space, basis = its pose rotation (rotation_quaternion).
The hips' translation is turned into the target's frame and scaled by the hip heights.
"""

from __future__ import annotations

import bpy
from mathutils import Quaternion, Vector


def fcurves(action):
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


def twist_y(q: Quaternion) -> Quaternion:
    """The part of q that turns about the local Y axis (the bone's own axis)."""
    t = Quaternion((q.w, 0.0, q.y, 0.0))
    if t.magnitude < 1e-8:
        return Quaternion()
    t.normalize()
    return t


def steady(q: Quaternion, prev: Quaternion | None) -> Quaternion:
    """The same rotation written on one side: q and -q are one orientation, but blending a clip
    written with q into one written with -q swings the bone the long way round (an arm spinning a
    full turn between two clips). First key: w >= 0 (every clip agrees); then no sign jumps."""
    if prev is None:
        return -q if q.w < 0 else q
    return -q if q.dot(prev) < 0 else q


def canonical(action) -> int:
    """Rewrite an existing action's quaternion curves the same way. Returns the keys flipped."""
    groups: dict[str, dict[int, object]] = {}
    for fc in fcurves(action):
        if fc.data_path.endswith("rotation_quaternion"):
            groups.setdefault(fc.data_path, {})[fc.array_index] = fc
    flipped = 0
    for g in groups.values():
        if len(g) < 4:
            continue
        n = min(len(g[i].keyframe_points) for i in range(4))
        prev = None
        for k in range(n):
            q = Quaternion([g[i].keyframe_points[k].co.y for i in range(4)])
            s = steady(q, prev)
            if s.w != q.w or s.x != q.x:
                flipped += 1
                for i in range(4):
                    kp = g[i].keyframe_points[k]
                    kp.co.y = -kp.co.y
                    kp.handle_left.y = -kp.handle_left.y
                    kp.handle_right.y = -kp.handle_right.y
            prev = s
        for i in range(4):
            g[i].update()
    return flipped


def _norm(name: str) -> str:
    return name.lower()


# bones whose rest pose differs between a T-pose and an A-pose rig: their direction is matched; all
# the others keep the source's turn away from its rest (the rigs place them by different rules:
# a pelvis bone leans forward in one and back in the other)
ARMS = ("upperarm_", "lowerarm_", "hand_", "thigh_", "calf_")  # and legs: A-pose bodies splay them


def retarget(src_arm, src_act, dst_arm, out_name: str, *, hips: str = "pelvis", frames=None,
             match: tuple = ARMS):  # fmt: skip
    """A new action `out_name` (fake user) for dst_arm that plays src_act. Bones are matched by
    name, case-insensitively ("Head" = "head", "Root" = "root"). Bones named in `match` point where
    the source's point; the others repeat the source's rotation away from the rest pose."""
    sb = src_arm.data.bones
    tb = dst_arm.data.bones
    t_by = {_norm(b.name): b for b in tb}
    rest_s = {b.name: b.matrix_local.to_quaternion() for b in sb}
    rest_t = {b.name: b.matrix_local.to_quaternion() for b in tb}
    pair = {b.name: t_by.get(_norm(b.name)) for b in sb}
    conv = {}
    for s_name, t in pair.items():
        if t is None:
            continue
        d = rest_s[s_name].inverted() @ rest_t[t.name]
        conv[s_name] = twist_y(d) if _norm(s_name).startswith(match) else d
    curves = {(fc.data_path, fc.array_index): fc for fc in fcurves(src_act)}
    f0, f1 = (round(x) for x in src_act.frame_range)
    frames = list(frames or range(f0, f1 + 1))

    def src_basis(bone: str, f: float) -> Quaternion:
        p = f'pose.bones["{bone}"].rotation_quaternion'
        if not any((p, i) in curves for i in range(4)):
            return Quaternion()
        return Quaternion([
            curves[(p, i)].evaluate(f) if (p, i) in curves else (1.0 if i == 0 else 0.0)
            for i in range(4)
        ]).normalized()  # fmt: skip

    def src_loc(bone: str, f: float) -> Vector | None:
        p = f'pose.bones["{bone}"].location'
        if not any((p, i) in curves for i in range(3)):
            return None
        return Vector([curves[(p, i)].evaluate(f) if (p, i) in curves else 0.0 for i in range(3)])

    order: list = []  # parents before children

    def walk(b):
        order.append(b)
        for c in b.children:
            walk(c)

    for b in sb:
        if b.parent is None:
            walk(b)
    hs, ht = sb.get(hips), t_by.get(hips)
    hip_k = ht.head_local.z / max(1e-6, hs.head_local.z) if hs and ht else 1.0
    rows: dict[tuple[str, int], list[float]] = {}
    last: dict[str, Quaternion] = {}
    for f in frames:
        ms: dict[str, Quaternion] = {}
        mt: dict[str, Quaternion] = {}
        for b in order:
            n = b.name
            par = b.parent.name if b.parent else None
            local_rest = (rest_s[par].inverted() @ rest_s[n]) if par else rest_s[n]
            ms[n] = (ms[par] @ local_rest if par else local_rest) @ src_basis(n, f)
            t = pair.get(n)
            if t is None:
                continue
            mt[t.name] = ms[n] @ conv[n]
        for t in tb:  # target bones the source lacks: rest relative to their parent
            if t.name not in mt:
                par = t.parent.name if t.parent else None
                lr = (rest_t[par].inverted() @ rest_t[t.name]) if par else rest_t[t.name]
                mt[t.name] = (mt[par] @ lr) if par and par in mt else rest_t[t.name]
        for b in order:
            t = pair.get(b.name)
            if t is None:
                continue
            par = t.parent.name if t.parent else None
            base = (mt[par] @ rest_t[par].inverted() @ rest_t[t.name]) if par else rest_t[t.name]
            q = base.inverted() @ mt[t.name]
            q = steady(q, last.get(t.name))
            last[t.name] = q
            for i in range(4):
                rows.setdefault((f'pose.bones["{t.name}"].rotation_quaternion', i), []).extend(
                    (f, q[i])
                )
        if hs and ht:
            v = src_loc(hs.name, f)
            if v is not None:
                arm_space = rest_s[hs.name] @ v
                w = (rest_t[ht.name].inverted() @ arm_space) * hip_k
                for i in range(3):
                    rows.setdefault((f'pose.bones["{ht.name}"].location', i), []).extend((f, w[i]))
    act = bpy.data.actions.new(out_name)
    act.use_fake_user = True
    dst_arm.animation_data_create()
    keep = dst_arm.animation_data.action
    dst_arm.animation_data.action = act
    for (path, i), co in rows.items():
        fc = act.fcurve_ensure_for_datablock(dst_arm, path, index=i)
        fc.keyframe_points.add(len(co) // 2)
        fc.keyframe_points.foreach_set("co", co)
        fc.update()
    dst_arm.animation_data.action = keep
    return act


def play(arm, act) -> None:
    """Make `arm` play `act` (Blender 5 also needs the action's slot assigned)."""
    ad = arm.animation_data_create()
    ad.action = act
    if hasattr(ad, "action_slot") and act.slots and ad.action_slot is None:
        ad.action_slot = act.slots[0]


def check(src_arm, src_act, dst_arm, act, frame: int, *, tol: float = 6.0) -> list:
    """Bones whose direction differs from the source's by more than `tol` degrees at `frame`."""
    sc = bpy.context.scene
    play(src_arm, src_act)
    play(dst_arm, act)
    sc.frame_set(frame)
    bpy.context.view_layer.update()
    by = {_norm(b.name): b for b in dst_arm.pose.bones}
    bad = []
    for pb in src_arm.pose.bones:
        t = by.get(_norm(pb.name))
        if t is None or (pb.tail - pb.head).length < 1e-4 or "leaf" in pb.name:
            continue
        if _norm(pb.name).startswith(ARMS):  # where it points
            a = (src_arm.matrix_world.to_3x3() @ (pb.tail - pb.head)).normalized()
            b = (dst_arm.matrix_world.to_3x3() @ (t.tail - t.head)).normalized()
            ang = a.angle(b) * 57.2958
        else:  # how far it turned from its rest
            ds = pb.matrix.to_quaternion() @ pb.bone.matrix_local.to_quaternion().inverted()
            dt = t.matrix.to_quaternion() @ t.bone.matrix_local.to_quaternion().inverted()
            ang = ds.rotation_difference(dt).angle * 57.2958
        if ang > tol:
            bad.append((pb.name, round(ang, 1)))
    return bad
