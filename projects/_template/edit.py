"""<Proje adı>: tek cümlelik açıklama.

Akış:
    1) uv run vlogkit analyze <video>        -> kesmeler, loş bölgeler, konuşma, vuruşlar, kontak sayfası
    2) Aşağıdaki SOURCE / OUTPUT / CAPTIONS / LIFTS'i doldur
    3) uv run vlogkit build <proje> -s base   (sonra) uv run vlogkit preview <proje> -t 2 -t 5
    4) uv run vlogkit build <proje>  &&  uv run vlogkit check <çıktı> --cuts

Bu şablon: tek kaynak videoyu renklendirir, loş yerleri aydınlatır, altyazı ekler, sesi -14 LUFS'a
getirir. Hook, geri sarma, meme varyantı gibi örnekler docs/workflow.md'de.
"""

from __future__ import annotations

from functools import cached_property
from pathlib import Path

from vlogkit.audio.mix import AudioGraph
from vlogkit.ff import probe
from vlogkit.graphics import caption
from vlogkit.project import Edit
from vlogkit.video.grade import INDOOR_WARM, lift
from vlogkit.video.graph import SEGMENT_TAIL, render_intermediate
from vlogkit.video.zoom import Zoom, zoom_crop

SOURCE = "klasor/video.mp4"  # VLOGS_ROOT'a göre (~/yt-vlogs/...)
OUTPUT = "klasor/video_EDIT"  # uzantısız; varyantlar "_<ad>" eki alır

# (metin, başlangıç, bitiş, ekstra): [köşeli] = vurgu rengi, emoji serbest
CAPTIONS = [
    ("Merhaba [dünya] 👋", 0.5, 3.0, {}),
]
LIFTS: list[tuple] = []  # (t0, t1, miktar[, fade_out]): loş planlar için gamma artışı


class TemplateEdit(Edit):
    variants = ("v1",)
    output = OUTPUT

    @cached_property
    def source(self) -> Path:
        return self.ctx.footage(SOURCE)

    @property
    def nframes(self) -> int:
        info = probe(self.source)
        return info.frames or round(info.duration * self.fps)

    def build_base(self, out: Path) -> None:
        grade = INDOOR_WARM.but(gamma=f"1.07*{lift(LIFTS)}") if LIFTS else INDOOR_WARM
        zoom = Zoom()  # e.g. Zoom().push(t0, t1, 0.06) inside a single shot
        fc = f"[0:v]{grade.filter()},{zoom_crop(zoom)},{SEGMENT_TAIL}[v]"
        render_intermediate([["-i", self.source]], fc, out)

    def elements(self) -> list:
        return [caption(text, t0, t1, **kw) for text, t0, t1, kw in CAPTIONS]

    def audio(self) -> AudioGraph:
        g = AudioGraph(self.duration)
        src = g.input(self.source)
        g.chain(f"[{src}:a]anull", "src")
        return g


EDIT = TemplateEdit
