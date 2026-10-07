"""`vlogkit review`: the retention checklist of docs/viral-edit.md, measured on a render.

Sections: length, hook, pacing, ending (+ optional loop for Shorts), sound, text. Every line is
✓ (fine), ! (fix it or explain why not) or · (information / optional). The report is written to
build/review/<name>.md and is meant to be pasted into the final message of an edit.
"""

from __future__ import annotations

from collections.abc import Sequence
from itertools import pairwise
from pathlib import Path

from vlogkit.analysis import ending, hook, pacing
from vlogkit.analysis.hook import Check
from vlogkit.analysis.transcribe import Segment
from vlogkit.config import BUILD_DIR
from vlogkit.ff import PathLike, probe


def _length(duration: float, kind: str) -> Check:
    if kind == "short":
        if duration > 180:
            return Check("Süre", False, f"{duration:.0f} sn: 3 dakikayı geçen video Short sayılmaz")
        sweet = 34 <= duration <= 50
        return Check(
            "Süre",
            True if sweet else None,
            f"{duration:.1f} sn (en iyi Short'lar çoğunlukla 34-50 sn; kural değil)",
        )
    return Check("Süre", None, f"{duration / 60:.1f} dk")


def _start(e) -> float | None:
    """When an element's text appears: `t0`, or the first word of a Karaoke."""
    t0 = getattr(e, "t0", None)
    if t0 is None and getattr(e, "words", None):
        t0 = e.words[0][0]
    return t0


def _captions(elements) -> list[tuple[float, str]]:
    """(start, text) of every text element, karaoke hooks included (they carry the promise)."""
    return [
        (float(t0), e.text)
        for e in elements
        if getattr(e, "text", "") and (t0 := _start(e)) is not None
    ]


def _density(captions: Sequence[tuple[float, str]], duration: float) -> Check:
    """Long videos: text support is dense in the first 30-40 s, sparse afterwards (Onur)."""
    early = sum(1 for t, _ in captions if t <= 40)
    late = len(captions) - early
    per_min = late / max(1e-6, (duration - 40) / 60) if duration > 40 else 0.0
    return Check(
        "Yazı yoğunluğu",
        None,
        f"ilk 40 sn'de {early} yazı, sonrasında dakikada {per_min:.1f} "
        "(öneri: başta yoğun, sonra 3-4 dakikada bir)",
    )


def shot_sheet(
    path: Path, cuts: Sequence[float], duration: float, vertical: bool, out: Path, limit: int = 60
) -> Path:
    """The middle frame of every shot, in order: the fastest way to see what each shot shows."""
    from vlogkit.analysis.sheets import frames_sheet

    marks = [0.0, *cuts, duration]
    mids = [(a + b) / 2 for a, b in pairwise(marks) if b - a > 0.05]
    if len(mids) > limit:  # very long videos: an even sample
        mids = [mids[round(i * (len(mids) - 1) / (limit - 1))] for i in range(limit)]
    size = (144, 256) if vertical else (256, 144)
    cols = 10 if vertical else 6
    sheet = frames_sheet(path, mids, out, cols=cols, size=size)
    _label(sheet, mids, cols, size)
    return sheet


def _label(sheet: Path, times: Sequence[float], cols: int, size: tuple[int, int]) -> None:
    """'<shot> · <time>' in the corner of every tile, so shots can be named in a plan."""
    from PIL import Image, ImageDraw

    from vlogkit.graphics.style import font

    im = Image.open(sheet).convert("RGB")
    d = ImageDraw.Draw(im)
    f = font("ExtraBold", 15)
    for i, t in enumerate(times):
        x, y = (i % cols) * size[0], (i // cols) * size[1]
        label = f"{i + 1} · {t:.1f}s"
        w = int(d.textlength(label, font=f)) + 8
        d.rectangle((x, y, x + w, y + 20), fill=(0, 0, 0))
        d.text((x + 4, y + 2), label, font=f, fill=(255, 207, 64))
    im.save(sheet, quality=90)


def review(
    path: PathLike,
    kind: str | None = None,
    *,
    elements: Sequence | None = None,
    promise: Sequence[str] = (),
    words: Sequence[Segment] | None = None,
    lang: str = "tr",
    speech: bool = True,
    out: Path | None = None,
    cuts: Sequence[float] | None = None,
    cut_checks: bool = True,
) -> tuple[str, Path]:
    """Markdown report + its path. elements: the project's overlay elements (captions etc.).
    cuts: the project's exact cut list (Edit.cuts()); otherwise detected cuts are refined."""
    from vlogkit.analysis.loudness import measure
    from vlogkit.graphics.elements import emoji_notes

    path = Path(path)
    info = probe(path)
    kind = kind or ("short" if info.vertical else "long")
    captions = _captions(elements or [])
    if words is None and speech and info.has_audio:
        from vlogkit.analysis.transcribe import transcribe

        span = None if kind == "short" else 20.0  # long videos: the opening is what matters
        try:
            words = transcribe(path, lang, words=True, duration=span)
        except Exception:  # no whisper: the checks that need speech say so
            words = []
    words = list(words or [])

    lines = [
        f"# İzlenme süresi kontrolü: {path.name}",
        "",
        f"{'Short' if kind == 'short' else 'Uzun video'} · {info.width}x{info.height}",
        "",
    ]

    def section(title: str, checks: Sequence[Check] | Sequence[str]) -> None:
        lines.append(f"## {title}")
        lines.extend(c.line() if isinstance(c, Check) else c for c in checks)
        lines.append("")

    section("Süre", [_length(info.duration, kind)])
    section("Kanca", hook.check(path, kind, promise=promise, words=words, captions=captions))
    pace = pacing.analyze(path, kind, extra=pacing.overlay_starts(elements or []))
    section("Tempo", pacing.report(pace))
    out = out or BUILD_DIR / "review" / f"{path.stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    sheet = shot_sheet(
        path, pace.cuts, info.duration, info.vertical, out.with_name(f"{path.stem}_planlar.jpg")
    )
    section(
        "Planlar",
        [
            Check(
                "Plan sayfası",
                None,
                f"{len(pace.cuts) + 1} plan, her birinin orta karesi: {sheet}. Her plan hikâyede bir şey "
                "anlatıyor mu bak: kamerayı kurma, lense eğilme, kaydı başlatma/durdurma anı kalmasın.",
            )
        ],
    )
    if cut_checks:
        from vlogkit.analysis import cutcheck

        rep = cutcheck.check(path, out.with_name(f"{path.stem}_kesmeler"), exact_cuts=cuts)
        pages = ", ".join(str(p) for p in rep.sheets) or "kesme yok"
        section(
            "Kesmeler",
            [
                Check(
                    "Kesme sayfaları",
                    None,
                    f"{len(rep.cuts)} kesme, her birinin 1,5 sn öncesi, son karesi, ilk karesi ve "
                    f"1,5 sn sonrası: {pages}. Yarım kalan hareket, zıplayan kadraj, flaş var mı bak; "
                    "şüpheli kesmeyi `vlogkit strip` ile incele.",
                ),
                *(Check("Kesme", fix, text) for fix, text in rep.findings),
            ],
        )
    section("Bitiş", ending.check(path, kind, words if kind == "short" else []))
    if info.has_audio:
        lo = measure(path)
        ok = abs(lo.integrated + 14) <= 1 and lo.true_peak <= -1.0
        section(
            "Ses",
            [
                Check(
                    "Loudness",
                    ok,
                    f"{lo.integrated:.1f} LUFS, {lo.true_peak:.1f} dBTP "
                    "(hedef -14 LUFS, <= -1 dBTP)",
                )
            ],
        )
    text_checks: list[Check] = [Check("Emoji", False, n) for n in emoji_notes(elements or [])]
    if elements and info.width and info.height:
        from vlogkit.graphics.captions import safe_notes

        text_checks += [
            Check("Güvenli alan", fix, note)
            for fix, note in safe_notes(elements, (info.width, info.height))
        ]
    if kind == "long" and captions:
        text_checks.append(_density(captions, info.duration))
    if text_checks:
        section("Yazı", text_checks)
    fixes = sum(1 for ln in lines if ln.startswith("! "))
    lines.insert(4, f"**{fixes} düzeltilecek madde**" if fixes else "**Düzeltilecek madde yok**")
    lines.insert(5, "")

    text = "\n".join(lines).rstrip() + "\n"
    out.write_text(text)
    return text, out
