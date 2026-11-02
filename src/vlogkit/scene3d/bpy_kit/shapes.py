"""Mesh building blocks made with bmesh (no operators, so they work headless on any OS).

Everything is soft: boxes get a rounded bevel, spheres are smooth shaded. Units are metres; the
characters face -Y (towards a camera standing on -Y looking at +Y).
"""

from __future__ import annotations

import contextlib
import math

import bmesh
import bpy
from mathutils import Matrix, Vector


def _link(
    ob: bpy.types.Object, parent: bpy.types.Object | None, collection=None
) -> bpy.types.Object:
    (collection or bpy.context.collection).objects.link(ob)
    if parent is not None:
        ob.parent = parent
    return ob


def _finish(me: bpy.types.Mesh, smooth: bool = True) -> None:
    for p in me.polygons:
        p.use_smooth = smooth
    me.update()


def empty(name: str, loc=(0, 0, 0), parent=None, collection=None) -> bpy.types.Object:
    ob = bpy.data.objects.new(name, None)
    ob.empty_display_size = 0.05
    ob.location = loc
    return _link(ob, parent, collection)


def rbox(
    name: str,
    size,
    material,
    loc=(0, 0, 0),
    radius: float = 0.04,
    parent=None,
    segments: int = 4,
    collection=None,
) -> bpy.types.Object:
    """A box with rounded edges (bevel modifier), `size` = full (x, y, z)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    _finish(me, smooth=False)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    r = min(radius, min(size) * 0.49)
    if r > 0:
        bev = ob.modifiers.new("bevel", "BEVEL")
        bev.width = r
        bev.segments = segments
        bev.limit_method = "NONE"
        bev.harden_normals = False
        for p in me.polygons:
            p.use_smooth = True
    ob.data.materials.append(material)
    return _link(ob, parent, collection)


def sphere(
    name: str,
    radius: float,
    material,
    loc=(0, 0, 0),
    scale=(1, 1, 1),
    parent=None,
    segments: int = 32,
    rings: int = 16,
    collection=None,
) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=rings, radius=radius)
    bm.to_mesh(me)
    bm.free()
    _finish(me)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.scale = scale
    ob.data.materials.append(material)
    return _link(ob, parent, collection)


def cap(
    name: str,
    radius: float,
    material,
    cut_z: float,
    loc=(0, 0, 0),
    scale=(1, 1, 1),
    parent=None,
    front_cut: float | None = None,
    thickness: float = 0.0,
    collection=None,
) -> bpy.types.Object:
    """A sphere with everything below `cut_z` (local) removed: hair, a hood, a dome. With
    `front_cut` the face side below that height is also cut away (a hairline)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=40, v_segments=20, radius=radius)
    gone = [
        v
        for v in bm.verts
        if v.co.z < cut_z
        or (front_cut is not None and v.co.y < -radius * 0.35 and v.co.z < front_cut)
    ]
    bmesh.ops.delete(bm, geom=gone, context="VERTS")
    bm.to_mesh(me)
    bm.free()
    _finish(me)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.scale = scale
    ob.data.materials.append(material)
    if thickness:
        s = ob.modifiers.new("solid", "SOLIDIFY")
        s.thickness = thickness
        s.offset = -1
    return _link(ob, parent, collection)


def cylinder(
    name: str,
    radius: float,
    depth: float,
    material,
    loc=(0, 0, 0),
    rot=(0, 0, 0),
    parent=None,
    segments: int = 32,
    bevel: float = 0.0,
    radius2: float | None = None,
    collection=None,
) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(
        bm,
        cap_ends=True,
        cap_tris=False,
        segments=segments,
        radius1=radius,
        radius2=radius if radius2 is None else radius2,
        depth=depth,
    )
    bm.to_mesh(me)
    bm.free()
    _finish(me, smooth=True)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    ob.data.materials.append(material)
    if bevel:
        b = ob.modifiers.new("bevel", "BEVEL")
        b.width = bevel
        b.segments = 3
        b.limit_method = "ANGLE"
    return _link(ob, parent, collection)


def plane(
    name: str, size, material, loc=(0, 0, 0), rot=(0, 0, 0), parent=None, collection=None
) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
    bmesh.ops.scale(bm, vec=Vector((size[0], size[1], 1)), verts=bm.verts)
    bm.to_mesh(me)
    bm.free()
    _finish(me, smooth=False)
    ob = bpy.data.objects.new(name, me)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    ob.data.materials.append(material)
    return _link(ob, parent, collection)


def curve(
    name: str,
    points,
    material,
    bevel: float = 0.012,
    loc=(0, 0, 0),
    parent=None,
    cyclic: bool = False,
    collection=None,
) -> bpy.types.Object:
    """A smooth tube through `points` (a mouth line, a brow, a cable)."""
    cu = bpy.data.curves.new(name, "CURVE")
    cu.dimensions = "3D"
    cu.bevel_depth = bevel
    cu.bevel_resolution = 4
    cu.use_fill_caps = True
    sp = cu.splines.new("NURBS")
    sp.points.add(len(points) - 1)
    for p, co in zip(sp.points, points, strict=True):
        p.co = (*co, 1.0)
    sp.order_u = min(4, len(points))
    sp.use_endpoint_u = not cyclic
    sp.use_cyclic_u = cyclic
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.data.materials.append(material)
    return _link(ob, parent, collection)


def text(
    name: str,
    body: str,
    material,
    size: float = 0.3,
    loc=(0, 0, 0),
    rot=(90, 0, 0),
    extrude: float = 0.01,
    align: str = "CENTER",
    font_path: str | None = None,
    parent=None,
    collection=None,
) -> bpy.types.Object:
    """3D text in the scene (signs, newspaper headlines, labels on things)."""
    cu = bpy.data.curves.new(name, "FONT")
    cu.body = body
    cu.size = size
    cu.extrude = extrude
    cu.align_x = align
    cu.align_y = "CENTER"
    if font_path:
        with contextlib.suppress(RuntimeError):
            cu.font = bpy.data.fonts.load(font_path, check_existing=True)
    ob = bpy.data.objects.new(name, cu)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    ob.data.materials.append(material)
    return _link(ob, parent, collection)


def look_at(ob: bpy.types.Object, target) -> None:
    bpy.context.view_layer.update()  # matrix_world is stale right after setting .location
    d = Vector(target) - ob.matrix_world.translation
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()


def apply_matrix(ob: bpy.types.Object, m: Matrix) -> None:
    ob.matrix_world = m @ ob.matrix_world
