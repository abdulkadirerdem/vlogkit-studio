"""The 3D parts of the studio's setup screen: Blender and the Turkish voice model.

Both rows are optional ("optional": True): the studio counts as ready without them, "Hepsini kur"
leaves them out, and a job of the 3D type asks for them. Installing runs in the background like
the other steps (ui.setup tasks): Blender with Homebrew's cask on macOS or winget on Windows, the
voice model as its own `uv tool` and then one short line, so the model weights (~5 GB) are
downloaded before the first video.
"""

from __future__ import annotations

import os
import platform

from vlogkit.config import BUILD_DIR
from vlogkit.scene3d import blender, library
from vlogkit.speech import tts

STEP_IDS = ("blender", "voice", "lib3d")


def rows() -> list[dict]:
    b = blender.status()
    cmd = blender.install_command()
    system = platform.system()
    if b["ok"]:
        bdetail = f"3B sahneleri render eder. Bu bilgisayarda var: Blender {b['version']}"
    elif cmd:
        bdetail = "3B sahneleri render eder (3B animasyon işleri için). " + (
            "Homebrew ile kurulur." if system == "Darwin" else "winget ile kurulur."
        )
    else:
        bdetail = (
            "3B sahneleri render eder. blender.org/download adresinden kur, sonra bu ekranı yenile."
        )
    have_voice = tts.vox_installed() and (BUILD_DIR / "voices" / ".vox_ready").exists()
    vdetail = (
        "Kanal sesi: vurgulu Türkçe anlatım, internetsiz ve ücretsiz (VoxCPM2, Apache-2.0). "
        "3B animasyon için gerekli."
    )
    return [
        {
            "id": "blender",
            "label": "Blender (3B animasyon)",
            "detail": bdetail,
            "size": "~1 GB",
            "done": bool(b["ok"]),
            "optional": True,
            "manual": not cmd and not b["ok"],
        },
        {
            "id": "lib3d",
            "label": "3B karakter ve mekân kütüphanesi",
            "detail": (
                "Gerçekçi insanlar (14 kişi, yüz ifadeleri), 260'tan fazla hareket kaydı, gerçek "
                "gökyüzü ve dokular (hepsi CC0)"
                + (
                    ""
                    if library.people_path().exists() or not library.ready()
                    else ". Yeni sürüm var: gerçekçi insanlar için tekrar indir"
                )
            ),
            "size": "~610 MB",
            # an older library still renders (the Quaternius bodies); the row offers the update
            "done": library.ready() and library.people_path().exists(),
            "optional": True,
        },
        {
            "id": "voice",
            "label": "Türkçe ses modeli",
            "detail": vdetail,
            "size": "~5 GB",
            "done": have_voice,
            "optional": True,
        },
    ]


def run(step: str, run_task) -> None:
    """Start an install in the background with ui.setup's task runner."""
    if step == "blender":
        cmd = blender.install_command()
        if not cmd:
            raise RuntimeError(
                "Bu bilgisayarda paket yöneticisi yok: Blender'ı blender.org'dan kur"
            )

        def after() -> None:
            blender.find.cache_clear()
            blender.version.cache_clear()
            if not blender.status()["ok"]:
                raise RuntimeError("Blender kuruldu ama bulunamadı: ekranı yenile")

        run_task("step:blender", [cmd], after=after)
    elif step == "voice":
        steps = [] if tts.vox_python() else [tts.install_vox_cmd()]

        def warm() -> (
            None
        ):  # downloads the model weights once (~5 GB, the first line takes a while)
            tts._tool_dir.cache_clear()
            tts.speak([tts.Line("Kanal sesi hazır.")], BUILD_DIR / "voices", engine="voxcpm")
            (BUILD_DIR / "voices" / ".vox_ready").write_text("ok")

        env_cmd = steps

        os.environ.setdefault("UV_HTTP_TIMEOUT", "900")
        run_task("step:voice", env_cmd, after=warm)
    elif step == "lib3d":
        from vlogkit.ui import setup as ui_setup

        def progress(x: float) -> None:
            with ui_setup._lock:
                ui_setup.tasks["step:lib3d"]["progress"] = x

        run_task("step:lib3d", [], after=lambda: library.fetch(progress))
    else:
        raise ValueError(f"bilinmeyen adım: {step}")
