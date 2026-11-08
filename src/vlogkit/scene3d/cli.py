"""`vlogkit 3d ...`: 3D "what if" videos rendered by Blender (see docs/3d.md)."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Annotated

import typer

app = typer.Typer(
    help="3B videolar: Blender + yerel seslendirme (docs/3d.md).", no_args_is_help=True
)
TEMPLATE = Path(__file__).with_name("template")


def _ok(flag: bool) -> str:
    return "✅" if flag else "❌"


@app.command()
def status() -> None:
    """Blender ve seslendirme motorlarının durumu."""
    from vlogkit.scene3d import blender
    from vlogkit.speech import tts

    b = blender.status()
    typer.echo(
        f"{_ok(b['ok'])} Blender                 {b['path'] or '-'} {b['version'] or ''} {'' if b['ok'] else '(' + b['why'] + ')'}"
    )
    typer.echo(
        f"{_ok(tts.qwen_installed())} Türkçe ses modeli       kanal sesi, Qwen3 Türkçe ({tts.QWEN_MODEL}){'' if tts.qwen_installed() else ' -> vlogkit 3d install-voice'}"
    )
    from vlogkit.scene3d import library

    typer.echo(
        f"{_ok(library.ready())} 3B kütüphane            {library.ROOT if library.ready() else '-> vlogkit 3d fetch'}"
    )


@app.command()
def fetch() -> None:
    """3B kütüphaneyi indir (karakterler, animasyonlar, gökyüzü, dokular; ~160 MB, CC0)."""
    from vlogkit.scene3d import library

    last = [0]

    def show(x: float) -> None:
        if int(x * 10) > last[0]:
            last[0] = int(x * 10)
            typer.echo(f"  %{last[0] * 10}")

    library.fetch(show)
    typer.echo(f"✅ {library.ROOT}")


@app.command("install-voice")
def install_voice() -> None:
    """Kanal sesini (VoxCPM2, kendi ortamında; Apple Silicon'da MLX) kur ve modeli indir (~5 GB, bir kez)."""
    import subprocess

    from vlogkit.config import BUILD_DIR
    from vlogkit.speech import tts

    if not tts.vox_python():
        subprocess.run(
            tts.install_vox_cmd(), check=True, env={**os.environ, "UV_HTTP_TIMEOUT": "900"}
        )
        tts._tool_dir.cache_clear()
    typer.echo("model indiriliyor ve deneniyor (ilk sefer birkaç dakika)...")
    s = tts.speak([tts.Line("Kanal sesi hazır.")], BUILD_DIR / "voices", engine="voxcpm")[0]
    (BUILD_DIR / "voices" / ".vox_ready").write_text("ok")
    typer.echo(f"✅ hazır: {s.path} ({s.duration:.1f} sn)")


@app.command()
def new(
    name: str,
    title: Annotated[str, typer.Option(help="Videonun sorusu / başlığı")] = "Peki ya ...?",
    fmt: Annotated[
        str, typer.Option("--format", "-f", help="pekiya | kesit (docs/formats/)")
    ] = "pekiya",
) -> None:
    """Şablondan yeni 3B proje: scene.json + edit.py + NOTES.md. Bir format seçilirse sahne o
    formatın çalışılmış örneğiyle başlar (docs/formats/<format>.md)."""
    from vlogkit.config import PROJECTS_DIR
    from vlogkit.scene3d import formats

    if fmt not in formats.FORMATS:
        raise typer.BadParameter(f"format: {', '.join(formats.FORMATS)}")
    dest = PROJECTS_DIR / name
    if dest.exists():
        raise typer.BadParameter(f"{dest} zaten var")
    shutil.copytree(TEMPLATE, dest, ignore=shutil.ignore_patterns("scene_*.json"))
    example = TEMPLATE / f"scene_{fmt}.json"
    if example.exists():
        shutil.copyfile(example, dest / "scene.json")
    scene = json.loads((dest / "scene.json").read_text(encoding="utf-8"))
    scene["title"] = title
    scene["output"] = f"3d/{name}"
    (dest / "scene.json").write_text(
        json.dumps(scene, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    typer.echo(dest)


@app.command()
def render(
    project: str,
    step: Annotated[
        list[str] | None, typer.Option("--step", "-s", help="base | overlay | audio | compose")
    ] = None,
) -> None:
    """Derlemeyi ajan oturumundan bağımsız başlat (oturum kapansa da sürer); hemen döner."""
    from vlogkit.scene3d import detach

    st = detach.start(project, "v1", step)
    typer.echo(
        f"render başladı (pid {st['pid']}); izlemek için: uv run vlogkit 3d progress {project}"
    )


@app.command()
def progress(project: str) -> None:
    """Arka plandaki render ne durumda: kare, hız, kalan süre, sonuç."""
    from vlogkit.scene3d import detach

    p = detach.progress(project)
    if not p.get("status"):
        typer.echo("bu proje için başlatılmış bir render yok (vlogkit 3d render PROJE)")
        raise typer.Exit(1)
    left = f", kalan ~{p['left_s'] // 60} dk" if p.get("left_s") else ""
    speed = f", {p['per_frame']} sn/kare" if p.get("per_frame") else ""
    typer.echo(f"{p['status']}: {p['frames']}/{p['total']} kare{speed}{left}")
    if p.get("output"):
        typer.echo(f"çıktı: {p['output']}")
    if p.get("error"):
        typer.echo(f"hata: {p['error']}")
    if p["status"] in ("killed", "error"):
        for ln in p.get("log_tail", []):
            typer.echo(f"  {ln}")


@app.command()
def senaryolar(
    tumu: Annotated[bool, typer.Option("--tumu", help="Arşivdekiler dahil")] = False,
) -> None:
    """Kayıtlı senaryolar (projects/_senaryolar): puan, durum, sorunlar."""
    from vlogkit.scene3d import scenarios

    rows = scenarios.list_all(tumu)
    if not rows:
        typer.echo(f"senaryo yok ({scenarios.DIR})")
        return
    for r in rows:
        bad = f"  ! {'; '.join(r['problems'])}" if r["problems"] else ""
        typer.echo(f"{r['total']:>4} {r['status']:<10} {r['id']:<40} {r['title']}{bad}")


@app.command("senaryo-kontrol")
def senaryo_kontrol(
    sid: Annotated[str | None, typer.Argument(help="Senaryo kimliği (--tum ile verilmez)")] = None,
    tum: Annotated[
        bool, typer.Option("--tum", help="Klasördeki bütün senaryoları tek seferde doğrula")
    ] = False,
) -> None:
    """Bir senaryo dosyasını doğrula (yazdıktan sonra); --tum ile hepsini."""
    from vlogkit.scene3d import scenarios

    if bool(sid) == tum:
        raise typer.BadParameter("ya bir senaryo kimliği ver ya --tum")
    if tum:
        checks = [(r["id"], r["problems"]) for r in scenarios.list_all(include_archived=True)]
        if not checks:
            typer.echo(f"senaryo yok ({scenarios.DIR})")
            return
    else:
        checks = [(sid, scenarios.validate(scenarios.load(sid)))]
    for one, problems in checks:
        if problems:
            for p in problems:
                typer.echo(f"! {one}: {p}")
        else:
            typer.echo(f"✅ {one}: tamam")
    if any(problems for _, problems in checks):
        raise typer.Exit(1)


@app.command("senaryo-durum")
def senaryo_durum(
    sid: str, durum: str, proje: Annotated[str | None, typer.Option("--proje")] = None
) -> None:
    """Senaryonun durumunu değiştir: yeni | secildi | uretiliyor | uretildi | arsiv."""
    from vlogkit.scene3d import scenarios

    scenarios.set_status(sid, durum, proje)
    typer.echo(f"{sid}: {durum}")


@app.command()
def kit(
    as_json: Annotated[bool, typer.Option("--json", help="Makine için JSON")] = False,
) -> None:
    """Kitte ne var: mekânlar, eşyalar, hareketler, yüz ifadeleri, kadrajlar, kamera hareketleri."""
    from vlogkit.scene3d import catalog
    from vlogkit.speech import tts

    data = {
        "sets": catalog.SETS,
        "props": catalog.PROPS,
        "actions": catalog.ACTIONS,
        "faces": list(catalog.FACES),
        "frames": catalog.FRAMES,
        "moves": catalog.MOVES,
        "bodies": list(catalog.BODIES),
        "hair": list(catalog.HAIR),
        "outfits": list(catalog.OUTFITS),
        "sfx": list(catalog.SFX),
        "fx": catalog.FX,
        "looks": catalog.LOOKS,
        "crowd": list(catalog.CROWD_DO),
        "voices": tts.POCKET_VOICES,
        "emotions": list(tts.POCKET_EMOTIONS),
    }
    if as_json:
        typer.echo(json.dumps(data, ensure_ascii=False, indent=1))
        return
    for k, v in data.items():
        typer.echo(f"\n## {k}")
        if isinstance(v, dict):
            for name, desc in v.items():
                typer.echo(f"- {name}: {desc}")
        else:
            typer.echo(", ".join(v))


def _edit(project: str):
    from vlogkit.project import load
    from vlogkit.scene3d.edit import Scene3DEdit

    e = load(project)
    if not isinstance(e, Scene3DEdit):
        raise typer.BadParameter(f"{project} bir 3B proje değil (scene.json yok)")
    return e


@app.command()
def plan(project: str) -> None:
    """Anlatımı seslendir (önbellekli) ve zaman çizelgesini yaz: beat'ler ve içlerindeki planlar
    (kesme anı, mekân, kamera, görünüm, efektler)."""
    from vlogkit.scene3d import plan as planmod

    e = _edit(project)
    long = []
    for b in e.beats:
        typer.echo(f"{b.index + 1:>2}. {b.t0:6.2f}-{b.t1:6.2f} ({b.dur:4.1f} sn) {b.raw['say']}")
        shots = planmod.beat_shots(b, float(e.fps))
        for s in shots:
            cam = s["camera"]
            look = s["look"].get("kind") if isinstance(s["look"], dict) else s["look"]
            fx = ", ".join(f["kind"] for f in s["fx"])
            dur = s["frames"] / float(e.fps)
            extra = " ".join(x for x in (f"[{look}]" if look else "", f"efekt: {fx}" if fx else "",
                                         "kalabalık" if s["crowd"] else "") if x)  # fmt: skip
            typer.echo(
                f"      {s['id']:<5} {s['at']:6.2f} +{dur:3.1f} sn  {s['set']:<10} "
                f"{cam.get('frame', 'medium')}/{cam.get('move', 'push'):<8} {extra}"
            )
            if b.index == len(e.beats) - 1 and s is shots[-1] and e.spec.get("end"):
                dur -= float(e.spec["end"].get("seconds", 2.0))  # the end card is not a held shot
            if dur > 3.2:
                long.append(f"{s['id']} ({dur:.1f} sn)")
    typer.echo(
        f"Toplam: {e.duration:.1f} sn, {e.nframes} kare, {sum(len(planmod.beat_shots(b, float(e.fps))) for b in e.beats)} plan"
    )
    if long:
        typer.echo(
            "!  3 saniyeden uzun planlar (bir kesme ya da yeni olay ekle): " + ", ".join(long)
        )


def _frames_at(
    e, times: list[float], quality: str, out_dir: Path
) -> list[tuple[float, dict, Path]]:
    """Render single frames at these times (with the counter, captions and looks on top)."""
    from PIL import Image

    from vlogkit.graphics.render import compose_frame
    from vlogkit.scene3d import blender, framing, plan
    from vlogkit.scene3d.edit import looked

    p = e.render_plan(quality)
    only: dict[str, list[int]] = {}
    want = []
    for t in times:
        shot, f = plan.shot_at(p, t, float(e.fps))
        only.setdefault(shot["id"], []).append(f)
        want.append((t, shot, f))
    for s in p["shots"]:
        s["out"] = str(out_dir / s["id"])
    p["only"] = only
    plan_path = out_dir / "preview_plan.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    edges = framing.Collector({s["id"]: s["at"] for s in p["shots"]})
    blender.run(plan_path, edges.feed)
    els = e.elements()
    out = []
    for t, shot, f in want:
        src = Path(shot["out"]) / f"{f:05d}.png"
        frame = looked(shot, f, src) if shot.get("look") else Image.open(src)
        bg = frame.convert("RGBA").resize(e.layout.size)
        bg.alpha_composite(compose_frame(els, t, e.layout.size))
        path = out_dir / f"onizleme_{t:06.2f}.jpg"
        bg.convert("RGB").save(path, quality=88)
        out.append((t, shot, path))
    for note in edges.notes():
        typer.echo(note)
    return out


@app.command()
def preview(
    project: str,
    at: Annotated[list[float], typer.Option("--at", "-t", help="Saniye (tekrarlanabilir)")],
    quality: Annotated[str, typer.Option(help="draft | normal | high")] = "draft",
) -> None:
    """Belirli anları Blender'da tek kare render et, üstüne sayaç ve altyazıyı koy (PNG)."""
    e = _edit(project)
    for _t, _shot, path in _frames_at(e, list(at), quality, e.ctx.work / "preview3d"):
        typer.echo(path)


@app.command()
def kontak(
    project: str,
    quality: Annotated[str, typer.Option(help="draft | normal | high")] = "draft",
    cols: Annotated[int, typer.Option(help="Satırdaki kare sayısı")] = 6,
) -> None:
    """Render'dan önce her planın ortasından bir kare: tek sayfada plan no, zaman, söylenen
    kelimeler ve telefon arayüzünün kapattığı alanlar (kırmızı). Read ile bak, sonra render."""
    from PIL import Image, ImageDraw

    from vlogkit.graphics.style import font, unsafe_zones

    e = _edit(project)
    p = e.render_plan("draft")
    times = [s["at"] + s["frames"] / float(e.fps) / 2 for s in p["shots"]]
    frames = _frames_at(e, times, quality, e.ctx.work / "kontak")
    w = 300
    h = round(w * e.layout.h / e.layout.w)
    rows = (len(frames) + cols - 1) // cols
    label = 64
    sheet = Image.new("RGB", (cols * w, rows * (h + label)), "#111214")
    d = ImageDraw.Draw(sheet)
    words = [(wd, a) for b in e.beats for wd, a, _z in b.words]
    for i, (_t, shot, path) in enumerate(frames):
        im = Image.open(path).convert("RGB").resize((w, h))
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        k = w / e.layout.w
        for _name, (x0, y0, x1, y1) in unsafe_zones(e.layout.size):
            od.rectangle(
                (x0 * k, y0 * k, x1 * k, y1 * k),
                fill=(255, 40, 40, 16),
                outline=(255, 60, 60, 200),
                width=2,
            )
        im = Image.alpha_composite(im.convert("RGBA"), ov).convert("RGB")
        x, y = (i % cols) * w, (i // cols) * (h + label)
        sheet.paste(im, (x, y))
        end = shot["at"] + shot["frames"] / float(e.fps)
        said = " ".join(wd for wd, a in words if shot["at"] - 0.05 <= a < end)[:44]
        d.text((x + 6, y + h + 4), f"{shot['id']}  {shot['at']:.1f}s +{shot['frames'] / float(e.fps):.1f}",
               font=font("ExtraBold", 18), fill="#ffd23f")  # fmt: skip
        d.text((x + 6, y + h + 28), said, font=font("SemiBold", 15), fill="#e8e8e8")
    out = e.ctx.work / "kontak.jpg"
    sheet.save(out, quality=86)
    typer.echo(out)


def _delivered(e) -> Path:
    from vlogkit.config import VLOGS_ROOT

    video = VLOGS_ROOT / f"{e.spec['output']}.mp4"
    if not video.exists():
        raise typer.BadParameter(f"{video} yok: önce derle (3d render)")
    return video


@app.command()
def kontrol(project: str) -> None:
    """Bitmiş videonun makine kontrolü: seslendirme senaryoyla eşleşiyor mu (whisper), ölü an
    (3 sn'den uzun hiç değişmeyen görüntü), 3 sn'den uzun plan, okunamayacak kadar kısa
    altyazı, ses seviyesi. `!` satırlarını düzelt ya da nedenini yaz."""
    from vlogkit.scene3d import quality

    e = _edit(project)
    rep = quality.check(e, _delivered(e))
    for line in rep.lines():
        typer.echo(line)
    out = e.ctx.work / "kontrol.json"
    out.write_text(json.dumps({"problems": rep.problems, "notes": rep.notes, "stats": rep.stats},
                              ensure_ascii=False, indent=1), encoding="utf-8")  # fmt: skip
    if rep.problems:
        raise typer.Exit(1)


@app.command()
def puanla(project: str) -> None:
    """Paylaşmadan önce kör puan: yeni bir Claude oturumu yalnız izleyicinin gördüğünü (2 sn'de
    bir kare, anlatım, sayılar) görür ve 7 satırlık tabloyla 70 üzerinden puanlar; en zayıf yeri
    ve en etkili 3 düzeltmeyi yazar. Aboneliği kullanır (birkaç dakika)."""
    from vlogkit.scene3d import quality

    e = _edit(project)
    video = _delivered(e)
    rep = quality.check(e, video)
    res = quality.rate(e, video, rep)
    (e.ctx.work / "puan.json").write_text(
        json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    for k, q in quality.RUBRIC:
        typer.echo(f"{res.get('puanlar', {}).get(k, '?'):>3}  {k:<10} {q}")
    typer.echo(f"Toplam: {res['toplam']}/{res['en_fazla']}")
    typer.echo(f"En zayıf: {res.get('en_zayif', '')}")
    for d in res.get("duzeltmeler", []):
        typer.echo(f"- {d}")


@app.command()
def voice(
    text: str,
    voice_id: Annotated[
        list[str] | None,
        typer.Option("--voice", "-v", help="male_1 ... female_3 (tekrarlanabilir)"),
    ] = None,
    engine: Annotated[
        str, typer.Option(help="auto (kanal sesi) | qwen | pocket | system")
    ] = "auto",
    emotion: Annotated[
        str | None, typer.Option(help="Pocket: notr, mutlu, sakin, heyecanli, uzgun, kizgin")
    ] = None,
) -> None:
    """Sesleri dinlet: aynı cümleyi birkaç sesle seslendir ve "Seçim:" bloğunu yaz."""
    from vlogkit.config import BUILD_DIR
    from vlogkit.speech import tts

    eng = tts.pick_engine(engine)
    voices = (
        voice_id
        or ([""] if eng == "qwen" else None)
        or (list(tts.POCKET_VOICES) if eng == "pocket" else (tts.system_voices()[:1] or [""]))
    )
    out = BUILD_DIR / "voices"
    said = tts.speak([tts.Line(text, v or None, emotion) for v in voices], out, eng)
    typer.echo("Seçim: Hangi ses?")
    for i, (v, s) in enumerate(zip(voices, said, strict=True), 1):
        desc = "kanal sesi" if eng == "qwen" else tts.POCKET_VOICES.get(v, "sistem sesi")
        named = out / f"ses-{v or ('kanal' if eng == 'qwen' else 'sistem')}-{s.path.stem[:6]}.wav"
        shutil.copyfile(s.path, named)
        typer.echo(
            f"{i}. {v or ('kanal sesi' if eng == 'qwen' else 'sistem')} ({desc}, {s.duration:.1f} sn) — {named}"
        )
