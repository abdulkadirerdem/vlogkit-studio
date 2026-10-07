"""macOS notification when a studio job finishes (jobs can run for half an hour).

terminal-notifier (brew) is preferred: clicking the notification opens the job in the browser.
Plain osascript works everywhere but a click only opens Script Editor.
Set VLOGKIT_NOTIFY=0 to turn notifications off (the tests do).
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess

_NOTIFIER = ("/opt/homebrew/bin/terminal-notifier", "/usr/local/bin/terminal-notifier")


def enabled() -> bool:
    return os.environ.get("VLOGKIT_NOTIFY", "1") != "0"


def notify(title: str, message: str, url: str | None = None) -> None:
    if not enabled():
        return
    tn = shutil.which("terminal-notifier") or next(
        (p for p in _NOTIFIER if os.path.exists(p)), None
    )
    if tn:
        cmd = [
            tn,
            "-title",
            "vlogkit Stüdyo",
            "-subtitle",
            title,
            "-message",
            message or " ",
            "-group",
            "vlogkit",
            "-sound",
            "Glass",
        ]
        if url:
            cmd += ["-open", url]
    else:
        q = lambda s: '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'  # noqa: E731
        cmd = [
            "osascript",
            "-e",
            f'display notification {q(message or " ")} with title "vlogkit Stüdyo" '
            f'subtitle {q(title)} sound name "Glass"',
        ]
    with contextlib.suppress(OSError):
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
