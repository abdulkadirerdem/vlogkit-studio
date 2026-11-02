"""Turning the kit's `VKEDGE` lines into warnings: which scene text did not fit in the frame.

Blender finds them (bpy_kit/framecheck.py); here they are collected over a run, the worst reading
per text kept, and written as one line each:

    !  b04 (13,5 sn): "4 TUR, 2 SAAT ARA" yazısının %38'i kadraj dışında (sağ)
"""

from __future__ import annotations

import json


class Collector:
    """Feed it every Blender output line; `notes()` gives the warnings, worst first."""

    def __init__(self, seconds: dict[str, float] | None = None):
        self.seconds = seconds or {}  # shot id -> when it starts in the video
        self.worst: dict[tuple[str, str], dict] = {}

    def feed(self, line: str) -> bool:
        """True when the line was a framing report (so the caller can skip it)."""
        if not line.startswith("VKEDGE "):
            return False
        try:
            d = json.loads(line[7:])
        except ValueError:
            return True
        key = (d.get("shot", ""), d.get("text", ""))
        if key not in self.worst or d.get("visible", 1) < self.worst[key].get("visible", 1):
            self.worst[key] = d
        return True

    def notes(self) -> list[str]:
        out = []
        for d in sorted(self.worst.values(), key=lambda x: (x.get("visible", 1), x.get("shot"))):
            where = f" ({d['side']})" if d.get("side") else ""
            at = self.seconds.get(d.get("shot", ""))
            when = f" ({at:.1f} sn)".replace(".", ",") if at is not None else ""
            missing = round(100 * (1 - float(d.get("visible", 0))))
            out.append(
                f'!  {d.get("shot", "?")}{when}: "{d.get("text", "")}" yazısının '
                f"%{missing}'i kadraj dışında{where}"
            )
        return out
