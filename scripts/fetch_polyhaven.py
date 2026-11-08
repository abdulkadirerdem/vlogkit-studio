"""Download Poly Haven textures and models (CC0) for the 3D library. Developer tool.

    uv run python scripts/fetch_polyhaven.py DOWNLOADS_DIR

Textures land as DOWNLOADS_DIR/phtex/<id>_{diff,nor,rough}.jpg (the names bpy_kit/look.pbr reads),
models as DOWNLOADS_DIR/ph/<id>/<id>.gltf with their files (what build_3d_world.py imports).
Poly Haven's API terms ask for a unique User-Agent and no hammering: one request at a time.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

UA = {
    "User-Agent": "vlogkit-library-builder/1.0 (+https://github.com/abdulkadirerdem/vlogkit-studio)"
}
API = "https://api.polyhaven.com"

# the cutaway's soil strata and the surfaces seen up close: 2K; the rest 1K
TEXTURES_2K = ["sparse_grass", "brown_mud_02", "cracked_red_ground", "gravelly_sand", "rocks_ground_05",
               "cliff_side", "stacked_stone_wall", "gravel_stones"]  # fmt: skip
TEXTURES_1K = ["white_stucco", "red_brick_03", "clay_roof_tiles_02", "wood_planks", "concrete_wall_003",
               "snow_02", "green_metal_rust", "rusty_metal_02", "brown_mud_dry"]  # fmt: skip
MODELS = ["wooden_bucket_01", "Barrel_01", "rusted_spade_01", "picke_dirty_01", "watering_can_metal_01",
          "compost_bags", "root_cluster_01", "root_cluster_02", "grass_medium_01", "rock_moss_set_01",
          "boulder_01", "wooden_crate_01", "tree_stump_01", "utility_box_01", "water_manhole_cover",
          "wooden_ladder", "planter_box_01"]  # fmt: skip


def get(url: str) -> bytes:
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except OSError:
            time.sleep(2 + 3 * attempt)
    raise RuntimeError(f"indirilemedi: {url}")


def files(asset: str) -> dict:
    return json.loads(get(f"{API}/files/{asset}"))


def texture(asset: str, res: str, out: Path) -> int:
    f = files(asset)
    n = 0
    for ours, theirs in (("diff", "Diffuse"), ("nor", "nor_gl"), ("rough", "Rough")):
        node = f.get(theirs) or f.get(theirs.lower())
        if not node:
            continue
        item = node.get(res, node.get("1k"))["jpg"]
        dest = out / f"{asset}_{ours}.jpg"
        if not dest.exists():
            dest.write_bytes(get(item["url"]))
            n += item.get("size", 0)
            time.sleep(0.3)
    return n


def model(asset: str, out: Path) -> int:
    g = files(asset)["gltf"]["1k"]["gltf"]
    d = out / asset
    d.mkdir(parents=True, exist_ok=True)
    n = 0
    dest = d / f"{asset}.gltf"
    if not dest.exists():
        dest.write_bytes(get(g["url"]))
        n += g.get("size", 0)
    for rel, item in (g.get("include") or {}).items():
        p = d / rel
        if p.exists():
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(get(item["url"]))
        n += item.get("size", 0)
        time.sleep(0.2)
    return n


def main() -> None:
    root = Path(sys.argv[1])
    tex, mod = root / "phtex", root / "ph"
    tex.mkdir(parents=True, exist_ok=True)
    mod.mkdir(parents=True, exist_ok=True)
    total = 0
    for a in TEXTURES_2K:
        total += texture(a, "2k", tex)
        print("doku", a, flush=True)
    for a in TEXTURES_1K:
        total += texture(a, "1k", tex)
        print("doku", a, flush=True)
    for a in MODELS:
        total += model(a, mod)
        print("model", a, flush=True)
    print(f"bitti: {total / 1e6:.0f} MB indirildi")


if __name__ == "__main__":
    main()
