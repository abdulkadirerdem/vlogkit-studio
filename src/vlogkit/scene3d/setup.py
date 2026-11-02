"""The 3D parts of the studio's setup screen: Blender and the Turkish voice model.

Both rows are optional ("optional": True): the studio counts as ready without them, "Hepsini kur"
leaves them out, and a job of the 3D type asks for them. Installing runs in the background like
the other steps (ui.setup tasks): Blender with Homebrew's cask on macOS or winget on Windows, the
voice model as its own `uv tool` and then one short line, so the model weights (~440 MB) are
downloaded before the first video.
"""

from __future__ import annotations

import os
import platform

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
    have_voice = tts.pocket_installed()
    vdetail = (
        "Türkçe anlatım, internetsiz ve ücretsiz (Pocket TTS, 6 ses). 3B animasyon için gerekli."
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
            "detail": "Gerçekçi iskeletli karakterler, 43 animasyon, gerçek gökyüzü ve dokular (hepsi CC0)",
            "size": "~320 MB",
            "done": library.ready(),
            "optional": True,
        },
        {
            "id": "voice",
            "label": "Türkçe ses modeli",
            "detail": vdetail,
            "size": "~1,2 GB",
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
        env_cmd = tts.install_pocket_cmd()

        def warm() -> None:  # downloads the model weights once (the first line takes a while)
            from vlogkit.config import BUILD_DIR

            tts.speak([tts.Line("Merhaba.")], BUILD_DIR / "voices", engine="pocket")

        os.environ.setdefault("UV_HTTP_TIMEOUT", "900")
        run_task("step:voice", [env_cmd], after=warm)
    elif step == "lib3d":
        from vlogkit.ui import setup as ui_setup

        def progress(x: float) -> None:
            with ui_setup._lock:
                ui_setup.tasks["step:lib3d"]["progress"] = x

        run_task("step:lib3d", [], after=lambda: library.fetch(progress))
    else:
        raise ValueError(f"bilinmeyen adım: {step}")
