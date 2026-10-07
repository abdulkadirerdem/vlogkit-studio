"""Open the studio with one click: start the server in the background if needed, open the browser.

`vlogkit shortcut` builds a macOS app on the Desktop that calls `vlogkit open`.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
import webbrowser
from pathlib import Path

from vlogkit.config import BUILD_DIR, FONTS_DIR, REPO_ROOT

DEFAULT_PORT = 8765
APP_NAME = "vlogkit Stüdyo"
LOG = BUILD_DIR / "ui" / "server.log"
DESKTOP = Path.home() / "Desktop"


def is_running(port: int = DEFAULT_PORT) -> bool:
    """True if a vlogkit studio (not some other app) answers on this port."""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=1.5) as r:
            return b"vlogkit" in r.read(4096)
    except Exception:
        return False


def start_background(port: int = DEFAULT_PORT, timeout: float = 20.0) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    log = LOG.open("ab")
    subprocess.Popen(
        [sys.executable, "-m", "vlogkit.cli", "ui", "--no-open", "--port", str(port)],
        cwd=REPO_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=log,
        stderr=subprocess.STDOUT,
        start_new_session=True,  # survives the launcher (and the Terminal/app that started it)
    )
    t = time.time()
    while time.time() - t < timeout:
        if is_running(port):
            return
        time.sleep(0.3)
    raise RuntimeError(f"stüdyo {timeout:.0f} sn içinde açılmadı, günlük: {LOG}")


def open_studio(port: int = DEFAULT_PORT, browser: bool = True) -> str:
    url = f"http://127.0.0.1:{port}/"
    if not is_running(port):
        start_background(port)
    if browser:
        webbrowser.open(url)
    return url


# --------------------------------------------------------------------------- desktop app
def _icon_png(path: Path, size: int = 1024) -> None:
    from PIL import Image, ImageDraw, ImageFont

    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pad = int(size * 0.09)  # macOS icon grid leaves a margin around the rounded square
    d.rounded_rectangle(
        (pad, pad, size - pad, size - pad), radius=int(size * 0.2), fill=(27, 29, 31, 255)
    )
    font = ImageFont.truetype(str(FONTS_DIR / "Montserrat-Black.ttf"), int(size * 0.5))
    d.text(
        (size / 2, size * 0.53),
        "vk",
        font=font,
        anchor="mm",
        fill=(255, 207, 64, 255),
        stroke_width=int(size * 0.02),
        stroke_fill=(10, 11, 12, 255),
    )
    im.save(path)


def _icns(dest: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        png = Path(tmp) / "icon.png"
        _icon_png(png)
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for s in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                name = f"icon_{s}x{s}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(
                    [
                        "sips",
                        "-z",
                        str(s * scale),
                        str(s * scale),
                        str(png),
                        "--out",
                        str(iconset / name),
                    ],
                    check=True,
                    capture_output=True,
                )
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)], check=True)


def create_shortcut(dest_dir: Path = DESKTOP, name: str = APP_NAME) -> Path:
    """Build `<name>.app`: double-click -> `uv run vlogkit open` in this repo."""
    uv = shutil.which("uv") or "/opt/homebrew/bin/uv"
    app = dest_dir / f"{name}.app"
    if app.exists():
        shutil.rmtree(app)
    # an installed copy runs exactly its release's lock (a rewritten uv.lock would look like a
    # hand edit to the updater)
    frozen = " --frozen" if (REPO_ROOT / ".release").exists() else ""
    path_env = "/opt/homebrew/bin:/opt/homebrew/sbin:$HOME/.local/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
    script = [
        f'set repo to "{REPO_ROOT}"',
        f'set uvbin to "{uv}"',
        f'do shell script "export PATH={path_env}; cd " & quoted form of repo & " && " & '
        f'quoted form of uvbin & " run{frozen} vlogkit open > /dev/null 2>&1"',
    ]
    cmd = ["osacompile", "-o", str(app)]
    for line in script:
        cmd += ["-e", line]
    subprocess.run(cmd, check=True, capture_output=True)
    _icns(app / "Contents" / "Resources" / "applet.icns")
    subprocess.run(["touch", str(app)], check=False)  # make Finder pick up the new icon
    return app


def restart(port: int = DEFAULT_PORT, timeout: float = 30.0) -> None:
    """Start the studio again once the old server has let go of the port (after an update)."""
    t = time.time()
    while is_running(port) and time.time() - t < timeout:
        time.sleep(0.3)
    start_background(port)


if __name__ == "__main__":  # python -m vlogkit.ui.launcher restart PORT
    if len(sys.argv) >= 2 and sys.argv[1] == "restart":
        restart(int(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_PORT)
