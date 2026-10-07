"""`vlogkit recipe PROJE [-v VARYANT]`: what an approved edit is made of, as a reusable recipe.

When the user approves a cut, its shape is worth keeping: how fast it opens, the shot rhythm and
how it changes, the text family, the sound layers, the effects that were used, and the strategy
lines of the project's NOTES.md. The recipe is measured from the delivered video and the project
(no render) and written to recipes/<project>-<variant>.md in the repo, so it travels with the
code. When the user later says "şu videodaki gibi yap", the agent reads it and adapts the numbers
to the new material: a pattern, not a rule.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from collections.abc import Sequence
from pathlib import Path

from vlogkit.config import REPO_ROOT

RECIPES_DIR = REPO_ROOT / "recipes"
# names in edit.py that mean an effect or tool was used (what the recipe lists under "Efektler")
EFFECTS = {
    "SpeedRamp": "hız rampası",
    "WhipPan": "whip pan",
    "Glitch": "glitch",
    "Freeze": "freeze",
    "CutFX": "kesme efekti",
    "RewindFX": "geri sarma",
    "Flash": "flaş",
    "zoom_crop": "zoom / punch-in",
    "Zoom(": "zoom / punch-in",
    "pip_graph": "resim içinde resim",
    "Pip(": "resim içinde resim",
    "background": "arka plan değiştirme",
    "stabilize": "sabitleme",
    "upscale": "büyütme",
    "lut_filter": "LUT / renk eşleme",
    "auto_lift": "otomatik ışık",
    "HookTitle": "kanca başlığı",
    "styled(": "adlı altyazı stili",
    "jumpcut": "jump cut",
    "keep_segments": "boşluk / dolgu kesimi",
}


def _thirds(shots: Sequence[tuple[float, float]], duration: float) -> list[float]:
    """Average shot length in the first, middle and last third (by where the shot starts)."""
    out = []
    for k in range(3):
        a, b = duration * k / 3, duration * (k + 1) / 3
        lens = [t1 - t0 for t0, t1 in shots if a <= t0 < b]
        out.append(sum(lens) / len(lens) if lens else 0.0)
    return out


def _notes_lines(path: Path) -> list[str]:
    """The filled lines of NOTES.md's goal, strategy and preference sections (template lines out)."""
    if not path.exists():
        return []
    keep, out = False, []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            keep = any(k in line for k in ("Amaç", "Strateji", "tercih"))
            continue
        text = line.strip()
        filled = len(text.strip("-[] :")) > 2 and "YYYY" not in text
        if keep and text.startswith("-") and filled and not text.endswith(":"):  # not a prompt
            out.append(text)
    return out


def effects_used(source: str) -> list[str]:
    found: list[str] = []
    for key, name in EFFECTS.items():
        if re.search(re.escape(key), source) and name not in found:
            found.append(name)
    return found


def measure(edit, timeline_data: dict, loudness=None) -> dict:
    """Everything the recipe says, as numbers (tested without a render)."""
    from vlogkit.export import timeline as tl
    from vlogkit.graphics.elements import count_emoji

    duration = timeline_data.get("duration") or edit.duration
    shots_tr = tl.track(timeline_data, "shots")
    shots = [(x["t0"], x["t1"]) for x in shots_tr["items"]] if shots_tr else []
    lens = [b - a for a, b in shots]
    texts_tr = tl.track(timeline_data, "text")
    items = texts_tr["items"] if texts_tr else []
    texts = [x for x in items if ": " in x["label"]]  # elements that say something
    kinds = Counter(x.get("kind") or x["label"].split(":")[0] for x in texts)
    graphics = Counter(x.get("kind") or x["label"] for x in items if ": " not in x["label"])
    elements = edit.elements()
    caps = [e for e in elements if type(e).__name__ == "Caption" and getattr(e, "text", "")]
    try:
        stems = list(edit.audio().stem_names())
    except Exception:  # an audio graph that needs build files
        stems = []
    source = ""
    src_file = Path(edit.ctx.project_dir) / "edit.py" if hasattr(edit.ctx, "project_dir") else None
    if src_file and src_file.exists():
        source = src_file.read_text(encoding="utf-8")
    return {
        "duration": duration,
        "vertical": bool(getattr(edit.layout, "h", 0) > getattr(edit.layout, "w", 1)),
        "shots": len(shots),
        "first_cut": shots[0][1] if len(shots) > 1 else None,
        "shot_avg": sum(lens) / len(lens) if lens else None,
        "shot_median": statistics.median(lens) if lens else None,
        "shot_min": min(lens) if lens else None,
        "shot_max": max(lens) if lens else None,
        "thirds": _thirds(shots, duration) if shots else [],
        "texts": len(texts),
        "texts_per_min": len(texts) / (duration / 60) if duration else 0.0,
        "first_text": min((x["t0"] for x in texts), default=None),
        "kinds": dict(kinds.most_common()),
        "graphics": dict(graphics.most_common()),
        "emoji_caps": sum(1 for c in caps if count_emoji(c.text)),
        "caps": len(caps),
        "hook_title": "HookTitle" in kinds,
        "stems": stems,
        "loudness": loudness,
        "effects": effects_used(source),
        "chapters": len(tl.track(timeline_data, "chapters")["items"])
        if tl.track(timeline_data, "chapters")
        else 0,
        "last_shot": lens[-1] if lens else None,
        "notes": _notes_lines(Path(edit.ctx.project_dir) / "NOTES.md")
        if hasattr(edit.ctx, "project_dir")
        else [],
    }


def _s(x: float | None, unit: str = " sn") -> str:
    return "?" if x is None else f"{x:.1f}{unit}"


def render_md(name: str, video: str, m: dict) -> str:
    kind = "Short / Reels" if m["vertical"] else "uzun video"
    lines = [
        f"# Tarif: {name}",
        "",
        f'Kaynak: `{video}` ({_s(m["duration"])}, {kind}). Kullanıcı "şu videodaki gibi" '
        "derse bunu oku. Sayılar bir kalıp, kural değil: yeni videonun malzemesine göre uyarla.",
        "",
        "## Açılış",
        f"- İlk kesme: {_s(m['first_cut'])}; ilk yazı: {_s(m['first_text'])}"
        + ("; kanca başlığı var" if m["hook_title"] else ""),
        "",
        "## Plan ritmi",
        f"- {m['shots']} plan; ortalama {_s(m['shot_avg'])}, ortanca {_s(m['shot_median'])}, "
        f"en kısa {_s(m['shot_min'])}, en uzun {_s(m['shot_max'])}",
    ]
    if m["thirds"]:
        a, b, c = m["thirds"]
        lines.append(f"- Üçte birlere göre ortalama plan: baş {_s(a)}, orta {_s(b)}, son {_s(c)}")
    if m["last_shot"] is not None:
        lines.append(f"- Son plan: {_s(m['last_shot'])}")
    kinds = ", ".join(f"{k} {v}" for k, v in m["kinds"].items()) or "yok"
    lines += [
        "",
        "## Yazı",
        f"- {m['texts']} yazı (dakikada {m['texts_per_min']:.0f}): {kinds}",
    ]
    if m["graphics"]:
        lines.append(
            "- Grafik ve efekt: " + ", ".join(f"{k} {v}" for k, v in m["graphics"].items())
        )
    if m["caps"]:
        lines.append(f"- Emoji: {m['emoji_caps']}/{m['caps']} altyazıda")
    if m["chapters"]:
        lines.append(f"- Bölüm: {m['chapters']}")
    lines += ["", "## Ses", f"- Katmanlar: {', '.join(m['stems']) or 'bilinmiyor'}"]
    if m["loudness"] is not None:
        lines.append(f"- Seviye: {m['loudness']}")
    lines += ["", "## Efektler", f"- {', '.join(m['effects']) or 'yok'}"]
    if m["notes"]:
        lines += ["", "## Strateji (NOTES.md)", *m["notes"]]
    lines += ["", "## Uygularken", *advice(m), ""]
    return "\n".join(lines)


def advice(m: dict) -> list[str]:
    out = []
    if m["first_cut"] is not None:
        out.append(f"- Açılışı aynı hızda kur: ilk kesme ~{m['first_cut']:.1f} sn civarında.")
    if m["thirds"] and all(m["thirds"]):
        a, _, c = m["thirds"]
        if c < a * 0.8:
            out.append("- Sona doğru hızlan: son üçte birde planlar başa göre belirgin kısa.")
        elif c > a * 1.25:
            out.append("- Sona doğru yavaşla: son üçte birde planlar daha uzun (nefes, manzara).")
        else:
            out.append("- Ritmi baştan sona benzer tut.")
    if m["shot_avg"]:
        out.append(f"- Ortalama planı ~{m['shot_avg']:.1f} sn tut; malzeme zayıfsa daha kısa.")
    if m["kinds"]:
        top = ", ".join(list(m["kinds"])[:3])
        out.append(f"- Aynı yazı ailesini kullan: {top}.")
    if m["hook_title"]:
        out.append("- Açılışa kanca başlığı koy (vaat tek satır).")
    if m["caps"] and m["emoji_caps"] > max(1, m["caps"] // 3):
        out.append("- Emojiyi kopyalama: kaynakta kuraldan fazla; en fazla üç altyazıda bir.")
    if m["effects"]:
        out.append(f"- Aynı efekt dozunu kullan: {', '.join(m['effects'][:4])}.")
    return out


def write(edit, out_dir: Path = RECIPES_DIR) -> Path:
    """Measure the built edit and write recipes/<project>-<variant>.md."""
    from vlogkit.analysis.loudness import measure as loudness
    from vlogkit.export import timeline as tl

    video = edit.output_path
    if not Path(video).exists():
        raise FileNotFoundError(f"{video} yok: önce derle (vlogkit build {edit.ctx.name})")
    # the project's own tracks (texts, chapters, notes) always come from the edit; only shots it
    # does not list are taken from the video (cached detection)
    data = tl.from_edit(edit)
    if not tl.track(data, "shots"):
        detected = tl.track(tl.ensure_shots(video), "shots")
        if detected:
            data["tracks"].insert(0, detected)
    try:
        lo = str(loudness(video))
    except Exception:  # a video without sound
        lo = None
    name = f"{edit.ctx.name}-{edit.variant}"
    m = measure(edit, data, lo)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{name}.md"
    out.write_text(render_md(name, str(video), m), encoding="utf-8")
    return out
