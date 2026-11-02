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
        f"{_ok(tts.pocket_installed())} Türkçe ses modeli       Pocket TTS ({tts.POCKET_PACKAGE}){'' if tts.pocket_installed() else ' -> vlogkit 3d install-voice'}"
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
    """Türkçe ses modelini (Pocket TTS, ~1 GB ile birlikte torch) ayrı bir ortama kur."""
    import subprocess

    from vlogkit.speech import tts

    if tts.pocket_installed():
        typer.echo("zaten kurulu")
        return
    subprocess.run(
        tts.install_pocket_cmd(), check=True, env={**os.environ, "UV_HTTP_TIMEOUT": "900"}
    )
    typer.echo("✅ kuruldu; model ilk kullanımda iner (~440 MB)")


@app.command()
def new(
    name: str,
    title: Annotated[str, typer.Option(help="Videonun sorusu / başlığı")] = "Peki ya ...?",
) -> None:
    """Şablondan yeni 3B proje: scene.json + edit.py + NOTES.md."""
    from vlogkit.config import PROJECTS_DIR

    dest = PROJECTS_DIR / name
    if dest.exists():
        raise typer.BadParameter(f"{dest} zaten var")
    shutil.copytree(TEMPLATE, dest)
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
    """Anlatımı seslendir (önbellekli) ve beat zaman çizelgesini yaz: süre, cümle, mekân, kamera."""
    e = _edit(project)
    for b in e.beats:
        cam = b.raw.get("camera", {})
        typer.echo(
            f"{b.index + 1:>2}. {b.t0:6.2f}-{b.t1:6.2f} ({b.dur:4.1f} sn) {b.raw['set']:<10} {cam.get('frame', 'medium')}/{cam.get('move', 'push'):<8} {b.raw['say']}"
        )
    typer.echo(f"Toplam: {e.duration:.1f} sn, {e.nframes} kare")


@app.command()
def preview(
    project: str,
    at: Annotated[list[float], typer.Option("--at", "-t", help="Saniye (tekrarlanabilir)")],
    quality: Annotated[str, typer.Option(help="draft | normal | high")] = "draft",
) -> None:
    """Belirli anları Blender'da tek kare render et, üstüne sayaç ve altyazıyı koy (PNG)."""
    from PIL import Image

    from vlogkit.graphics.render import compose_frame
    from vlogkit.scene3d import blender, framing

    e = _edit(project)
    p = e.render_plan(quality)
    only: dict[str, list[int]] = {}
    want = []
    for t in at:
        b = next((x for x in e.beats if x.t0 <= t < x.t1), e.beats[-1])
        shot = p["shots"][b.index]
        f = min(shot["frames"], max(1, round((t - b.t0) * e.fps) + 1))
        only.setdefault(shot["id"], []).append(f)
        want.append((t, shot, f))
    out_dir = e.ctx.work / "preview3d"
    for s in p["shots"]:
        s["out"] = str(out_dir / s["id"])
    p["only"] = only
    plan_path = out_dir / "preview_plan.json"
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    edges = framing.Collector({p["shots"][b.index]["id"]: b.t0 for b in e.beats})
    blender.run(plan_path, edges.feed)
    els = e.elements()
    for t, shot, f in want:
        bg = Image.open(Path(shot["out"]) / f"{f:05d}.png").convert("RGBA").resize(e.layout.size)
        bg.alpha_composite(compose_frame(els, t, e.layout.size))
        path = out_dir / f"onizleme_{t:06.2f}.jpg"
        bg.convert("RGB").save(path, quality=88)
        typer.echo(path)
    for note in edges.notes():
        typer.echo(note)


@app.command()
def voice(
    text: str,
    voice_id: Annotated[
        list[str] | None,
        typer.Option("--voice", "-v", help="male_1 ... female_3 (tekrarlanabilir)"),
    ] = None,
    engine: Annotated[str, typer.Option(help="auto | pocket | system")] = "auto",
    emotion: Annotated[
        str | None, typer.Option(help="Pocket: notr, mutlu, sakin, heyecanli, uzgun, kizgin")
    ] = None,
) -> None:
    """Sesleri dinlet: aynı cümleyi birkaç sesle seslendir ve "Seçim:" bloğunu yaz."""
    from vlogkit.config import BUILD_DIR
    from vlogkit.speech import tts

    eng = tts.pick_engine(engine)
    voices = voice_id or (
        list(tts.POCKET_VOICES) if eng == "pocket" else (tts.system_voices()[:1] or [""])
    )
    out = BUILD_DIR / "voices"
    said = tts.speak([tts.Line(text, v or None, emotion) for v in voices], out, eng)
    typer.echo("Seçim: Hangi ses?")
    for i, (v, s) in enumerate(zip(voices, said, strict=True), 1):
        desc = tts.POCKET_VOICES.get(v, "sistem sesi")
        named = out / f"ses-{v or 'sistem'}-{s.path.stem[:6]}.wav"
        shutil.copyfile(s.path, named)
        typer.echo(f"{i}. {v or 'sistem'} ({desc}, {s.duration:.1f} sn) — {named}")
