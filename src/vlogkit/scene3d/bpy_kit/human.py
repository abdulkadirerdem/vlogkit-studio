"""Realistic rigged people from the 3D library (Quaternius Universal Base Characters, CC0), dressed
by the kit itself so no two look alike.

Clothes are cut from the body: the faces a garment covers are chosen by the bone weights (a shirt
= spine, clavicles, upper arms (and forearms for long sleeves); trousers = pelvis, thighs (and
calves); shoes = feet), copied, smoothed (no muscles showing through the fabric) and pushed out
along their normals. They keep the body's weights, so they move with every animation. Skin under
cloth is masked away so it never pokes through.

Spec (the scene.json cast entry, same keys as the toon characters where they overlap):
    {"sex": "male|female", "skin": "light|dark|#hex", "hair": "short|long|buns|buzzed|parted|bald",
     "hair_color": "#hex", "beard": bool, "top": "tshirt|longsleeve|hoodie|tank|coat|suit",
     "shirt": "#hex", "bottom": "jeans|trousers|shorts|skirt", "pants": "#hex",
     "shoes": "#hex", "height": 1.0, "build": 1.0}
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

import bmesh
import bpy

from . import look

LIB = os.environ.get("VK3D_LIB", "")  # path of vk3d_humans.blend (set by the runner)
HAIRS = {
    "short": "Hair_SimpleParted", "parted": "Hair_SimpleParted", "long": "Hair_Long",
    "buns": "Hair_Buns", "bun": "Hair_Buns", "buzzed": "Hair_Buzzed", "bald": None,
}  # fmt: skip
TOPS = {  # garment -> bone groups it covers
    "tshirt": ("spine_01", "spine_02", "spine_03", "clavicle", "upperarm"),
    "tank": ("spine_01", "spine_02", "spine_03"),
    "longsleeve": ("spine_01", "spine_02", "spine_03", "clavicle", "upperarm", "lowerarm"),
    "hoodie": ("spine_01", "spine_02", "spine_03", "clavicle", "upperarm", "lowerarm"),
    "coat": (
        "spine_01",
        "spine_02",
        "spine_03",
        "clavicle",
        "upperarm",
        "lowerarm",
        "pelvis",
        "thigh",
    ),
    "suit": ("spine_01", "spine_02", "spine_03", "clavicle", "upperarm", "lowerarm"),
}
BOTTOMS = {
    "jeans": ("pelvis", "thigh", "calf"),
    "trousers": ("pelvis", "thigh", "calf"),
    "shorts": ("pelvis", "thigh"),
    "skirt": ("pelvis", "thigh"),
}
THICK = {"tshirt": 0.018, "tank": 0.016, "longsleeve": 0.018, "hoodie": 0.028, "coat": 0.032, "suit": 0.022,
         "jeans": 0.009, "trousers": 0.01, "shorts": 0.01, "skirt": 0.03, "shoes": 0.012}  # tops sit over bottoms  # fmt: skip
DEFAULT = {"sex": "male", "skin": "light", "hair": "short", "hair_color": "#3b2a20", "top": "tshirt",
           "shirt": "#e25b45", "bottom": "jeans", "pants": "#35507a", "shoes": "#f2f2f2",
           "height": 1.0, "build": 1.0, "beard": False}  # fmt: skip


@dataclass
class Human:
    name: str
    root: bpy.types.Object  # the armature object (moved and turned like a toon root)
    body: bpy.types.Object
    parts: list = field(default_factory=list)
    spec: dict = field(default_factory=dict)
    height: float = 1.8

    @property
    def joints(self) -> dict:  # compatibility with the toon API (camera targets)
        return {"root": self.root}


_loaded = False


def load_library() -> None:
    """Append everything once per Blender session (collections, actions, images)."""
    global _loaded
    if _loaded:
        return
    if not LIB or not os.path.exists(LIB):
        raise RuntimeError(
            "3B kütüphane yok (vk3d_humans.blend): `vlogkit 3d fetch` ya da Ayarlar > Kurulum"
        )
    colls = (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.actions,
        bpy.data.armatures,
        bpy.data.images,
    )
    before = {(type(x).__name__, x.name) for c in colls for x in c}
    with bpy.data.libraries.load(LIB, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c.startswith(("human_", "hair"))]
        dst.actions = list(src.actions)
        dst.images = list(src.images)
    for a in bpy.data.actions:
        a.use_fake_user = True
    KEEP_NAMES.update({(type(x).__name__, x.name) for c in colls for x in c} - before)
    _loaded = True


KEEP: set[int] = set()
KEEP_NAMES: set[tuple[str, str]] = set()  # library datablocks the per-shot cleanup must not delete

# --------------------------------------------------------------------------- MakeHuman people
# vk3d_people.blend (scripts/build_3d_people.py): MakeHuman bodies (CC0) with real proportions,
# skins, hair and clothes, ARKit face units and visemes as shape keys, and every clip retargeted
# onto them ("mp_<clip>"). Used when the library has it; the Quaternius bodies stay the fallback.
PEOPLE = ""
_people_loaded = False


def people_path() -> str:
    if PEOPLE:
        return PEOPLE if os.path.exists(PEOPLE) else ""
    if LIB:
        p = os.path.join(os.path.dirname(LIB), "vk3d_people.blend")
        return p if os.path.exists(p) else ""
    return ""


def load_people() -> bool:
    global _people_loaded
    if _people_loaded:
        return True
    path = people_path()
    if not path:
        return False
    colls = (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.actions,
             bpy.data.armatures, bpy.data.images)  # fmt: skip
    before = {(type(x).__name__, x.name) for c in colls for x in c}
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = [c for c in src.collections if c.startswith("person_")]
        dst.actions = [a for a in src.actions if a.startswith("mp_")]
    for a in bpy.data.actions:
        if a.name.startswith("mp_"):
            a.use_fake_user = True
    KEEP_NAMES.update({(type(x).__name__, x.name) for c in colls for x in c} - before)
    _people_loaded = True
    return True


def presets() -> dict[str, bpy.types.Object]:
    out = {}
    for c in bpy.data.collections:
        if c.name.startswith("person_"):
            rig = next((o for o in c.objects if o.type == "ARMATURE"), None)
            if rig is not None:
                out[c.name[len("person_") :]] = rig
    return out


def pick_preset(name: str, s: dict, raw: dict) -> str | None:
    """The body that fits the cast entry: an explicit `person`, else sex, age (kid / old from
    the toon keys), build (big -> heavy), skin (dark), outfit (suit)."""
    have = presets()
    if not have:
        return None
    if raw.get("person") in have:
        return raw["person"]
    sex = "f" if s.get("sex") == "female" else "m"
    want = []
    if float(s.get("height", 1.0)) < 0.85:
        want.append("kid")
    if (
        s.get("hair_color", "").lower() in ("#b9b6b0", "#c8c8c8", "#d9d9d9", "#9e9e9e")
        or raw.get("body") == "old"
    ):
        want.append("old")
    if float(s.get("build", 1.0)) > 1.1:
        want.append("heavy")
    if s.get("skin") == "dark":
        want.append("dark")
    if s.get("top") == "suit":
        want.append("suit")
    mine = sorted(k for k in have if k.startswith(sex + "_"))
    for w in want:
        hit = [k for k in mine if w in k]
        if hit:
            return hit[sum(map(ord, name)) % len(hit)]
    plain = [k for k in mine if not any(t in k for t in ("kid", "old", "heavy", "suit"))] or mine
    return plain[sum(map(ord, name)) % len(plain)] if plain else None


# t-shirt outfits whose top is the upper part of the texture (the tee above, jeans/shorts below):
# the cast's shirt colour is put on the tee only. value: the tee's own colour (None = white)
TEES = {  # outfit -> (the tee's own colour or None for white, extra tee areas (u0, u1, v0, v1))
    "male_casualsuit02": ("#3b6db3", [(0.765, 1.0, 0.0, 0.42)]),
    "male_casualsuit04": ("#3b6db3", [(0.765, 1.0, 0.0, 0.42)]),
    "female_casualsuit01": ("#3b6db3", [(0.74, 1.0, 0.0, 0.47)]),
    "female_casualsuit02": ("#3b6db3", [(0.74, 1.0, 0.0, 0.47)]),
    "male_casualsuit06": (None, []),
}  # fmt: skip


def _recolor_tee(ob, color: str) -> None:
    import colorsys

    for slot in ob.material_slots:
        m = slot.material
        if m is None or not m.use_nodes:
            continue
        nt = m.node_tree
        tex = next((n for n in nt.nodes if n.type == "TEX_IMAGE" and n.image
                    and "diffuse" in n.image.name.lower()
                    and any(n.image.name.lower().startswith(k) for k in TEES)), None)  # fmt: skip
        if tex is None:
            continue
        key = next(k for k in TEES if tex.image.name.lower().startswith(k))
        if ob.users > 1 or m.users > 1:
            slot.material = m = m.copy()
            nt = m.node_tree
            tex = next(
                n
                for n in nt.nodes
                if n.type == "TEX_IMAGE" and n.image and n.image.name == tex.image.name
            )
        links = [lk for lk in nt.links if lk.from_node == tex and lk.from_socket.name == "Color"]
        want = look.hex_rgba(color)[:3]
        base, rects = TEES[key]
        if base:  # a coloured tee: turn its hue, keep the fabric's light and shade
            hb, sb, vb = colorsys.rgb_to_hsv(*look.hex_rgba(base)[:3])
            hw, sw, vw = colorsys.rgb_to_hsv(*want)
            hsv = nt.nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Hue"].default_value = (0.5 + hw - hb) % 1.0
            hsv.inputs["Saturation"].default_value = min(2.0, sw / max(0.05, sb))
            hsv.inputs["Value"].default_value = min(2.5, vw / max(0.05, vb))
            nt.links.new(tex.outputs["Color"], hsv.inputs["Color"])
            new = hsv.outputs["Color"]
        else:  # a white tee: dye it
            mul = nt.nodes.new("ShaderNodeMix")
            mul.data_type, mul.blend_type = "RGBA", "MULTIPLY"
            mul.inputs["Factor"].default_value = 1.0
            nt.links.new(tex.outputs["Color"], mul.inputs[6])
            mul.inputs[7].default_value = (*want, 1.0)
            new = mul.outputs[2]
        # only on the tee: the upper part of the texture (V above ~0.6)
        uv = nt.nodes.new("ShaderNodeTexCoord")
        sep = nt.nodes.new("ShaderNodeSeparateXYZ")
        nt.links.new(uv.outputs["UV"], sep.inputs[0])
        mr = nt.nodes.new("ShaderNodeMapRange")
        mr.inputs["From Min"].default_value, mr.inputs["From Max"].default_value = 0.56, 0.6
        nt.links.new(sep.outputs["Y"], mr.inputs["Value"])
        mask = mr.outputs["Result"]
        for u0, u1, v0, v1 in rects:  # the sleeves, laid out elsewhere in the texture
            cells = []
            for axis, lo, hi in (("X", u0, u1), ("Y", v0, v1)):
                a_ = nt.nodes.new("ShaderNodeMath")
                a_.operation = "GREATER_THAN"
                nt.links.new(sep.outputs[axis], a_.inputs[0])
                a_.inputs[1].default_value = lo
                b_ = nt.nodes.new("ShaderNodeMath")
                b_.operation = "LESS_THAN"
                nt.links.new(sep.outputs[axis], b_.inputs[0])
                b_.inputs[1].default_value = hi
                c_ = nt.nodes.new("ShaderNodeMath")
                c_.operation = "MULTIPLY"
                nt.links.new(a_.outputs[0], c_.inputs[0])
                nt.links.new(b_.outputs[0], c_.inputs[1])
                cells.append(c_.outputs[0])
            box = nt.nodes.new("ShaderNodeMath")
            box.operation = "MULTIPLY"
            nt.links.new(cells[0], box.inputs[0])
            nt.links.new(cells[1], box.inputs[1])
            mx = nt.nodes.new("ShaderNodeMath")
            mx.operation = "MAXIMUM"
            nt.links.new(mask, mx.inputs[0])
            nt.links.new(box.outputs[0], mx.inputs[1])
            mask = mx.outputs[0]
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        nt.links.new(mask, mix.inputs["Factor"])
        nt.links.new(tex.outputs["Color"], mix.inputs[6])
        nt.links.new(new, mix.inputs[7])
        for lk in links:
            nt.links.new(mix.outputs[2], lk.to_socket)


def build_person(name: str, preset: str, s: dict) -> Human:
    src = bpy.data.collections[f"person_{preset}"]
    coll = bpy.context.collection
    mapping = {}
    for o in src.objects:
        c = o.copy()
        if o.data is not None:
            c.data = o.data.copy()
        c.name = f"{name}.{o.name.split('.', 1)[-1]}"
        coll.objects.link(c)
        mapping[o] = c
    for o, c in mapping.items():
        if o.parent in mapping:
            c.parent = mapping[o.parent]
        for m in c.modifiers:
            if m.type == "ARMATURE" and m.object in mapping:
                m.object = mapping[m.object]
    arm = next(c for c in mapping.values() if c.type == "ARMATURE")
    arm.name = f"{name}.rig"
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.rotation_mode = "QUATERNION"
        pb.location, pb.scale, pb.rotation_quaternion = (0, 0, 0), (1, 1, 1), (1, 0, 0, 0)
    parts = [c for c in mapping.values() if c is not arm]
    body = next((c for c in parts if c.name.endswith(".body")), parts[0])
    head = arm.data.bones.get("head") or arm.data.bones.get("Head")
    height = (head.tail_local.z if head else 1.75) * arm.scale.z
    k = float(s.get("height", 1.0)) if preset.split("_")[1] != "kid" else 1.0
    arm.scale = (k, k, k)
    arm.rotation_mode = "XYZ"
    arm["vk_mpfb"] = True
    if s.get("_shirt_given"):
        for o in parts:
            if o.type == "MESH":
                _recolor_tee(o, s["shirt"])
    return Human(name, arm, body, parts, s, height * k)


def _copy_hierarchy(sex: str, name: str) -> tuple[bpy.types.Object, list[bpy.types.Object]]:
    src = bpy.data.collections[f"human_{sex}"]
    coll = bpy.context.collection
    mapping = {}
    for o in src.objects:
        c = o.copy()
        if o.data is not None:
            c.data = o.data.copy()
        c.name = f"{name}.{o.name.split('_', 1)[1]}"
        coll.objects.link(c)
        mapping[o] = c
    for o, c in mapping.items():
        if o.parent in mapping:
            c.parent = mapping[o.parent]
        for m in c.modifiers:
            if m.type == "ARMATURE" and m.object in mapping:
                m.object = mapping[m.object]
    arm = next(c for c in mapping.values() if c.type == "ARMATURE")
    return arm, [c for c in mapping.values() if c is not arm]


def _tint(ob: bpy.types.Object, color: str, mix: float = 1.0) -> None:
    """Multiply the object's base colour (texture or flat) by `color`."""
    for slot in ob.material_slots:
        if not slot.material:
            continue
        m = slot.material.copy()
        slot.material = m
        nt = m.node_tree
        p = next((n for n in nt.nodes if n.type == "BSDF_PRINCIPLED"), None)
        if not p:
            continue
        link = next((lk for lk in nt.links if lk.to_socket == p.inputs["Base Color"]), None)
        mul = nt.nodes.new("ShaderNodeMix")
        mul.data_type = "RGBA"
        mul.blend_type = "MULTIPLY"
        mul.inputs["Factor"].default_value = mix
        if link:
            nt.links.new(link.from_socket, mul.inputs[6])
        else:
            mul.inputs[6].default_value = p.inputs["Base Color"].default_value
        mul.inputs[7].default_value = look.hex_rgba(color)
        nt.links.new(mul.outputs[2], p.inputs["Base Color"])


def _groups_weight(ob: bpy.types.Object, prefixes: tuple[str, ...]) -> list[float]:
    """Per vertex: total weight of the vertex groups whose bone name starts with a prefix."""
    idx = [g.index for g in ob.vertex_groups if g.name.startswith(prefixes)]
    out = [0.0] * len(ob.data.vertices)
    for v in ob.data.vertices:
        out[v.index] = sum(g.weight for g in v.groups if g.group in idx)
    return out


# straight cuts, per garment: (bone, t along the bone 0=head..1=tail, keep "head"|"tail" side)
# plus the waist/hem/neck levels as heights relative to the pelvis bone's head (m)
CUTS = {
    "tshirt": {"limb": [("upperarm", 0.55, "head")], "hem": 0.07, "neck": True},
    "tank": {"limb": [("upperarm", 0.02, "head")], "hem": 0.07, "neck": True},
    "longsleeve": {"limb": [("lowerarm", 0.93, "head")], "hem": 0.07, "neck": True},
    "hoodie": {"limb": [("lowerarm", 0.95, "head")], "hem": 0.02, "neck": True},
    "suit": {"limb": [("lowerarm", 0.95, "head")], "hem": -0.04, "neck": True},
    "coat": {
        "limb": [("lowerarm", 0.95, "head"), ("thigh", 0.05, "head")],
        "hem": -0.16,
        "neck": True,
    },
    "jeans": {"limb": [("calf", 0.94, "head")], "waist": 0.13},
    "trousers": {"limb": [("calf", 0.96, "head")], "waist": 0.13},
    "shorts": {"limb": [("thigh", 0.62, "head")], "waist": 0.13},
    "skirt": {"limb": [("thigh", 0.5, "head")], "waist": 0.13},
    "shoes": {"limb": [("calf", 0.985, "tail")]},
}


def _bone_pt(arm, body, bone: str, t: float):
    b = arm.data.bones[bone]
    inv = body.matrix_world.inverted()
    head = inv @ (arm.matrix_world @ b.head_local)
    tail = inv @ (arm.matrix_world @ b.tail_local)
    return head.lerp(tail, t), (tail - head).normalized()


def _garment(
    body: bpy.types.Object,
    arm,
    name: str,
    prefixes: tuple[str, ...],
    kind: str,
    color: str,
    extra_mask: list[bool] | None = None,
) -> tuple[bpy.types.Object, set[int]]:
    from mathutils import Vector

    bpy.context.view_layer.update()
    grow = {"top": ("pelvis", "lowerarm", "neck_01"), "bottom": ("spine_01", "calf", "foot")}
    extra = grow["top"] if kind in TOPS else grow["bottom"] if kind in BOTTOMS else ()
    w = _groups_weight(body, tuple(prefixes) + extra)
    me = body.data
    faces = [f.index for f in me.polygons if sum(w[v] for v in f.vertices) / len(f.vertices) > 0.3]
    keep = set(faces)
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    # glTF splits vertices along UV seams: weld them, or smoothing tears the garment open there
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    # straight hems, cuffs and waists: cut each limb with a plane across its bone, and the torso
    # with level planes (only that part's faces, so an infinite plane never touches the rest)
    deform = bm.verts.layers.deform.active
    names = {g.index: g.name for g in body.vertex_groups}

    def side_faces(suffix: str | None, limb_bones: tuple[str, ...] | None):
        out = []
        for f in bm.faces:
            tot: dict[str, float] = {}
            for v in f.verts:
                for gi, wt in v[deform].items():
                    tot[names[gi]] = tot.get(names[gi], 0) + wt
            top = max(tot, key=tot.get) if tot else ""
            if limb_bones is None or (
                top.startswith(limb_bones) and (suffix is None or top.endswith(suffix))
            ):
                out.append(f)
        return out

    def cut(geom_faces, co, no):
        geom = (
            list({e for f in geom_faces for e in f.edges})
            + list({v for f in geom_faces for v in f.verts})
            + list(geom_faces)
        )
        if geom_faces:
            bmesh.ops.bisect_plane(bm, geom=geom, plane_co=co, plane_no=no, clear_inner=True)

    rule = CUTS.get(kind, {})
    chains = {"upperarm": ("upperarm", "lowerarm", "hand"), "lowerarm": ("lowerarm", "hand"),
              "thigh": ("thigh", "calf", "foot", "ball"), "calf": ("calf", "foot", "ball")}  # fmt: skip
    for bone, t, keep_side in rule.get("limb", []):
        for sfx in ("_l", "_r"):
            co, d = _bone_pt(arm, body, bone + sfx, t)
            no = -d if keep_side == "head" else d
            cut(side_faces(sfx, chains.get(bone, (bone,))), co, no)
    pelvis, _ = _bone_pt(arm, body, "pelvis", 0.0)
    up = (body.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))).normalized()
    if rule.get("hem") is not None:
        cut(side_faces(None, ("spine", "pelvis", "thigh")), pelvis + up * rule["hem"], up)
    if rule.get("waist") is not None:
        cut(list(bm.faces), pelvis + up * rule["waist"], -up)
    if rule.get("neck"):
        neck, _ = _bone_pt(arm, body, "neck_01", 0.0)
        cut(side_faces(None, ("neck", "Head")), neck + up * 0.005, -up)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context="VERTS")
    border = {v.index for v in bm.verts if v.is_boundary}
    new = bpy.data.meshes.new(name)
    bm.to_mesh(new)
    bm.free()
    ob = bpy.data.objects.new(name, new)
    bpy.context.collection.objects.link(ob)
    for g in body.vertex_groups:
        ob.vertex_groups.new(name=g.name)
    ob.parent = arm
    ob.matrix_world = body.matrix_world.copy()
    for p in new.polygons:
        p.use_smooth = True
    inner = ob.vertex_groups.new(name="vk_inner")  # hems and cuffs stay where the body is
    inner.add([v.index for v in new.vertices if v.index not in border], 1.0, "REPLACE")
    sm = ob.modifiers.new("smooth", "SMOOTH")  # cloth hides the muscles
    sm.factor, sm.iterations = 0.75, 8 if kind not in ("shoes",) else 4
    sm.vertex_group = "vk_inner"
    dp = ob.modifiers.new("loose", "DISPLACE")
    dp.direction, dp.strength, dp.mid_level = "NORMAL", THICK.get(kind, 0.01), 0.0
    so = ob.modifiers.new("thick", "SOLIDIFY")
    so.thickness, so.offset = 0.006 if kind != "shoes" else 0.02, 1.0
    am = ob.modifiers.new("armature", "ARMATURE")
    am.object = arm
    rough = 0.9 if kind in ("jeans", "hoodie", "tshirt", "longsleeve", "tank", "shorts") else 0.55
    ob.data.materials.append(_fabric(color, rough, denim=kind == "jeans"))
    # the body under the garment hides, except near its edges (a moving hem never shows a hole)
    from mathutils.kdtree import KDTree

    gv = [v.co.copy() for v in new.vertices]
    gb = [new.vertices[i].co.copy() for i in border]
    kd_all, kd_edge = KDTree(len(gv)), KDTree(max(1, len(gb)))
    for i, c in enumerate(gv):
        kd_all.insert(c, i)
    for i, c in enumerate(gb):
        kd_edge.insert(c, i)
    kd_all.balance()
    kd_edge.balance()
    hide = set()
    for v in me.vertices:
        _, _, d = kd_all.find(v.co)
        if d is not None and d < 0.012 and (not gb or kd_edge.find(v.co)[2] > 0.04):
            hide.add(v.index)
    return ob, hide


def _sneakers(arm, body, name: str, color: str) -> list[bpy.types.Object]:
    """A sneaker per foot: upper, white sole, toe cap and a lace panel, carried by the foot bone."""
    from mathutils import Matrix, Vector

    from . import shapes

    bpy.context.view_layer.update()
    upper = _fabric(color, 0.6)
    sole = look.mat("#f4f2ee", rough=0.7)
    lace = look.mat("#fafafa", rough=0.8)
    out = []
    for sfx in ("_l", "_r"):
        bone = arm.data.bones[f"foot{sfx}"]
        ball = arm.data.bones.get(f"ball{sfx}")
        heel = arm.matrix_world @ bone.head_local
        toe = arm.matrix_world @ (ball.tail_local if ball else bone.tail_local)
        fwd = Vector((toe.x - heel.x, toe.y - heel.y, 0)).normalized()
        length = (Vector((toe.x, toe.y, 0)) - Vector((heel.x, heel.y, 0))).length + 0.09
        k = arm.matrix_world.to_scale().x
        root = shapes.empty(f"{name}.shoe{sfx}", (0, 0, 0))
        c = Vector((heel.x, heel.y, 0)) + fwd * (length / 2 - 0.06)
        ang = math.atan2(fwd.x, -fwd.y)
        shapes.rbox(
            f"{name}.shoe{sfx}.upper",
            (0.105 * k, length, 0.085 * k),
            upper,
            (0, 0.0, 0.055 * k),
            0.04 * k,
            root,
        )
        shapes.rbox(
            f"{name}.shoe{sfx}.sole",
            (0.115 * k, length + 0.012, 0.032 * k),
            sole,
            (0, 0, 0.016 * k),
            0.012 * k,
            root,
        )
        shapes.rbox(
            f"{name}.shoe{sfx}.toe",
            (0.1 * k, 0.07, 0.05 * k),
            sole,
            (0, -length / 2 + 0.035, 0.03 * k),
            0.02 * k,
            root,
        )
        shapes.rbox(
            f"{name}.shoe{sfx}.lace",
            (0.05 * k, length * 0.4, 0.012 * k),
            lace,
            (0, -length * 0.05, 0.098 * k),
            0.005 * k,
            root,
        )
        root.matrix_world = Matrix.Translation(c) @ Matrix.Rotation(ang + math.pi, 4, "Z")
        mw = root.matrix_world.copy()
        root.parent = arm
        root.parent_type = "BONE"
        root.parent_bone = f"foot{sfx}"
        root.matrix_world = mw
        out.append(root)
    return out


def _fabric(color: str, rough: float, denim: bool = False) -> bpy.types.Material:
    """Cloth: a fine noise in the colour and the bump so it reads as fabric, not plastic."""
    m = bpy.data.materials.new(f"cloth_{color.lstrip('#')}")
    m.use_nodes = True
    nt = m.node_tree
    p = nt.nodes["Principled BSDF"]
    p.inputs["Roughness"].default_value = rough
    if "Sheen Weight" in p.inputs:
        p.inputs["Sheen Weight"].default_value = 0.3
    noise = nt.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 900.0 if not denim else 1400.0
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    base = look.hex_rgba(color)
    ramp.color_ramp.elements[0].color = (*(c * 0.86 for c in base[:3]), 1)
    ramp.color_ramp.elements[1].color = base
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], p.inputs["Base Color"])
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    nt.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], p.inputs["Normal"])
    m.diffuse_color = base
    return m


def build(name: str, spec: dict | None = None) -> Human:
    load_library()
    s = {**DEFAULT, **_from_toon(spec or {})}
    raw = dict(spec or {})
    if not raw.get("classic") and load_people():
        preset = pick_preset(name, s, raw)
        if preset:
            return build_person(name, preset, {**s, "_shirt_given": "shirt" in raw})
    sex = "female" if s.get("sex") == "female" else "male"
    arm, parts = _copy_hierarchy(sex, name)
    arm.name = f"{name}.rig"
    # build on the rest pose whatever the library file was saved in (shoes and garments are
    # placed from the posed bones)
    if arm.animation_data:
        arm.animation_data.action = None
    for pb in arm.pose.bones:
        pb.location, pb.scale = (0, 0, 0), (1, 1, 1)
        pb.rotation_quaternion, pb.rotation_euler = (1, 0, 0, 0), (0, 0, 0)
    bpy.context.view_layer.update()
    body = next(o for o in parts if o.type == "MESH" and "Super" in o.name)
    eyebrows = next((o for o in parts if "Eyebrows" in o.name), None)
    # skin: the light or dark texture, tinted
    skin = s.get("skin", "light")
    if skin in ("dark", "light"):
        img_name = {
            "male": f"T_Superhero_Male_{'Dark' if skin == 'dark' else 'Ligh'}",
            "female": f"T_Superhero_Female_{'Dark' if skin == 'dark' else 'Light'}_BaseColor",
        }[sex]
        img = bpy.data.images.get(img_name)
        if img:
            for slot in body.material_slots:
                slot.material = slot.material.copy()
                for n in slot.material.node_tree.nodes:
                    if (
                        n.type == "TEX_IMAGE"
                        and "Normal" not in (n.image.name if n.image else "")
                        and "Rough" not in (n.image.name if n.image else "")
                    ):
                        n.image = img
    else:
        _tint(body, skin, 1.0)
    # the base bodies are "superheroes": the normal map carries six-pack and bulging muscles;
    # a quarter of it keeps the skin's detail and loses the bodybuilder
    for slot in body.material_slots:
        if slot.material is None or not slot.material.use_nodes:
            continue
        if slot.material.users > 1:
            slot.material = slot.material.copy()
        for n in slot.material.node_tree.nodes:
            if n.type == "NORMAL_MAP":
                n.inputs["Strength"].default_value = float(s.get("muscle", 0.3))
    if eyebrows:
        _tint(eyebrows, s["hair_color"])
    # hair
    hair_key = HAIRS.get(s.get("hair", "short"), "Hair_SimpleParted")
    if hair_key:
        src = bpy.data.objects.get(hair_key)
        if src:
            h = src.copy()
            h.data = src.data.copy()
            h.name = f"{name}.hair"
            bpy.context.collection.objects.link(h)
            h.parent = arm
            h.matrix_world = body.matrix_world.copy()
            if not any(m.type == "ARMATURE" for m in h.modifiers):
                h.modifiers.new("armature", "ARMATURE")
            for m in h.modifiers:
                if m.type == "ARMATURE":
                    m.object = arm
            _tint(h, s["hair_color"])
            parts.append(h)
    if s.get("beard") and bpy.data.objects.get("Hair_Beard"):
        src = bpy.data.objects["Hair_Beard"]
        b = src.copy()
        b.data = src.data.copy()
        bpy.context.collection.objects.link(b)
        b.parent = arm
        b.matrix_world = body.matrix_world.copy()
        for m in b.modifiers:
            if m.type == "ARMATURE":
                m.object = arm
        _tint(b, s["hair_color"])
        parts.append(b)
    # clothes
    hidden: set[int] = set()
    top, bottom = s.get("top", "tshirt"), s.get("bottom", "jeans")
    if top in TOPS:
        g, cov = _garment(body, arm, f"{name}.top", TOPS[top], top, s["shirt"])
        parts.append(g)
        hidden |= cov
    if bottom in BOTTOMS:
        g, cov = _garment(body, arm, f"{name}.bottom", BOTTOMS[bottom], bottom, s["pants"])
        parts.append(g)
        hidden |= cov
    parts += _sneakers(arm, body, name, s["shoes"])
    fw = _groups_weight(body, ("foot", "ball"))
    hidden |= {i for i, x in enumerate(fw) if x > 0.5}
    if hidden:
        vg = body.vertex_groups.new(name="vk_covered")
        vg.add(sorted(hidden), 1.0, "REPLACE")
        mk = body.modifiers.new("hide_under_cloth", "MASK")
        mk.vertex_group, mk.invert_vertex_group = "vk_covered", True
        body.modifiers.move(len(body.modifiers) - 1, 0)
    # size: height and build (bone scale keeps the proportions of the animations)
    k = float(s.get("height", 1.0))
    arm.scale = (k, k, k)
    # ordinary arms, not a superhero's: thinner across, the same length (animations unchanged)
    arm_k = float(s.get("arms", 0.86))
    for bn in ("upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r"):
        pb = arm.pose.bones.get(bn)
        if pb:
            pb.scale = (arm_k, 1.0, arm_k)
    build_k = float(s.get("build", 1.0))
    if abs(build_k - 1.0) > 1e-3:
        for bn in ("spine_01", "spine_02", "spine_03", "pelvis"):
            pb = arm.pose.bones.get(bn)
            if pb:
                pb.scale = (build_k, 1.0, build_k)
    arm.rotation_mode = "XYZ"
    return Human(name, arm, body, parts, s, 1.82 * k)


def _from_toon(spec: dict) -> dict:
    """The toon cast keys (body, outfit, mustache...) mean the same thing on a real person."""
    s = dict(spec)
    body = s.pop("body", None)
    if body == "kid":
        s.setdefault("height", 0.74)
    elif body == "big":
        s.setdefault("build", 1.22)
    elif body == "tall":
        s.setdefault("height", 1.08)
    elif body == "old":
        s.setdefault("hair_color", "#b9b6b0")
    outfit = s.pop("outfit", None)
    if outfit in ("lab", "doctor", "chef"):
        s.setdefault("top", "coat")
        s.setdefault("shirt", "#f5f5f2")
    elif outfit == "suit":
        s.setdefault("top", "suit")
        s.setdefault("bottom", "trousers")
        s.setdefault("pants", s.get("shirt", "#2d3340"))
    if s.pop("mustache", False):
        s["beard"] = True
    if s.get("sleeves") == "long" and s.get("top", "tshirt") == "tshirt":
        s["top"] = "longsleeve"
    if s.get("hair") in ("curly", "hood", "cap"):
        s["hair"] = "short"
    for k in ("sleeves", "glasses", "hood_color", "cap_color", "style"):
        s.pop(k, None)
    return s


def is_human_spec(spec: dict) -> bool:
    return spec.get("style", "realistic") == "realistic"


R = math.radians
