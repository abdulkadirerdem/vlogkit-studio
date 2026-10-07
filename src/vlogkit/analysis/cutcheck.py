"""Cut checks on a render: the mistakes that hide at the edit points.

One decode of the delivered file at full frame rate (tiny picture) gives every frame's brightness
and frame-difference score. From that:

    exact cuts      the frame with the biggest jump near each detected cut
    short shots     a shot of a few frames between two cuts (a leftover sliver)
    black frames    a dark frame or stretch in the middle of the video
    frozen picture  the same frame held for a while (a source that ran out, a stuck segment)
    level jumps     the sound level jumping across a cut (two takes at different volume)

plus cut sheets: per cut, the frames 1.5 s before, just before, just after and 1.5 s after, so a
jump cut, a flash or a half-finished gesture is seen before the user sees it.
Nothing here decides: every finding is "look at this" with a time.
"""

from __future__ import annotations

import re
import statistics
from collections.abc import Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg, probe
from vlogkit.timecode import FPS_NTSC

_PTS = re.compile(r"pts_time:([0-9.]+)")
_YAVG = re.compile(r"lavfi\.signalstats\.YAVG=([0-9.]+)")
_SCORE = re.compile(r"lavfi\.scd\.score=([0-9.]+)")

CUT_SCORE = 8.0  # frame-difference score of a hard cut (same as scenes.detect_cuts)
SHORT_SHOT = 0.2  # s: shorter than this between two cuts = probably a leftover
BLACK_Y = 19.0  # mean luma (0-255; video-range black is 16, a dark night shot stays above ~20)
SLIVER = 0.2  # s: black this short is a leftover frame, longer is a dip (maybe intended)
SLIVER_SCORE = 12.0  # both edges of a leftover sliver jump this much; the frame right after a
#                      cut in a moving shot often jumps ~9 too (an "aftershock", not a shot)
FROZEN = 1.0  # s of identical frames
FROZEN_SCORE = 0.0005  # a repeated frame decodes identical (0.000); a still talking head
#                        at this size still scores 0.002-0.02
LEVEL_JUMP = 8.0  # LU between the 0.8 s before and after a cut
PER_PAGE = 12


@dataclass(frozen=True)
class FrameStat:
    t: float
    luma: float
    score: float  # frame difference to the previous frame (scdet, 0-100)


@dataclass
class CutReport:
    cuts: list[float]
    findings: list[tuple[bool | None, str]] = field(default_factory=list)  # (fix?, text)
    sheets: list[Path] = field(default_factory=list)


def frame_stats(path: PathLike) -> list[FrameStat]:
    """Brightness and difference score of every frame (one decode, 96 px wide)."""
    r = ffmpeg(
        [
            "-i",
            path,
            "-an",
            "-vf",
            # format=yuv420p: 8-bit values, so black reads 16 (on 10-bit input YAVG reads 64)
            "scale=96:-2,format=yuv420p,signalstats,scdet=threshold=100,"
            "metadata=print:key=lavfi.signalstats.YAVG,metadata=print:key=lavfi.scd.score",
            "-f",
            "null",
            "-",
        ],
        loglevel="info",
        capture=True,
    )
    return parse_stats(r.stderr)


def parse_stats(log: str) -> list[FrameStat]:
    rows: dict[float, list[float | None]] = {}
    t = None
    for line in log.splitlines():
        if m := _PTS.search(line):
            t = float(m.group(1))
            rows.setdefault(t, [None, None])
        elif t is not None and (m := _YAVG.search(line)):
            rows[t][0] = float(m.group(1))
        elif t is not None and (m := _SCORE.search(line)):
            rows[t][1] = float(m.group(1))
    return [FrameStat(t, v[0], v[1] or 0.0) for t, v in sorted(rows.items()) if v[0] is not None]


def spikes(
    stats: Sequence[FrameStat], threshold: float = CUT_SCORE, ratio: float = 3.0, radius: int = 5
) -> list[float]:
    """Hard cuts at full frame rate: a frame whose difference score is high *and* stands out
    from its neighbours. A whip pan or a shaky run scores high for many frames in a row and is
    not a cut; a one-frame flash is two cuts one frame apart (and then a 1-frame shot)."""
    out = []
    for i, s in enumerate(stats):
        if s.score < threshold:
            continue
        around = [x.score for x in (*stats[max(0, i - radius) : i], *stats[i + 1 : i + 1 + radius])]
        base = statistics.median(around) if around else 0.0
        if s.score >= ratio * max(base, 1.0):
            out.append(s.t)
    return out


def short_shots(cuts: Sequence[float], limit: float = SHORT_SHOT) -> list[tuple[float, float]]:
    return [(a, b) for a, b in pairwise(cuts) if b - a < limit]


def slivers(
    stats: Sequence[FrameStat], limit: float = SHORT_SHOT, edge: float = SLIVER_SCORE
) -> list[tuple[float, float]]:
    """Short shots whose both edges are strong cuts (a few frames of another picture)."""
    strong = spikes(stats, threshold=edge)
    return short_shots(strong, limit)


def runs(stats: Sequence[FrameStat], pred, min_len: float, fps: float) -> list[tuple[float, float]]:
    """[start, end) stretches where pred(frame) holds for at least `min_len` seconds."""
    spans, begin = [], None
    for s in stats:
        if pred(s):
            begin = s.t if begin is None else begin
        elif begin is not None:
            spans.append((begin, s.t))
            begin = None
    if begin is not None and stats:
        spans.append((begin, stats[-1].t + 1 / fps))
    return [(a, b) for a, b in spans if b - a >= min_len - 1e-6]


def black_spans(
    stats: Sequence[FrameStat], duration: float, fps: float
) -> list[tuple[float, float]]:
    """Dark frames inside the video. A fade in at the start or out at the end is intended."""
    spans = runs(stats, lambda s: s.luma < BLACK_Y, 1 / fps, fps)
    return [(a, b) for a, b in spans if a > 0.05 and b < duration - 0.05]


def frozen_spans(stats: Sequence[FrameStat], fps: float) -> list[tuple[float, float]]:
    return [
        (a, b)
        for a, b in runs(
            stats, lambda s: s.score <= FROZEN_SCORE and s.luma >= BLACK_Y, FROZEN, fps
        )
    ]


def level_jumps(
    cuts: Sequence[float], loud: Sequence[tuple[float, float]], jump: float = LEVEL_JUMP
) -> list[tuple[float, float]]:
    """(cut, LU difference) where the momentary level differs a lot across the cut and both sides
    have sound (> -45 LUFS): two takes at different volume, or music cut mid-phrase."""
    out = []
    for c in cuts:
        before = [v for t, v in loud if c - 0.8 <= t < c - 0.1 and v > -70]
        after = [v for t, v in loud if c + 0.1 < t <= c + 0.8 and v > -70]
        if not before or not after:
            continue
        a, b = sum(before) / len(before), sum(after) / len(after)
        if min(a, b) > -45 and abs(a - b) >= jump:
            out.append((c, b - a))
    return out


def sheet_times(
    cut: float, duration: float, fps: Fraction, prev: float = 0.0, nxt: float | None = None
) -> list[float]:
    """Up to 1.5 s before, the last frame before, the first frame after, up to 1.5 s after; the
    outer two stay inside the shots that meet at the cut (fast montages: never a third shot)."""
    fd = float(1 / fps)
    last = duration - fd
    nxt = duration if nxt is None else nxt
    raw = [max(cut - 1.5, prev), cut - fd, cut, min(cut + 1.5, nxt - fd)]
    return [min(max(0.0, t), last) for t in raw]


def cut_sheets(
    src: PathLike,
    cuts: Sequence[float],
    flagged: set[float],
    out_base: Path,
    *,
    vertical: bool,
    limit: int = 36,
) -> list[Path]:
    """Pages of PER_PAGE cuts, one row per cut: before / just before | just after / after.
    Over `limit` cuts: the flagged ones plus an even sample of the rest."""
    from PIL import Image, ImageDraw

    from vlogkit.graphics.style import font

    if not cuts:
        return []
    out_base.parent.mkdir(parents=True, exist_ok=True)
    info = probe(src)
    fps = info.fps or FPS_NTSC
    chosen = list(cuts)
    if len(chosen) > limit:
        rest = [c for c in chosen if c not in flagged]
        k = max(0, limit - len(flagged))
        sample = (
            [rest[round(i * (len(rest) - 1) / max(1, k - 1))] for i in range(k)] if rest else []
        )
        chosen = sorted(set(sample) | (set(cuts) & flagged))
    size = (108, 192) if vertical else (192, 108)
    label_w, gap = 150, 10
    f_big, f_small = font("ExtraBold", 15), font("SemiBold", 12)
    pages: list[Path] = []
    for p in range(0, len(chosen), PER_PAGE):
        page = chosen[p : p + PER_PAGE]
        rows = []
        for c in page:
            k = cuts.index(c)
            prev = cuts[k - 1] if k > 0 else 0.0
            nxt = cuts[k + 1] if k + 1 < len(cuts) else info.duration
            rows.append(sheet_times(c, info.duration, fps, prev, nxt))
        from vlogkit.analysis.sheets import grab

        flat = grab(src, [t for r in rows for t in r], size)
        width = label_w + 4 * size[0] + gap + 3 * 2
        im = Image.new("RGB", (width, len(page) * (size[1] + 6) + 6), (18, 20, 23))
        d = ImageDraw.Draw(im)
        for i, (c, row) in enumerate(zip(page, rows, strict=True)):
            y = 6 + i * (size[1] + 6)
            k = cuts.index(c) + 1
            color = (255, 90, 90) if c in flagged else (255, 207, 64)
            d.text((8, y + 4), f"Kesme {k}", font=f_big, fill=color)
            d.text((8, y + 26), f"{c:.3f} sn", font=f_small, fill=(220, 220, 220))
            d.text((8, y + 44), "önce  |  sonra", font=f_small, fill=(150, 150, 150))
            if c in flagged:
                d.text((8, y + 62), "bak", font=f_small, fill=(255, 90, 90))
            x = label_w
            for j, t in enumerate(row):
                frame = flat[4 * i + j]
                if frame is not None:
                    im.paste(frame, (x, y))
                d.text((x + 3, y + 2), f"{t:.2f}", font=f_small, fill=(255, 207, 64))
                x += size[0] + (gap if j == 1 else 2)
            d.line(
                [
                    (label_w + 2 * size[0] + 2 + gap // 2, y),
                    (label_w + 2 * size[0] + 2 + gap // 2, y + size[1]),
                ],
                fill=(255, 70, 70),
                width=2,
            )
        suffix = "" if p == 0 else f"_{p // PER_PAGE + 1}"
        path = out_base.with_name(f"{out_base.name}{suffix}.jpg")
        im.save(path, quality=88)
        pages.append(path)
    return pages


def check(
    path: PathLike,
    out_base: Path,
    *,
    exact_cuts: Sequence[float] | None = None,
    sheets: bool = True,
) -> CutReport:
    """All cut checks + cut sheets. The findings always come from the render itself (a stray
    frame is exactly what the project's own cut list would not know about); the sheets show the
    project's cuts (Edit.cuts()) when given, the detected ones otherwise."""
    from vlogkit.analysis.loudness import momentary

    info = probe(path)
    fps = info.fps or FPS_NTSC
    stats = frame_stats(path)
    found = [c for c in spikes(stats) if 0 < c < info.duration]
    shown = [c for c in (exact_cuts if exact_cuts is not None else found) if 0 < c < info.duration]
    rep = CutReport(shown)
    flagged: set[float] = set()

    def near(a: float, b: float) -> set[float]:
        return {c for c in shown if a - 0.2 <= c <= b + 0.2}

    blacks = black_spans(stats, info.duration, float(fps))
    for a, b in blacks:
        n = round((b - a) * float(fps))
        if b - a <= SLIVER:
            rep.findings.append((False, f"{a:.2f} sn: {n} siyah kare (kesmede kalmış olabilir)"))
        else:
            rep.findings.append(
                (None, f"{a:.2f}-{b:.2f} sn: kararma ({b - a:.1f} sn); geçiş değilse kontrol et")
            )
        flagged |= near(a, b)
    for a, b in slivers(stats):
        if any(x < b and a < y for x, y in blacks):  # the black frames above, said once
            continue
        n = round((b - a) * float(fps))
        rep.findings.append(
            (False, f"{a:.2f} sn: {n} karelik plan; kasıtlı değilse (flash, glitch) at")
        )
        flagged |= near(a, b)
    for a, b in frozen_spans(stats, float(fps)):
        rep.findings.append(
            (
                None,
                f"{a:.2f}-{b:.2f} sn: görüntü {b - a:.1f} sn donuk; freeze efekti değilse kaynak "
                "kısa kalmış ya da bir parça takılmış olabilir",
            )
        )
    if info.has_audio and shown:
        jumps = level_jumps(shown, momentary(path))
        flagged |= {c for c, _ in jumps}
        if len(jumps) > 3:  # a music video jumps with its music: one line, the agent judges
            where = ", ".join(f"{c:.1f} ({j:+.0f})" for c, j in jumps)
            rep.findings.append(
                (
                    None,
                    f"{len(jumps)} kesmede ses seviyesi 8 LU'dan fazla sıçrıyor: {where}. "
                    "Müziğin kendi dinamiği değilse, iki deneme farklı seviyede kalmış olabilir",
                )
            )
        else:
            for c, jump in jumps:
                rep.findings.append(
                    (
                        None,
                        f"{c:.2f} sn kesmesinde ses {jump:+.0f} LU sıçrıyor: kasıtlı değilse eşitle",
                    )
                )
    if sheets:
        rep.sheets = cut_sheets(path, shown, flagged, out_base, vertical=info.vertical)
    return rep
