"""`vlogkit analyze`: one command that produces everything we looked at by hand for Short 01."""

from __future__ import annotations

import json
from dataclasses import asdict
from itertools import pairwise
from pathlib import Path

from vlogkit.analysis import beats as beats_mod
from vlogkit.analysis import letterbox, loudness, luma, scenes, sheets, transcribe
from vlogkit.config import tools
from vlogkit.ff import PathLike, probe


def analyze(
    src: PathLike,
    out_dir: PathLike,
    *,
    lang: str = "tr",
    speech: bool = True,
    music: bool = True,
    sheet_fps: float = 1.0,
) -> Path:
    src, out = Path(src), Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    info = probe(src, count_frames=True)
    data: dict = {"file": str(src), "info": {k: str(v) for k, v in asdict(info).items()}}

    data["cuts"] = scenes.detect_cuts(src)
    box = letterbox.active_area(src)
    boxed = bool(info.width and info.height) and box.w * box.h < 0.9 * info.width * info.height
    if boxed:
        data["active_area"] = asdict(box)
    curve = luma.luma_curve(src, crop=box.inset(2).crop() if boxed else None)
    data["dark_spans"] = luma.dark_spans(curve)
    if info.has_audio:
        data["loudness"] = asdict(loudness.measure(src))
        sheets.spectrogram(src, out / "spectrogram.png")
    cols = 10 if info.vertical else 6
    size = (180, 320) if info.vertical else (320, 180)
    sheets.contact_sheet(src, out / "sheet.jpg", fps=sheet_fps, cols=cols, size=size)

    t = tools()
    if speech and info.has_audio and t.whisper_cli and t.whisper_model.exists():
        segs = transcribe.transcribe(src, lang)
        data["speech"] = [asdict(s) | {"suspicious": s.suspicious} for s in segs]
    if music and info.has_audio and t.aubio:
        data["beats"] = beats_mod.beats(src)

    (out / "report.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))
    (out / "report.md").write_text(_markdown(src, info, data))
    return out / "report.md"


def _markdown(src: Path, info, d: dict) -> str:
    fps = f"{float(info.fps):.3f}" if info.fps else "?"
    lines = [
        f"# Analiz: {src.name}",
        "",
        f"- **Teknik:** {info.width}x{info.height}, {fps} fps, {info.duration:.2f} sn, "
        f"{info.frames} kare, ses: {'var' if info.has_audio else 'yok'}",
        f"- **Kesmeler ({len(d['cuts'])}):** " + ", ".join(f"{c:.3f}" for c in d["cuts"]),
    ]
    if info.fps and info.frames and info.duration:
        avg = info.frames / info.duration
        if abs(avg - float(info.fps)) / float(info.fps) > 0.05:
            lines.append(
                f"- **Değişken kare hızı:** ortalama {avg:.2f} fps. Başta `fps=` filtresiyle "
                "sabitle; kare numarasıyla (select, trim=start_frame) çalışan araçlar kayar"
            )
    if "active_area" in d:
        b = d["active_area"]
        lines.append(
            f"- **Siyah bant:** görüntü {b['w']}x{b['h']} (x={b['x']}, y={b['y']}); "
            "parlaklık sadece bu alanda ölçüldü"
        )
    lines += [
        "- **Loş bölgeler (YAVG<45):** "
        + (", ".join(f"{a:.2f}–{b:.2f}" for a, b in d["dark_spans"]) or "yok"),
    ]
    if "loudness" in d:
        lo = d["loudness"]
        lines.append(
            f"- **Ses:** {lo['integrated']:.1f} LUFS, {lo['true_peak']:.1f} dBTP "
            "(spektrogram: `spectrogram.png`)"
        )
    if "beats" in d:
        b = d["beats"]
        gaps = [y - x for x, y in pairwise(b)]
        avg = sum(gaps) / len(gaps) if gaps else 0
        lines.append(f"- **Vuruşlar:** {len(b)} adet, ortalama aralık {avg:.2f} sn")
    if "speech" in d:
        lines += ["", "## Konuşma", ""]
        if not d["speech"]:
            lines.append("_Konuşma bulunamadı._")
        for s in d["speech"]:
            flag = " ⚠️ muhtemel halüsinasyon (müzik)" if s["suspicious"] else ""
            lines.append(f"- `{s['start']:.2f}–{s['end']:.2f}` {s['text']}{flag}")
    lines += ["", "Kontak sayfası: `sheet.jpg`", ""]
    return "\n".join(lines)
