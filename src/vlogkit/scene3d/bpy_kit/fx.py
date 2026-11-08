"""Effects: what happens in a shot at a moment of the line (a crack runs across the floor, glass
shatters, a fireball blooms, water rises, money rains).

Every effect is built from plain objects and keyframes (no simulation caches), so a shot renders
the same on any machine and a preview frame is as exact as the full render. Entries come from the
plan resolved: `t` is seconds on the beat's timeline; `pos` [x, y, z] or `on` (an actor or a prop
id) says where; `size` scales; `dur` is how long it lasts.
"""

from __future__ import annotations

import math
import random

import bmesh
import bpy
from mathutils import Vector

from . import look, shapes

R = math.radians
G = 9.81


class Ctx:
    """What an effect needs from the shot: time, places, the camera, the things in it."""

    def __init__(self, fps: float, span: int, cam, actors: dict, props: dict, seed: int = 0):
        self.fps, self.span, self.cam = fps, span, cam
        self.actors, self.props = actors, props
        self.rng = random.Random(seed)
        self.gravity = G

    def frame(self, t: float) -> int:
        return max(1, min(self.span, 1 + round(t * self.fps)))

    def where(self, e: dict, default_z: float = 0.0) -> Vector:
        on = e.get("on")
        if isinstance(on, str) and on in self.actors:
            r = self.actors[on].root
            bpy.context.scene.frame_set(self.frame(e["t"]))
            p = r.matrix_world.translation
            return Vector((p.x, p.y, default_z if "pos" not in e else e["pos"][2]))
        if isinstance(on, str) and on in self.props:
            return self.props[on].center()
        p = e.get("pos") or [0, 0, default_z]
        return Vector((p[0], p[1], p[2] if len(p) > 2 else default_z))


# --------------------------------------------------------------------------- helpers
def _mat(
    color: str,
    emit: float = 0.0,
    alpha: float = 1.0,
    rough: float = 0.6,
    metal: float = 0.0,
    blended: bool = False,
    name: str = "fx",
):
    """An effect's own material (its alpha / glow are keyed, so it is never shared)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    rgba = look.hex_rgba(color)
    p.inputs["Base Color"].default_value = rgba
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Alpha"].default_value = alpha
    if emit:
        p.inputs["Emission Color"].default_value = rgba
        p.inputs["Emission Strength"].default_value = emit
    if hasattr(m, "surface_render_method"):
        m.surface_render_method = "BLENDED" if blended else "DITHERED"
    elif hasattr(m, "blend_method"):
        m.blend_method = "BLEND" if blended else "HASHED"
    if hasattr(m, "use_transparent_shadow"):
        m.use_transparent_shadow = True
    m.diffuse_color = rgba
    return m


def _soft(m, wisp: float = 0.6):
    """Make a sphere read as a puff of smoke or fire: its alpha fades towards the silhouette
    (facing ratio) and is broken up by noise, so no hard ball edge shows. The keyed alpha goes
    through a Value node ("vk_alpha"), which _key_input finds."""
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    a = nt.nodes.new("ShaderNodeValue")
    a.name = "vk_alpha"
    a.outputs[0].default_value = p.inputs["Alpha"].default_value
    lw = nt.nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.5
    edge = nt.nodes.new("ShaderNodeMapRange")
    edge.inputs["From Min"].default_value, edge.inputs["From Max"].default_value = 0.15, 0.9
    edge.inputs["To Min"].default_value, edge.inputs["To Max"].default_value = 1.0, 0.0
    nt.links.new(lw.outputs["Facing"], edge.inputs["Value"])
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.5
    noise.inputs["Detail"].default_value = 4.0
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    wn = nt.nodes.new("ShaderNodeMapRange")
    wn.inputs["From Min"].default_value, wn.inputs["From Max"].default_value = 0.35, 0.65
    wn.inputs["To Min"].default_value, wn.inputs["To Max"].default_value = 1.0 - wisp, 1.0
    nt.links.new(noise.outputs["Fac"], wn.inputs["Value"])
    m1 = nt.nodes.new("ShaderNodeMath")
    m1.operation = "MULTIPLY"
    nt.links.new(edge.outputs["Result"], m1.inputs[0])
    nt.links.new(wn.outputs["Result"], m1.inputs[1])
    m2 = nt.nodes.new("ShaderNodeMath")
    m2.operation = "MULTIPLY"
    nt.links.new(m1.outputs[0], m2.inputs[0])
    nt.links.new(a.outputs[0], m2.inputs[1])
    nt.links.new(m2.outputs[0], p.inputs["Alpha"])
    return m


def _key_input(m, name: str, frames_values) -> None:
    p = m.node_tree.nodes.get("Principled BSDF")
    alpha = m.node_tree.nodes.get("vk_alpha")
    sock = alpha.outputs[0] if (name == "Alpha" and alpha is not None) else p.inputs[name]
    for f, v in frames_values:
        sock.default_value = v
        sock.keyframe_insert("default_value", frame=f)


def _show(ob, f0: int, f1: int | None = None) -> None:
    """Visible from f0 (and until f1)."""
    for f, hidden in ((1, True), (f0, False), *(((f1, True),) if f1 else ())):
        if f == 1 and f0 <= 1:
            continue
        ob.hide_render = ob.hide_viewport = hidden
        ob.keyframe_insert("hide_render", frame=f)
        ob.keyframe_insert("hide_viewport", frame=f)
    if f0 <= 1:
        ob.hide_render = ob.hide_viewport = False


def _linear(ob) -> None:
    from .anim import _fcurves

    ad = ob.animation_data
    if ad and ad.action:
        for fc in _fcurves(ad.action):
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"


def _ease(ob, kind: str = "out") -> None:
    from .anim import _fcurves

    ad = ob.animation_data
    if not (ad and ad.action):
        return
    for fc in _fcurves(ad.action):
        if fc.data_path.startswith("hide"):
            continue
        for kp in fc.keyframe_points:
            if kind == "linear":
                kp.interpolation = "LINEAR"
            elif kind == "bounce":
                kp.interpolation, kp.easing = "BOUNCE", "EASE_OUT"
            elif kind == "back":
                kp.interpolation, kp.easing = "BACK", "EASE_OUT"
            else:
                kp.interpolation = "SINE"
                kp.easing = {"in": "EASE_IN", "inout": "EASE_IN_OUT"}.get(kind, "EASE_OUT")


def _chunk(name: str, size: float, mat, rng: random.Random, flat: bool = False):
    """An irregular rock / concrete chunk (or a thin glass shard)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    if flat:
        pts = [Vector((rng.uniform(-1, 1), 0, rng.uniform(-1, 1))) * size for _ in range(3)]
        vs = [bm.verts.new(p) for p in pts]
        vs2 = [bm.verts.new(p + Vector((0, size * 0.06, 0))) for p in pts]
        bm.faces.new(vs)
        bm.faces.new(list(reversed(vs2)))
        for i in range(3):
            j = (i + 1) % 3
            bm.faces.new([vs[i], vs[j], vs2[j], vs2[i]])
    else:
        bmesh.ops.create_icosphere(bm, subdivisions=1, radius=size)
        for v in bm.verts:
            v.co *= rng.uniform(0.65, 1.25)
            v.co.z *= 0.7
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = False
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    bpy.context.collection.objects.link(ob)
    return ob


def _ballistic(
    ctx: Ctx,
    ob,
    p0: Vector,
    v0: Vector,
    f0: int,
    life: float,
    bounce: float = 0.35,
    spin: float = 8.0,
    floor: float = 0.0,
    every: int = 1,
) -> None:
    """Throw an object: gravity, a few bounces on the floor, spin that dies on the ground."""
    dt = 1.0 / ctx.fps
    p, v = p0.copy(), v0.copy()
    w = Vector((ctx.rng.uniform(-1, 1), ctx.rng.uniform(-1, 1), ctx.rng.uniform(-1, 1))) * spin
    rot = Vector((ctx.rng.uniform(0, 6), ctx.rng.uniform(0, 6), ctx.rng.uniform(0, 6)))
    f1 = min(ctx.span, f0 + round(life * ctx.fps))
    resting = False
    g = ctx.gravity
    for f in range(f0, f1 + 1):
        if (f - f0) % every == 0 or f == f1:
            ob.location = p
            ob.rotation_euler = rot
            ob.keyframe_insert("location", frame=f)
            ob.keyframe_insert("rotation_euler", frame=f)
        if resting:
            continue
        v.z -= g * dt
        if g == 0:  # space: drift, slowly
            v *= 0.985
        p += v * dt
        rot += w * dt
        if g and p.z < floor:
            p.z = floor
            if abs(v.z) < 1.0:
                v = Vector((0, 0, 0))
                resting = True
            else:
                v.z = -v.z * bounce
                v.x *= 0.6
                v.y *= 0.6
                w *= 0.5
    _linear(ob)


def _burst_dirs(ctx: Ctx, n: int, up: float = 0.6, spread: float = 1.0):
    for _ in range(n):
        a = ctx.rng.uniform(0, 2 * math.pi)
        h = ctx.rng.uniform(0.2, 1.0) * spread
        yield Vector((math.cos(a) * h, math.sin(a) * h, ctx.rng.uniform(up * 0.6, up * 1.6)))


# --------------------------------------------------------------------------- effects
def crack(ctx: Ctx, e: dict, i: int) -> None:
    """Cracks run out from a point across the floor (or a wall facing the camera)."""
    size = float(e.get("size", 1.0))
    c = ctx.where(e)
    f0 = ctx.frame(e["t"])
    f1 = min(ctx.span, f0 + max(3, round(float(e.get("dur", 0.45)) * ctx.fps)))
    wall = bool(e.get("wall"))
    ink = _mat(e.get("color", "#1a1714"), rough=0.95, name=f"crack{i}")

    def to3(u, v):
        return c + (Vector((u, -0.03, v)) if wall else Vector((u, v, 0.006)))

    branches = []
    for k in range(int(e.get("n", 6))):
        a = 2 * math.pi * k / int(e.get("n", 6)) + ctx.rng.uniform(-0.35, 0.35)
        pts, u, v, d = [(0.0, 0.0)], 0.0, 0.0, a
        length = size * ctx.rng.uniform(0.9, 1.7)
        steps = 8
        for _ in range(steps):
            d += ctx.rng.uniform(-0.6, 0.6)
            u += math.cos(d) * length / steps
            v += math.sin(d) * length / steps
            pts.append((u, v))
            if ctx.rng.random() < 0.35:  # a side branch
                bd = d + ctx.rng.choice((-1, 1)) * ctx.rng.uniform(0.5, 1.1)
                bl = length * ctx.rng.uniform(0.15, 0.35)
                branches.append([(u, v), (u + math.cos(bd) * bl, v + math.sin(bd) * bl)])
        branches.append(pts)
    for k, pts in enumerate(branches):
        cu = bpy.data.curves.new(f"crack{i}.{k}", "CURVE")
        cu.dimensions = "3D"
        cu.bevel_depth = 0.012 * size * (1.0 if len(pts) > 2 else 0.6)
        cu.bevel_resolution = 1
        cu.bevel_factor_mapping_end = "SPLINE"
        sp = cu.splines.new("POLY")
        sp.points.add(len(pts) - 1)
        for p, (u, v) in zip(sp.points, pts, strict=True):
            p.co = (*to3(u, v), 1.0)
        # wider at the centre, a hairline at the tips
        for j, p in enumerate(sp.points):
            p.radius = max(0.15, 1.0 - j / max(1, len(pts) - 1))
        ob = bpy.data.objects.new(f"crack{i}.{k}", cu)
        ob.data.materials.append(ink)
        bpy.context.collection.objects.link(ob)
        delay = 0 if len(pts) > 2 else round((f1 - f0) * 0.4)
        for f, v in ((1, 0.0), (f0 + delay, 0.0), (f1 + delay, 1.0)):
            cu.bevel_factor_end = v
            cu.keyframe_insert("bevel_factor_end", frame=f)
    if e.get("debris", True):
        debris(ctx, {**e, "n": e.get("n_debris", 8), "size": size * 0.5, "pos": list(c)}, i)
        smoke(ctx, {**e, "size": size * 0.6, "dur": 1.2, "color": "#a49e94", "pos": list(c)}, i)


def debris(ctx: Ctx, e: dict, i: int, glass: bool = False) -> None:
    size = float(e.get("size", 1.0))
    c = ctx.where(e, default_z=0.1)
    f0 = ctx.frame(e["t"])
    n = int(e.get("n", 14 if not glass else 36))
    if glass:
        m = _mat(e.get("color", "#cfe8f2"), alpha=0.45, rough=0.03, name=f"glass{i}")
    else:
        m = _mat(e.get("color", "#8a857d"), rough=0.9, name=f"debris{i}")
    for k, d in enumerate(_burst_dirs(ctx, n, up=0.9 if not glass else 0.5)):
        s = size * ctx.rng.uniform(0.03, 0.11) * (1.6 if glass else 1)
        ob = _chunk(f"{'shard' if glass else 'chunk'}{i}.{k}", s, m, ctx.rng, flat=glass)
        _show(ob, f0)
        v = d * ctx.rng.uniform(2.5, 5.5) * math.sqrt(size)
        _ballistic(ctx, ob, c + d * 0.05, v, f0, float(e.get("dur", 3.0)), every=2)


def shatter(ctx: Ctx, e: dict, i: int) -> None:
    flash(ctx, {**e, "color": "#e8f6ff", "size": 0.4 * float(e.get("size", 1))}, i)
    debris(ctx, e, i, glass=True)


def smoke(ctx: Ctx, e: dict, i: int) -> None:
    """Puffs that rise, swell and thin out."""
    size = float(e.get("size", 1.0))
    c = ctx.where(e)
    f0 = ctx.frame(e["t"])
    dur = float(e.get("dur", 2.5))
    color = e.get("color", "#6f6c69")
    n = int(e.get("n", max(12, round(14 * size))))
    for k in range(n):
        m = _soft(_mat(color, alpha=0.0, rough=1.0, blended=True, name=f"smoke{i}.{k}"))
        p0 = c + Vector((ctx.rng.uniform(-0.3, 0.3) * size, ctx.rng.uniform(-0.3, 0.3) * size, 0.1))
        ob = shapes.sphere(f"smoke{i}.{k}", 0.24 * size, m, p0, segments=20, rings=12)
        tex = bpy.data.textures.new(f"smoke{i}.{k}", "CLOUDS")
        tex.noise_scale = 0.35 * size
        dm = ob.modifiers.new("lumps", "DISPLACE")
        dm.texture = tex
        dm.strength = 0.25 * size
        start = f0 + round(k * dur * 0.35 * ctx.fps / n)
        life = round(dur * ctx.fps)
        end = min(ctx.span, start + life)
        rise = Vector(
            (ctx.rng.uniform(-0.3, 0.3), ctx.rng.uniform(-0.3, 0.3), 1.6 * size * dur / 2.5)
        )
        _show(ob, start)
        for f, sc, loc in ((start, 0.3, p0), (end, 1.0 + 0.6 * ctx.rng.random(), p0 + rise)):
            ob.scale = (sc, sc, sc)
            ob.location = loc
            ob.keyframe_insert("scale", frame=f)
            ob.keyframe_insert("location", frame=f)
        _ease(ob, "out")
        _key_input(m, "Alpha", ((start, 0.0), (start + max(2, life // 5), 0.55), (end, 0.0)))


def fire(ctx: Ctx, e: dict, i: int) -> None:
    """Flickering flames and their light, from `t` for `dur` (default: to the end)."""
    size = float(e.get("size", 1.0))
    c = ctx.where(e)
    f0 = ctx.frame(e["t"])
    f1 = ctx.frame(e["t"] + float(e["dur"])) if e.get("dur") else None
    # tongues of flame: tall soft-edged drops (no hard silhouette), red-orange outside, a
    # yellow core, each flickering and licking upwards on its own; a moderate glow keeps the
    # colour (a strong one went pale pink)
    from .anim import _fcurves

    layers = (
        ("#ff5a12", 1.05, 0.13, 2.4, 6),
        ("#ff9418", 0.85, 0.1, 3.4, 6),
        ("#ffd448", 0.55, 0.065, 4.6, 6),
    )
    for k, (col, h, r, glow, n) in enumerate(layers):
        for j in range(n):
            m = _soft(_mat(col, emit=glow, alpha=0.85, blended=True, name=f"fire{i}.{k}{j}"), 0.55)
            off = Vector((ctx.rng.uniform(-0.24, 0.24), ctx.rng.uniform(-0.14, 0.14), 0)) * size
            hh = h * size * ctx.rng.uniform(0.7, 1.2)
            rr = r * size * ctx.rng.uniform(0.8, 1.2)
            ob = shapes.sphere(f"fire{i}.{k}{j}", rr, m, c + off + Vector((0, 0, hh * 0.5)),
                               scale=(1.0, 1.0, hh / (2 * rr)), segments=16, rings=12)  # fmt: skip
            _show(ob, f0, f1)
            ob.keyframe_insert("scale", frame=f0)
            ob.keyframe_insert("location", frame=f0)
            for fc in _fcurves(ob.animation_data.action):
                nm = fc.modifiers.new("NOISE")
                if fc.data_path == "scale":  # breathing tongues, taller jumps than widths
                    nm.scale = 2.5 + j * 0.7
                    nm.strength = (0.45 if fc.array_index == 2 else 0.18) * (
                        ob.scale[fc.array_index]
                    )
                else:  # licking sideways and up
                    nm.scale = 3.0 + j
                    nm.strength = (0.06 if fc.array_index < 2 else 0.1) * size
                nm.phase = 13 * k + 7 * j + 3 * fc.array_index
    light = look.point(c + Vector((0, -0.2, 0.9 * size)), 0, "#ff8a3a", 0.3, f"firelight{i}")
    light.data.energy = 400 * size * size
    light.data.keyframe_insert("energy", frame=f0)
    from .anim import _fcurves

    for fc in _fcurves(light.data.animation_data.action):
        nm = fc.modifiers.new("NOISE")
        nm.scale, nm.strength = 2, 160 * size * size
    _show(light, f0, f1)


def sparks(ctx: Ctx, e: dict, i: int) -> None:
    size = float(e.get("size", 1.0))
    c = ctx.where(e, default_z=0.5)
    f0 = ctx.frame(e["t"])
    for k, d in enumerate(_burst_dirs(ctx, int(e.get("n", 24)), up=0.8)):
        m = _mat(e.get("color", "#ffd27a"), emit=25, name=f"spark{i}.{k}")
        ob = shapes.cylinder(f"spark{i}.{k}", 0.006 * size, 0.09 * size, m, c, segments=6)
        life = ctx.rng.uniform(0.35, 0.8)
        _show(ob, f0, min(ctx.span, f0 + round(life * ctx.fps)))
        v = d * ctx.rng.uniform(3, 6) * math.sqrt(size)
        ob.rotation_euler = v.to_track_quat("Z", "Y").to_euler()
        _ballistic(ctx, ob, c.copy(), v, f0, life, bounce=0.2, spin=0)


def explosion(ctx: Ctx, e: dict, i: int) -> None:
    """A fireball blooms and darkens, a flash of light, smoke rolls up, chunks fly."""
    size = float(e.get("size", 1.0))
    c = ctx.where(e, default_z=0.4 * size)
    f0 = ctx.frame(e["t"])
    for k in range(12):
        m = _soft(_mat("#ffb347", emit=12, alpha=1.0, blended=True, name=f"boom{i}.{k}"), 0.45)
        off = Vector(
            (ctx.rng.uniform(-0.55, 0.55), ctx.rng.uniform(-0.45, 0.45), ctx.rng.uniform(0, 0.8))
        )
        ob = shapes.sphere(f"boom{i}.{k}", 0.32 * size, m, c + off * size, segments=24, rings=12)
        tex = bpy.data.textures.new(f"boom{i}.{k}", "CLOUDS")
        tex.noise_scale = 0.4 * size
        dm = ob.modifiers.new("lumps", "DISPLACE")
        dm.texture, dm.strength = tex, 0.35 * size
        _show(ob, f0, min(ctx.span, f0 + round(1.6 * ctx.fps)))
        grow = 1.2 + 0.5 * ctx.rng.random()
        for f, sc in (
            (f0, 0.05),
            (f0 + round(0.18 * ctx.fps), grow),
            (f0 + round(1.6 * ctx.fps), grow * 1.5),
        ):
            ob.scale = (sc, sc, sc)
            ob.keyframe_insert("scale", frame=f)
        _ease(ob, "out")
        p = m.node_tree.nodes.get("Principled BSDF")
        for f, col, em, a in (
            (f0, "#ffe58a", 14, 1.0),
            (f0 + round(0.25 * ctx.fps), "#ff7a12", 8, 0.95),
            (f0 + round(0.8 * ctx.fps), "#8a2a0a", 2, 0.6),
            (f0 + round(1.6 * ctx.fps), "#2a1a12", 0, 0.0),
        ):
            p.inputs["Emission Color"].default_value = look.hex_rgba(col)
            p.inputs["Emission Color"].keyframe_insert("default_value", frame=f)
            p.inputs["Emission Strength"].default_value = em
            p.inputs["Emission Strength"].keyframe_insert("default_value", frame=f)
            va = m.node_tree.nodes["vk_alpha"].outputs[0]
            va.default_value = a
            va.keyframe_insert("default_value", frame=f)
    light = look.point(c, 0, "#ffa040", 0.5, f"boomlight{i}")
    for f, en in ((f0 - 1, 0), (f0 + 2, 9000 * size * size), (f0 + round(0.9 * ctx.fps), 0)):
        light.data.energy = en
        light.data.keyframe_insert("energy", frame=max(1, f))
    smoke(ctx, {**e, "t": e["t"] + 0.25, "size": size * 1.4, "dur": 3.0, "color": "#3c3836", "pos": list(c - Vector((0, 0, c.z)))}, i)  # fmt: skip
    debris(ctx, {**e, "n": e.get("n", 16), "pos": list(c)}, i)
    sparks(ctx, {**e, "n": 20, "pos": list(c)}, i)
    shake(ctx, {**e, "amount": e.get("amount", 0.06), "dur": 0.8}, i)


def flash(ctx: Ctx, e: dict, i: int) -> None:
    size = float(e.get("size", 1.0))
    c = ctx.where(e, default_z=1.5)
    f0 = ctx.frame(e["t"])
    light = look.point(c, 0, e.get("color", "#ffffff"), 0.5, f"flash{i}")
    for f, en in ((f0 - 1, 0), (f0 + 1, 6000 * size * size), (f0 + round(0.3 * ctx.fps), 0)):
        light.data.energy = en
        light.data.keyframe_insert("energy", frame=max(1, f))


def shake(ctx: Ctx, e: dict, i: int) -> None:
    from . import camera

    f0 = ctx.frame(e["t"])
    f1 = min(ctx.span, f0 + max(4, round(float(e.get("dur", 0.6)) * ctx.fps)))
    camera._shake(ctx.cam, float(e.get("amount", 0.04)), f0, f1, blend=2)


def flood(ctx: Ctx, e: dict, i: int) -> None:
    """Water rises over the floor to `level` m, rippling."""
    f0 = ctx.frame(e["t"])
    f1 = min(ctx.span, f0 + round(float(e.get("dur", 3.0)) * ctx.fps))
    level = float(e.get("level", 1.0))
    m = _water_mat(e.get("color", "#2f6f86"), f"flood{i}")
    c = ctx.where(e)
    ob = shapes.plane(f"flood{i}", (80, 80), m, (c.x, c.y, -0.02))
    _show(ob, f0)
    for f, z in ((f0, -0.02), (f1, level)):
        ob.location.z = z
        ob.keyframe_insert("location", index=2, frame=f)
    _ease(ob, "inout")


def _water_mat(color: str, name: str):
    m = _mat(color, alpha=0.82, rough=0.06, name=name)
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 3.0
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    if "Specular IOR Level" in p.inputs:
        p.inputs["Specular IOR Level"].default_value = 0.9
    return m


def pour(ctx: Ctx, e: dict, i: int) -> None:
    """A stream falls from `pos` to the floor and a puddle spreads around it."""
    size = float(e.get("size", 1.0))
    c = ctx.where(e, default_z=0.6)
    f0 = ctx.frame(e["t"])
    f1 = min(ctx.span, f0 + round(float(e.get("dur", 3.0)) * ctx.fps))
    m = _water_mat(e.get("color", "#6fb4d2"), f"pour{i}")
    top = shapes.empty(f"pour{i}.top", c)
    h = max(0.05, c.z)
    st = shapes.cylinder(
        f"pour{i}.stream", 0.035 * size, h, m, (0, 0, -h / 2), parent=top, segments=12
    )
    del st
    _show(top, f0)
    for f, s in ((f0, 0.01), (f0 + round(0.25 * ctx.fps), 1.0)):
        top.scale = (1, 1, s)
        top.keyframe_insert("scale", index=2, frame=f)
    pud = shapes.cylinder(f"pour{i}.puddle", 1.0, 0.01, m, (c.x, c.y, 0.006), segments=40)
    _show(pud, f0 + round(0.25 * ctx.fps))
    r1 = 1.4 * size
    for f, r in ((f0 + round(0.25 * ctx.fps), 0.05), (f1, r1)):
        pud.scale = (r, r * 0.85, 1)
        pud.keyframe_insert("scale", frame=f)
    _ease(pud, "out")


RAIN = {  # item -> (color(s), size (w, h), fall speed m/s, sway)
    "money": (["#7fb56b", "#6aa45a", "#8cc27a"], (0.16, 0.07), 1.3, 0.5),
    "confetti": (["#ff4d6d", "#ffd23f", "#3ec1d3", "#9b5de5", "#00f5d4"], (0.05, 0.03), 1.6, 0.35),
    "water": (["#c4e6f5"], (0.014, 0.34), 9.0, 0.0),  # streaks: a drop as motion blur shows it
    "snow": (["#ffffff"], (0.03, 0.03), 0.8, 0.3),
}


def rain(ctx: Ctx, e: dict, i: int) -> None:
    """Things falling from the sky over `area` [x0, y0, x1, y1]. Rain and snow keep falling: every
    drop loops from the top to the ground for as long as it rains (none hangs in the air before
    its turn or stays stuck on the ground); money and confetti fall once and stay where they land.
    """
    item = e.get("item", "money")
    colors, (w, h), speed, sway = RAIN.get(item, RAIN["money"])
    if e.get("color"):
        colors = [e["color"]]
    c = ctx.where(e)
    x0, y0, x1, y1 = e.get("area") or (c.x - 3, c.y - 2, c.x + 3, c.y + 3)
    t0 = float(e["t"])
    dur = float(e.get("dur", (ctx.span / ctx.fps) - t0))
    n = int(e.get("n", {"money": 70, "confetti": 160, "water": 220, "snow": 160}.get(item, 80)))
    mats = [
        _mat(col, alpha=0.55 if item == "water" else 1.0, rough=0.2 if item == "water" else 0.5,
             emit=0.6 if item in ("water", "snow") else 0.0, name=f"rain{i}.{k}")
        for k, col in enumerate(colors)
    ]  # fmt: skip
    from .anim import _fcurves

    if item in ("water", "snow"):
        ground = float(e.get("ground", 0.0))
        f_on = ctx.frame(t0)
        f_off = ctx.frame(t0 + dur) if e.get("dur") else None
        for k in range(n):
            top = ctx.rng.uniform(4.5, 7.5)
            # each its own speed (a sheet of identical drops reads as a pattern)
            v = speed * ctx.rng.uniform(0.85, 1.2)
            period = max(4, round((top - ground) / v * ctx.fps))
            phase = ctx.rng.randint(0, period - 1)  # mid-fall when the rain starts
            p = Vector((ctx.rng.uniform(x0, x1), ctx.rng.uniform(y0, y1), top))
            ob = shapes.plane(f"rain{i}.{k}", (w, h), mats[k % len(mats)], p, (90, 0, 0))
            if item == "snow":
                ob.rotation_euler = (R(90), 0, ctx.rng.uniform(0, 6))
            fa = f_on - phase
            for f, z in ((fa, top), (fa + period, ground + h / 2)):
                ob.location.z = z
                ob.keyframe_insert("location", index=2, frame=f)
            _linear(ob)
            for fc in _fcurves(ob.animation_data.action):
                fc.modifiers.new("CYCLES")
            if sway:  # snow drifts
                ob.keyframe_insert("location", index=0, frame=fa)
                for fc in _fcurves(ob.animation_data.action):
                    if fc.data_path == "location" and fc.array_index == 0:
                        nm = fc.modifiers.new("NOISE")
                        nm.scale, nm.strength, nm.phase = 18, sway, k * 3.1
            _show(ob, f_on, f_off)
        return

    for k in range(n):
        top = ctx.rng.uniform(4.5, 7.5)
        fall = top / speed
        start = t0 + ctx.rng.uniform(-fall * 0.8, max(0.0, dur - fall * 0.5))
        p = Vector((ctx.rng.uniform(x0, x1), ctx.rng.uniform(y0, y1), top))
        ob = shapes.plane(f"rain{i}.{k}", (w, h), mats[k % len(mats)], p, (90, 0, 0))
        fa, fb = 1 + round(start * ctx.fps), 1 + round((start + fall) * ctx.fps)
        if fb < 1 or fa > ctx.span:
            bpy.data.objects.remove(ob)
            continue
        for f, z in ((fa, top), (fb, 0.01)):
            ob.location.z = z
            ob.keyframe_insert("location", index=2, frame=f)
        ob.rotation_euler = (ctx.rng.uniform(0, 6), ctx.rng.uniform(0, 6), ctx.rng.uniform(0, 6))
        ob.keyframe_insert("rotation_euler", frame=fa)
        ob.rotation_euler = (ctx.rng.uniform(6, 14), ctx.rng.uniform(6, 14), ctx.rng.uniform(0, 6))
        ob.keyframe_insert("rotation_euler", frame=fb)
        ob.keyframe_insert("location", index=0, frame=fa)
        ob.keyframe_insert("location", index=1, frame=fa)
        _linear(ob)
        _show(ob, max(1, fa))  # not hanging in the sky before its turn
        if sway:
            for fc in _fcurves(ob.animation_data.action):
                if fc.data_path == "location" and fc.array_index < 2:
                    nm = fc.modifiers.new("NOISE")
                    nm.scale, nm.strength, nm.phase = 18, sway, k * 3.1 + fc.array_index


def beam(ctx: Ctx, e: dict, i: int) -> None:
    """A beam of light from `pos` to `to` (a point, an actor or a prop id)."""
    size = float(e.get("size", 1.0))
    a = ctx.where(e, default_z=1.4)
    to = e.get("to") or [a.x, a.y, 30]
    b = (
        ctx.where({**e, "on": to, "pos": None})
        if isinstance(to, str)
        else Vector((to[0], to[1], to[2] if len(to) > 2 else 0))
    )
    f0 = ctx.frame(e["t"])
    f1 = ctx.frame(e["t"] + float(e["dur"])) if e.get("dur") else None
    d = b - a
    m = _mat(e.get("color", "#7fe3ff"), emit=18, alpha=0.9, blended=True, name=f"beam{i}")
    root = shapes.empty(f"beam{i}", a)
    root.rotation_euler = d.to_track_quat("Z", "Y").to_euler()
    shapes.cylinder(
        f"beam{i}.core", 0.05 * size, d.length, m, (0, 0, d.length / 2), parent=root, segments=16
    )
    _show(root, f0, f1)
    for ch in root.children:
        _show(ch, f0, f1)
    for f, s in ((f0, 0.01), (f0 + max(2, round(0.15 * ctx.fps)), 1.0)):
        root.scale = (1, 1, s)
        root.keyframe_insert("scale", index=2, frame=f)
    light = look.point(b, 0, e.get("color", "#7fe3ff"), 0.3, f"beamlight{i}")
    light.data.energy = 600 * size
    light.data.keyframe_insert("energy", frame=f0 + 2)
    light.data.energy = 0
    light.data.keyframe_insert("energy", frame=max(1, f0 - 1))


# ---- things that happen to a prop
def _realize(root) -> list:
    """The mesh objects that make up a prop, as real objects (library instances unpacked)."""
    out = []
    bpy.context.view_layer.update()
    for ob in [root, *root.children_recursive]:
        if ob.type == "MESH":
            out.append(ob)
        elif ob.instance_type == "COLLECTION" and ob.instance_collection:
            for src in ob.instance_collection.all_objects:
                if src.type != "MESH":
                    continue
                c = src.copy()
                c.data = src.data.copy()
                c.parent = None
                bpy.context.collection.objects.link(c)
                c.matrix_world = ob.matrix_world @ src.matrix_world
                out.append(c)
            ob.hide_render = ob.hide_viewport = True
    return out


def _lava(name: str, color: str):
    """A molten core: glowing orange veins over dark red rock."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes.get("Principled BSDF")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 6.0
    noise.inputs["Detail"].default_value = 8.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.42
    ramp.color_ramp.elements[0].color = look.hex_rgba("#2a0a04")
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = look.hex_rgba(color)
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Emission Color"])
    p.inputs["Emission Strength"].default_value = 7.0
    p.inputs["Roughness"].default_value = 0.8
    m.diffuse_color = look.hex_rgba(color)
    return m


def split(ctx: Ctx, e: dict, i: int) -> None:
    """Cut a prop in two along `axis` (x | y | z): a flash, the halves drift apart and turn their
    molten insides towards the camera, rocks and sparks fly out of the gap."""
    prop = ctx.props[e["target"]]
    f0 = ctx.frame(e["t"])
    f1 = min(ctx.span, f0 + round(float(e.get("dur", 1.6)) * ctx.fps))
    centre = prop.center()
    size = prop.size()
    axis = {"x": Vector((1, 0, 0)), "y": Vector((0, 1, 0)), "z": Vector((0, 0, 1))}[
        e.get("axis", "x")
    ]
    gap = float(e.get("gap", size * 0.08))
    core = _lava(f"core{i}", e.get("color", "#ff7a1a"))
    bpy.context.scene.frame_set(f0)
    to_cam = ctx.cam.matrix_world.translation - centre
    parts = _realize(prop.root)
    for side in (1, -1):
        holder = shapes.empty(f"half{i}.{side}", centre)
        for src in parts:
            c = src.copy()
            c.data = src.data.copy()
            c.animation_data_clear()
            bpy.context.collection.objects.link(c)
            mw = src.matrix_world.copy()
            c.parent = None
            me = c.data
            for m in list(c.modifiers):
                if m.type != "ARMATURE":
                    c.modifiers.remove(m)
            bm = bmesh.new()
            bm.from_mesh(me)
            bm.transform(mw)
            geom = bm.verts[:] + bm.edges[:] + bm.faces[:]
            res = bmesh.ops.bisect_plane(
                bm, geom=geom, plane_co=centre, plane_no=axis * side,
                clear_inner=True, clear_outer=False,
            )  # fmt: skip
            cut = [g for g in res["geom_cut"] if isinstance(g, bmesh.types.BMEdge)]
            if cut:
                filled = bmesh.ops.holes_fill(bm, edges=cut, sides=0)
                me.materials.append(core)
                for fce in filled.get("faces", []):
                    fce.material_index = len(me.materials) - 1
                    fce.smooth = False
            bm.transform(mw.inverted())
            bm.to_mesh(me)
            bm.free()
            c.matrix_world = mw
            c.parent = holder
            c.matrix_parent_inverse = holder.matrix_world.inverted()
            _show(c, f0)
        # turn the cut face (it looks along -axis*side) part of the way towards the camera
        n = -axis * side
        turn = math.atan2(n.x * to_cam.y - n.y * to_cam.x, n.x * to_cam.x + n.y * to_cam.y)
        for f, k in ((f0, 0.0), (f0 + round(0.25 * ctx.fps), 0.35), (f1, 1.0)):
            holder.location = (
                centre + axis * side * gap * k + Vector((0, 0, 0.04 * size * k * side))
            )
            holder.rotation_euler = (R(4 * side * k), R(6 * side * k), turn * 0.55 * k)
            holder.keyframe_insert("location", frame=min(f, ctx.span))
            holder.keyframe_insert("rotation_euler", frame=min(f, ctx.span))
        _ease(holder, "out")
    for src in parts:
        for f, hid in ((f0 - 1, False), (f0, True)):
            src.hide_render = src.hide_viewport = hid
            src.keyframe_insert("hide_render", frame=max(1, f))
            src.keyframe_insert("hide_viewport", frame=max(1, f))
    # the glow sits in the gap: it lights the cut faces, barely the outside
    glow = look.point(centre, 0, e.get("color", "#ff7a1a"), size * 0.05, f"coreglow{i}")
    s2 = size * size
    for f, en in (
        (f0 - 1, 0),
        (f0 + 2, 120 * s2),
        (f0 + round(0.4 * ctx.fps), 25 * s2),
        (f1, 18 * s2),
    ):
        glow.data.energy = en
        glow.data.keyframe_insert("energy", frame=max(1, min(ctx.span, f)))
    debris(
        ctx,
        {**e, "pos": list(centre), "n": e.get("n", 26), "size": size * 0.35, "color": "#6d625a"},
        i,
    )
    sparks(ctx, {**e, "pos": list(centre), "n": 30, "size": size * 0.4, "color": "#ffb04a"}, i)


def pop(ctx: Ctx, e: dict, i: int) -> None:
    """A prop appears with a little overshoot."""
    root = ctx.props[e["target"]].root
    f0 = ctx.frame(e["t"])
    s = root.scale.copy()
    for f, k in (
        (1, 0.0),
        (f0, 0.0),
        (f0 + round(0.18 * ctx.fps), 1.15),
        (f0 + round(0.3 * ctx.fps), 1.0),
    ):
        if f == 1 and f0 <= 1:
            continue
        root.scale = s * max(k, 1e-3)
        root.keyframe_insert("scale", frame=f)
    sparks(ctx, {**e, "on": e["target"], "n": 14, "size": 0.6}, i)


def vanish(ctx: Ctx, e: dict, i: int) -> None:
    root = ctx.props[e["target"]].root
    f0 = ctx.frame(e["t"])
    s = root.scale.copy()
    for f, k in ((f0, 1.0), (f0 + round(0.1 * ctx.fps), 1.1), (f0 + round(0.3 * ctx.fps), 0.001)):
        root.scale = s * k
        root.keyframe_insert("scale", frame=f)
    sparks(ctx, {**e, "on": e["target"], "n": 14, "size": 0.6}, i)


def _pit_box(cutters) -> tuple[Vector, Vector]:
    bpy.context.view_layer.update()
    pts = [c.matrix_world @ Vector(b) for c in cutters for b in c.bound_box]
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return lo, hi


def collapse(ctx: Ctx, e: dict, i: int) -> None:
    """A pit's walls give way: clods break off the sides and fall, loose soil piles up from the
    bottom to `to` (m), dust rises, the ground shakes. `target`: the pit's id."""
    from . import props

    cutters = props.PITS.get(e.get("target", ""))
    if not cutters:
        return
    lo, hi = _pit_box(cutters)
    bottom = lo.z
    top_fill = float(e.get("to", bottom + (min(0.0, hi.z) - bottom) * 0.25))
    f0 = ctx.frame(e["t"])
    dur = float(e.get("dur", 1.4))
    soil = bpy.data.materials.get("set.strata") or _mat("#5a3b24", rough=0.95, name=f"clod{i}")
    yb = max(0.05, min(hi.y, 0.9))
    for k in range(int(e.get("n", 34))):
        side = ctx.rng.choice((-1, 1))
        x = (lo.x + 0.08) if side < 0 else (hi.x - 0.08)
        z = ctx.rng.uniform(max(bottom + 0.6, -3.2), -0.15)
        y = ctx.rng.uniform(0.05, yb)
        ob = _chunk(f"clod{i}.{k}", ctx.rng.uniform(0.05, 0.16), soil, ctx.rng)
        start = f0 + round(ctx.rng.uniform(0.0, dur * 0.6) * ctx.fps)
        _show(ob, start)
        v = Vector(
            (
                -side * ctx.rng.uniform(0.3, 1.2),
                ctx.rng.uniform(-0.1, 0.1),
                ctx.rng.uniform(-0.5, 0.4),
            )
        )
        _ballistic(ctx, ob, Vector((x, y, z)), v, start, 2.5, bounce=0.15, spin=5.0,
                   floor=bottom + 0.05, every=2)  # fmt: skip
    # the loose soil piling up from the bottom
    o = {"pit": e["target"], "material": "soil", "from": bottom, "to": top_fill, "_order": 40}
    root = props.layer(f"collapse{i}", o, None)
    root.location = o.get("at", (0, 0, bottom))
    for f, k in (
        (1, 0.01),
        (f0 + round(0.25 * ctx.fps), 0.01),
        (min(ctx.span, f0 + round(dur * ctx.fps)), 1.0),
    ):
        root.scale = (1, 1, k)
        root.keyframe_insert("scale", index=2, frame=max(1, f))
    _ease(root, "out")
    mid = (lo + hi) / 2
    smoke(ctx, {"t": e["t"] + 0.15, "pos": [mid.x, 0.15, bottom + 0.4], "size": 0.7, "dur": 2.0,
                "color": "#9b8a72", "n": 7}, 100 + i)  # fmt: skip
    shake(ctx, {"t": e["t"], "amount": e.get("amount", 0.035), "dur": 0.7}, i)


def dig(ctx: Ctx, e: dict, i: int) -> None:
    """A pit being dug: the soil in it empties from the top down while clods fly out over the
    edge and land on the lawn (`target`: the pit's id, `dur` seconds)."""
    from . import props

    cutters = props.PITS.get(e.get("target", ""))
    if not cutters:
        return
    lo, hi = _pit_box(cutters)
    f0 = ctx.frame(e["t"])
    dur = float(e.get("dur", 1.8))
    f1 = min(ctx.span, f0 + round(dur * ctx.fps))
    o = {"pit": e["target"], "material": "strata", "from": lo.z, "to": 0.0, "_order": 41}
    root = props.layer(f"dig{i}", o, None)
    root.location = o.get("at", (0, 0, lo.z))
    for f, k in ((1, 1.0), (f0, 1.0), (f1, 0.001)):
        root.scale = (1, 1, k)
        root.keyframe_insert("scale", index=2, frame=max(1, f))
    _ease(root, "inout")
    _show(root, 1, min(ctx.span, f1 + 1))
    soil = bpy.data.materials.get("set.strata") or _mat("#5a3b24", rough=0.95, name=f"spoil{i}")
    n = int(e.get("n", 26))
    for k in range(n):
        start = f0 + round(dur * ctx.fps * k / n)
        ob = _chunk(f"spoil{i}.{k}", ctx.rng.uniform(0.04, 0.1), soil, ctx.rng)
        _show(ob, start)
        side = ctx.rng.choice((-1, 1))
        v = Vector(
            (side * ctx.rng.uniform(0.8, 1.8), ctx.rng.uniform(0.2, 0.9), ctx.rng.uniform(3.0, 4.2))
        )
        p0 = Vector((ctx.rng.uniform(lo.x + 0.2, hi.x - 0.2), ctx.rng.uniform(0.1, 0.5), -0.1))
        _ballistic(ctx, ob, p0, v, start, 2.0, bounce=0.1, spin=6.0, floor=0.02, every=2)


def drop(ctx: Ctx, e: dict, i: int) -> None:
    """Something poured into a pit from above (gravel, sand, stones): pieces fall in a stream
    and land on the rising surface (`target` pit, `material`, `to`: where the pile ends)."""
    from . import props

    cutters = props.PITS.get(e.get("target", ""))
    if not cutters:
        return
    lo, hi = _pit_box(cutters)
    f0 = ctx.frame(e["t"])
    dur = float(e.get("dur", 1.4))
    top = float(e.get("to", lo.z + 0.5))
    m = props._layer_material(e.get("material", "gravel"))
    n = int(e.get("n", 46))
    cx = (lo.x + hi.x) / 2
    for k in range(n):
        start = f0 + round(dur * ctx.fps * k / n)
        ob = _chunk(f"drop{i}.{k}", ctx.rng.uniform(0.02, 0.05), m, ctx.rng)
        _show(ob, start)
        p0 = Vector(
            (
                cx + ctx.rng.uniform(-0.25, 0.25),
                ctx.rng.uniform(0.1, 0.45),
                0.6 + ctx.rng.uniform(0, 0.3),
            )
        )
        v = Vector((ctx.rng.uniform(-0.4, 0.4), 0, -ctx.rng.uniform(0.5, 1.5)))
        floor = lo.z + (top - lo.z) * (k / n)
        _ballistic(ctx, ob, p0, v, start, 2.0, bounce=0.05, spin=4.0, floor=floor, every=2)


def burst(ctx: Ctx, e: dict, i: int) -> None:
    """Something under pressure bursts (a frozen pipe, a tank): a crack opens at `pos`, a spray
    of droplets, then a steady leak."""
    c = ctx.where(e, default_z=0.0)
    color = e.get("color", "#cfeefa")
    crack(ctx, {"t": e["t"], "pos": [c.x, c.y - 0.04, c.z], "wall": True, "size": float(e.get("size", 0.35)),
                "dur": 0.2, "debris": False, "n": 5, "color": "#1d2328"}, i)  # fmt: skip
    f0 = ctx.frame(e["t"])
    m = _mat(color, alpha=0.75, rough=0.05, name=f"spray{i}")
    for k, d in enumerate(_burst_dirs(ctx, int(e.get("n", 40)), up=0.5)):
        ob = shapes.sphere(f"spray{i}.{k}", ctx.rng.uniform(0.008, 0.02), m, c, segments=8, rings=6)
        life = ctx.rng.uniform(0.4, 0.9)
        _show(ob, f0, min(ctx.span, f0 + round(life * ctx.fps)))
        v = Vector((d.x, -abs(d.y) - 0.6, d.z)) * ctx.rng.uniform(1.5, 3.2)
        _ballistic(ctx, ob, c.copy(), v, f0, life, bounce=0.1, spin=0, floor=-50)
    if e.get("leak", True):
        pour(ctx, {"t": e["t"] + 0.2, "pos": [c.x, c.y - 0.05, c.z], "dur": float(e.get("dur", 2.0)),
                   "size": 0.35, "color": color}, 200 + i)  # fmt: skip
    shake(ctx, {"t": e["t"], "amount": 0.02, "dur": 0.35}, i)


EFFECTS = {
    "crack": crack, "debris": debris, "shatter": shatter, "explosion": explosion, "smoke": smoke,
    "fire": fire, "sparks": sparks, "flood": flood, "pour": pour, "rain": rain, "flash": flash,
    "shake": shake, "beam": beam, "split": split, "pop": pop, "vanish": vanish,
    "collapse": collapse, "burst": burst, "dig": dig, "drop": drop,
}  # fmt: skip


def apply(ctx: Ctx, items: list[dict]) -> None:
    for i, e in enumerate(items):
        EFFECTS[e["kind"]](ctx, e, i)
    bpy.context.scene.frame_set(1)
