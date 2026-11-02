"""Publishing package: everything a finished video needs to go up on YouTube Shorts, Instagram
Reels and TikTok, written by the agent (docs/yayin.md), posted by a person.

No platform API, no app review: the studio shows each platform's text with Copy buttons, the
cover, and opens the upload page; the person drags the video in and pastes. One file next to the
video, `<video>.yayin.json`, plus covers `<video>.kapak-<platform>.jpg`:

    {"video": "ziplama.mp4", "scenario": "herkes-ziplasa" | null, "cover_text": "HERKES ZIPLARSA?",
     "cover_at": 12.4,
     "youtube":   {"title": "...", "description": "...", "tags": ["..."], "hashtags": ["#shorts"],
                   "cover": "ziplama.kapak-youtube.jpg"},
     "instagram": {"caption": "...", "hashtags": ["#pekiya"], "cover": "ziplama.kapak-instagram.jpg"},
     "tiktok":    {"caption": "...", "hashtags": ["#pekiya"], "cover": "ziplama.kapak-tiktok.jpg"},
     "posted":    {"youtube": "2026-11-02 21:40"}}

`check()` returns (problems, warnings): problems break a platform's limits, warnings are reach
advice (docs/yayin.md). A video made from a scenario (projects/_senaryolar/) starts from that
scenario's titles and hashtags (`draft`).
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

PLATFORMS = ("youtube", "instagram", "tiktok")
LABEL = {"youtube": "YouTube Shorts", "instagram": "Instagram Reels", "tiktok": "TikTok"}
UPLOAD_URL = {
    "youtube": "https://www.youtube.com/upload",
    "instagram": "https://www.instagram.com/",  # web: Oluştur (+) > Gönderi; a video goes up as a Reel
    "tiktok": "https://www.tiktok.com/tiktokstudio/upload",
}
# hard limits of the platforms, then what reaches best (docs/yayin.md)
YT_TITLE_MAX, YT_TITLE_FEED = 100, 60
YT_DESC_MAX, YT_TAGS_CHARS = 5000, 500
IG_CAPTION_MAX, IG_FIRST_LINE, IG_HASHTAGS_MAX = 2200, 125, 5
TT_CAPTION_MAX = 4000
HASHTAGS = {"youtube": (3, 5), "instagram": (3, 5), "tiktok": (3, 5)}
_TAG = re.compile(r"^#[^\s#]{1,60}$")


def upload_url(platform: str) -> str:
    return UPLOAD_URL[platform]


def path_for(video: str | Path) -> Path:
    v = Path(video)
    return v.with_name(v.stem + ".yayin.json")


def cover_path(video: str | Path, platform: str) -> Path:
    v = Path(video)
    return v.with_name(f"{v.stem}.kapak-{platform}.jpg")


def load(video: str | Path) -> dict | None:
    p = path_for(video)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def save(video: str | Path, pkg: dict) -> Path:
    p = path_for(video)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(pkg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(p)
    return p


def _tags(where: str, tags, lo_hi: tuple[int, int], problems: list, warnings: list) -> list[str]:
    if tags is None:
        tags = []
    if not isinstance(tags, list):
        problems.append(f'{where}.hashtags: liste olmalı (["#pekiya", ...])')
        return []
    for t in tags:
        if not isinstance(t, str) or not _TAG.match(t):
            problems.append(f"{where}.hashtags: '{t}' # ile başlamalı, boşluksuz tek kelime")
    lo, hi = lo_hi
    if len(tags) < lo:
        warnings.append(f"{where}: {lo}-{hi} hashtag önerilir ({len(tags)} var)")
    if len({t.lower() for t in tags if isinstance(t, str)}) != len(tags):
        problems.append(f"{where}.hashtags: aynı etiket iki kez")
    return [t for t in tags if isinstance(t, str)]


def check(pkg: dict, base_dir: str | Path | None = None) -> tuple[list[str], list[str]]:
    """(problems, warnings). `base_dir`: where the covers are looked for (the video's folder)."""
    problems: list[str] = []
    warnings: list[str] = []
    for k in set(pkg) - {
        "video",
        "scenario",
        "cover_text",
        "cover_at",
        "posted",
        "notes",
        *PLATFORMS,
    }:
        problems.append(f"bilinmeyen alan '{k}'")
    if not any(pkg.get(p) for p in PLATFORMS):
        problems.append("en az bir platform gerekli: youtube, instagram, tiktok")

    yt = pkg.get("youtube")
    if yt:
        title = str(yt.get("title") or "").strip()
        if not title:
            problems.append("youtube.title gerekli")
        elif len(title) > YT_TITLE_MAX:
            problems.append(f"youtube.title {len(title)} karakter: en fazla {YT_TITLE_MAX}")
        elif len(title) > YT_TITLE_FEED:
            warnings.append(
                f"youtube.title {len(title)} karakter: Shorts akışında ~{YT_TITLE_FEED}'tan sonrası kesilir"
            )
        if len(str(yt.get("description") or "")) > YT_DESC_MAX:
            problems.append(f"youtube.description en fazla {YT_DESC_MAX} karakter")
        if "<" in title or ">" in title:
            problems.append("youtube.title: < ve > kullanılamaz")
        tags = yt.get("tags") or []
        if not isinstance(tags, list):
            problems.append("youtube.tags: liste olmalı")
        elif sum(len(str(t)) + 1 for t in tags) > YT_TAGS_CHARS:
            problems.append(f"youtube.tags toplam {YT_TAGS_CHARS} karakteri geçiyor")
        hs = _tags("youtube", yt.get("hashtags"), HASHTAGS["youtube"], problems, warnings)
        if hs and "#shorts" not in {h.lower() for h in hs}:
            warnings.append("youtube.hashtags: #shorts ekle")

    ig = pkg.get("instagram")
    if ig:
        cap = str(ig.get("caption") or "").strip()
        hs = _tags("instagram", ig.get("hashtags"), HASHTAGS["instagram"], problems, warnings)
        if not cap:
            problems.append("instagram.caption gerekli")
        if len(full_caption("instagram", ig)) > IG_CAPTION_MAX:
            problems.append(f"instagram: açıklama + etiketler en fazla {IG_CAPTION_MAX} karakter")
        if len(hs) > IG_HASHTAGS_MAX:
            problems.append(f"instagram.hashtags: en fazla {IG_HASHTAGS_MAX} (Instagram sınırı)")
        if cap and len(cap.split("\n")[0]) > IG_FIRST_LINE:
            warnings.append(
                f"instagram.caption: ilk satır {IG_FIRST_LINE} karakterden uzun, '...devamı'nda kalır"
            )

    tt = pkg.get("tiktok")
    if tt:
        cap = str(tt.get("caption") or "").strip()
        _tags("tiktok", tt.get("hashtags"), HASHTAGS["tiktok"], problems, warnings)
        if not cap:
            problems.append("tiktok.caption gerekli")
        if len(full_caption("tiktok", tt)) > TT_CAPTION_MAX:
            problems.append(f"tiktok: açıklama + etiketler en fazla {TT_CAPTION_MAX} karakter")

    if base_dir is not None:
        for p in PLATFORMS:
            cv = (pkg.get(p) or {}).get("cover")
            if pkg.get(p) and cv and not (Path(base_dir) / cv).exists():
                warnings.append(f"{p}.cover: {cv} yok (vlogkit yayin-kapak ile üret)")
    words = len(str(pkg.get("cover_text") or "").split())
    if words > 5:
        warnings.append(f"cover_text {words} kelime: kapakta 3-5 kelime okunur")
    return problems, warnings


def full_caption(platform: str, d: dict) -> str:
    """The text pasted into the platform's description box, hashtags included."""
    tags = " ".join(d.get("hashtags") or [])
    body = str((d.get("description") if platform == "youtube" else d.get("caption")) or "").strip()
    if tags and not all(t in body for t in d.get("hashtags") or []):
        body = f"{body}\n\n{tags}" if body else tags
    return body


def fields(pkg: dict, platform: str) -> list[dict]:
    """What the studio shows with a Copy button each: [{"label", "text"}]."""
    d = pkg.get(platform) or {}
    if platform == "youtube":
        out = [
            {"label": "Başlık", "text": str(d.get("title") or "")},
            {"label": "Açıklama", "text": full_caption("youtube", d)},
        ]
        if d.get("tags"):
            out.append({"label": "Etiketler", "text": ", ".join(d["tags"])})
        return out
    return [{"label": "Açıklama", "text": full_caption(platform, d)}]


def mark_posted(video: str | Path, platform: str, posted: bool = True) -> dict:
    if platform not in PLATFORMS:
        raise ValueError(f"platform: {', '.join(PLATFORMS)}")
    pkg = load(video)
    if pkg is None:
        raise FileNotFoundError(path_for(video))
    marks = pkg.setdefault("posted", {})
    if posted:
        marks[platform] = time.strftime("%Y-%m-%d %H:%M")
    else:
        marks.pop(platform, None)
    save(video, pkg)
    return pkg


# ---------------------------------------------------------------------------- 3D projects
def project_of(video: str | Path) -> Path | None:
    """The 3D project folder whose scene.json renders this video (None for other videos)."""
    from vlogkit.config import PROJECTS_DIR, VLOGS_ROOT

    v = Path(video).expanduser().resolve()
    for scene in sorted(PROJECTS_DIR.glob("*/scene.json")):
        try:
            out = json.loads(scene.read_text(encoding="utf-8")).get("output")
        except (OSError, ValueError):
            continue
        if out and (VLOGS_ROOT / f"{out}.mp4").resolve() == v:
            return scene.parent
    return None


def scenario_of(video: str | Path) -> dict | None:
    """The scenario this video was produced from: its `project` is the video's project, or its
    title is the scene's title."""
    from vlogkit.scene3d import scenarios

    proj = project_of(video)
    if proj is None:
        return None
    try:
        title = json.loads((proj / "scene.json").read_text(encoding="utf-8")).get("title")
    except (OSError, ValueError):
        title = None
    for row in scenarios.list_all(include_archived=True):
        if row.get("project") == proj.name or (title and row.get("title") == title):
            return scenarios.load(row["id"])
    return None


def draft(video: str | Path) -> dict:
    """A starting package from the video's scenario (titles, hashtags, hook, ending question);
    the agent finishes it. Without a scenario: empty fields to fill."""
    v = Path(video)
    s = scenario_of(v) or {}
    titles = s.get("titles") or {}
    yt_titles = titles.get("youtube") or ([s["title"]] if s.get("title") else [])
    tags = [t if t.startswith("#") else f"#{t}" for t in s.get("hashtags") or []]
    question = str(s.get("ending") or "").strip()
    hook = str(s.get("hook") or "").strip()
    body = "\n\n".join(x for x in (hook, question) if x)
    return {
        "video": v.name,
        "scenario": s.get("id"),
        "cover_text": "",
        "youtube": {
            "title": yt_titles[0] if yt_titles else "",
            "description": body,
            "tags": [],
            "hashtags": (["#shorts"] + [t for t in tags if t.lower() != "#shorts"])[:5],
            "cover": cover_path(v, "youtube").name,
        },
        "instagram": {
            "caption": "\n\n".join(
                x for x in (titles.get("instagram") or s.get("title") or "", question) if x
            ),
            "hashtags": tags[:IG_HASHTAGS_MAX],
            "cover": cover_path(v, "instagram").name,
        },
        "tiktok": {
            "caption": titles.get("tiktok") or s.get("title") or "",
            "hashtags": tags[:5],
            "cover": cover_path(v, "tiktok").name,
        },
    }


def strong_moment(video: str | Path) -> float | None:
    """For a rendered 3D video: the middle of the beat with the biggest counter value (else of the
    beat two thirds in), from the project's render plan. None when it cannot be told."""
    from vlogkit.config import BUILD_DIR

    proj = project_of(video)
    if proj is None:
        return None
    rp = BUILD_DIR / proj.name / "v1" / "render_plan.json"
    try:
        plan = json.loads(rp.read_text(encoding="utf-8"))
        scene = json.loads((proj / "scene.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    fps = float(plan.get("fps") or 30)
    spans: dict[int, list[float]] = {}  # beat index -> [start, end] (a beat may have several shots)
    t = 0.0
    for shot in plan.get("shots") or []:
        m = re.match(r"b(\d+)", str(shot.get("id", "")))
        d = float(shot.get("frames", 0)) / fps
        if m:
            k = int(m.group(1)) - 1
            span = spans.setdefault(k, [t, t + d])
            span[1] = t + d
        t += d
    if not spans:
        return None
    beats = scene.get("beats") or []
    valued = [
        (abs(float((b.get("hud") or {}).get("value", 0) or 0)), i)
        for i, b in enumerate(beats)
        if isinstance(b.get("hud"), dict) and i in spans
    ]
    k = max(valued)[1] if valued and max(valued)[0] > 0 else sorted(spans)[len(spans) * 2 // 3]
    a, b = spans[k]
    return round((a + b) / 2, 2)


def picture_source(video: str | Path) -> Path:
    """Where a cover frame comes from: the 3D project's picture before captions (base.mov) when
    it is there, else the video itself."""
    from vlogkit.config import BUILD_DIR

    proj = project_of(video)
    if proj is not None:
        base = BUILD_DIR / proj.name / "v1" / "base.mov"
        if base.exists():
            return base
    return Path(video)


def cover(
    video: str | Path, text: str, at: float | None = None, platforms: tuple[str, ...] = PLATFORMS
) -> tuple[float, list[Path]]:
    """1080x1920 covers from one frame: the picture vivid, the words big in the centre band (every
    platform puts its buttons at the top and bottom, Instagram's grid shows the middle 3:4).
    Returns (the frame's time, the cover files). The time goes into the package as `cover_at`:
    TikTok's web upload picks its cover from the video's frames."""
    import tempfile

    from vlogkit.analysis import thumbs as th
    from vlogkit.ff import extract_frame
    from vlogkit.graphics.thumbnail import PORTRAIT, Words, design

    v = Path(video)
    if at is None:
        at = strong_moment(v)
    if at is None:  # the sharpest, most colourful moment without burned-in text
        best = th.pick(th.score(v), 1)
        at = best[0].t if best else None
    if at is None:  # text on every frame (captions throughout): two fifths in, past the hook
        from vlogkit.ff import probe

        at = round(probe(v).duration * 0.4, 2)
    src = picture_source(v)
    made = []
    with tempfile.TemporaryDirectory() as tmp:
        frame = extract_frame(src, at, Path(tmp) / "kare.png")
        words = (
            # under the face (characters stand with the head around 0.3-0.45), above the
            # platforms' bottom buttons, inside Instagram's 3:4 grid crop
            (Words(text.replace("\\n", "\n"), 0.5, 0.6, size=0.085, anchor="mm", max_w=0.9),)
            if text.strip()
            else ()
        )
        for p in platforms:
            made.append(
                design(
                    frame, cover_path(v, p), size=PORTRAIT, words=words, vignette=0.28, vivid=1.25
                )
            )
    return at, made
