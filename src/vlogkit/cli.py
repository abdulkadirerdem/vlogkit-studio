"""`vlogkit` command line. Run `uv run vlogkit --help`."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Annotated

import typer

from vlogkit import __version__
from vlogkit.config import BUILD_DIR, FONTS_DIR, LIBRARY_DIR, PROJECTS_DIR, VLOGS_ROOT, tools

app = typer.Typer(
    help="Vlog kurgu araç seti: analiz, build, önizleme, kontrol.",
    no_args_is_help=True,
    add_completion=False,
)
assets_app = typer.Typer(
    help="Üçüncü taraf medya kütüphanesi (manifest.toml).", no_args_is_help=True
)
app.add_typer(assets_app, name="assets")
extras_app = typer.Typer(
    help="İsteğe bağlı dış araçlar (DeepFilterNet, Demucs).", no_args_is_help=True
)
app.add_typer(extras_app, name="extras")


def _ok(flag: bool) -> str:
    return "✅" if flag else "❌"


@app.command()
def version() -> None:
    """Sürümü yaz."""
    typer.echo(__version__)


@app.command()
def doctor() -> None:
    """Gerekli araçların, modelin, fontların ve kütüphanenin durumunu kontrol et."""
    import subprocess

    t = tools()
    filters = ""
    if t.ffmpeg:
        filters = subprocess.run(
            [t.ffmpeg, "-hide_banner", "-filters"], capture_output=True, text=True
        ).stdout
    need = ("drawtext", "scdet", "loudnorm")
    rows = [
        ("ffmpeg", bool(t.ffmpeg), t.ffmpeg or "brew install ffmpeg-full"),
        (
            "ffmpeg filtreleri (drawtext, scdet, loudnorm)",
            all(f" {n} " in filters for n in need),
            "ffmpeg-full gerekli (normal ffmpeg'de yok)",
        ),
        ("ffprobe", bool(t.ffprobe), t.ffprobe or "ffmpeg-full ile gelir"),
        ("whisper-cli", bool(t.whisper_cli), t.whisper_cli or "brew install whisper-cpp"),
        ("whisper modeli", t.whisper_model.exists(), str(t.whisper_model)),
        ("aubio", bool(t.aubio), t.aubio or "brew install aubio"),
        (
            "claude (Claude Code, vlogkit ui için)",
            bool(t.claude),
            t.claude or "claude.ai/code -> kurulum",
        ),
        ("fontlar", any(FONTS_DIR.glob("Montserrat-*.ttf")), str(FONTS_DIR)),
        ("emoji fontu", Path("/System/Library/Fonts/Apple Color Emoji.ttc").exists(), "macOS"),
    ]
    from vlogkit import assets

    m = assets.manifest()
    have = sum(a.path.exists() for a in m.values())
    rows.append(
        (
            "medya kütüphanesi",
            have == len(m),
            f"{have}/{len(m)} dosya ({LIBRARY_DIR}) -> vlogkit assets fetch",
        )
    )
    for name, ok, detail in rows:
        typer.echo(f"{_ok(ok)} {name:<48} {detail}")
    from vlogkit import extras
    from vlogkit.analysis import ocr

    typer.echo("\nİsteğe bağlı araçlar:")
    for name, path in extras.status().items():
        typer.echo(f"{_ok(bool(path))} {name:<48} {path or f'vlogkit extras install {name}'}")
    typer.echo(f"{_ok(ocr.available())} {'Vision OCR (yazı tanıma, macOS)':<48} swiftc + tools/ocr")
    typer.echo(f"\nvlogs kökü: {VLOGS_ROOT}\nbuild: {BUILD_DIR}")


@app.command()
def analyze(
    video: Path,
    out: Annotated[Path | None, typer.Option(help="Rapor klasörü")] = None,
    lang: str = "tr",
    speech: bool = True,
    music: bool = True,
) -> None:
    """Kesmeler, loş bölgeler, loudness, konuşma, vuruşlar + kontak sayfası -> report.md."""
    from vlogkit.analysis.report import analyze as run

    out = out or BUILD_DIR / "analysis" / video.stem
    path = run(video, out, lang=lang, speech=speech, music=music)
    typer.echo(path.read_text())
    typer.echo(f"-> {out}")


@app.command()
def sheet(
    video: Path,
    start: float = 0.0,
    duration: Annotated[float | None, typer.Option(help="Varsayılan: sonuna kadar")] = None,
    fps: float = 1.0,
    cols: int = 10,
    out: Path | None = None,
) -> None:
    """Zaman damgalı kontak sayfası (videoya bakmanın en hızlı yolu)."""
    from vlogkit.analysis.sheets import contact_sheet

    out = out or BUILD_DIR / "sheets" / f"{video.stem}_{start:g}.jpg"
    out.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(contact_sheet(video, out, start=start, duration=duration, fps=fps, cols=cols))


@app.command()
def frame(
    video: Path,
    at: Annotated[list[float], typer.Option("--at", "-t", help="Saniye (tekrarlanabilir)")],
    grid: Annotated[bool, typer.Option(help="0-1 koordinat ızgarası çiz")] = True,
    width: Annotated[int, typer.Option(help="Görüntü genişliği (px)")] = 1280,
) -> None:
    """Tek bir kareyi büyük göster: zaman, kare numarası, kaynak boyutu ve koordinat ızgarası.
    Kırpma, yüz konumu ve grafik yerleşimi için koordinatı tahmin etme, buradan oku."""
    from vlogkit.analysis.sheets import frame_image

    for t in at:
        out = BUILD_DIR / "frames" / f"{video.stem}_{t:.3f}.png"
        try:
            typer.echo(frame_image(video, t, out, width=width, grid=grid))
        except ValueError as e:
            raise typer.BadParameter(str(e)) from e


@app.command()
def strip(
    video: Path,
    start: Annotated[float, typer.Option(help="Başlangıç (sn)")] = 0.0,
    end: Annotated[float | None, typer.Option(help="Bitiş (sn); varsayılan başlangıç + 20")] = None,
    mark: Annotated[
        list[float] | None, typer.Option("--mark", "-m", help="Kırmızı çizgi (kesme adayı, sn)")
    ] = None,
    lang: str = "tr",
) -> None:
    """Kesme kararı için tek görsel: 10 kare + ses dalgası + sessiz bantlar + kelimeler (whisper).
    Kelimenin bittiği, nefesin ve sonraki cümlenin başladığı yer buradan okunur."""
    from vlogkit.analysis.strip import strip as run

    end = end if end is not None else start + 20
    out = BUILD_DIR / "strips" / f"{video.stem}_{start:g}-{end:g}.png"
    try:
        typer.echo(run(video, out, start, end, lang=lang, marks=mark or ()))
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


@app.command()
def transcribe(
    video: Path,
    lang: str = "tr",
    words: Annotated[bool, typer.Option(help="Kelime bazlı zamanlar (karaoke için)")] = False,
    start: float = 0.0,
    duration: float | None = None,
    beam: Annotated[int | None, typer.Option(help="Beam search genişliği (ör. 5)")] = None,
    no_context: Annotated[
        bool,
        typer.Option("--no-context", help="Pencereleri bağımsız çöz (müzikte tekrar döngüsü)"),
    ] = False,
    prompt: Annotated[str | None, typer.Option(help="İpucu metni (yazı/dil yönlendirme)")] = None,
    vocab: Annotated[
        bool, typer.Option(help="assets/vocab.txt'deki özel adları ipucu olarak ver")
    ] = True,
) -> None:
    """whisper.cpp ile konuşmayı yazıya dök (önbellekli: aynı dosya ikinci kez çözülmez)."""
    from vlogkit.analysis.transcribe import transcribe as run

    segs = run(
        video,
        lang,
        words=words,
        start=start,
        duration=duration,
        beam=beam,
        no_context=no_context,
        prompt=prompt,
        vocab=vocab,
    )
    for s in segs:
        flag = "  ⚠️ halüsinasyon?" if s.suspicious else ""
        typer.echo(f"{s.start:7.2f} – {s.end:7.2f}  {s.text}{flag}")


@app.command()
def projects() -> None:
    """Projeleri listele."""
    from vlogkit.project import list_projects, load

    for name in list_projects():
        e = load(name)
        typer.echo(f"{name:<24} variants: {', '.join(e.variants)}")


@app.command()
def build(
    project: str,
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
    step: Annotated[
        list[str] | None,
        typer.Option("--step", "-s", help="base | overlay | audio | compose (tekrarlanabilir)"),
    ] = None,
    out: Annotated[Path | None, typer.Option(help="Çıktı dosyası (varsayılan: projedeki)")] = None,
) -> None:
    """Bir projeyi (veya seçili adımlarını) derle."""
    from vlogkit.disk import NoSpace
    from vlogkit.project import STEPS, load

    edit = load(project, variant, out)
    try:
        path = edit.run(step or STEPS)
    except NoSpace as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(1) from e
    typer.echo(f"✅ {path}")


@app.command()
def preview(
    project: str,
    at: Annotated[list[float], typer.Option("--at", "-t", help="Saniye (tekrarlanabilir)")],
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
    on_base: Annotated[bool, typer.Option(help="Varsa base.mov üstüne bindir")] = True,
    grid: Annotated[bool, typer.Option(help="0-1 koordinat ızgarası çiz (yerleşim için)")] = False,
) -> None:
    """Grafik katmanını belirli anlarda PNG olarak önizle."""
    from vlogkit.graphics.render import preview as run
    from vlogkit.project import load

    edit = load(project, variant)
    bg = edit.base_path if on_base and edit.base_path.exists() else None
    for p in run(edit.elements(), at, edit.ctx.work / "preview", bg, edit.layout.size, grid=grid):
        typer.echo(p)


@app.command()
def check(
    video: Path,
    cuts: Annotated[bool, typer.Option(help="Kesme zamanlarını da listele")] = False,
) -> None:
    """Teslim öncesi kontrol: çözünürlük, kare sayısı, süre, loudness (+ kesmeler)."""
    from vlogkit.analysis.loudness import measure
    from vlogkit.analysis.scenes import detect_cuts
    from vlogkit.ff import probe

    info = probe(video, count_frames=True)
    fps = f"{float(info.fps):.3f}" if info.fps else "?"
    typer.echo(
        f"{info.width}x{info.height} @ {fps} fps, {info.frames} kare, {info.duration:.3f} sn"
    )
    if info.has_audio:
        lo = measure(video)
        ok = abs(lo.integrated + 14) <= 1 and lo.true_peak <= -1.0
        typer.echo(f"{_ok(ok)} ses: {lo}  (hedef -14 LUFS, <= -1 dBTP)")
    if info.vertical and (info.width, info.height) != (1080, 1920):
        typer.echo("⚠️ dikey ama 1080x1920 değil")
    if cuts:
        typer.echo("kesmeler: " + " ".join(f"{c:.3f}" for c in detect_cuts(video)))


@app.command("log")
def log_cmd(
    paths: Annotated[list[Path], typer.Argument(help="Ham klasör ya da klipler")],
    out: Annotated[Path | None, typer.Option(help="Varsayılan: build/log/<klasör>")] = None,
    speech: Annotated[bool, typer.Option(help="Konuşmaları da yaz (whisper)")] = True,
    lang: str = "tr",
    vlm: Annotated[
        bool, typer.Option(help="Yerel video modeli her parçayı izleyip ne olduğunu yazsın (yavaş)")
    ] = False,
) -> None:
    """Kurgudan önce ham çekim kaydı: her klip parça parça (ne görünüyor, konuşma, kurulum/bulanık
    bayrakları) + tüm klibi kapsayan sayfalar. Claude notlarını log.json'a yazar. --vlm ile yerel
    model her parçayı 4 kare/sn izler ("model" sütunu); önbellekli, kesilirse kaldığı yerden."""
    from vlogkit.analysis import footage

    first = paths[0]
    name = first.name if first.is_dir() else first.parent.name
    out = out or BUILD_DIR / "log" / name
    lg = footage.log(
        paths[0] if len(paths) == 1 and first.is_dir() else paths,
        out,
        speech,
        lang,
        progress=lambda msg: typer.echo(f"  {msg}"),
        vlm=vlm,
    )
    usable = footage.selects(lg)
    flagged = sum(k.t1 - k.t0 for k in lg.chunks if k.flags)
    typer.echo(
        f"{len(lg.clips)} klip, {len(lg.chunks)} parça; bayraklı {flagged / 60:.1f} dk, "
        f"{len(usable)} kullanılabilir aralık"
    )
    described = sum(1 for k in lg.chunks if k.local)
    if described:
        typer.echo(f"yerel model: {described}/{len(lg.chunks)} parça açıklandı")
    typer.echo(f"-> {out / 'log.md'}\n-> {out / 'log.json'}\n-> {out / 'sheets'}")


@app.command()
def find(
    target: Annotated[Path, typer.Argument(help="Ham klasör (log'u olan) ya da log.json")],
    words: Annotated[list[str], typer.Argument(help="Aranan kelimeler; iki dilde ver: ateş fire")],
    limit: Annotated[int, typer.Option("-n", min=1, help="En fazla kaç sonuç")] = 12,
) -> None:
    """Ham çekimde anlamla arama: log'daki açıklama, hikâye adımı, yerel modelin cümlesi,
    Vision etiketleri ve konuşma içinde. Model sütunu İngilizce: kelimeleri iki dilde ver.
    Sonuçlar + her biri için 3 kare → build/find/."""
    from vlogkit.analysis import find as fd
    from vlogkit.analysis.footage import Log

    try:
        lg = Log.load(fd.log_path(target))
    except FileNotFoundError as e:
        raise typer.BadParameter(str(e)) from e
    hits = fd.search(lg, words, limit)
    if not hits:
        typer.echo("Sonuç yok. Başka kelime dene (iki dilde), ya da log'u --vlm ile zenginleştir.")
        return
    for k, h in enumerate(hits, 1):
        mark = "" if h.usable else "  [bayraklı]"
        typer.echo(
            f"{k:2}. {Path(h.clip).name}  {h.t0:7.2f}-{h.t1:7.2f} sn  "
            f"(en iyi {h.best[0]:.1f}-{h.best[1]:.1f})  {', '.join(h.matched)}{mark}"
        )
        typer.echo(f"     {h.snippet[:150]}")
    slug = "_".join(fd.norm(" ".join(words)))[:40] or "arama"
    typer.echo(f"-> {fd.frames_page(hits, BUILD_DIR / 'find' / f'{slug}.jpg')}")


@app.command()
def ask(
    video: Path,
    question: Annotated[
        str, typer.Argument(help="Soru, ör. 'Kapıdan dışarı çıkıyor mu, hangi saniyede?'")
    ],
    start: Annotated[float, typer.Option(help="Aralığın başı (sn)")] = 0.0,
    end: Annotated[float | None, typer.Option(help="Aralığın sonu (sn); en fazla 60 sn")] = None,
    face: Annotated[
        bool, typer.Option(help="Yüzü takip eden yakın planı göster (mimik, tepki)")
    ] = False,
) -> None:
    """Bir video aralığı hakkında yerel video modeline soru sor (4 kare/sn izler). Aday anı
    doğrulamak için: yön, eylem, tam saniye. Cevap İngilizce olabilir; son kararı sayfaya bakarak ver."""
    from vlogkit.analysis import localvlm

    _need_vlm(localvlm)
    try:
        typer.echo(
            localvlm.ask(video, start, end if end is not None else start + 30, question, face=face)
        )
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e


def _need_vlm(localvlm) -> None:
    if not localvlm.available():
        raise typer.BadParameter(
            "yerel video modeli kurulu değil: uv run vlogkit extras install vlm"
        )


@app.command()
def face(
    video: Path,
    start: Annotated[float, typer.Option(help="Aralığın başı (sn)")] = 0.0,
    end: Annotated[float | None, typer.Option(help="Aralığın sonu (sn); en fazla 30 sn")] = None,
    as_json: Annotated[bool, typer.Option("--json", help="Ham JSON yaz")] = False,
) -> None:
    """Kameraya konuşan kişinin mimiği: yüzü takip eden yakın plan yerel modele gösterilir.
    İfade, enerji, gülümseme/gülme, kameraya bakış, tuhaflık ve anlar. Sesi duymaz: ton ve
    espri için transcript'e bak. Aynı satırın denemelerini karşılaştırmak için."""
    import json

    from vlogkit.analysis import localvlm

    _need_vlm(localvlm)
    try:
        r = localvlm.expression(video, start, end if end is not None else start + 15)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    if as_json:
        typer.echo(json.dumps(r, ensure_ascii=False, indent=2))
        return
    yn = {True: "evet", False: "hayır"}
    energy = {"low": "düşük", "medium": "orta", "high": "yüksek"}.get(r["energy"], r["energy"])
    typer.echo(f"ifade: {r['expression']}")
    typer.echo(
        f"enerji: {energy or '?'}, gülümseme: {yn[r['smile']]}, gülme: {yn[r['laugh']]}, "
        f"kameraya bakış: {yn[r['eye_contact']]}, tuhaf: {yn[r['awkward']]}"
    )
    for m in r["moments"]:
        typer.echo(f"  {m}")
    typer.echo(f"(yüz bulunan kare: {r['faces_found']}; anların saniyeleri yaklaşık)")


@app.command()
def gaps(
    video: Path,
    lang: str = "tr",
    min_pause: Annotated[float, typer.Option(help="Bu kadar uzun duraklar kesilir (sn)")] = 0.45,
    pad: Annotated[float, typer.Option(help="Kesmenin iki yanında bırakılan nefes (sn)")] = 0.12,
    soft: Annotated[
        bool, typer.Option(help="'yani', 'şey' gibi anlamlı olabilenleri de kes")
    ] = False,
    silence: Annotated[bool, typer.Option(help="silencedetect de kullan (müzikte kapat)")] = True,
) -> None:
    """Konuşmadaki boşlukları ve dolgu kelimeleri bul (kesme adayları, onay için)."""
    import json
    from dataclasses import asdict

    from vlogkit.analysis.speech import find_cuts, keep_segments, saved
    from vlogkit.ff import probe

    cuts = find_cuts(video, lang, min_pause=min_pause, pad=pad, silence=silence)
    for c in cuts:
        tag = {"pause": "duraklama", "filler": "dolgu", "quiet": "konuşmasız"}[c.kind]
        tag += " (isteğe bağlı)" if c.soft else ""
        typer.echo(f"{c.start:8.2f} – {c.end:8.2f}  {c.duration:5.2f} sn  {tag:<8} {c.text}")
    dur = probe(video).duration
    keep = keep_segments(dur, cuts, include_soft=soft)
    typer.echo(
        f"{len(cuts)} aday, {saved(cuts, soft):.1f} sn kazanç "
        f"({dur:.1f} -> {sum(b - a for a, b in keep):.1f} sn)"
    )
    out = BUILD_DIR / "analysis" / video.stem / "gaps.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"cuts": [asdict(c) for c in cuts], "keep": keep}, indent=1))
    typer.echo(f"-> {out}  (edit.py: speech.keep_segments + video.jumpcut)")


@app.command()
def thumbs(
    video: Path,
    text: Annotated[
        str, typer.Option(help="Kapak yazısı: 3-5 kelime, satır için \\n, \\[vurgu]")
    ] = "",
    n: Annotated[int, typer.Option("-n", help="Kaç aday")] = 3,
    at: Annotated[
        list[float] | None, typer.Option("--at", "-t", help="Kareyi elle seç (sn)")
    ] = None,
    out: Path | None = None,
) -> None:
    """Kapak adayları: en net/renkli kareler + kapak yazısıyla hazır kapaklar."""
    from vlogkit.analysis import thumbs as th
    from vlogkit.graphics.thumbnail import compose
    from vlogkit.graphics.thumbnail import sheet as thumbs_sheet

    out = out or BUILD_DIR / "thumbs" / video.stem
    frames = [th.Frame(t, 0, 0, 0) for t in at] if at else th.pick(th.score(video), n)
    pngs = th.extract(video, frames, out)
    if len(text.split()) > 5:
        typer.echo("⚠️ kapak yazısı 5 kelimeden uzun: 1,5 sn'de okunmaz")
    made = [
        compose(png, text.replace("\\n", "\n"), out / f"kapak_{i}.jpg")
        for i, png in enumerate(pngs, 1)
    ]
    for f, path in zip(frames, made, strict=True):
        typer.echo(f"{f.t:7.2f} sn  {path}")
    typer.echo(f"-> {thumbs_sheet(made, out / 'kapaklar.jpg')}")


@app.command()
def review(
    video: Annotated[Path | None, typer.Argument(help="Varsayılan: projenin çıktısı")] = None,
    project: Annotated[str | None, typer.Option("--project", "-p")] = None,
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
    kind: Annotated[str | None, typer.Option(help="short | long (varsayılan: en-boydan)")] = None,
    promise: Annotated[str, typer.Option(help="Vaat kelimeleri, virgülle: 'zirve,5 saat'")] = "",
    lang: str = "tr",
    speech: bool = True,
    cut_checks: Annotated[
        bool, typer.Option("--cuts/--no-cuts", help="Kesme kontrolleri ve kesme sayfaları")
    ] = True,
) -> None:
    """Teslim öncesi izlenme süresi kontrolü: kanca, tempo, kesmeler, bitiş/loop, ses, yazı."""
    from vlogkit.analysis.review import review as run

    elements = cuts = None
    if project:
        from vlogkit.project import load

        edit = load(project, variant)
        same = video is None or Path(video).resolve() == edit.output_path.resolve()
        video = video or edit.output_path
        elements = edit.elements()
        cuts = edit.cuts() if same else None  # the project's exact cuts fit its own output only
    if not video:
        raise typer.BadParameter("video ya da --project ver")
    keys = [p.strip() for p in promise.split(",") if p.strip()]
    text, out = run(
        video,
        kind,
        elements=elements,
        promise=keys,
        lang=lang,
        speech=speech,
        cuts=cuts,
        cut_checks=cut_checks,
    )
    typer.echo(text)
    typer.echo(f"-> {out}")


@app.command()
def moments(
    video: Path,
    lang: str = "tr",
    min_len: Annotated[float, typer.Option("--min", help="En kısa aday (sn)")] = 15.0,
    max_len: Annotated[float, typer.Option("--max", help="En uzun aday (sn)")] = 60.0,
) -> None:
    """Uzun videodan Short adayları: konuşma paragraflarından 15-60 sn'lik pencereler, açılış
    cümlesi, konuşma yoğunluğu, en yüksek ses, hareket ve kare sayfaları. Puan vermez: sen
    Kanca/Akış/Değer (1-5) ile sıralarsın (docs/viral-edit.md)."""
    from vlogkit.analysis import moments as mo

    try:
        found = mo.find(video, lang, min_len, max_len)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    out = BUILD_DIR / "analysis" / video.stem
    md, pages = mo.write(found, video, out)
    typer.echo(f"{len(found)} aday")
    typer.echo(f"-> {md}")
    for p in pages:
        typer.echo(f"-> {p}")


@app.command()
def captions(
    video: Annotated[
        Path | None, typer.Option(help="Arka plan için video (varsayılan: gri)")
    ] = None,
    at: Annotated[float, typer.Option("--at", "-t", help="Arka plan karesi (sn)")] = 1.0,
    text: Annotated[
        str, typer.Option(help="Örnek yazı; \\[köşeli parantez] vurgulanır")
    ] = "Göle [5 saat] kaldı",
    landscape: Annotated[bool, typer.Option(help="Yatay (16:9) düzende göster")] = False,
) -> None:
    """Altyazı stilleri galerisi: pop, kutu, sade, karaoke, büyük; platformun kapattığı
    bölgeler kırmızı. Kullanıcıya göster, seçtiği stili projede `captions.styled` ile kullan."""
    from PIL import Image

    from vlogkit.graphics.captions import STYLES, gallery
    from vlogkit.graphics.style import LANDSCAPE, VERTICAL

    bg = None
    if video:
        from vlogkit.ff import extract_frame

        frame = BUILD_DIR / "captions" / f"_{video.stem}_{at:g}.png"
        frame.parent.mkdir(parents=True, exist_ok=True)
        extract_frame(video, at, frame)
        bg = Image.open(frame)
        landscape = landscape or bg.width > bg.height
    out = BUILD_DIR / "captions" / f"galeri{'_' + video.stem if video else ''}.jpg"
    for name, (desc, _) in STYLES.items():
        typer.echo(f"{name:<8} {desc}")
    typer.echo(f"-> {gallery(out, bg, text, LANDSCAPE if landscape else VERTICAL)}")


@app.command()
def beats(song: Path) -> None:
    """Şarkının yapısı: BPM, ölçü başları, ölçü başına enerji, drop'lar (ritme göre kurgu için)."""
    import json
    from dataclasses import asdict

    from vlogkit.analysis.music import analyze, report

    m = analyze(song)
    for line in report(m):
        typer.echo(line)
    out = BUILD_DIR / "analysis" / song.stem / "music.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    d = asdict(m) | {"path": str(m.path)}
    out.write_text(json.dumps(d, indent=1))
    typer.echo(f"-> {out}")


@app.command()
def music(
    video: Annotated[Path, typer.Argument(help="Sahnenin videosu (kurgu ya da ham klip)")],
    tracks: Annotated[
        list[str],
        typer.Option(
            "--track", "-t", help="Kütüphane id'si ya da dosya; başlangıç: id@42 (id@0 baştan)"
        ),
    ],
    start: Annotated[float, typer.Option("--start", "-s", help="Sahne başlangıcı (sn)")] = 0.0,
    duration: Annotated[float, typer.Option("--duration", "-d", help="Sahne süresi (sn)")] = 30.0,
    level: Annotated[
        float, typer.Option(help="Müzik seviyesi (LUFS); konuşmasız sahnede -16 civarı")
    ] = -20.0,
    sound: Annotated[
        bool, typer.Option(help="Sahnenin kendi sesi (içinde eski müzik varsa --no-sound)")
    ] = True,
) -> None:
    """Aday müzikleri sahnenin altında dinlet: parça başına önizleme + kullanıcıya Seçim bloğu."""
    from vlogkit.audio import audition

    try:
        picks = [audition.parse(t) for t in tracks]
        a = audition.audition(video, picks, start, duration, level, sound=sound)
    except (ValueError, FileNotFoundError) as e:
        raise typer.BadParameter(str(e)) from e
    for p in a.previews:
        typer.echo(
            f"{p.path.name}: {p.track.path.name} {p.offset:g} sn'den {p.track.page}".rstrip()
        )
    typer.echo("\nSon mesaja ekle (kullanıcı dinleyip seçer):\n")
    typer.echo(a.block())


@app.command()
def reel(
    song: Path,
    clips: Annotated[list[Path], typer.Argument(help="Kaynak klipler, kronolojik sırayla")],
    start: Annotated[
        float | None,
        typer.Option(help="Şarkıda başlangıç (sn); yoksa drop ~2,5 sn'ye gelecek şekilde"),
    ] = None,
    length: Annotated[float, typer.Option(help="Süre (sn), ölçü sonuna yuvarlanır")] = 20.0,
    lead: Annotated[float, typer.Option(help="Otomatik başlangıçta drop'tan önceki süre")] = 2.5,
    name: Annotated[str | None, typer.Option(help="Çıktı adı (varsayılan <klasör>_Reel)")] = None,
    out_dir: Annotated[Path | None, typer.Option(help="Varsayılan: ilk klibin klasörü")] = None,
    plan_file: Annotated[
        Path | None, typer.Option("--plan", help="Düzenlenmiş plan.json ile yeniden derle")
    ] = None,
    seed: int = 0,
    ocr: Annotated[bool, typer.Option(help="Gömülü yazılı anları atla (Vision OCR)")] = True,
    dry_run: Annotated[bool, typer.Option(help="Sadece planı göster")] = False,
    bpm: Annotated[
        float | None,
        typer.Option(help="Şarkı dosyası yoksa: tempo (ŞARKI o zaman sadece şarkının adı)"),
    ] = None,
    energy: Annotated[
        str | None,
        typer.Option("--map", help="--bpm ile: ölçü başına enerji, ör. '....--##D###' (. - # D)"),
    ] = None,
    first_beat: Annotated[float, typer.Option(help="--bpm ile: ilk ölçü başı (sn)")] = 0.0,
    hook: Annotated[
        str | None, typer.Option(help="Kanca başlığı: ilk saniyelerde üstte tek satır vaat")
    ] = None,
) -> None:
    """Müziğe göre montaj (Reels/Shorts): kesmeler vuruşta, en iyi anlar drop'ta; müzikli + müziksiz çıktı."""
    from vlogkit.analysis.music import analyze, grid
    from vlogkit.video import beatcut

    first = clips[0] if clips else None
    name = name or (f"{first.parent.name}_Reel" if first else "Reel")
    out = (out_dir or (first.parent if first else Path.cwd())) / f"{name}.mp4"
    work = BUILD_DIR / "reels" / name
    tempo = None
    if bpm:
        if not energy:
            raise typer.BadParameter("--bpm ile --map de gerekli (ör. '....--##D###')")
        tempo = {"bpm": bpm, "energy": energy, "first_downbeat": first_beat, "path": str(song)}
    if plan_file:
        plan = beatcut.Plan.load(plan_file)
    else:
        music = grid(**tempo) if tempo else analyze(song)
        typer.echo(
            f"müzik: {music.bpm:g} BPM, drop: {', '.join(f'{d:.2f}' for d in music.drops) or 'yok'}"
        )
        sources = [beatcut.moments(c, use_ocr=ocr) for c in clips]
        if start is None:
            start, length = beatcut.auto_start(music, lead=lead, length=length)
        plan = beatcut.plan(music, sources, start, length, seed=seed)
        plan.grid = tempo
    if hook is not None:
        plan.hook = hook
    for line in beatcut.summary(plan):
        typer.echo(line)
    work.mkdir(parents=True, exist_ok=True)
    plan.save(work / "plan.json")
    if dry_run:
        typer.echo(f"-> {work / 'plan.json'}")
        return
    made = beatcut.render(plan, work, out)
    for key in ("video", "silent", "note", "plan"):
        typer.echo(f"-> {made[key]}")


@extras_app.command("list")
def extras_list() -> None:
    """Kurulu mu, nerede?"""
    from vlogkit import extras

    for name, path in extras.status().items():
        typer.echo(f"{_ok(bool(path))} {name:<12} {path or ''}")


@extras_app.command("install")
def extras_install(name: str) -> None:
    """Kur: deepfilter (~28 MB), demucs (~0,5 GB + model) ya da vlm (yerel video modeli, ~6 GB)."""
    from vlogkit import extras

    typer.echo(f"✅ {extras.install(name)}")


@app.command("match-color")
def match_color(
    video: Path,
    ref: Annotated[Path, typer.Option("--ref", help="Referans: resim ya da video")],
    ref_at: Annotated[
        float | None, typer.Option("--ref-at", help="Referans videoda saniye (yoksa 5 kare)")
    ] = None,
    at: Annotated[
        list[float] | None,
        typer.Option("--at", "-t", help="Hedefte ölçülecek saniye (tekrarlanabilir; yoksa 5 kare)"),
    ] = None,
    strength: Annotated[float, typer.Option(help="0 = değişmez, 1 = tam eşleme")] = 0.8,
    out: Annotated[Path | None, typer.Option(help=".cube yolu")] = None,
) -> None:
    """Planın rengini referans kareye uydur -> 3D LUT (.cube) + önce/sonra görseli.
    Grade zincirinde Grade'den önce: `colormatch.lut_filter(cube)`."""
    from vlogkit.video import colormatch

    if not 0 <= strength <= 1:
        raise typer.BadParameter("--strength 0-1 arası olmalı")
    name = f"{video.stem}_{ref.stem}" + (f"_{ref_at:g}s" if ref_at is not None else "")
    out = out or BUILD_DIR / "color" / f"{name}.cube"
    try:
        r = colormatch.match(video, ref, out, at=at, ref_at=ref_at, strength=strength)
    except (ValueError, FileNotFoundError) as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(f"✅ {r['cube']}")
    typer.echo(f"önizleme: {r['preview']}")
    typer.echo(r["summary"])


@app.command()
def stabilize(
    video: Path,
    preset: Annotated[str, typer.Option(help="running | walking | tripod-ish")] = "running",
    start: float = 0.0,
    duration: Annotated[float | None, typer.Option(help="Varsayılan: sonuna kadar")] = None,
    out: Path | None = None,
) -> None:
    """Titrek el çekimini sabitle (vid.stab, 2 geçiş) -> ProRes HQ. Sadece ham, yazısız görüntüye."""
    from vlogkit.video.stabilize import stabilize as run

    out = out or BUILD_DIR / "stabilize" / f"{video.stem}_{preset}.mov"
    out.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"✅ {run(video, out, preset, start=start, duration=duration)}")


@app.command()
def background(
    video: Path,
    bg: Annotated[
        str,
        typer.Option(
            "--bg",
            help="studio[:#renk] | keep[:#renk][:güç] | #renk | gradient:#üst,#alt | resim.jpg"
            " | klip.mp4 ya da klip.mp4@sn | frame:klip.mp4@sn",
        ),
    ] = "studio",
    start: float = 0.0,
    duration: Annotated[float | None, typer.Option(help="Varsayılan: sonuna kadar")] = None,
    blur: Annotated[float, typer.Option(help="Arka planı bulanıklaştır (1080p px, ör. 20)")] = 0.0,
    feather: Annotated[float, typer.Option(help="Kenar yumuşaklığı (1080p px)")] = 2.5,
    match: Annotated[bool, typer.Option(help="Kişinin ışık/rengini arkaya hafifçe uydur")] = False,
    mode: Annotated[str, typer.Option(help="Maske: hybrid | fg | accurate | balanced")] = "hybrid",
    out: Path | None = None,
) -> None:
    """Konuşan kafanın arkasını değiştir/güzelleştir (Apple Vision maskesi) -> ProRes HQ 10-bit."""
    from vlogkit.video import background as bgmod

    if not bgmod.available():
        raise typer.BadParameter("Vision maskesi macOS + swiftc (Xcode CLT) ister")
    if mode not in bgmod.MODES:
        raise typer.BadParameter(f"--mode: {' | '.join(bgmod.MODES)}")
    try:
        spec = bgmod.parse_spec(bg)
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    name = f"{video.stem}_{spec.kind}" + (f"_{start:g}s" if start else "")
    out = out or BUILD_DIR / "background" / f"{name}.mov"
    kw = {"blur": blur, "feather": feather, "match": match, "mode": mode}
    typer.echo(f"✅ {bgmod.replace(video, out, spec, start=start, duration=duration, **kw)}")


@app.command()
def redact(
    video: Path,
    faces: Annotated[
        bool, typer.Option("--faces", help="Yüzleri bul ve gizle (Apple Vision)")
    ] = False,
    keep_main: Annotated[
        bool,
        typer.Option("--keep-main", help="--faces ile: en büyük, ortadaki yüz (sen) açık kalsın"),
    ] = False,
    box: Annotated[
        list[str] | None,
        typer.Option(
            "--box",
            help="Takip edilecek şey: x,y,en,boy@sn (0-1, sol üst köşe; `frame` ızgarasından oku)."
            " Tekrarlanabilir",
        ),
    ] = None,
    mode: Annotated[
        str, typer.Option(help="blur (gizle) | spotlight (vurgula, gerisi kararır)")
    ] = "blur",
    start: float = 0.0,
    duration: Annotated[float | None, typer.Option(help="Varsayılan: sonuna kadar")] = None,
    strength: Annotated[
        float | None,
        typer.Option(help="blur: bulanıklık, 1080p px (30); spotlight: karartma 0-1 (0.5)"),
    ] = None,
    min_size: Annotated[
        float, typer.Option(help="Bundan küçük yüzleri atla (kare yüksekliğine oran, ör. 0.03)")
    ] = 0.0,
    out: Path | None = None,
) -> None:
    """Hareket eden bir şeyi gizle ya da vurgula: yabancı yüzler, plaka (blur) ya da tek kişiye
    spot ışığı (spotlight). Apple Vision takibi -> ProRes HQ 10-bit."""
    from vlogkit.video import redact as rd

    if not rd.available():
        raise typer.BadParameter("Vision takibi macOS + swiftc (Xcode CLT) ister")
    if mode not in rd.MODES:
        raise typer.BadParameter(f"--mode: {' | '.join(rd.MODES)}")
    if not faces and not box:
        raise typer.BadParameter("--faces ya da en az bir --box ver")
    if keep_main and not faces:
        raise typer.BadParameter("--keep-main yalnız --faces ile çalışır")
    try:
        boxes = [rd.parse_box(b) for b in box or []]
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    end = start + duration if duration else None
    for _, at in boxes:
        if at < start or (end is not None and at >= end):
            raise typer.BadParameter(
                f"--box zamanı ({at:g} sn) --start/--duration aralığında olmalı"
            )
    tracks, everyone = [], []
    if faces:
        found = rd.faces(video, start, duration, min_size=min_size, keep_main=keep_main)
        note = ""
        if keep_main:
            everyone = rd.faces(video, start, duration, min_size=min_size)  # önbellekten
            note = " (senin yüzün hariç)" if len(everyone) > len(found) else " (ana yüz yok: hepsi)"
        typer.echo(f"Yüz: {len(found)} iz{note}")
        tracks += found
    for b, at in boxes:
        tr = rd.track(video, b, at, end)
        lost = f", {tr.lost:.1f} sn'de kayboldu" if tr.lost is not None else ""
        typer.echo(f"Kutu @{at:g}: {tr.t0:.1f}-{tr.t1:.1f} sn takip edildi{lost}")
        tracks.append(tr)
    if not tracks:
        typer.echo(
            "Bu aralıkta senin yüzün dışında yüz yok, çıktı yazılmadı."
            if faces and keep_main and everyone
            else "Bu aralıkta yüz bulunamadı, çıktı yazılmadı."
        )
        raise typer.Exit(1)
    name = f"{video.stem}_{mode}" + (f"_{start:g}s" if start else "")
    out = out or BUILD_DIR / "redact" / f"{name}.mov"
    try:
        path = rd.render(
            video, out, tracks, mode, start=start, duration=duration, strength=strength
        )
    except ValueError as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(f"✅ {path}")


@app.command()
def denoise(
    video: Path,
    atten: Annotated[
        float | None, typer.Option(help="En fazla şu kadar dB bastır (18-25 ortam sesini korur)")
    ] = 20.0,
    start: float = 0.0,
    duration: float | None = None,
    out: Path | None = None,
) -> None:
    """Konuşma sesini temizle (DeepFilterNet): rüzgâr, nefes, uğultu -> 48 kHz WAV."""
    from vlogkit.audio.denoise import deepfilter

    out = out or BUILD_DIR / "denoise" / f"{video.stem}.wav"
    out.parent.mkdir(parents=True, exist_ok=True)
    kw = {"start": start, "duration": duration} if duration else {"start": start}
    typer.echo(f"✅ {deepfilter(video, out, atten, **kw)}")


@app.command()
def sync(
    ref: Annotated[Path, typer.Argument(help="Referans kayıt (genelde kamera)")],
    others: Annotated[
        list[Path], typer.Argument(help="Aynı anın diğer kayıtları (telefon, 2. kamera)")
    ],
    max_offset: Annotated[
        float | None, typer.Option(help="En fazla bu kadar sn kayık ara (biliniyorsa)")
    ] = None,
) -> None:
    """Kayıtları sesinden eşle: diğer kaydın 0. saniyesi referansta kaçıncı saniye (+ güven, kayma)."""
    from vlogkit.audio.sync import offset

    for other in others:
        try:
            s = offset(ref, other, max_offset=max_offset)
        except ValueError as e:
            raise typer.BadParameter(str(e)) from e
        drift = "kayma ölçülemedi" if s.drift is None else f"kayma {s.drift * 1000:+.0f} ms"
        typer.echo(
            f"{other.name} 0 sn = {ref.name} {s.offset:.3f} sn "
            f"(güven {s.confidence:.2f}, {drift} / {s.overlap:.0f} sn)"
        )
        if not s.reliable:
            typer.echo(
                "⚠️ düşük güven: ortak ses az ya da yok, bu sayı tahmin; strip ile kontrol et"
            )
        elif s.drift is not None and abs(s.drift) > 1 / 30:
            typer.echo("⚠️ kayma 1 kareden büyük: uzun kaydı parça parça eşle")


@app.command()
def separate(
    video: Path,
    start: float = 0.0,
    duration: float | None = None,
    out: Path | None = None,
) -> None:
    """Konuşmayı müzikten ayır (Demucs): vocals.wav + no_vocals.wav."""
    from vlogkit.audio.separate import separate as run

    out = out or BUILD_DIR / "separate" / video.stem
    kw = {"start": start, "duration": duration} if duration else {"start": start}
    for stem, path in run(video, out, **kw).items():
        typer.echo(f"✅ {stem}: {path}")


@app.command()
def upscale(
    video: Path,
    target: Annotated[
        str, typer.Option(help="GENxYÜK, ör. 1920x1080 ya da 1080x1920")
    ] = "1920x1080",
    unletterbox: Annotated[bool, typer.Option(help="Önce siyah bantları kırp (aktif alan)")] = True,
    denoise: bool = True,
    start: float = 0.0,
    duration: float | None = None,
    out: Path | None = None,
) -> None:
    """Düşük çözünürlüğü Apple'ın ML süper çözünürlüğüyle büyüt (gürültü filtresi + 4x) -> ProRes."""
    from vlogkit.video import reframe, vt

    if not vt.available():
        raise typer.BadParameter(
            "Apple VT süper çözünürlük bu Mac'te yok (macOS 26 + Apple silicon)"
        )
    w, h = (int(x) for x in target.lower().split("x"))
    parts = []
    if start or duration:
        parts.append(
            f"trim=start={start}"
            + (f":duration={duration}" if duration else "")
            + ",setpts=PTS-STARTPTS"
        )
    if unletterbox:
        from vlogkit.analysis.letterbox import active_area

        parts.append(reframe.crop(active_area(video)))
    out = out or BUILD_DIR / "upscale" / f"{video.stem}_{w}x{h}.mov"
    out.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(
        f"✅ {vt.upscale(video, out, denoise=denoise, target=(w, h), vf=','.join(parts) or None)}"
    )


@app.command()
def slowmo(
    video: Path,
    factor: Annotated[int, typer.Option(help="Kaç kat yavaş (ara kare üretir)")] = 2,
    out: Path | None = None,
) -> None:
    """Gerçek ara karelerle yavaş çekim (Apple VT kare hızı dönüştürme); ses çıkmaz."""
    from vlogkit.video import vt

    out = out or BUILD_DIR / "slowmo" / f"{video.stem}_x{factor}.mov"
    out.parent.mkdir(parents=True, exist_ok=True)
    typer.echo(f"✅ {vt.interpolate(video, out, factor=factor, slowmo=True)}")


@app.command()
def resolve(
    project: str,
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
    out: Annotated[
        Path | None, typer.Option(help="Varsayılan: çıktının yanında <ad>_resolve/")
    ] = None,
    stems: Annotated[bool, typer.Option(help="Sesleri ayrı izlerle de ver (_stems.fcpxml)")] = True,
) -> None:
    """DaVinci Resolve'a katmanlı aktarım: plan plan görüntü, her grafik ayrı klip, düzenlenebilir metin."""
    from vlogkit.export.resolve import export
    from vlogkit.project import load

    folder = export(load(project, variant), out, stems=stems)
    typer.echo(f"✅ {folder}  (Resolve: File > Import > Timeline, ayrıntı README.txt)")


@app.command()
def timeline(
    target: Annotated[str, typer.Argument(help="Proje adı ya da video dosyası")],
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
    at: Annotated[
        list[float] | None, typer.Option("--at", "-t", help="Bu saniyede ne var (tekrarlanabilir)")
    ] = None,
) -> None:
    """Kurgunun zaman çizelgesi: planlar, yazılar, bölümler, notlar (Stüdyo bunu çizer).
    Kullanıcının "[01:23.4 · plan 12] ..." yorumunu projede bulmak için: --at 83.4."""
    from vlogkit.export import timeline as tl

    video = Path(target).expanduser()
    if video.is_file():
        data = tl.ensure_shots(video)
    else:
        from vlogkit.project import load

        edit = load(target, variant)
        video = edit.output_path
        saved = tl.load(video) if video.exists() else None
        if saved and not saved.get("stale"):
            # the build's own timeline: it describes the video the user commented on, even if
            # edit.py has changed since (a comment is about what was seen, not what is planned)
            data = saved if tl.track(saved, "shots") else tl.ensure_shots(video)
        elif video.exists():
            if saved:
                typer.echo("(kayıtlı çizelge videodan eski: edit.py'den yeniden yazılıyor)")
            tl.write(tl.from_edit(edit), video)
            data = tl.ensure_shots(video)
        else:
            data = tl.from_edit(edit)
            typer.echo(f"(çıktı henüz yok: {video}; planlar derlemeden sonra)")
    for tr in data.get("tracks", []):
        how = " (videodan bulundu)" if tr.get("detected") else ""
        typer.echo(f"{tr['label']}: {len(tr['items'])}{how}")
    for t in at or []:
        typer.echo(tl.describe(data, t))
    if video.exists():
        typer.echo(f"-> {tl.path_for(video)}")


@app.command()
def recipe(
    project: str,
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
) -> None:
    """Onaylanan kurgunun tarifi: açılış, plan ritmi, yazı ailesi, ses katmanları, efektler ve
    NOTES.md stratejisi → recipes/<proje>-<varyant>.md. "Şu videodaki gibi" denince okunur."""
    from vlogkit.export import recipe as rc
    from vlogkit.project import load

    try:
        out = rc.write(load(project, variant))
    except FileNotFoundError as e:
        raise typer.BadParameter(str(e)) from e
    typer.echo(out.read_text())
    typer.echo(f"-> {out}")


@app.command()
def disk(
    clean: Annotated[bool, typer.Option("--clean", help="Eski ara dosyaları sil")] = False,
    older_than: Annotated[
        float, typer.Option(help="Bu kadar gündür derlenmeyen varyantlar (0: hepsi)")
    ] = 14,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Sormadan sil")] = False,
) -> None:
    """Disk: boş yer, build'deki ara dosyalar (varyant başına) ve eski olanları silme."""
    from vlogkit import disk as dk

    all_units = dk.units()
    typer.echo(f"Boş: {dk.gb(dk.free_bytes())}")
    typer.echo(f"Ara dosyalar (yeniden derlenebilir): {dk.gb(dk.total(all_units))}")
    for u in sorted(all_units, key=lambda u: -u.size)[:15]:
        if u.size:
            rel = u.path.relative_to(BUILD_DIR)
            typer.echo(f"  {dk.gb(u.size):>9}  {rel}  ({u.age_days:.0f} gün önce)")
    old = dk.plan(older_than, all_units)
    files, freed = dk.removable(old)
    if not files:
        typer.echo(f"{older_than:g} günden eski ara dosya yok.")
        return
    typer.echo(
        f"{older_than:g} günden eski {len(old)} varyant: {len(files)} dosya, {dk.gb(freed)} açılır "
        "(teslim videoları, kayıtlar ve önbellekler kalır; varyant yeniden derlenince geri gelir)."
    )
    if not clean:
        typer.echo(f"Silmek için: uv run vlogkit disk --clean --older-than {older_than:g}")
        return
    if not yes and not typer.confirm("Silinsin mi?"):
        return
    typer.echo(f"Silindi: {dk.gb(dk.clean(old))}; boş: {dk.gb(dk.free_bytes())}")


@app.command()
def licenses(
    project: str,
    variant: Annotated[str | None, typer.Option("--variant", "-v")] = None,
    out: Annotated[Path | None, typer.Option(help="Derlemede --out verildiyse aynısı")] = None,
) -> None:
    """Derlenmiş videonun lisans dosyası (<video>.lisans.md) ve telif itiraz metni, derlemeden."""
    from vlogkit.export import licenses as lic
    from vlogkit.project import load

    edit = load(project, variant, out)
    if not edit.output_path.exists():
        raise typer.BadParameter(f"{edit.output_path} yok: önce derle")
    path, guessed = lic.refresh(edit)
    if not path:
        typer.echo("Bu videoda kütüphaneden medya yok: lisans dosyası gerekmiyor.")
        return
    typer.echo(f"-> {path}")
    if guessed:
        typer.echo("! eski derleme: ses ve grafiklerin kullandıkları yazıldı; görüntü adımının "
                   "eklediği stok klipler için yeniden derle")  # fmt: skip


@app.command()
def new(name: str) -> None:
    """projects/_template'ten yeni proje oluştur."""
    dst = PROJECTS_DIR / name
    if dst.exists():
        raise typer.BadParameter(f"{dst} zaten var")
    shutil.copytree(PROJECTS_DIR / "_template", dst)
    typer.echo(f"✅ {dst}/edit.py  (önce: vlogkit analyze <video>)")


@app.command()
def ui(
    port: Annotated[int, typer.Option(help="Yerel port")] = 8765,
    open_browser: Annotated[bool, typer.Option("--open/--no-open", help="Tarayıcıyı aç")] = True,
) -> None:
    """Yerel arayüz: video seç, görev işaretle, Claude Code (abonelik) ile edit'i yaptır."""
    from vlogkit.ui.server import serve

    serve(port, open_browser)


@app.command("open")
def open_cmd(port: Annotated[int, typer.Option(help="Yerel port")] = 8765) -> None:
    """Stüdyoyu aç: sunucu çalışmıyorsa arka planda başlatır, tarayıcıyı açar."""
    from vlogkit.ui.launcher import open_studio

    typer.echo(open_studio(port))


@app.command()
def shortcut(
    dest: Annotated[Path | None, typer.Option(help="Klasör (varsayılan: Masaüstü)")] = None,
) -> None:
    """Masaüstüne çift tıkla açılan 'vlogkit Stüdyo' uygulaması (macOS) oluştur."""
    from vlogkit.ui.launcher import DESKTOP, create_shortcut

    try:
        typer.echo(f"✅ {create_shortcut(dest or DESKTOP)}")
    except RuntimeError as e:
        typer.echo(f"✗ {e}", err=True)
        raise typer.Exit(1) from e


@assets_app.command("list")
def assets_list(kind: str | None = None) -> None:
    """Manifest'teki varlıklar ve durumları."""
    from vlogkit import assets

    for a in assets.manifest().values():
        if kind and a.kind != kind:
            continue
        typer.echo(f"{_ok(a.path.exists())} {a.id:<30} {a.kind:<6} {a.license:<24} {a.description}")


@assets_app.command("fetch")
def assets_fetch(ids: list[str] | None = None, force: bool = False) -> None:
    """Eksik varlıkları indir (ffprobe ile doğrular)."""
    from vlogkit import assets

    for aid, status in assets.fetch(ids or None, force):
        typer.echo(f"{aid:<30} {status}")


if __name__ == "__main__":
    app()
