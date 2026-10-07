"""Voice cleanup chain (phone/GoPro/action-cam speech) as an ffmpeg audio filter string.

Order matters:
  highpass (rumble, wind, handling) -> [arnndn] -> afftdn (steady hiss/fan/traffic bed)
  -> EQ (cut mud, add presence) -> deesser (after the presence boost, which sharpens "s")
  -> gentle compressor (evens out near/far talking) -> [lowpass]

Loudness is *not* set here: the final mix is normalised to -14 LUFS by `audio.loudness`.
Use it on the voice/source track only, before mixing with music:

    graph.chain(f"[0:a]atrim=0:{d},asetpts=PTS-STARTPTS,{voice_chain('outdoor-wind')}")

afftdn needs to know how loud the noise is. Its own noise tracking (`tn=1`) barely moved a
steady -39 dBFS hiss in tests (0.7 dB); with a fixed floor set ~4+ dB above the real noise it
removes the full `nr`. So the floor is *measured* (`noise_floor_db`: 10th percentile of 50 ms RMS
windows = the room tone between words) and set 6 dB above that: `voice_for(src, preset)`.
arnndn (RNNoise) is stronger on non-stationary noise but needs a model file (e.g. the
`rnnoise-models` repo); it is only used when a path is given.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from pathlib import Path

from vlogkit.ff import PathLike, ffmpeg
from vlogkit.timecode import fmt


def _lin(db: float) -> float:
    return 10 ** (db / 20)


def _escape(path: PathLike) -> str:
    # filter-graph option values: ':' separates options, '\\' and "'" are special
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


@dataclass(frozen=True)
class Voice:
    """Knobs of the chain. None switches a stage off."""

    highpass: float | None = 80.0  # Hz
    highpass_poles: int = 2  # 2 = 12 dB/oct; wind wants 2 stacked stages (`steep`)
    steep: bool = False
    rnnoise: PathLike | None = None  # RNNoise model file (.rnnn)
    denoise: float | None = 10.0  # afftdn noise reduction, dB
    noise_floor: float = -45.0  # afftdn floor, dB; use voice_for() to set it from the source
    mud: tuple[float, float] | None = (300.0, -2.0)  # (Hz, dB) boxiness cut
    presence: tuple[float, float] | None = (3200.0, 2.5)  # (Hz, dB) intelligibility lift
    deess: float | None = 0.45  # deesser intensity 0..1
    # gentle: ~1.5 dB gain reduction on loud speech; a harder squash lifts the noise floor back
    compress: tuple[float, float] | None = (-18.0, 2.0)  # (threshold dB, ratio)
    makeup: float = 1.0  # dB after the compressor
    lowpass: float | None = None  # Hz

    def but(self, **changes) -> Voice:
        return replace(self, **changes)

    def filter(self) -> str:
        parts: list[str] = []
        if self.highpass:
            hp = f"highpass=f={fmt(self.highpass)}:p={self.highpass_poles}"
            parts += [hp, hp] if self.steep else [hp]
        if self.rnnoise:
            parts.append(f"arnndn=m='{_escape(self.rnnoise)}'")
        if self.denoise:
            nf = min(-20.0, max(-80.0, self.noise_floor))
            parts.append(f"afftdn=nr={fmt(self.denoise)}:nf={fmt(nf)}")
        if self.mud:
            parts.append(f"equalizer=f={fmt(self.mud[0])}:t=o:w=1.2:g={fmt(self.mud[1])}")
        if self.presence:
            parts.append(f"equalizer=f={fmt(self.presence[0])}:t=o:w=1.4:g={fmt(self.presence[1])}")
        if self.deess:
            parts.append(f"deesser=i={fmt(self.deess)}:m=0.5:f=0.5:s=o")
        if self.compress:
            th, ratio = self.compress
            parts.append(
                f"acompressor=threshold={_lin(th):.5f}:ratio={fmt(ratio)}:attack=15:release=180:"
                f"knee=4:makeup={max(1.0, _lin(self.makeup)):.4f}"
            )
        if self.lowpass:
            parts.append(f"lowpass=f={fmt(self.lowpass)}")
        return ",".join(parts) or "anull"


PRESETS: dict[str, Voice] = {
    # quiet room, decent mic: just tidy up
    "light": Voice(),
    # phone held at arm's length: boxy and thin, more hiss, uneven distance
    "phone": Voice(
        highpass=100.0,
        denoise=14.0,
        mud=(450.0, -3.5),
        presence=(3500.0, 3.0),
        compress=(-20.0, 2.5),
        makeup=1.5,
    ),
    # outside with wind / traffic: steep low cut, stronger denoise, no extra presence
    # (it would lift the wind hiss), soft top
    "outdoor-wind": Voice(
        highpass=140.0,
        steep=True,
        denoise=18.0,
        noise_floor=-38.0,
        mud=(250.0, -2.0),
        presence=(2800.0, 1.5),
        deess=0.35,
        compress=(-20.0, 2.0),
        makeup=1.0,
        lowpass=11000.0,
    ),
}


def voice_chain(preset: str | Voice = "light", **overrides) -> str:
    """Filter string for a preset name (or a Voice), with field overrides."""
    v = PRESETS[preset] if isinstance(preset, str) else preset
    return (v.but(**overrides) if overrides else v).filter()


def noise_floor_db(
    src: PathLike, start: float = 0.0, duration: float | None = None, percentile: float = 0.1
) -> float:
    """Noise floor of a recording in dBFS: a low percentile of 50 ms RMS windows (mono, 48 kHz).

    Speech has pauses, so the quiet windows are the room tone / hiss / wind under the voice.
    Full band on purpose: resampling to 16 kHz would drop the top of broadband hiss (~5 dB).
    """
    args: list = ["-ss", f"{start:.3f}", "-i", src]
    if duration:
        args += ["-t", f"{duration:.3f}"]
    key = "lavfi.astats.Overall.RMS_level"
    af = (
        "aresample=48000,asetnsamples=n=2400:p=0,astats=metadata=1:reset=1,"
        f"ametadata=mode=print:key={key}:file=-"
    )
    r = ffmpeg([*args, "-vn", "-ac", "1", "-af", af, "-f", "null", "-"], capture=True)
    levels = sorted(float(x) for x in re.findall(rf"{re.escape(key)}=(-?[\d.]+)", r.stdout))
    if not levels:
        return -90.0
    return levels[min(len(levels) - 1, int(len(levels) * percentile))]


def voice_for(
    src: PathLike, preset: str | Voice = "light", margin: float = 6.0, cap: float = -30.0, **kw
) -> Voice:
    """The preset with afftdn's floor set from the source's measured noise (+ margin dB).

    Measure the *raw* voice track. On material that already has music under it the quiet
    windows are the music, and denoising "down to" it would chew the music; `cap` keeps the
    floor at or below -30 dBFS (loud wind on a GoPro measures around -35).
    """
    v = PRESETS[preset] if isinstance(preset, str) else preset
    return v.but(noise_floor=min(cap, noise_floor_db(src, **kw) + margin))


def clean_voice(src: PathLike, out: PathLike, preset: str | Voice = "light", **overrides) -> Path:
    """Render just the cleaned audio of `src` (wav/m4a...), e.g. to A/B it by ear."""
    ffmpeg(["-y", "-i", src, "-vn", "-af", voice_chain(preset, **overrides), out])
    return Path(out)
