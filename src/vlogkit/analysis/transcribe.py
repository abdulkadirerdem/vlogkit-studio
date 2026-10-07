"""Speech-to-text with whisper.cpp (`brew install whisper-cpp`), segment or word level.

Results are cached in build/cache/transcripts by file (path, size, mtime) and settings: the same
file is never transcribed twice (review, gaps, strip and the Studio all ask for the same words).

Proper nouns of the channel (places, people) live in assets/vocab.txt, one per line. They are
given to whisper as its initial prompt, so "Kaçkar" is not written "Kaçgar" or "Kaçkır".
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from vlogkit.config import ASSETS_DIR, BUILD_DIR, require, tools
from vlogkit.ff import PathLike, ffmpeg

VOCAB_FILE = ASSETS_DIR / "vocab.txt"
CACHE_DIR = BUILD_DIR / "cache" / "transcripts"
PROMPT_CHARS = 400  # whisper keeps ~224 prompt tokens; stay well inside

# Whisper invents these on music-only audio (YouTube outro phrases from its training data).
HALLUCINATIONS = (
    "izlediğiniz için teşekkür",
    "bir sonraki videoda görüşmek",
    "altyazı m.k",
    "abone olmayı unutmayın",
    "thanks for watching",
    "subtitles by",
    "中文字幕",  # Chinese "subtitles by ..." credits
    "字幕志愿者",
    "优优独播剧场",
    "ming pao",
)


@dataclass(frozen=True)
class Segment:
    start: float
    end: float
    text: str

    @property
    def suspicious(self) -> bool:
        # Python lowers "İ" to "i" + a combining dot, which never matches: read the text both the
        # Turkish way (İ->i, I->ı) and the English way (I->i)
        tr = self.text.replace("İ", "i").replace("I", "ı").lower()
        en = self.text.replace("İ", "i").lower()
        return any(h in low for low in (tr, en) for h in HALLUCINATIONS)


def whisper_cmd(
    cli: str,
    model: str | Path,
    wav: str | Path,
    out_base: str | Path,
    lang: str,
    *,
    words: bool = False,
    beam: int | None = None,
    no_context: bool = False,
    prompt: str | None = None,
) -> list[str]:
    """whisper-cli arguments.

    Under music whisper loops ("好 好 好 ...") or copies the previous window. no_context (-mc 0)
    decodes each window on its own, beam (-bs) makes the decoder less greedy, prompt nudges the
    script (e.g. "以下是普通话的句子。" for simplified Chinese).
    """
    cmd = [cli, "-m", str(model), "-l", lang, "-f", str(wav), "-oj", "-of", str(out_base), "-np"]
    if words:
        cmd += ["-ml", "1", "-sow"]
    if beam:
        cmd += ["-bs", str(beam)]
    if no_context:
        cmd += ["-mc", "0"]
    if prompt:
        cmd += ["--prompt", prompt]
    return cmd


def load_vocab(path: Path = VOCAB_FILE) -> list[str]:
    """The channel's proper nouns: one per line, '#' starts a comment, duplicates dropped."""
    if not path.exists():
        return []
    terms: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        term = line.split("#", 1)[0].strip()
        if term and term not in terms:
            terms.append(term)
    return terms


def vocab_prompt(terms: list[str], limit: int = PROMPT_CHARS) -> str | None:
    """'Kaçkar, Rize, Soğanlı.': as many terms as fit in `limit` characters, in file order."""
    out: list[str] = []
    for term in terms:
        if len(", ".join([*out, term])) + 1 > limit:
            break
        out.append(term)
    return ", ".join(out) + "." if out else None


def _cache_file(path: PathLike, settings: dict) -> Path | None:
    try:
        st = os.stat(path)
    except OSError:
        return None
    key = json.dumps(
        [str(Path(path).resolve()), st.st_size, st.st_mtime_ns, settings], sort_keys=True
    )
    return CACHE_DIR / f"{Path(path).stem[:40]}-{hashlib.sha1(key.encode()).hexdigest()[:16]}.json"


def transcribe(
    path: PathLike,
    lang: str = "tr",
    *,
    words: bool = False,
    start: float = 0.0,
    duration: float | None = None,
    beam: int | None = None,
    no_context: bool = False,
    prompt: str | None = None,
    vocab: bool = True,
    cache: bool = True,
) -> list[Segment]:
    """Transcribe (a part of) a media file. words=True gives one segment per word (for karaoke).

    Music-heavy video: scan short windows (`start`/`duration`) with no_context=True and beam=5,
    and only trust lines that come out the same across settings and languages.
    Without an explicit `prompt`, the vocabulary (assets/vocab.txt) is the prompt; vocab=False
    turns that off (e.g. when whisper starts writing the names into music).
    """
    t = tools()
    if prompt is None and vocab:
        prompt = vocab_prompt(load_vocab())
    settings = {
        "model": t.whisper_model.name,
        "lang": lang,
        "words": words,
        "start": round(start, 3),
        "duration": round(duration, 3) if duration else None,
        "beam": beam,
        "no_context": no_context,
        "prompt": prompt,
    }
    cached = _cache_file(path, settings) if cache else None
    if cached and cached.exists():
        return [Segment(**s) for s in json.loads(cached.read_text())]
    segs = drop_prompt_echo(
        _run_whisper(path, lang, words, start, duration, beam, no_context, prompt), prompt
    )
    if cached:
        cached.parent.mkdir(parents=True, exist_ok=True)
        tmp = cached.with_name(f"{cached.stem}.{os.getpid()}.{threading.get_ident()}.tmp")
        tmp.write_text(json.dumps([asdict(s) for s in segs], ensure_ascii=False))
        tmp.replace(cached)
    return segs


def drop_hallucinated_words(words: list[Segment], window: int = 6) -> list[Segment]:
    """Word-level transcripts: remove runs of words that together say a known hallucination
    ("Altyazı M.K.", "İzlediğiniz için teşekkürler") - one word alone never matches."""

    def says(run: list[Segment]) -> bool:
        return bool(run) and Segment(0, 0, " ".join(w.text for w in run)).suspicious

    bad: set[int] = set()
    for i in range(len(words)):
        for n in range(2, window + 1):
            run = words[i : i + n]
            if len(run) < n:
                break
            if says(run):
                if not says(run[1:]):  # the shortest run that starts here: mark it
                    bad.update(range(i, i + n))
                break
    return [w for k, w in enumerate(words) if k not in bad]


def _words(text: str) -> list[str]:
    return [w for w in "".join(c if c.isalnum() else " " for c in text.casefold()).split() if w]


def drop_prompt_echo(segs: list[Segment], prompt: str | None) -> list[Segment]:
    """On silence or music whisper sometimes just repeats its prompt ("Kaçkar, Rize, Soğanlı."):
    remove runs of whole segments that say exactly the prompt and nothing else."""
    target = _words(prompt or "")
    if len(target) < 2:  # one name alone is also a real word ("Kaçkar!"): never drop it
        return segs
    out: list[Segment] = []
    i = 0
    while i < len(segs):
        got: list[str] = []
        j = i
        while j < len(segs) and len(got) < len(target):
            got += _words(segs[j].text)
            j += 1
        if got == target:
            i = j  # an echo: skip those segments
            continue
        out.append(segs[i])
        i += 1
    return out


def cached(path: PathLike, lang: str = "tr", *, words: bool = False) -> list[Segment] | None:
    """The whole file's transcript if it is already in the cache (never runs whisper)."""
    t = tools()
    settings = {
        "model": t.whisper_model.name,
        "lang": lang,
        "words": words,
        "start": 0.0,
        "duration": None,
        "beam": None,
        "no_context": False,
        "prompt": vocab_prompt(load_vocab()),
    }
    f = _cache_file(path, settings)
    if f and f.exists():
        return [Segment(**s) for s in json.loads(f.read_text())]
    return None


def _run_whisper(
    path: PathLike,
    lang: str,
    words: bool,
    start: float,
    duration: float | None,
    beam: int | None,
    no_context: bool,
    prompt: str | None,
) -> list[Segment]:
    t = tools()
    cli = require(t.whisper_cli, "whisper-cli")
    if not t.whisper_model.exists():
        raise RuntimeError(f"Whisper modeli yok: {t.whisper_model}")
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "a.wav"
        cut = ["-ss", str(start)] + (["-t", str(duration)] if duration else [])
        ffmpeg(["-y", *cut, "-i", path, "-vn", "-ar", "16000", "-ac", "1", wav])
        cmd = whisper_cmd(
            cli,
            t.whisper_model,
            wav,
            Path(tmp) / "out",
            lang,
            words=words,
            beam=beam,
            no_context=no_context,
            prompt=prompt,
        )
        subprocess.run(cmd, check=True, capture_output=True)
        data = json.loads((Path(tmp) / "out.json").read_text())
    segs = []
    for item in data.get("transcription", []):
        text = item["text"].strip()
        if not text:
            continue
        segs.append(
            Segment(
                start + item["offsets"]["from"] / 1000, start + item["offsets"]["to"] / 1000, text
            )
        )
    return segs
