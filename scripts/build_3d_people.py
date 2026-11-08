"""Build the people library (vk3d_people.blend) with MakeHuman / MPFB2. Developer tool.

    BLENDER_USER_RESOURCES=DEV_PROFILE blender -b --addons bl_ext.user_default.mpfb \\
        -P scripts/build_3d_people.py -- HUMANS.blend OUT.blend

DEV_PROFILE is a Blender profile of its own (not the user's) with the MPFB 2.0.18 extension
(extensions.blender.org, GPL code, only on the developer machine) and, in its MPFB user data,
the CC0 asset packs: makehuman_system_assets_cc0, faceunits01 (ARKit face units), visemes02 (Meta
visemes), from static.makehumancommunity.org. Nothing GPL ends up in the file: the meshes,
textures, rigs and shape keys are CC0 assets.

HUMANS.blend is the motion library (Quaternius UAL "ual_*" and Mesh2Motion "m2m_*" actions on its
male_Armature): every clip is retargeted once onto a reference MakeHuman body ("mp_<clip>"),
direction-matched for the arms (T-pose clips on A-pose bodies, scripts/retarget.py).

The file holds, per preset, a collection "person_<id>": the armature ("<id>.rig", MPFB
game_engine rig, quaternion rotations), the body ("<id>.body") with 52 ARKit face units and 15
visemes as shape keys, eyes, eyebrows, eyelashes, teeth, tongue, hair, clothes and shoes, the shape
keys also on every part that follows the face. Textures are packed; clothes and hair at 1K.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retarget

# id -> phenotype, skin, hair, eyebrows, clothes
PRESETS = {
    "m_young": ({"gender": 1.0, "age": 0.5, "muscle": 0.5, "weight": 0.5, "height": 0.55},
                "young_caucasian_male", "short02", "eyebrow001", ["male_casualsuit01", "shoes01"]),
    "m_young_slim": ({"gender": 1.0, "age": 0.45, "muscle": 0.45, "weight": 0.35, "height": 0.6},
                     "young_caucasian_male2", "short04", "eyebrow003", ["male_casualsuit03", "shoes02"]),
    "m_young_dark": ({"gender": 1.0, "age": 0.5, "muscle": 0.55, "weight": 0.5, "height": 0.55},
                     "young_african_male", "afro01", "eyebrow002", ["male_casualsuit02", "shoes01"]),
    "m_mid": ({"gender": 1.0, "age": 0.68, "muscle": 0.5, "weight": 0.6, "height": 0.5},
              "middleage_caucasian_male", "short01", "eyebrow004", ["male_casualsuit04", "shoes03"]),
    "m_mid_heavy": ({"gender": 1.0, "age": 0.7, "muscle": 0.4, "weight": 0.85, "height": 0.45},
                    "middleage_caucasian_male", "short03", "eyebrow005", ["male_worksuit01", "shoes03"]),
    "m_old": ({"gender": 1.0, "age": 0.9, "muscle": 0.35, "weight": 0.6, "height": 0.4},
              "old_caucasian_male", "short01", "eyebrow006", ["male_casualsuit05", "shoes04"]),
    "m_suit": ({"gender": 1.0, "age": 0.62, "muscle": 0.5, "weight": 0.55, "height": 0.55},
               "middleage_caucasian_male", "short02", "eyebrow001", ["male_elegantsuit01", "shoes05"]),
    "m_kid": ({"gender": 1.0, "age": 0.2, "muscle": 0.5, "weight": 0.45, "height": 0.5},
              "young_caucasian_male", "short04", "eyebrow001", ["male_casualsuit06", "shoes01"]),
    "f_young": ({"gender": 0.0, "age": 0.5, "muscle": 0.45, "weight": 0.45, "height": 0.5},
                "young_caucasian_female", "ponytail01", "eyebrow008", ["female_casualsuit01", "shoes02"]),
    "f_young_long": ({"gender": 0.0, "age": 0.48, "muscle": 0.45, "weight": 0.4, "height": 0.55},
                     "young_caucasian_female2", "long01", "eyebrow009", ["female_casualsuit02", "shoes06"]),
    "f_young_asian": ({"gender": 0.0, "age": 0.5, "muscle": 0.45, "weight": 0.42, "height": 0.45},
                      "young_asian_female", "bob01", "eyebrow010", ["female_sportsuit01", "shoes02"]),
    "f_mid": ({"gender": 0.0, "age": 0.68, "muscle": 0.4, "weight": 0.6, "height": 0.5},
              "middleage_caucasian_female", "bob02", "eyebrow011", ["female_elegantsuit01", "shoes06"]),
    "f_old": ({"gender": 0.0, "age": 0.9, "muscle": 0.3, "weight": 0.6, "height": 0.42},
              "old_caucasian_female", "bob01", "eyebrow012", ["female_casualsuit01", "shoes04"]),
    "f_kid": ({"gender": 0.0, "age": 0.2, "muscle": 0.45, "weight": 0.45, "height": 0.5},
              "young_caucasian_female", "braid01", "eyebrow008", ["female_casualsuit02", "shoes02"]),
}  # fmt: skip
REFERENCE = "m_young"  # the body the clips are retargeted onto
SEATED = ("sitting-", "sit-ground", "sleeping", "laytoidle", "meditate", "tired-kneeling")


def build_person(pid: str):
    from bl_ext.user_default.mpfb.services.faceservice import FaceService
    from bl_ext.user_default.mpfb.services.humanservice import HumanService

    pheno, skin, hair, brows, clothes = PRESETS[pid]
    before = set(bpy.data.objects)
    info = HumanService._create_default_human_info_dict()
    info["phenotype"].update(pheno)
    info.update({
        "name": pid, "rig": "game_engine", "eyes": "high-poly/high-poly.mhclo",
        "eyebrows": f"{brows}/{brows}.mhclo", "eyelashes": "eyelashes01/eyelashes01.mhclo",
        "teeth": "teeth_base/teeth_base.mhclo", "tongue": "tongue01/tongue01.mhclo",
        "hair": f"{hair}/{hair}.mhclo", "clothes": [f"{c}/{c}.mhclo" for c in clothes],
        "skin_mhmat": f"{skin}/{skin}.mhmat", "skin_material_type": "ENHANCED_SSS",
        "eyes_material_type": "MAKESKIN", "alternative_materials": {},
    })  # fmt: skip
    settings = HumanService.get_default_deserialization_settings()
    settings["subdiv_levels"] = 0
    body = HumanService.deserialize_from_dict(info, settings)
    FaceService.load_targets(
        body, load_microsoft_visemes=False, load_meta_visemes=False, load_arkit_faceunits=True
    )
    FaceService.interpolate_targets(body)
    new = [o for o in bpy.data.objects if o not in before]
    rig = next(o for o in new if o.type == "ARMATURE")
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"  # MPFB rigs come as Euler; the clips are quaternions
    coll = bpy.data.collections.new(f"person_{pid}")
    bpy.context.scene.collection.children.link(coll)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    rig.name = f"{pid}.rig"
    body.name = f"{pid}.body"
    for o in new:
        if o.type == "MESH" and o is not body and not o.name.startswith(pid + "."):
            o.name = f"{pid}.{o.name.split('.', 1)[-1]}"
    rig["vk_preset"] = pid
    rig["vk_sex"] = "female" if pheno["gender"] < 0.5 else "male"
    rig["vk_age"] = pheno["age"]
    return coll, rig, body


def bake_modelling_keys(obj) -> None:
    """Fold the MakeHuman modelling shape keys (age, weight...: "$md-..." / "$...") into the
    basis, so only the face keys remain (fewer keys, a lighter file, nothing to set at runtime)."""
    sk = obj.data.shape_keys
    if not sk:
        return
    model = [kb for kb in sk.key_blocks[1:] if kb.name.startswith("$")]
    if not model:
        return
    basis = sk.key_blocks[0]
    co = [0.0] * (len(obj.data.vertices) * 3)
    base = [0.0] * len(co)
    basis.data.foreach_get("co", base)
    total = list(base)
    for kb in model:
        kb.data.foreach_get("co", co)
        w = kb.value
        for i in range(len(co)):
            total[i] += (co[i] - base[i]) * w
    # every face key moves by the same offset (it was relative to the old basis)
    rest = [kb for kb in sk.key_blocks[1:] if not kb.name.startswith("$")]
    for kb in rest:
        kb.data.foreach_get("co", co)
        kb.data.foreach_set("co", [c + (t - b) for c, t, b in zip(co, total, base, strict=True)])
    basis.data.foreach_set("co", total)
    obj.data.vertices.foreach_set("co", total)
    for kb in model:
        obj.shape_key_remove(kb)


FACE_PARTS = ("body", "eyebrow", "eyelash", "high-poly", "teeth", "tongue")


def prune_keys() -> None:
    """Face shape keys only where the face is: hair and clothes do not need 52 copies of
    themselves (the file was mostly shape keys)."""
    for o in bpy.data.objects:
        if o.type != "MESH" or not o.data.shape_keys:
            continue
        if any(k in o.name.lower() for k in FACE_PARTS):
            continue
        for kb in list(o.data.shape_keys.key_blocks)[1:]:
            o.shape_key_remove(kb)
        if len(o.data.shape_keys.key_blocks) == 1:
            o.shape_key_remove(o.data.shape_keys.key_blocks[0])


# MakeHuman's own logo printed on four t-shirts: covered with the fabric next to it (no brand
# on our people). (centre x, centre y from the top, radius, donor offset dx, dy) in texture space
LOGOS = {
    "male_casualsuit02": [(0.565, 0.164, 0.085, -0.37, 0.0)],
    "male_casualsuit04": [(0.558, 0.176, 0.09, -0.39, 0.0)],
    "female_casualsuit01": [(0.79, 0.24, 0.088, -0.17, 0.0)],
    "female_casualsuit02": [(0.79, 0.24, 0.088, -0.17, 0.0)],
    "male_casualsuit06": [(0.53, 0.155, 0.11, 0.0, 0.14), (0.245, 0.14, 0.06, 0.0, 0.1),
                          (0.74, 0.155, 0.035, 0.0, 0.07)],
}  # fmt: skip


def delogo() -> int:
    import numpy as np

    done = 0
    for img in bpy.data.images:
        key = next((k for k in LOGOS if img.name.lower().startswith(k)), None)
        if key is None or "_ao" in img.name.lower() or img.size[0] == 0:
            continue
        w, h = img.size
        px = np.empty(w * h * img.channels, dtype=np.float32)
        img.pixels.foreach_get(px)
        px = px.reshape(h, w, img.channels)
        yy, xx = np.mgrid[0:h, 0:w]
        for cx, cy, r, dx, dy in LOGOS[key]:
            # image rows start at the bottom: "from the top" fractions flip
            ccx, ccy = cx * w, (1 - cy) * h
            d = np.sqrt((xx - ccx) ** 2 + (yy - ccy) ** 2) / (r * w)
            mask = np.clip((1.15 - d) / 0.15, 0.0, 1.0)[..., None]  # 1 inside, feathered edge
            sx, sy = round(dx * w), round(-dy * h)
            donor = np.roll(np.roll(px, -sy, axis=0), -sx, axis=1)
            px = px * (1 - mask) + donor * mask
        img.pixels.foreach_set(px.astype(np.float32).ravel())
        img.update()
        done += 1
    return done


def shrink_images(tmp: Path) -> None:
    """Every texture re-saved as JPEG at the size the frame needs: skin colour 2K (faces are
    seen close), the rest 1K, normal maps too. (Scaling alone is lost: packing reads the file.)"""
    tmp.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.image_settings.quality = 88
    for img in list(bpy.data.images):
        if img.size[0] == 0 or img.source != "FILE":
            continue
        n = img.name.lower()
        skin = "normal" not in n and ("skin" in n or "skinned" in n)
        side = 2048 if skin else 1024
        if img.size[0] > side:
            img.scale(side, side)
        # hair, brows, lashes and eyes are cut out by their alpha: those stay PNG
        alpha = (img.channels == 4 and any(
            k in n for k in ("hair", "brow", "lash", "eye", "afro", "bob", "braid", "ponytail",
                             "long", "short")
        )) or (img.channels == 4 and img.alpha_mode != "NONE" and "diffuse" not in n)  # fmt: skip
        out = tmp / (Path(img.name).stem + (".png" if alpha else ".jpg"))
        img.filepath_raw = str(out)
        img.file_format = "PNG" if alpha else "JPEG"
        img.save()
        img.filepath = str(out)
        img.reload()


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    humans, out = Path(args[0]), Path(args[1])
    for o in list(bpy.data.objects):
        bpy.data.objects.remove(o)
    only = os.environ.get("VK_ONLY")
    ids = [p for p in PRESETS if not only or p in only.split(",")]
    if REFERENCE not in ids:
        ids.insert(0, REFERENCE)
    rigs = {}
    for pid in ids:
        coll, rig, body = build_person(pid)
        for o in coll.objects:
            if o.type == "MESH":
                bake_modelling_keys(o)
        rigs[pid] = (rig, body)
        print("VKPERSON", pid, len(coll.objects), "objects", flush=True)
    # the motions: every clip of the humans library, retargeted onto the reference body
    with bpy.data.libraries.load(str(humans)) as (src, dst):
        dst.objects = ["male_Armature"]
        dst.actions = [a for a in src.actions if a.startswith(("ual_", "m2m_"))]
    q = next(o for o in dst.objects if o)
    bpy.context.scene.collection.objects.link(q)
    ref_rig, ref_body = rigs[REFERENCE]
    done = 0
    for a in list(dst.actions):
        if a is None:
            continue
        name = "mp_" + a.name.split("_", 1)[1]
        act = retarget.retarget(q, a, ref_rig, name)
        for k in ("vk_seat_z", "vk_seat_y"):
            if k in a:
                act[k] = a[k]  # re-measured below on the reference body
        if a.name.split("_", 1)[1].startswith(SEATED):
            act["vk_seat_z"], act["vk_seat_y"] = seat(ref_rig, ref_body, act)
        bpy.data.actions.remove(a)
        done += 1
    bpy.data.objects.remove(q, do_unlink=True)
    for rig, _b in rigs.values():
        if rig.animation_data:
            rig.animation_data.action = None
        for pb in rig.pose.bones:
            pb.rotation_quaternion, pb.location, pb.scale = (1, 0, 0, 0), (0, 0, 0), (1, 1, 1)
    prune_keys()
    print("VKDELOGO", delogo(), flush=True)
    shrink_images(out.parent / "_people_tex")
    for blk in (bpy.data.meshes, bpy.data.armatures, bpy.data.materials, bpy.data.images):
        for x in list(blk):
            if x.users == 0:
                blk.remove(x)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print("VKPEOPLE", len(rigs), "people", done, "clips", flush=True)


def seat(rig, body, act) -> tuple[float, float]:
    retarget.play(rig, act)
    f0, f1 = act.frame_range
    bpy.context.scene.frame_set(round((f0 + f1) / 2))
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    pelvis = rig.matrix_world @ rig.pose.bones["pelvis"].head
    pts = [body.matrix_world @ v.co for v in me.vertices]
    near = [
        p
        for p in pts
        if abs(p.x - pelvis.x) < 0.2 and abs(p.y - pelvis.y) < 0.25 and p.z < pelvis.z
    ]
    ev.to_mesh_clear()
    rig.animation_data.action = None
    if not near:
        return round(pelvis.z - 0.12, 4), round(pelvis.y, 4)
    low = min(near, key=lambda p: p.z)
    return round(low.z, 4), round(pelvis.y, 4)


if __name__ == "__main__":
    main()
