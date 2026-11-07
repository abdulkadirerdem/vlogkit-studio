"""Text to speech, free and local, on macOS and Windows.

Engines (`ENGINES`), best first:
- **pocket**: Pocket TTS Turkish (code Apache-2.0, weights CC-BY-4.0, ~440 MB, runs on the CPU
  faster than real time). Installed as an isolated `uv tool` (torch never enters vlogkit's own
  environment); six built-in voices and voice cloning from a 5-10 s recording.
- **system**: the operating system's own voice, nothing to install: macOS `say` (Yelda for
  Turkish), Windows SAPI through PowerShell (Microsoft Tolga when the Turkish voice is there).

`speak(lines, out_dir)` renders each line to its own WAV once (cache by text + voice + engine) and
returns the files with their measured durations. Durations are measured from the audio, never
estimated from the text.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import wave
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ENGINES = ("auto", "qwen", "pocket", "system")
# The channel voice: Qwen3-TTS fine-tuned on Turkish (Apache-2.0), always speaking as the one
# reference recording below (made with Chatterbox's own voice, MIT), so every video has the same
# narrator. Digits are spelled out first: the model reads them badly.
QWEN_PACKAGE = "qwen-tts"
QWEN_MODEL = "erkamk/qwen3-0.6b-tr"
CHANNEL_VOICE = Path(__file__).resolve().parents[3] / "assets" / "voice" / "kanal.wav"
# What the reference says: with it the clone takes the reference's delivery too (its energy, pace,
# the way it hits the key word), not only its timbre.
CHANNEL_TEXT = CHANNEL_VOICE.with_suffix(".txt")
QWEN_WORKER = Path(__file__).with_name("qwen_worker.py")
QWEN_LICENSE = {
    "title": "Qwen3-TTS (Türkçe ince ayar, erkamk/qwen3-0.6b-tr); kanal sesi Chatterbox (Resemble AI) ile üretildi",
    "author": "Qwen (Alibaba), erkamk; Resemble AI",
    "license": "Apache-2.0 (model), MIT (Chatterbox)",
    "page": "https://huggingface.co/erkamk/qwen3-0.6b-tr",
}
POCKET_PACKAGE = "pocket-tts-turkish"
POCKET_REPO = "wite-tech/pocket-tts-turkish"
POCKET_VOICES = {
    "female_1": "Kadın, parlak ve enerjik",
    "female_2": "Kadın, sıcak ve net",
    "female_3": "Kadın, kendinden emin",
    "male_1": "Erkek, sakin ve derin (anlatıcı)",
    "male_2": "Erkek, enerjik",
    "male_3": "Erkek, net ve keskin",
}
POCKET_EMOTIONS = ("notr", "mutlu", "sakin", "heyecanli", "saskin", "uzgun", "kizgin")
# The model's own names are Turkish-spelled and fewer than ours: map ASCII (and the diacritic
# spelling) onto them, None = neutral. "heyecanli" has no model tag of its own; "mutlu" is the
# closest the model has.
POCKET_EMOTION_TAGS = {
    "notr": None,
    "nötr": None,
    "mutlu": "mutlu",
    "sakin": "sakin",
    "heyecanli": "mutlu",
    "heyecanlı": "mutlu",
    "saskin": "şaşkın",
    "şaşkın": "şaşkın",
    "uzgun": "üzgün",
    "üzgün": "üzgün",
    "kizgin": "kızgın",
    "kızgın": "kızgın",
}
POCKET_LICENSE = {
    "title": "Pocket TTS Turkish (ses modeli)",
    "author": "Wite Tech; Kyutai Pocket TTS",
    "license": "CC-BY-4.0 (model), Apache-2.0 (kod)",
    "page": f"https://huggingface.co/{POCKET_REPO}",
}
SYSTEM_VOICE = {"Darwin": "Yelda", "Windows": "Microsoft Tolga"}
WORKER = Path(__file__).with_name("pocket_worker.py")


@dataclass(frozen=True)
class Line:
    text: str
    voice: str | None = None  # engine voice id (pocket: male_1 ...; system: a voice name)
    emotion: str | None = None  # pocket only
    speed: float = 1.0


@dataclass(frozen=True)
class Spoken:
    line: Line
    path: Path
    duration: float
    engine: str


# --------------------------------------------------------------------------- discovery
def _uv() -> str | None:
    found = shutil.which("uv")
    if found:
        return found
    home = Path.home()
    for p in (
        home / ".local" / "bin" / "uv.exe",
        home / ".local" / "bin" / "uv",
        Path("/opt/homebrew/bin/uv"),
    ):
        if p.exists():
            return str(p)
    return None


@cache
def _tool_dir() -> Path | None:  # asked once: the studio polls the setup rows every few seconds
    uv = _uv()
    if not uv:
        return None
    r = subprocess.run([uv, "tool", "dir"], capture_output=True, text=True, encoding="utf-8")
    return Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def _tool_python(package: str, env_var: str) -> Path | None:
    env = os.environ.get(env_var)
    if env:
        return Path(env)
    d = _tool_dir()
    if not d:
        return None
    base = d / package
    for p in (base / "Scripts" / "python.exe", base / "bin" / "python"):
        if p.exists():
            return p
    return None


def qwen_python() -> Path | None:
    """The Python of the qwen-tts tool environment (the channel voice), when installed."""
    return _tool_python(QWEN_PACKAGE, "VLOGKIT_QWEN_PYTHON")


def qwen_installed() -> bool:
    return qwen_python() is not None


def install_qwen_cmd() -> list[str]:
    """Its own isolated environment (torch never enters vlogkit's); the weights (~4 GB) come
    with the first line spoken."""
    uv = _uv()
    if not uv:
        raise RuntimeError("uv bulunamadı: vlogkit kurulumunu yeniden çalıştır")
    return [
        uv,
        "tool",
        "install",
        QWEN_PACKAGE,
        "--python",
        "3.12",
        "--with",
        "soundfile",
        "--with",
        "setuptools<81",
    ]


def pocket_python() -> Path | None:
    """The Python of the pocket-tts-turkish tool environment, when installed."""
    env = os.environ.get("VLOGKIT_POCKET_PYTHON")
    if env:
        return Path(env)
    d = _tool_dir()
    if not d:
        return None
    base = d / POCKET_PACKAGE
    for p in (base / "Scripts" / "python.exe", base / "bin" / "python"):
        if p.exists():
            return p
    return None


def pocket_installed() -> bool:
    return pocket_python() is not None


def install_pocket_cmd() -> list[str]:
    """The command that installs the engine (its own isolated environment, CPU torch)."""
    uv = _uv()
    if not uv:
        raise RuntimeError("uv bulunamadı: vlogkit kurulumunu yeniden çalıştır")
    return [uv, "tool", "install", POCKET_PACKAGE, "--python", "3.12"]


def system_available() -> bool:
    s = platform.system()
    if s == "Darwin":
        return bool(shutil.which("say"))
    if s == "Windows":
        return bool(shutil.which("powershell") or shutil.which("pwsh"))
    return False


def pick_engine(engine: str = "auto") -> str:
    if engine not in ENGINES:
        raise ValueError(f"ses motoru: {' | '.join(ENGINES)}")
    if engine != "auto":
        return engine
    # The system voices (macOS Yelda, Windows Tolga) sound robotic: never chosen on their own; a
    # project can still ask for "system" explicitly (a quick draft without the model).
    if qwen_installed():
        return "qwen"  # the channel voice; Pocket and the system voices only when asked for
    raise RuntimeError(
        "Türkçe ses modeli kurulu değil: Ayarlar > Kurulum > Türkçe ses modeli (ya da `vlogkit 3d install-voice`)"
    )


def system_voices() -> list[str]:
    """Voice names the OS offers (Turkish first)."""
    s = platform.system()
    if s == "Darwin" and shutil.which("say"):
        r = subprocess.run(["say", "-v", "?"], capture_output=True, text=True, encoding="utf-8")
        names = [ln.split("  ")[0].strip() for ln in r.stdout.splitlines() if ln.strip()]
        tr = [ln.split("  ")[0].strip() for ln in r.stdout.splitlines() if "tr_TR" in ln]
        return tr + [n for n in names if n not in tr]
    if s == "Windows":
        ps = (
            "Add-Type -AssemblyName System.Speech;"
            "(New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() |"
            " ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"
        )
        r = subprocess.run(_powershell(ps), capture_output=True, text=True, encoding="utf-8")
        rows = [ln.split("|") for ln in r.stdout.splitlines() if "|" in ln]
        return [n for n, c in rows if c.startswith("tr")] + [
            n for n, c in rows if not c.startswith("tr")
        ]
    return []


def _powershell(script: str) -> list[str]:
    exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    return [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", script]


# --------------------------------------------------------------------------- synthesis
def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _key(line: Line, engine: str, voice: str | None) -> str:
    raw = json.dumps([line.text, voice, line.emotion, line.speed, engine], ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _system_one(line: Line, voice: str | None, out: Path) -> None:
    s = platform.system()
    tmp_text = out.with_suffix(".txt")
    tmp_text.write_text(line.text, encoding="utf-8")
    try:
        if s == "Darwin":
            rate = round(185 * line.speed)
            cmd = [
                "say",
                "-r",
                str(rate),
                "-o",
                str(out),
                "--file-format=WAVE",
                "--data-format=LEI16@24000",
                "-f",
                str(tmp_text),
            ]
            if voice:
                cmd[1:1] = ["-v", voice]
            subprocess.run(cmd, check=True, capture_output=True)
        elif s == "Windows":
            rate = max(-10, min(10, round((line.speed - 1.0) * 10)))
            script = (
                "Add-Type -AssemblyName System.Speech;"
                "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer;"
                f"$v = '{(voice or '').replace(chr(39), '')}';"
                "if ($v) { try { $s.SelectVoice($v) } catch { } } else {"
                " $tr = $s.GetInstalledVoices() | Where-Object { $_.VoiceInfo.Culture.Name -like 'tr*' } | Select-Object -First 1;"
                " if ($tr) { $s.SelectVoice($tr.VoiceInfo.Name) } };"
                f"$s.Rate = {rate};"
                "$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000, [System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono);"
                f"$s.SetOutputToWaveFile('{out}', $fmt);"
                f"$s.Speak([System.IO.File]::ReadAllText('{tmp_text}', [System.Text.Encoding]::UTF8));"
                "$s.Dispose()"
            )
            subprocess.run(_powershell(script), check=True, capture_output=True)
        else:
            raise RuntimeError("sistem sesi yalnız macOS ve Windows'ta var")
    finally:
        tmp_text.unlink(missing_ok=True)


def emotion_tag(name: str | None) -> str | None:
    """Our emotion name -> the model's own tag (None = neutral). Raises on an unknown name."""
    if not name:
        return None
    key = str(name).strip().lower()
    if key not in POCKET_EMOTION_TAGS:
        raise RuntimeError(f"bilinmeyen duygu '{name}' (olanlar: {', '.join(POCKET_EMOTIONS)})")
    return POCKET_EMOTION_TAGS[key]


def _pocket_many(jobs: list[tuple[Line, str | None, Path]], voice_file: Path | None) -> None:
    py = pocket_python()
    if not py:
        raise RuntimeError("Pocket TTS kurulu değil: Ayarlar > Kurulum > Türkçe ses modeli")
    spec = {
        "voice_file": str(voice_file) if voice_file else None,
        "items": [
            {
                "text": ln.text,
                "voice": v or "male_1",
                "emotion": emotion_tag(ln.emotion),
                "speed": ln.speed,
                "out": str(p),
            }
            for ln, v, p in jobs
        ],
    }
    job = jobs[0][2].parent / "_pocket_job.json"
    job.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    r = subprocess.run(
        [str(py), str(WORKER), str(job)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    job.unlink(missing_ok=True)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-6:]
        raise RuntimeError("Pocket TTS çalışmadı: " + " | ".join(tail))


def _qwen_many(jobs: list[tuple[Line, str | None, Path]]) -> None:
    from vlogkit.speech.sayilar import spell

    py = qwen_python()
    if not py:
        raise RuntimeError("Türkçe ses modeli kurulu değil: Ayarlar > Kurulum > Türkçe ses modeli")
    spec = {
        "model": QWEN_MODEL,
        "ref": str(CHANNEL_VOICE),
        "ref_text": CHANNEL_TEXT.read_text(encoding="utf-8").strip()
        if CHANNEL_TEXT.exists()
        else None,
        "items": [{"text": spell(ln.text), "out": str(p)} for ln, _, p in jobs],
    }
    job = jobs[0][2].parent / "_qwen_job.json"
    job.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    env = {
        **os.environ,
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTORCH_ENABLE_MPS_FALLBACK": "1",
    }
    r = subprocess.run(
        [str(py), str(QWEN_WORKER), str(job)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    job.unlink(missing_ok=True)
    if r.returncode != 0:
        tail = (r.stderr or r.stdout).strip().splitlines()[-6:]
        raise RuntimeError("Türkçe ses modeli çalışmadı: " + " | ".join(tail))
    for ln, _, p in jobs:  # the model has no speed of its own: retime after it, pitch untouched
        retime(p, ln.speed)


def retime(path: Path, speed: float) -> None:
    """Slow down (< 1) or speed up (> 1) a spoken line in place, keeping its pitch.

    The channel voice speaks at the reference recording's pace; this is the only way to ask for a
    calmer, heavier delivery (`voice.speed` in scene.json). ffmpeg's atempo takes 0.5-2.0.
    """
    if abs(speed - 1.0) < 0.01:
        return
    if not 0.5 <= speed <= 2.0:
        raise RuntimeError(f"voice.speed 0,5 ile 2,0 arasında olmalı (verilen: {speed})")
    from vlogkit.ff import ffmpeg

    tmp = path.with_name(path.stem + ".retime.wav")
    ffmpeg(["-y", "-i", path, "-filter:a", f"atempo={speed:.3f}", tmp])
    tmp.replace(path)


def speak(
    lines: list[Line],
    out_dir: Path,
    engine: str = "auto",
    voice_file: Path | None = None,
) -> list[Spoken]:
    """Render every line (cached), return them with measured durations, in order."""
    eng = pick_engine(engine)
    out_dir.mkdir(parents=True, exist_ok=True)
    plan = []
    for ln in lines:
        voice = ln.voice
        if eng == "system" and not voice:
            voice = SYSTEM_VOICE.get(platform.system())
            if voice and platform.system() == "Darwin" and voice not in system_voices():
                voice = None
        if eng == "pocket" and (not voice or voice not in POCKET_VOICES):
            voice = "male_1"
        if eng == "qwen":  # one narrator for every video: the line's voice/emotion do not apply
            ref = CHANNEL_VOICE.read_bytes() + (
                CHANNEL_TEXT.read_bytes() if CHANNEL_TEXT.exists() else b""
            )
            voice = "kanal-" + hashlib.sha1(ref).hexdigest()[:8]
        tag = _key(ln, eng, voice) + (
            "-vf" + hashlib.sha1(voice_file.read_bytes()).hexdigest()[:8]
            if voice_file and eng == "pocket"
            else ""
        )
        plan.append((ln, voice, out_dir / f"{tag}.wav"))
    todo = [(ln, v, p) for ln, v, p in plan if not p.exists() or p.stat().st_size < 1000]
    if todo:
        if eng == "qwen":
            _qwen_many(todo)
        elif eng == "pocket":
            _pocket_many(todo, voice_file)
        else:
            for ln, v, p in todo:
                _system_one(ln, v, p)
    return [Spoken(ln, p, wav_duration(p), eng) for ln, v, p in plan]


def main() -> None:  # python -m vlogkit.speech.tts "metin" out.wav
    text, out = sys.argv[1], Path(sys.argv[2])
    s = speak([Line(text)], out.parent)[0]
    shutil.copyfile(s.path, out)
    print(f"{s.engine} {s.duration:.2f}s -> {out}")


if __name__ == "__main__":
    main()
