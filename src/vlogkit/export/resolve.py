"""DaVinci Resolve hand-off: the edit as a layered, editable FCPXML timeline.

The delivered video burns everything into one picture. This export keeps the layers apart, so the
video can be finished by hand without re-rendering or losing quality:

    V1        base.mov (graded, re-cut picture) split at every shot change
    V2 ...    one ProRes 4444 alpha clip per graphic element (caption, clock, flash...), rendered
              by the same code as the burned overlay: stacked in the same order they give the
              same frame. Elements that overlap in time sit on separate tracks (draw order kept),
              the others share tracks.
    top       every caption / subtitle / karaoke line again as a Resolve text clip, disabled and
              transparent. To change a word: switch that one on, switch its picture clip off.
    A1        the final mix (audio.wav, exactly what the video plays), or in <name>_stems.fcpxml
              one track per stem (main sound / effects) at the same level, before the limiter.
    markers   chapter titles (ChapterCard elements and Edit.chapters()).

Format: FCPXML 1.10 (Resolve 18+ imports it: File > Import > Timeline). Resolve's manual lists
multiple tracks, opacity, position/scale and text generators as supported for FCP X XML; imported
titles become its basic Text generator, with only part of the styling. ProRes 4444 alpha is
composited automatically; the layers carry straight (not premultiplied) alpha, like overlay.mov.

Media go to <folder>/media: base.mov and audio.wav are hard links to the build files (no copy when
on the same disk), layers and stems are rendered there.
"""

from __future__ import annotations

import json
import math
import os
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from PIL import Image

from vlogkit.analysis.loudness import measure, parse_loudnorm
from vlogkit.analysis.scenes import detect_cuts
from vlogkit.audio.mix import AudioGraph
from vlogkit.export.subtitles import plain
from vlogkit.graphics.elements import Element
from vlogkit.graphics.render import compose_frame, render_overlay

FCPXML_VERSION = "1.10"
# Final Cut Pro's built-in "Basic Title" (Resolve maps FCPXML titles to its Text generator).
TITLE_UID = ".../Titles.localized/Bumper:Opener.localized/Basic Title.localized/Basic Title.moti"
TEXT_KINDS = ("Caption", "Subtitle", "Karaoke")  # spoken/caption text -> editable title clip
STEM_NAMES = {"main": "Ana ses", "sfx": "Efektler", "music": "Müzik", "voice": "Konuşma"}
LIMITER = (  # = normalize() with its default ceiling
    "aresample=192000,alimiter=limit=0.8000:attack=4:release=60:asc=1:level=0,aresample=48000"
)


# --------------------------------------------------------------------------- time
def frame_duration(fps: Fraction) -> Fraction:
    return 1 / Fraction(fps)


def rt(frames: int, fps: Fraction) -> str:
    """Frame count -> FCPXML rational time, a whole number of frames ('3003/30000s')."""
    if frames == 0:
        return "0s"
    fd = frame_duration(fps)
    return f"{frames * fd.numerator}/{fd.denominator}s"


def first_frame_at(t: float, fps: Fraction) -> int:
    """Smallest n with float(n / fps) >= t: the same comparison the elements' draw() makes."""
    n = max(0, math.floor(t * float(fps)) - 2)
    while float(n / fps) < t:
        n += 1
    return n


# --------------------------------------------------------------------------- layers
@dataclass
class Layer:
    """One graphic element as a clip: frames [first, last) of the timeline."""

    index: int  # position in edit.elements() = draw order
    kind: str
    first: int
    last: int
    text: str = ""
    cx: float | None = None
    cy: float | None = None
    lane: int = 0
    path: Path | None = None

    @property
    def frames(self) -> int:
        return self.last - self.first

    @property
    def editable(self) -> bool:
        return self.kind in TEXT_KINDS and bool(plain(self.text).strip())

    @property
    def name(self) -> str:
        words = " ".join(plain(self.text).split())
        return f"{self.kind}: {words[:48]}" if words else self.kind

    @property
    def filename(self) -> str:
        return f"{self.index:03d}_{self.kind.lower()}.mov"


def time_window(e: Element) -> tuple[float, float] | None:
    """[start, end) in seconds from the element's own fields, None if it has no known window."""
    start = getattr(e, "t0", None)
    if start is None and getattr(e, "words", None):
        start = e.words[0][0]  # Karaoke
    if start is None and getattr(e, "imgs", None):
        start = min(t for _, t in e.imgs)  # Checklist
    end = getattr(e, "t1", None)
    if end is None:
        end = getattr(e, "t_end", None)
    if end is None and start is not None and hasattr(e, "dur"):
        end = start + e.dur  # Flash (same float sum as its draw())
    return (start, end) if start is not None and end is not None else None


def _drawn(e: Element, n: int, fps: Fraction, size: tuple[int, int]) -> bool:
    return compose_frame([e], float(n / fps), size).getbbox() is not None


def frame_span(
    e: Element, nframes: int, fps: Fraction, size: tuple[int, int]
) -> tuple[int, int] | None:
    """Frames [first, last) where the element draws something; None if it never does."""
    w = time_window(e)
    if w is None:  # unknown element: look at every frame (slow, but always right)
        drawn = [n for n in range(nframes) if _drawn(e, n, fps, size)]
        return (drawn[0], drawn[-1] + 1) if drawn else None
    first = min(first_frame_at(w[0], fps), nframes)
    last = min(first_frame_at(w[1], fps), nframes)
    while first < last and not _drawn(e, first, fps, size):  # fully transparent lead-in
        first += 1
    while last > first and not _drawn(e, last - 1, fps, size):
        last -= 1
    return (first, last) if last > first else None


def plan_layers(
    elements: Sequence[Element], nframes: int, fps: Fraction, size: tuple[int, int]
) -> list[Layer]:
    layers = []
    for i, e in enumerate(elements):
        span = frame_span(e, nframes, fps, size)
        if span is None:
            continue
        layers.append(
            Layer(
                index=i,
                kind=type(e).__name__,
                first=span[0],
                last=span[1],
                text=getattr(e, "text", "") or "",
                cx=getattr(e, "cx", None),
                cy=getattr(e, "cy", None),
            )
        )
    pack_lanes(layers)
    return layers


def _overlap(a: Layer, b: Layer) -> bool:
    return a.first < b.last and b.first < a.last


def pack_lanes(layers: Sequence[Layer], base: int = 1) -> int:
    """Assign lanes in draw order: above every earlier layer that overlaps in time (so the stack
    composites exactly like the overlay), as low as possible otherwise. Returns the top lane."""
    placed: list[Layer] = []
    for layer in layers:
        layer.lane = 1 + max((p.lane for p in placed if _overlap(p, layer)), default=base - 1)
        placed.append(layer)
    return max((p.lane for p in placed), default=base - 1)


def stack(layers: Sequence[tuple[Image.Image, int]]) -> Image.Image:
    """Composite per-element frames the way a timeline does: lower lane first, then draw order."""
    ordered = sorted(enumerate(layers), key=lambda x: (x[1][1], x[0]))
    out = Image.new("RGBA", ordered[0][1][0].size, (0, 0, 0, 0))
    for _, (im, _) in ordered:
        out.alpha_composite(im)
    return out


def render_layers(
    elements: Sequence[Element], layers: Sequence[Layer], folder: Path, fps: Fraction, size
) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for k, layer in enumerate(layers, 1):
        layer.path = folder / layer.filename
        print(f"  katman {k}/{len(layers)}: {layer.name} ({layer.frames} kare)", flush=True)
        render_overlay(
            [elements[layer.index]],
            layer.frames,
            layer.path,
            fps,
            size,
            progress=False,
            start=layer.first,
        )


# --------------------------------------------------------------------------- shots
def shot_starts(cuts_s: Sequence[float], nframes: int, fps: Fraction) -> list[int]:
    """Cut times (s) -> sorted segment start frames, always beginning with 0."""
    frames = {round(t * float(fps)) for t in cuts_s}
    return [0, *sorted(f for f in frames if 0 < f < nframes)]


# --------------------------------------------------------------------------- audio
def mix_gain(graph: AudioGraph, final_wav: Path, tmp: Path, meta: Path | None = None) -> float:
    """The gain (dB) that turned the raw mix into audio.wav: from the build's audio.json, else
    found again the way normalize() did (gain + limiter, measured until it matches the file)."""
    if meta and meta.exists():
        return float(json.loads(meta.read_text())["gain_db"])
    target = measure(final_wav).integrated
    raw = parse_loudnorm(
        graph.render(
            ["-f", "null", "-"], "loudnorm=I=-14:TP=-1.5:print_format=json", loglevel="info"
        ).stderr
    )
    gain = target - raw.integrated
    for _ in range(4):
        graph.render(["-c:a", "pcm_s24le", str(tmp)], f"volume={gain:.2f}dB,{LIMITER}")
        got = measure(tmp).integrated
        if abs(got - target) < 0.05:
            break
        gain += target - got
    tmp.unlink(missing_ok=True)
    return gain


def render_stems(graph: AudioGraph, gain_db: float, folder: Path) -> dict[str, Path]:
    """One 32-bit float wav per stem at the mix gain, no limiter: together they are the mix
    before its peak limiter (float, so peaks above 0 dBFS survive for the editor's own limiter)."""
    folder.mkdir(parents=True, exist_ok=True)
    out = {}
    for stem in graph.stem_names():
        path = folder / f"{stem}.wav"
        graph.render(
            ["-c:a", "pcm_f32le", str(path)],
            f"volume={gain_db:.2f}dB,aresample=48000",
            only=graph.stem_labels(stem),
        )
        out[stem] = path
    return out


# --------------------------------------------------------------------------- media files
def link_or_copy(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.unlink(missing_ok=True)
    try:
        os.link(src, dst)
    except OSError:  # another disk: copy
        shutil.copy2(src, dst)
    return dst


# --------------------------------------------------------------------------- FCPXML
@dataclass(frozen=True)
class AudioClip:
    path: Path
    name: str
    role: str  # FCP role: dialogue | music | effects


@dataclass(frozen=True)
class Marker:
    frame: int
    name: str


def _title_style(layer: Layer) -> dict[str, str]:
    size = {"Subtitle": "64"}.get(layer.kind, "84")
    face = "ExtraBold" if layer.kind != "Subtitle" else "Bold"
    return {
        "font": "Montserrat",
        "fontFace": face,
        "fontSize": size,
        "fontColor": "1 1 1 1",
        "strokeColor": "0 0 0 1",
        "strokeWidth": "6",
        "shadowColor": "0 0 0 0.75",
        "shadowOffset": "5 315",
        "shadowBlurRadius": "10",
        "alignment": "center",
    }


def build_fcpxml(
    *,
    name: str,
    fps: Fraction,
    size: tuple[int, int],
    nframes: int,
    base: Path,
    shots: Sequence[int],
    layers: Sequence[Layer],
    audio: Sequence[AudioClip],
    markers: Sequence[Marker] = (),
) -> ET.ElementTree:
    """The timeline. Everything hangs off the V1 shot clips (FCPXML 'connected clips'):
    lane > 0 = video tracks above, lane < 0 = audio tracks below."""
    w, h = size
    fd = frame_duration(fps)
    root = ET.Element("fcpxml", version=FCPXML_VERSION)
    res = ET.SubElement(root, "resources")
    ET.SubElement(
        res,
        "format",
        id="r1",
        frameDuration=f"{fd.numerator}/{fd.denominator}s",
        width=str(w),
        height=str(h),
        colorSpace="1-1-1 (Rec. 709)",
    )
    ids = iter(range(2, 1_000_000))

    def video_asset(path: Path, frames: int, nm: str) -> str:
        aid = f"r{next(ids)}"
        a = ET.SubElement(
            res,
            "asset",
            id=aid,
            name=nm,
            start="0s",
            duration=rt(frames, fps),
            hasVideo="1",
            format="r1",
            videoSources="1",
        )
        ET.SubElement(a, "media-rep", kind="original-media", src=path.resolve().as_uri())
        return aid

    def audio_asset(path: Path, nm: str) -> str:
        aid = f"r{next(ids)}"
        a = ET.SubElement(
            res,
            "asset",
            id=aid,
            name=nm,
            start="0s",
            duration=rt(nframes, fps),
            hasAudio="1",
            audioSources="1",
            audioChannels="2",
            audioRate="48000",
        )
        ET.SubElement(a, "media-rep", kind="original-media", src=path.resolve().as_uri())
        return aid

    base_id = video_asset(base, nframes, "Görüntü")
    layer_ids = {
        layer.index: video_asset(layer.path, layer.frames, layer.name)
        for layer in layers
        if layer.path
    }
    audio_ids = [(clip, audio_asset(clip.path, clip.name)) for clip in audio]
    texts = [layer for layer in layers if layer.editable]
    if texts:
        ET.SubElement(res, "effect", id="rT", name="Basic Title", uid=TITLE_UID)

    library = ET.SubElement(root, "library")
    event = ET.SubElement(library, "event", name="vlogkit")
    project = ET.SubElement(event, "project", name=name)
    seq = ET.SubElement(
        project,
        "sequence",
        format="r1",
        duration=rt(nframes, fps),
        tcStart="0s",
        tcFormat="NDF",
        audioLayout="stereo",
        audioRate="48k",
    )
    spine = ET.SubElement(seq, "spine")

    bounds = [*shots, nframes]
    shot_clips = []
    for k, (a, b) in enumerate(pairwise(bounds), 1):
        shot_clips.append(
            (
                a,
                b,
                ET.SubElement(
                    spine,
                    "asset-clip",
                    ref=base_id,
                    name=f"Plan {k:02d}",
                    offset=rt(a, fps),
                    start=rt(a, fps),
                    duration=rt(b - a, fps),
                    format="r1",
                    srcEnable="video",
                    tcFormat="NDF",
                ),
            )
        )

    def parent(frame: int) -> ET.Element:
        for a, b, clip in shot_clips:
            if a <= frame < b:
                return clip
        return shot_clips[-1][2]

    # children must come before markers inside a clip (DTD order): collect, then append
    children: dict[int, list[ET.Element]] = {id(c): [] for _, _, c in shot_clips}

    for layer in layers:
        if layer.index not in layer_ids:
            continue
        el = ET.Element(
            "asset-clip",
            ref=layer_ids[layer.index],
            lane=str(layer.lane),
            name=layer.name,
            offset=rt(layer.first, fps),
            start="0s",
            duration=rt(layer.frames, fps),
            format="r1",
            tcFormat="NDF",
        )
        children[id(parent(layer.first))].append(el)

    top = max((layer.lane for layer in layers), default=0)
    title_lanes = [
        Layer(t.index, t.kind, t.first, t.last, t.text, t.cx, t.cy) for t in texts
    ]  # own lanes above all graphics
    pack_lanes(title_lanes, base=top + 1)
    for n, (layer, lane) in enumerate(zip(texts, title_lanes, strict=True), 1):
        el = ET.Element(
            "title",
            ref="rT",
            lane=str(lane.lane),
            name=f"Metin: {' '.join(plain(layer.text).split())[:48]}",
            offset=rt(layer.first, fps),
            duration=rt(layer.frames, fps),
            enabled="0",
        )
        if layer.cx is not None and layer.cy is not None:
            ET.SubElement(
                el,
                "param",
                name="Position",
                key="9999/999166631/999166633/1/100/101",
                value=f"{layer.cx - w / 2:.0f} {h / 2 - layer.cy:.0f}",
            )
        text = ET.SubElement(el, "text")
        ET.SubElement(text, "text-style", ref=f"ts{n}").text = plain(layer.text)
        tsd = ET.SubElement(el, "text-style-def", id=f"ts{n}")
        ET.SubElement(tsd, "text-style", _title_style(layer))
        ET.SubElement(el, "adjust-blend", amount="0")  # invisible even if 'disabled' is ignored
        children[id(parent(layer.first))].append(el)

    first_clip = shot_clips[0][2]
    for k, (clip, aid) in enumerate(audio_ids, 1):
        children[id(first_clip)].append(
            ET.Element(
                "asset-clip",
                ref=aid,
                lane=str(-k),
                name=clip.name,
                offset="0s",
                start="0s",
                duration=rt(nframes, fps),
                audioRole=clip.role,
            )
        )

    marks: dict[int, list[ET.Element]] = {id(c): [] for _, _, c in shot_clips}
    for m in markers:
        clip = parent(m.frame)
        marks[id(clip)].append(
            ET.Element("marker", start=rt(m.frame, fps), duration=rt(1, fps), value=m.name)
        )
    for _, _, clip in shot_clips:
        clip.extend(children[id(clip)])
        clip.extend(marks[id(clip)])

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    return tree


def write_fcpxml(tree: ET.ElementTree, path: Path) -> Path:
    body = ET.tostring(tree.getroot(), encoding="unicode")
    path.write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n\n' + body + "\n",
        encoding="utf-8",
    )
    return path


# --------------------------------------------------------------------------- README
README = """vlogkit -> DaVinci Resolve
==========================

İçe aktarma
1. DaVinci Resolve'da bir proje aç: File > Import > Timeline (Shift+Cmd+I).
2. "{fcpxml}" dosyasını seç. "Automatically import source clips into media pool" açık kalsın.
   Medya bu klasörün media/ alt klasöründe; klasörü taşırsan Resolve yerini sorar, klasörü göster.
3. Katman kliplerinde yazı kenarları parlak ya da koyu görünürse: Media Pool'da media/layers
   kliplerini seç > sağ tık > Clip Attributes > Video > Alpha Mode: Straight.
   (Katmanlar düz/straight alfa ile yazıldı, videodaki overlay ile aynı.)

İzler
- V1: Görüntü, plan plan bölünmüş ({shots} plan). Kırpabilir, yer değiştirebilir, renk verebilirsin.
- V2-V{top}: Her yazı ve efekt ayrı bir klip ({layers} klip). Videodaki grafiklerle piksel piksel
  aynı; aynı anda görünenler ayrı izlerde, çizim sırası korunuyor.
- En üst iz(ler): Aynı yazılar düzenlenebilir Resolve metni olarak. Kapalı ve görünmez ({texts} klip).
- A1: Son miks, videodaki sesin aynısı.{stems_line}{markers_line}

Bir yazıyı değiştirmek (örn. bir kelimeyi silmek)
1. En üst izde, o zamandaki "Metin: ..." klibini seç, D tuşuyla etkinleştir.
2. Inspector > Video > Composite > Opacity: 100.
3. Inspector'da metni düzenle.
4. Altındaki resim katmanını (V2...) seç, D tuşuyla kapat.
Not: Resolve metninde kontur, gölge, vurgu rengi ve emoji birebir aynı olmaz. Görünüm tam aynı
kalsın istiyorsan değişikliği vlogkit'e söyle; sadece o katman yeniden üretilir.

Altyazı dosyaları
{sidecars}
Resolve'da: File > Import > Subtitle, ya da .srt dosyasını zaman çizelgesine sürükle.
"""


# --------------------------------------------------------------------------- export
def default_dir(edit) -> Path:
    out = edit.output_path
    return out.with_name(out.stem + "_resolve")


def _markers(edit, layers: Sequence[Layer]) -> list[Marker]:
    """Chapter markers: the project's chapters() (the YouTube chapter list) if it has them,
    otherwise where each ChapterCard appears. Plus the project's notes() as "Not: ..." markers
    (open questions and things to check, so they travel with the timeline)."""
    last = edit.nframes - 1
    marks: list[Marker] = []
    chapters = getattr(edit, "chapters", None)
    if callable(chapters):
        try:
            found = chapters()
        except Exception:  # a project whose chapters need a build step: fall back to the cards
            found = []
        marks = [Marker(min(round(c.start * float(edit.fps)), last), c.title) for c in found]
    if not marks:
        marks = [Marker(x.first, x.text) for x in layers if x.kind == "ChapterCard" and x.text]
    notes = edit.notes() if callable(getattr(edit, "notes", None)) else []
    marks += [
        Marker(min(max(0, round(t * float(edit.fps))), last), f"Not: {text}") for t, text in notes
    ]
    return sorted(marks, key=lambda m: m.frame)


def export(edit, out_dir: Path | None = None, stems: bool = True) -> Path:
    """Write the Resolve folder for a built edit (needs base.mov and audio.wav in its work dir)."""
    fps, size, nframes = edit.fps, edit.layout.size, edit.nframes
    for p in (edit.base_path, edit.audio_path):
        if not p.exists():
            raise FileNotFoundError(
                f"{p} yok. Önce: uv run vlogkit build {edit.ctx.name} -v {edit.variant} "
                "-s base -s audio"
            )
    folder = Path(out_dir) if out_dir else default_dir(edit)
    media = folder / "media"
    name = edit.output_path.stem
    print(f"== resolve -> {folder}", flush=True)

    base = link_or_copy(edit.base_path, media / "base.mov")
    mix = link_or_copy(edit.audio_path, media / "audio.wav")

    cuts = edit.cuts()
    if cuts is None:
        print("  plan kesmeleri aranıyor (scdet)", flush=True)
        cuts = detect_cuts(edit.base_path)
    shots = shot_starts(cuts, nframes, fps)

    elements = edit.elements()
    layers = plan_layers(elements, nframes, fps, size)
    old = media / "layers"
    if old.exists():
        shutil.rmtree(old)
    render_layers(elements, layers, media / "layers", fps, size)
    markers = _markers(edit, layers)

    common = dict(
        fps=fps, size=size, nframes=nframes, base=base, shots=shots, layers=layers, markers=markers
    )
    main = folder / f"{name}.fcpxml"
    write_fcpxml(
        build_fcpxml(name=name, audio=[AudioClip(mix, "Son miks", "dialogue")], **common), main
    )

    stems_file = None
    graph = edit.audio()
    if stems and len(graph.stem_names()) > 1:
        print("  stem'ler: " + ", ".join(graph.stem_names()), flush=True)
        gain = mix_gain(graph, edit.audio_path, media / "_gain.wav", edit.audio_meta_path)
        paths = render_stems(graph, gain, media / "stems")
        clips = [
            AudioClip(p, STEM_NAMES.get(s, s), "effects" if s == "sfx" else "dialogue")
            for s, p in paths.items()
        ]
        stems_file = folder / f"{name}_stems.fcpxml"
        write_fcpxml(build_fcpxml(name=f"{name} (stem)", audio=clips, **common), stems_file)

    sidecar_names = []
    for suffix, content in edit.sidecars().items():
        (folder / f"{name}{suffix}").write_text(content, encoding="utf-8")
        sidecar_names.append(f"- {name}{suffix}")

    top = max((layer.lane for layer in layers), default=0) + 1
    (folder / "README.txt").write_text(
        README.format(
            fcpxml=main.name,
            shots=len(shots),
            top=top,
            layers=len(layers),
            texts=sum(layer.editable for layer in layers),
            stems_line=(
                f'\n- Sesleri ayrı düzenlemek için bunun yerine "{stems_file.name}" dosyasını içe'
                " aktar: son miks yerine her stem ayrı izde gelir (limiter yok; bitince Fairlight'ta"
                " limiter ekle)."
                if stems_file
                else ""
            ),
            markers_line=f'\n- İşaretler: {len(markers)} (bölüm başlıkları ve "Not:" ile başlayan notlar).'
            if markers
            else "",
            sidecars="\n".join(sidecar_names) or "- (bu projede yok)",
        ),
        encoding="utf-8",
    )
    print(f"   -> {main}", flush=True)
    if stems_file:
        print(f"   -> {stems_file}", flush=True)
    return folder
