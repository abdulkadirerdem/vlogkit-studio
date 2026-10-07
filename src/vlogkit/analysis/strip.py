"""`vlogkit strip`: one picture of a stretch of video, for deciding where to cut.

    10 frames      evenly spread over the stretch, each with its time
    waveform       the sound, with quiet stretches (>= 0.4 s) shaded
    words          whisper's word timings, placed at their time
    marks          optional red lines (cuts, candidate in/out points)

The agent reads a cut decision off this image: the word ends, the breath, the gesture that starts
the next sentence. Words come from the whole file's cached transcript when it exists (review,
the Studio and `transcribe --words` make it), else the stretch alone is transcribed (cached too).
"""

from __future__ import annotations

import re
import tempfile
from collections.abc import Sequence
from pathlib import Path

from vlogkit.analysis.transcribe import Segment
from vlogkit.ff import PathLike, ffmpeg, probe

WIDTH = 1600
MAX_SPAN = 180.0  # s; past ~60 s the words get too dense to read and are left out
WORDS_SPAN = 60.0
QUIET_DB = -35.0
QUIET_MIN = 0.4
_SIL_START = re.compile(r"silence_start: ([-0-9.]+)")
_SIL_END = re.compile(r"silence_end: ([-0-9.]+)")


def quiet_spans(
    path: PathLike,
    start: float,
    span: float,
    noise_db: float = QUIET_DB,
    min_dur: float = QUIET_MIN,
) -> list[tuple[float, float]]:
    """Quiet stretches inside [start, start + span], in source seconds."""
    r = ffmpeg(
        [
            "-ss",
            f"{start:.3f}",
            "-t",
            f"{span:.3f}",
            "-i",
            path,
            "-vn",
            "-af",
            f"silencedetect=n={noise_db}dB:d={min_dur}",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
        capture=True,
    )
    starts = [max(0.0, float(x)) for x in _SIL_START.findall(r.stderr)]
    ends = [float(x) for x in _SIL_END.findall(r.stderr)]
    ends += [span] * (len(starts) - len(ends))  # still quiet at the end of the stretch
    return [(start + a, start + min(b, span)) for a, b in zip(starts, ends, strict=False) if b > a]


def place_words(
    words: Sequence[Segment], start: float, span: float, width: int, text_w, rows: int = 3
) -> list[tuple[int, int, str]]:
    """(x, row, text) for each word that fits: a word goes to the first row where it does not
    touch the previous word; words that fit nowhere are left out (the caller counts them)."""
    ends = [-(10**9)] * rows  # nothing placed yet: a word at x=0 fits
    out = []
    for w in words:
        if w.end < start or w.start > start + span:
            continue
        x = round((max(w.start, start) - start) / span * width)
        tw = text_w(w.text)
        for r in range(rows):
            if x > ends[r] + 4:
                out.append((x, r, w.text))
                ends[r] = x + tw
                break
    return out


def strip(
    src: PathLike,
    out: PathLike,
    start: float,
    end: float,
    *,
    words: Sequence[Segment] | None = None,
    lang: str = "tr",
    marks: Sequence[float] = (),
    frames: int = 10,
) -> Path:
    """Render the strip image (see module doc). words=None: transcribe the stretch (cached)."""
    from PIL import Image, ImageDraw

    from vlogkit.analysis.sheets import frames_sheet
    from vlogkit.graphics.style import font

    info = probe(src)
    if start >= info.duration:
        raise ValueError(f"başlangıç videonun süresini aşıyor ({info.duration:.2f} sn)")
    end = min(end, info.duration)
    span = end - start
    if span <= 0:
        raise ValueError("bitiş başlangıçtan sonra olmalı")
    if span > MAX_SPAN:
        raise ValueError(f"en fazla {MAX_SPAN:g} sn'lik bir aralık ver (şerit okunur kalsın)")
    show_words = span <= WORDS_SPAN and info.has_audio
    if words is None and show_words:
        from vlogkit.analysis.transcribe import cached, transcribe

        words = cached(src, lang, words=True)  # the whole file's words, if already transcribed
        if words is None:
            try:
                words = transcribe(src, lang, words=True, start=start, duration=span)
            except Exception:  # no whisper: the strip still shows picture and sound
                words = []
    from vlogkit.analysis.transcribe import drop_hallucinated_words

    words = drop_hallucinated_words([w for w in (words or []) if w.text.strip()])

    tile_w = WIDTH // frames
    dw, dh = info.display_size  # a rotated clip is shown turned
    aspect = (dh or 9) / (dw or 16)
    tile_h = round(tile_w * aspect)
    times = [start + (i + 0.5) * span / frames for i in range(frames)]
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    f_small = font("SemiBold", 13)
    f_label = font("ExtraBold", 13)
    ruler_h, wave_h, word_row = 26, 120, 20
    header_h = 30
    words_h = word_row * 3 if show_words else 0
    height = header_h + tile_h + ruler_h + wave_h + words_h + 8
    canvas = Image.new("RGB", (WIDTH, height), (18, 20, 23))
    d = ImageDraw.Draw(canvas)

    def x_of(t: float) -> int:
        return round((t - start) / span * WIDTH)

    with tempfile.TemporaryDirectory() as tmp:
        film = frames_sheet(src, times, Path(tmp) / "film.png", size=(tile_w, tile_h))
        canvas.paste(Image.open(film).convert("RGB"), (0, header_h))
        if info.has_audio:
            wave = Path(tmp) / "wave.png"
            ffmpeg(
                [
                    "-y",
                    "-ss",
                    f"{start:.3f}",
                    "-t",
                    f"{span:.3f}",
                    "-i",
                    src,
                    "-filter_complex",
                    f"aformat=channel_layouts=mono,showwavespic=s={WIDTH}x{wave_h}"
                    ":colors=0x46c2b2:scale=sqrt",
                    "-frames:v",
                    "1",
                    wave,
                ]
            )
            wave_top = header_h + tile_h + ruler_h
            canvas.paste(Image.open(wave).convert("RGB"), (0, wave_top))
        quiet = quiet_spans(src, start, span) if info.has_audio else []

    for i, t in enumerate(times):  # frame time labels
        label = f"{t:.2f}"
        x = i * tile_w
        box = d.textbbox((x + 3, header_h + 2), label, font=f_label)
        d.rectangle(box, fill=(0, 0, 0))
        d.text((x + 3, header_h + 2), label, font=f_label, fill=(255, 207, 64))

    ruler_top = header_h + tile_h
    wave_top = ruler_top + ruler_h
    step = 1.0 if span <= 30 else 5.0 if span <= 120 else 10.0
    tick = (start // step + 1) * step
    while tick < end:
        x = x_of(tick)
        d.line([(x, ruler_top), (x, ruler_top + 8)], fill=(170, 170, 170))
        d.text((x + 2, ruler_top + 8), f"{tick:g}", font=f_small, fill=(170, 170, 170))
        tick += step
    for t in times:  # where each frame was taken
        d.line([(x_of(t), ruler_top), (x_of(t), ruler_top + 4)], fill=(255, 207, 64), width=2)

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for a, b in quiet:
        od.rectangle([x_of(a), wave_top, x_of(b), wave_top + wave_h], fill=(120, 140, 255, 70))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    d = ImageDraw.Draw(canvas)

    dropped = 0
    if show_words:
        top = wave_top + wave_h + 4
        placed = place_words(words, start, span, WIDTH, lambda s: d.textlength(s, font=f_small))
        dropped = sum(1 for w in words if w.start <= end and w.end >= start) - len(placed)
        for x, r, text in placed:
            y = top + r * word_row
            d.line([(x, wave_top + wave_h - 6), (x, y)], fill=(90, 96, 104))
            d.text((x + 2, y), text, font=f_small, fill=(235, 235, 235))

    for m in marks:  # cut candidates
        if start <= m <= end:
            x = x_of(m)
            d.line([(x, header_h), (x, height)], fill=(255, 70, 70), width=2)
            d.text((x + 3, height - 18), f"{m:.2f}", font=f_label, fill=(255, 90, 90))

    note = f"{Path(src).name}   {start:.2f}-{end:.2f} sn ({span:.1f} sn)   mavi: sessiz >= {QUIET_MIN:g} sn"
    if show_words:
        note += "   kelimeler: whisper (yaklaşık)"
        if dropped > 0:
            note += f", {dropped} kelime sığmadı"
    elif info.has_audio:
        note += f"   kelimeler {WORDS_SPAN:g} sn'den uzun aralıkta gösterilmez"
    d.text((8, 8), note, font=font("SemiBold", 14), fill=(220, 220, 220))
    canvas.save(out)
    return out
