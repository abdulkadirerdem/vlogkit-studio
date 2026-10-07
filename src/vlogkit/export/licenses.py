"""Licenses of the third-party media in a delivered video, and the text for a copyright claim.

A platform can flag music months after upload (an author registers a Pixabay track with Content
ID later). The answer is the track's license page and a short dispute text, so every build writes
`<video>.lisans.md` next to the delivery: which library files the video uses (music, SFX, stock),
their author, license, page and the day the page showed no Content ID registration, plus a ready
English dispute text. Nothing is typed by hand: each build step records the library ids it
resolved (`assets.recording`, saved in the work dir as assets.json), so a partial rebuild
(`-s compose`) still knows what the earlier steps used. The studio shows the same data as a card.
"""

from __future__ import annotations

import json
from pathlib import Path

from vlogkit import assets

USED_FILE = "assets.json"  # in the variant's work dir: {step: [asset ids]}
KIND_NAMES = {"music": "müzik", "sfx": "ses efekti", "stock": "stok görüntü"}


def record(work: Path, step: str, ids: set[str]) -> None:
    """Remember which library files a build step used (replaces that step's earlier record)."""
    path = Path(work) / USED_FILE
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        data = {}
    data[step] = sorted(ids)
    path.write_text(json.dumps(data, indent=1))


def used(work: Path) -> list[str]:
    try:
        data = json.loads((Path(work) / USED_FILE).read_text())
    except (OSError, ValueError):
        return []
    return sorted({i for ids in data.values() for i in ids})


def entries(ids: list[str]) -> list[dict]:
    """Manifest facts for each id, music first (what a claim is about)."""
    m = assets.manifest()
    out = []
    for i in ids:
        a = m.get(i)
        if a is None:  # removed from the manifest since the build
            continue
        out.append(
            {
                "id": a.id,
                "kind": a.kind,
                "author": a.author,
                "license": a.license,
                "page": a.page,
                "checked": a.checked,
                "attribution": a.attribution,
                "description": a.description,
            }
        )
    return sorted(out, key=lambda e: (e["kind"] != "music", e["kind"], e["id"]))


def dispute_text(video: str, items: list[dict]) -> str:
    """English text for a Content ID / copyright dispute (YouTube, Instagram)."""
    music = [e for e in items if e["kind"] == "music"] or items
    lines = [
        f'The video "{video}" uses the following licensed audio/media. I have the right to use '
        "it in this video, including on a monetized channel:",
        "",
    ]
    for e in music:
        when = (
            f" As of {e['checked']}, its page showed no Content ID registration."
            if e["checked"]
            else ""
        )
        lines.append(
            f"- {e['id']} by {e['author']}, used under the {e['license']}: {e['page']}{when}"
        )
    credit = any(e["attribution"] for e in music)
    lines += [
        "",
        "These licenses allow commercial use"
        + (", and the video description credits the authors as required" if credit else "")
        + ", so the claim does not apply to this video. Please release it.",
    ]
    return "\n".join(lines)


def render_md(video: str, items: list[dict]) -> str:
    rows = [
        f"# Lisanslar: {video}",
        "",
        "Bu videodaki üçüncü taraf medya. Platform telif talebi gönderirse aşağıdaki itiraz "
        "metnini kullan, lisans sayfasının adresini ekle.",
        "",
        "| Parça | Tür | Yazar | Lisans | Sayfa | Content ID kontrolü |",
        "|---|---|---|---|---|---|",
    ]
    for e in items:
        rows.append(
            f"| {e['id']} | {KIND_NAMES.get(e['kind'], e['kind'])} | {e['author']} | "
            f"{e['license']} | {e['page']} | {e['checked'] or '-'} |"
        )
    if any(e["attribution"] for e in items):
        rows += ["", "Atıf gerekenler var: açıklamaya yazar ve sayfa adresini ekle."]
    rows += ["", "## İtiraz metni (İngilizce)", "", dispute_text(video, items), ""]
    return "\n".join(rows)


def for_edit(edit) -> list[dict]:
    return entries(used(edit.ctx.work))


def sidecar(video: Path) -> Path:
    video = Path(video)
    return video.with_name(video.stem + ".lisans.md")


def write(edit) -> Path | None:
    """`<video>.lisans.md` next to the delivery; an old one goes when nothing is used anymore."""
    items = for_edit(edit)
    path = sidecar(edit.output_path)
    if not items:
        path.unlink(missing_ok=True)
        return None
    path.write_text(render_md(edit.output_path.name, items), encoding="utf-8")
    return path


def refresh(edit) -> tuple[Path | None, bool]:
    """For a video built earlier: write its license note without a render, and put the data in
    its saved timeline (the studio card). A build from before 0.14 has no record of what it used:
    what the sound and graphics use now is taken instead (the picture step's own inserts are
    only known after a rebuild). Returns (note, guessed)."""
    from vlogkit.export import timeline

    guessed = not used(edit.ctx.work)
    if guessed:  # saved as the steps' own records: the next real build replaces them
        with assets.recording() as ids:
            edit.audio()
        record(edit.ctx.work, "audio", ids)
        with assets.recording() as ids:
            edit.elements()
        record(edit.ctx.work, "overlay", ids)
    path = write(edit)
    data = timeline.load(edit.output_path)
    if data is not None and not data.pop("stale", False):
        items = for_edit(edit)
        data.pop("licenses", None)
        if items:
            data["licenses"] = {
                "items": items,
                "dispute": dispute_text(edit.output_path.name, items),
                "file": str(sidecar(edit.output_path)),
            }
        timeline.write(data, edit.output_path)
    return path, guessed
