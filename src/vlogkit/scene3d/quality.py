"""Before posting: the machine checks a finished 3D video (`3d kontrol`) and a blind rater
(`3d puanla`).

The checks read the delivered mp4 itself, not the plan: what the voice actually says (whisper,
against the script), whether the picture ever stands still, how long the shots are, how long
each caption stays up, how loud it is. The rater is a fresh Claude session that sees only what a
viewer sees (frames every two seconds, the narration, a few numbers) and scores it on a fixed
rubric; it never sees scene.json, so it cannot be talked into liking the plan.
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import statistics
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from vlogkit.scene3d import formats, plan
from vlogkit.scene3d import spec as specmod

DEAD_DIFF = 1.2  # mean pixel change (0-255) under which two frames 0.25 s apart look the same
DEAD_SECONDS = 3.0
LONG_SHOT = 3.2
MIN_WORD_ON = 0.15  # s a single-word caption must stay up to be read
MIN_CHUNK_ON = 0.6
HEARD_OK = 0.7  # share of a line whisper must hear for it to count as spoken right


@dataclass
class Report:
    problems: list[str] = field(default_factory=list)  # "!" lines: fix before posting
    notes: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def lines(self) -> list[str]:
        return [f"!  {p}" for p in self.problems] + [f"   {n}" for n in self.notes]


def _fmt_t(t: float) -> str:
    return f"{t:.1f} sn".replace(".", ",")


def _sample_frames(video: Path, fps: float, width: int, out: Path) -> list[Path]:
    from vlogkit.ff import ffmpeg

    out.mkdir(parents=True, exist_ok=True)
    ffmpeg(["-y", "-i", str(video), "-vf", f"fps={fps},scale={width}:-2", str(out / "f_%05d.png")])
    return sorted(out.glob("f_*.png"))


def _still_runs(frames: list[Path], step: float) -> list[tuple[float, float]]:
    """Stretches where the picture does not change (mean difference under DEAD_DIFF)."""
    from PIL import Image, ImageChops, ImageStat

    runs, start, prev = [], None, None
    for i, f in enumerate(frames):
        im = Image.open(f).convert("L")
        if prev is not None:
            diff = ImageStat.Stat(ImageChops.difference(im, prev)).mean[0]
            t = i * step
            if diff < DEAD_DIFF:
                start = t - step if start is None else start
            elif start is not None:
                runs.append((start, t))
                start = None
        prev = im
    if start is not None:
        runs.append((start, len(frames) * step))
    return [(a, b) for a, b in runs if b - a >= DEAD_SECONDS]


def check(e, video: Path) -> Report:
    """Every machine check on the delivered video."""
    rep = Report()
    beats = e.beats
    p = e.render_plan("draft")
    shots = p["shots"]
    fps = float(e.fps)
    # pace: shot lengths, cuts per minute
    lens = [s["frames"] / fps for s in shots]
    total = beats[-1].t1
    rep.stats.update(
        duration=round(total, 1),
        shots=len(shots),
        cuts_per_min=round(60 * (len(shots) - 1) / max(1.0, total), 1),
        median_shot=round(statistics.median(lens), 2),
    )
    end = float((e.spec.get("end") or {}).get("seconds", 0)) if e.spec.get("end") else 0.0
    if lens:  # the last shot carries the end card: that part is not a held shot
        lens[-1] = max(0.0, lens[-1] - end)
    long = [f"{s['id']} ({_fmt_t(n)})" for s, n in zip(shots, lens, strict=True) if n > LONG_SHOT]
    if long:
        rep.problems.append("3 saniyeden uzun planlar: " + ", ".join(long))
    rep.notes.append(
        f"{len(shots)} plan, dakikada {rep.stats['cuts_per_min']} kesme, ortanca plan "
        f"{_fmt_t(rep.stats['median_shot'])}"
    )
    # captions: long enough on screen to be read
    mode = formats.caption_mode(e.spec)
    if mode != "off":
        least = MIN_WORD_ON if mode == "word" else MIN_CHUNK_ON
        short = []
        for b in beats:
            groups = plan.word_groups(b.words) if mode == "word" else plan.chunks(b.words)
            for k, (text, t0, _t1) in enumerate(groups):
                until = groups[k + 1][1] if k + 1 < len(groups) else b.t1
                if until - t0 < least:
                    short.append(f'"{specmod.spoken(text)}" ({_fmt_t(t0)})')
        if short:
            rep.problems.append(
                f"{len(short)} altyazı {least:g} sn'den kısa kalıyor: " + ", ".join(short[:6])
            )
    # the picture: does it ever stand still?
    with tempfile.TemporaryDirectory() as tmp:
        frames = _sample_frames(video, 4, 96, Path(tmp))
        for a, b in _still_runs(frames, 0.25):
            rep.problems.append(f"{_fmt_t(a)}-{_fmt_t(b)} arası görüntü hiç değişmiyor (ölü an)")
    # the voice: does it say the script? (whisper on the delivered audio)
    try:
        from vlogkit.analysis.transcribe import transcribe

        heard = transcribe(video, "tr", words=True, vocab=False, cache=False)
    except Exception as ex:  # whisper missing: say so, do not fail the check
        rep.notes.append(f"seslendirme kontrolü yapılamadı ({ex.__class__.__name__})")
        heard = None
    if heard is not None:
        bad = []
        for b in beats:
            want = [plan.norm_word(w) for w in specmod.spoken(b.raw["say"]).split()]
            got = [plan.norm_word(h.text) for h in heard if b.t0 - 0.2 <= h.start < b.t1 + 0.2]
            # letters, not words: whisper writes "yeraltı" as "yer altı"
            ratio = difflib.SequenceMatcher(None, "".join(want), "".join(got)).ratio()
            if ratio < HEARD_OK and not re.search(r"\d", b.raw["say"]):
                bad.append(
                    f"beat {b.index + 1} (%{round(100 * ratio)}): {specmod.spoken(b.raw['say'])}"
                )
        if bad:
            rep.problems.append("seslendirme senaryodan ayrılıyor, dinle: " + " | ".join(bad))
        else:
            rep.notes.append("seslendirme senaryoyla eşleşiyor (whisper)")
    # loudness
    try:
        from vlogkit.analysis.loudness import measure

        loud = measure(video)
        rep.stats.update(lufs=round(loud.integrated, 1), true_peak=round(loud.true_peak, 1))
        if abs(loud.integrated + 14) > 1.0 or loud.true_peak > -1.0:
            rep.problems.append(f"ses seviyesi {loud} (hedef -14 LUFS, en fazla -1 dBTP)")
        else:
            rep.notes.append(f"ses seviyesi {loud}")
    except Exception as ex:
        rep.notes.append(f"ses seviyesi ölçülemedi ({ex.__class__.__name__})")
    return rep


# --------------------------------------------------------------------------- the blind rater
RUBRIC = [
    ("kanca", "İlk 2-3 saniye: kaydırıp geçmeyi durduruyor mu? Soru/olay hemen var mı?"),
    ("merak", "Hikâye bir sonraki adımı merak ettiriyor mu (açık döngüler, tırmanış, ödül)?"),
    (
        "olay",
        "Anlatılan her cümle ekranda bir olay olarak görülüyor mu (sadece duran görüntü değil)?",
    ),
    (
        "goruntu",
        "Görüntü kalitesi ve tutarlılık: ışık, kadraj, ölçek, okunurluk, amatörlük izi var mı?",
    ),
    ("tempo", "Tempo: plan değişimleri, boşluk/ölü an, uzunluk formata uygun mu?"),
    ("anlasilir", "Sesi kapalı da anlaşılıyor mu: altyazı, sahne yazıları, sayaç?"),
    ("paylasim", "Sonunda yorum/paylaşım isteği doğuruyor mu; kanal bu videoyla takip edilir mi?"),
]


def _sheet(video: Path, out: Path, every: float = 2.0) -> Path:
    """Frames every `every` seconds, labelled with their time, in one image."""
    from PIL import Image, ImageDraw

    from vlogkit.graphics.style import font

    with tempfile.TemporaryDirectory() as tmp:
        frames = _sample_frames(video, 1 / every, 270, Path(tmp))
        if not frames:
            raise RuntimeError("videodan kare alınamadı")
        w, h = Image.open(frames[0]).size
        cols = 8
        rows = (len(frames) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * w, rows * h), "#000")
        d = ImageDraw.Draw(sheet)
        for i, f in enumerate(frames):
            x, y = (i % cols) * w, (i // cols) * h
            sheet.paste(Image.open(f).convert("RGB"), (x, y))
            d.rectangle((x, y, x + 64, y + 26), fill="#000")
            d.text(
                (x + 6, y + 4), f"{i * every:.0f} sn", font=font("ExtraBold", 16), fill="#ffd23f"
            )
    sheet.save(out, quality=84)
    return out


def rate(e, video: Path, report: Report | None = None) -> dict:
    """A fresh Claude session scores the video blind (frames, narration, numbers only)."""
    from vlogkit.config import tools
    from vlogkit.ui.runner import subscription_env

    claude = tools().claude
    if not claude:
        raise RuntimeError("claude CLI bulunamadı (Claude Code kurulu mu?)")
    work = Path(tempfile.mkdtemp(prefix="vk-puan-"))
    try:
        sheet = _sheet(video, work / "kareler.jpg")
        f = formats.get(e.spec)
        narration = "\n".join(specmod.spoken(b.raw["say"]) for b in e.beats)
        stats = json.dumps((report.stats if report else {}), ensure_ascii=False)
        rows = "\n".join(f"- {k}: {q}" for k, q in RUBRIC)
        prompt = f"""Sen kör bir video puanlayıcısısın. Instagram Reels / TikTok / YouTube Shorts için
yapılmış dikey bir 3B Türkçe videoyu, izleyicinin göreceği şeylerden puanlayacaksın. Videoyu
yapan kişiyi tanımıyorsun; nazik değil, dürüst ve kısa ol. Yüksek puan nadirdir: 10 yalnızca
milyonlarca izlenen en iyi örnekler içindir, ortalama bir video 5 alır.

Format: {f["title"]}: {f["line"]}.
Kareler (her 2 saniyede bir, sol üstte saniye): {sheet} (Read ile aç).
Sayılar: {stats}

Anlatım (sırasıyla):
{narration}

Her satıra 1-10 puan ver:
{rows}

Yalnızca şu JSON'u yaz, başka hiçbir şey yazma:
{{"puanlar": {{"kanca": n, "merak": n, "olay": n, "goruntu": n, "tempo": n, "anlasilir": n, "paylasim": n}},
 "toplam": n, "en_zayif": "tek cümle", "duzeltmeler": ["en etkili 3 düzeltme, somut"]}}"""
        r = subprocess.run(
            [claude, "-p", "--output-format", "json", "--allowedTools", "Read",
             "--add-dir", str(work)],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=subscription_env(),
            cwd=work,
            timeout=600,
        )  # fmt: skip
        if r.returncode != 0:
            raise RuntimeError("puanlayıcı çalışmadı: " + (r.stderr or r.stdout).strip()[-400:])
        text = json.loads(r.stdout).get("result", "")
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise RuntimeError("puanlayıcı JSON vermedi: " + text[:300])
        out = json.loads(m.group(0))
        scores = out.get("puanlar", {})
        out["toplam"] = sum(int(v) for v in scores.values())
        out["en_fazla"] = 10 * len(RUBRIC)
        return out
    finally:
        shutil.rmtree(work, ignore_errors=True)
