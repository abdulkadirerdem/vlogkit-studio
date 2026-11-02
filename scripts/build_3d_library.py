"""Build the 3D library file (vk3d_humans.blend) from Quaternius' CC0 packs. Developer tool.

    blender -b --factory-startup -P scripts/build_3d_library.py -- UBC_DIR UAL_GLB OUT.blend

UBC_DIR = "Universal Base Characters[Standard]" (extracted), UAL_GLB = UAL1_Standard.glb (no root
motion). The result holds, with every texture packed in:
- collections "human_male" and "human_female": armature + body + eyes + eyebrows (Icosphere helper
  removed), body textures (light and dark skin) as images "skin_<sex>_light|dark";
- collection "hair": every hairstyle mesh (rigged to the head bone), unparented;
- every animation as an action with a fake user ("ual_<name>").

Runtime (bpy_kit/human.py) appends from it, which is much faster than importing glTF per shot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import bpy


def clean() -> None:
    for coll in (
        bpy.data.objects,
        bpy.data.meshes,
        bpy.data.armatures,
        bpy.data.materials,
        bpy.data.actions,
        bpy.data.images,
        bpy.data.collections,
    ):
        for x in list(coll):
            coll.remove(x)


def imported(fn) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    fn()
    return [o for o in bpy.data.objects if o not in before]


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :]
    ubc, ual, out = Path(args[0]), Path(args[1]), Path(args[2])
    clean()
    scene_coll = bpy.context.scene.collection

    # animations (one armature carries them all; keep only the actions)
    objs = imported(lambda: bpy.ops.import_scene.gltf(filepath=str(ual)))
    for a in list(bpy.data.actions):  # a snapshot: renaming re-sorts the collection
        a.name = "ual_" + a.name
        a.use_fake_user = True
    for o in objs:
        bpy.data.objects.remove(o)

    base = ubc / "Base Characters" / "Godot - UE"
    tex = ubc / "Base Characters" / "Textures"
    for sex, file in (
        ("male", "Superhero_Male_FullBody.gltf"),
        ("female", "Superhero_Female_FullBody.gltf"),
    ):
        coll = bpy.data.collections.new(f"human_{sex}")
        scene_coll.children.link(coll)
        for o in imported(lambda f=file: bpy.ops.import_scene.gltf(filepath=str(base / f))):
            for c in o.users_collection:
                c.objects.unlink(o)
            if o.name.startswith("Icosphere"):
                bpy.data.objects.remove(o)
                continue
            coll.objects.link(o)
            o.name = f"{sex}_{o.name.split('.')[0]}"
            if o.type == "ARMATURE":
                o.animation_data_clear()
    for p in sorted(tex.glob("*.png")):
        img = bpy.data.images.load(str(p))
        img.name = p.stem
        img.use_fake_user = True

    hair_dir = ubc / "Hairstyles" / "Rigged to Head Bone" / "glTF (Godot -Unreal)"
    hcoll = bpy.data.collections.new("hair")
    scene_coll.children.link(hcoll)
    for p in sorted(hair_dir.glob("*.gltf")):
        for o in imported(lambda q=p: bpy.ops.import_scene.gltf(filepath=str(q))):
            for c in o.users_collection:
                c.objects.unlink(o)
            if o.type == "ARMATURE":
                bpy.data.objects.remove(o)
                continue
            o.parent = None
            o.name = p.stem
            hcoll.objects.link(o)
    # the glTFs name some textures wrongly ("T_Eye_Normal_png.png"): find the real files
    search = [tex, tex / "Normals Unity - Godot", base]
    for img in list(bpy.data.images):
        if img.packed_file or not img.filepath:
            continue
        p = Path(bpy.path.abspath(img.filepath))
        if p.exists():
            continue
        stem = p.stem.removesuffix("_png").removesuffix("_PNG")
        hit = next((d / f"{stem}.png" for d in search if (d / f"{stem}.png").exists()), None)
        if hit:
            img.filepath = str(hit)
            img.reload()
        else:
            print("VKMISSING", img.name, p.name)
            bpy.data.images.remove(img)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    print("VKLIB", out, len(bpy.data.actions), "actions", [c.name for c in bpy.data.collections])


if __name__ == "__main__":
    main()
