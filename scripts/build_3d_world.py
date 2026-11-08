"""Build the 3D world library (vk3d_world.blend): buildings, streets, trees, cars, furniture, the
Earth. Developer tool; every source is CC0 / public domain.

    blender -b --factory-startup -P scripts/build_3d_world.py -- DOWNLOADS_DIR OUT.blend

DOWNLOADS_DIR holds the extracted packs: city/x (Quaternius Downtown City MegaKit, Standard),
nature/x (Quaternius Stylized Nature MegaKit, Standard), cars/x (Quaternius Realistic Car Pack),
ph/<id>/<id>.gltf (Poly Haven models, 1k), earth/bluemarble_5400.jpg (NASA Blue Marble NG).

Every asset becomes a collection "kit_<name>" that stands on z=0, centred on x/y, lengthwise
along Y for vehicles; bpy_kit/props.py instances them. A JSON next to the .blend lists the
sizes (for placing buildings along a street).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

CITY = ["Building_Large_2", "Building_Medium_2_001", "Building_Small_1", "Street_2Lane", "Street_4Lane",
        "Street_4WayIntersection", "Sidewalk_Straight_3m", "Prop_ACUnit", "Prop_Bollard", "Prop_ManholeCover",
        "Prop_Planter_Single", "Sidewalk_Planter"]  # fmt: skip
NATURE = [*(f"CommonTree_{i}" for i in range(1, 6)), *(f"Pine_{i}" for i in range(1, 6)), *(f"TwistedTree_{i}" for i in range(1, 4)),
          "Bush_Common", "Bush_Common_Flowers", "Grass_Common_Tall", "Grass_Wispy_Tall", "Flower_3_Group", "Flower_4_Group",
          "Rock_Medium_1", "Rock_Medium_2", "Rock_Medium_3", "Fern_1", "Plant_1_Big"]  # fmt: skip
CARS = ["NormalCar1", "NormalCar2", "SUV", "SportsCar", "SportsCar2", "Taxi", "Cop"]
PH = ["SchoolDesk_01", "SchoolChair_01", "Sofa_01", "ArmChair_01", "CoffeeTable_01", "metal_office_desk", "WoodenChair_01",
      "potted_plant_01", "potted_plant_02", "street_lamp_01", "fire_hydrant", "metal_trash_can", "painted_wooden_bench",
      "wall_clock", "cardboard_box_01", "wooden_bookshelf_worn", "television_02", "classic_laptop", "dining_table",
      "desk_lamp_arm_01", "security_camera_01", "shrub_02",
      # library 3: the yard and the cutaway (scripts/fetch_polyhaven.py)
      "wooden_bucket_01", "Barrel_01", "rusted_spade_01", "picke_dirty_01", "watering_can_metal_01", "compost_bags",
      "root_cluster_01", "root_cluster_02", "grass_medium_01", "rock_moss_set_01", "boulder_01", "wooden_crate_01",
      "tree_stump_01", "utility_box_01", "water_manhole_cover", "wooden_ladder", "planter_box_01"]  # fmt: skip


def new_objects(fn) -> list[bpy.types.Object]:
    before = set(bpy.data.objects)
    fn()
    return [o for o in bpy.data.objects if o not in before]


def collect(name: str, objs: list[bpy.types.Object], lengthwise_y: bool = False) -> dict:
    """Put the objects in kit_<name>, standing on the ground, centred; returns its size."""
    objs = [o for o in objs if o.type in ("MESH", "EMPTY", "CURVE")]
    coll = bpy.data.collections.new(f"kit_{name}")
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        coll.objects.link(o)
    bpy.context.scene.collection.children.link(coll)
    bpy.context.view_layer.update()
    pts = [o.matrix_world @ Vector(c) for o in objs if o.type == "MESH" for c in o.bound_box]
    if not pts:
        return {}
    lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    centre = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    m = Matrix.Translation(-centre)
    if lengthwise_y and (hi.x - lo.x) > (hi.y - lo.y):
        m = Matrix.Rotation(1.5707963, 4, "Z") @ m
    for o in objs:
        if o.parent is None or o.parent not in objs:
            o.matrix_world = m @ o.matrix_world
    bpy.context.scene.collection.children.unlink(coll)
    coll.use_fake_user = True
    size = hi - lo
    if lengthwise_y and size.x > size.y:
        size = Vector((size.y, size.x, size.z))
    return {"size": [round(size.x, 3), round(size.y, 3), round(size.z, 3)]}


def main() -> None:
    a = sys.argv[sys.argv.index("--") + 1 :]
    src, out = Path(a[0]), Path(a[1])
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.collections, bpy.data.images):
        for x in list(coll):
            coll.remove(x)
    info: dict[str, dict] = {}
    city = src / "city" / "x" / "Exports" / "glTF (Godot)"
    for n in CITY:
        f = next(city.glob(f"{n}.gl*"), None)
        if f:
            info[n] = collect(n, new_objects(lambda f=f: bpy.ops.import_scene.gltf(filepath=str(f))))
    nature = src / "nature" / "x" / "glTF"
    for n in NATURE:
        f = next(nature.glob(f"{n}.gl*"), None)
        if f:
            info[n] = collect(n, new_objects(lambda f=f: bpy.ops.import_scene.gltf(filepath=str(f))))
    blends = next((src / "cars" / "x").glob("*/Blends"))
    for n in CARS:
        f = blends / f"{n}.blend"
        if not f.exists():
            continue
        with bpy.data.libraries.load(str(f), link=False) as (s, d):
            d.objects = [o for o in s.objects]
        objs = [o for o in d.objects if o is not None and o.type == "MESH"]
        for o in objs:
            bpy.context.scene.collection.objects.link(o)
        info[n] = collect(n, objs, lengthwise_y=True)
    for n in PH:
        f = src / "ph" / n / f"{n}.gltf"
        if f.exists():
            info[n] = collect(n, new_objects(lambda f=f: bpy.ops.import_scene.gltf(filepath=str(f))))
    earth = src / "earth" / "bluemarble_5400.jpg"
    if earth.exists():
        img = bpy.data.images.load(str(earth))
        img.name = "earth_bluemarble"
        img.use_fake_user = True
    for o in list(bpy.data.objects):  # cameras and lights that came with the car files
        if o.type in ("CAMERA", "LIGHT"):
            bpy.data.objects.remove(o)
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    out.with_suffix(".json").write_text(json.dumps(info, indent=1))
    print("VKWORLD", len(info), "assets ->", out)


if __name__ == "__main__":
    main()
