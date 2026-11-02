"""The 3D library: rigged people with their animations (vk3d_humans.blend) and HDRI skies.

Third-party, all CC0 or public domain: Quaternius Universal Base Characters, Universal Animation
Library, Downtown City MegaKit, Stylized Nature MegaKit and Realistic Car Pack (free editions); Poly
Haven HDRIs, textures and models; NASA's Blue Marble (vk3d_world.blend). Built from the original packs by scripts/build_3d_library.py and
published as one archive with the public release repo, so every install (macOS, Windows) fetches
the same bytes: `vlogkit 3d fetch` or Ayarlar > Kurulum. The archive is checked by SHA-256.
"""

from __future__ import annotations

import hashlib
import shutil
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from vlogkit.config import LIBRARY_DIR

VERSION = "2"
URL = f"https://github.com/abdulkadirerdem/vlogkit-studio/releases/download/3d-library-{VERSION}/vk3d-library-{VERSION}.zip"
SHA256 = "5671a2d312600f445dc7b256e35adf66a2934c61dc25b87c4c5d5d1658d81c04"
SIZE = 314_395_270
ROOT = LIBRARY_DIR / "3d"
CREDITS = (
    [
        (
            "Universal Base Characters (Standard)",
            "Quaternius",
            "CC0-1.0",
            "https://quaternius.itch.io/universal-base-characters",
        ),
        (
            "Universal Animation Library (Standard)",
            "Quaternius",
            "CC0-1.0",
            "https://quaternius.itch.io/universal-animation-library",
        ),
        (
            "HDRI: Kloofendal 48d Partly Cloudy (Pure Sky)",
            "Greg Zaal, Jarod Guest (Poly Haven)",
            "CC0-1.0",
            "https://polyhaven.com/a/kloofendal_48d_partly_cloudy_puresky",
        ),
        (
            "HDRI: Qwantani Dusk 2 (Pure Sky)",
            "Poly Haven",
            "CC0-1.0",
            "https://polyhaven.com/a/qwantani_dusk_2_puresky",
        ),
        (
            "HDRI: Brown Photostudio 02",
            "Poly Haven",
            "CC0-1.0",
            "https://polyhaven.com/a/brown_photostudio_02",
        ),
        (
            "HDRI: Studio Small 09",
            "Poly Haven",
            "CC0-1.0",
            "https://polyhaven.com/a/studio_small_09",
        ),
        ("HDRI: Pine Attic", "Poly Haven", "CC0-1.0", "https://polyhaven.com/a/pine_attic"),
    ]
    + [
        (
            "Downtown City MegaKit (Standard)",
            "Quaternius",
            "CC0-1.0",
            "https://quaternius.itch.io/downtown-city-megakit",
        ),
        (
            "Stylized Nature MegaKit (Standard)",
            "Quaternius",
            "CC0-1.0",
            "https://quaternius.itch.io/stylized-nature-megakit",
        ),
        ("Realistic Car Pack", "Quaternius", "CC0-1.0", "https://quaternius.itch.io/lowpoly-cars"),
        (
            "Blue Marble Next Generation (Dünya)",
            "NASA Earth Observatory",
            "Kamu malı (NASA)",
            "https://science.nasa.gov/earth/earth-observatory/blue-marble-next-generation/",
        ),
    ]
    + [
        (f"Model: {m}", "Poly Haven", "CC0-1.0", f"https://polyhaven.com/a/{m}")
        for m in (
            "SchoolDesk_01",
            "SchoolChair_01",
            "Sofa_01",
            "ArmChair_01",
            "CoffeeTable_01",
            "metal_office_desk",
            "WoodenChair_01",
            "potted_plant_01",
            "potted_plant_02",
            "street_lamp_01",
            "fire_hydrant",
            "metal_trash_can",
            "painted_wooden_bench",
            "wall_clock",
            "cardboard_box_01",
            "wooden_bookshelf_worn",
            "television_02",
            "classic_laptop",
            "dining_table",
            "desk_lamp_arm_01",
            "security_camera_01",
            "shrub_02",
        )
    ]
    + [
        (f"Doku: {t}", "Poly Haven", "CC0-1.0", f"https://polyhaven.com/a/{t}")
        for t in (
            "laminate_floor_02",
            "painted_plaster_wall",
            "asphalt_02",
            "aerial_grass_rock",
            "concrete_floor_02",
            "floor_tiles_06",
            "large_square_pattern_01",
        )
    ]
)


def blend_path() -> Path:
    return ROOT / "vk3d_humans.blend"


def world_path() -> Path:
    return ROOT / "vk3d_world.blend"


def world_ready() -> bool:
    return world_path().exists()


def hdri_dir() -> Path:
    return ROOT / "hdri"


def tex_dir() -> Path:
    return ROOT / "tex"


def ready() -> bool:
    return blend_path().exists() and hdri_dir().exists() and tex_dir().exists() and world_ready()


def fetch(progress: Callable[[float], None] | None = None, url: str | None = None) -> Path:
    """Download and unpack the library (resumes nothing: small enough to fetch again)."""
    ROOT.mkdir(parents=True, exist_ok=True)
    part = ROOT / "vk3d-library.zip.part"
    req = urllib.request.Request(url or URL, headers={"User-Agent": "vlogkit"})
    h = hashlib.sha256()
    with urllib.request.urlopen(req, timeout=60) as r, part.open("wb") as f:
        total = int(r.headers.get("Content-Length") or SIZE or 0)
        got = 0
        while chunk := r.read(1 << 20):
            f.write(chunk)
            h.update(chunk)
            got += len(chunk)
            if progress and total:
                progress(min(0.99, got / total))
    if SHA256 and h.hexdigest() != SHA256:
        part.unlink(missing_ok=True)
        raise RuntimeError("3B kütüphane bozuk indi (SHA-256 tutmuyor): tekrar dene")
    tmp = ROOT / "_unpack"
    if tmp.exists():
        shutil.rmtree(tmp)
    with zipfile.ZipFile(part) as z:
        for m in z.namelist():  # no absolute paths or ".." in an archive we unpack
            if m.startswith(("/", "\\")) or ".." in Path(m).parts:
                raise RuntimeError(f"arşivde geçersiz yol: {m}")
        z.extractall(tmp)
    for item in tmp.iterdir():
        dest = ROOT / item.name
        if dest.exists():
            shutil.rmtree(dest) if dest.is_dir() else dest.unlink()
        item.replace(dest)
    shutil.rmtree(tmp)
    part.unlink(missing_ok=True)
    return ROOT


def credits_md() -> str:
    lines = ["# 3B varlıklar", ""]
    lines += [f"- {t}: {a}, {lic}, {u}" for t, a, lic, u in CREDITS]
    return "\n".join(lines) + "\n"
