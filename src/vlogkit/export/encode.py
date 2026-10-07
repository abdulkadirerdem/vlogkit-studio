"""picture (+ alpha graphics layer) + audio -> delivery file."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from vlogkit.ff import ffmpeg
from vlogkit.timecode import FPS_NTSC


@dataclass(frozen=True)
class EncodePreset:
    crf: int = 16  # visually lossless-ish; YouTube re-encodes anyway, feed it quality
    preset: str = "slow"
    profile: str = "high"
    level: str = "4.2"
    gop: int = 60  # 2 s keyframe interval
    audio_bitrate: str = "320k"
    sample_rate: int = 48000
    bframes: int | None = None  # consecutive B-frames; None = x264's own default (3)


SHORTS = EncodePreset()  # 1080x1920 H.264 High, AAC 320k, bt709, +faststart
# The upload file for YouTube Shorts, per YouTube's recommended upload encoding settings
# (support.google.com/youtube/answer/1722171): High profile, 2 consecutive B-frames, closed GOP of
# half the frame rate, CABAC, 4:2:0, AAC-LC 48 kHz stereo at 384 kbps, moov atom at the front.
YOUTUBE_SHORTS = EncodePreset(gop=15, bframes=2, audio_bitrate="384k")
YOUTUBE_LONG = EncodePreset(gop=60, level="5.1")


def compose(
    base: str | Path,
    overlay: str | Path | None,
    audio: str | Path,
    out: str | Path,
    preset: EncodePreset = SHORTS,
    fps: Fraction = FPS_NTSC,
) -> Path:
    args: list = ["-y", "-i", base]
    if overlay:
        args += [
            "-i",
            overlay,
            "-i",
            audio,
            "-filter_complex",
            "[0:v][1:v]overlay=0:0:format=auto:eof_action=pass,format=yuv420p[v]",
            "-map",
            "[v]",
            "-map",
            "2:a",
        ]
    else:
        args += ["-i", audio, "-map", "0:v", "-map", "1:a", "-vf", "format=yuv420p"]
    args += [
        "-c:v",
        "libx264",
        "-preset",
        preset.preset,
        "-crf",
        str(preset.crf),
        "-profile:v",
        preset.profile,
        "-level:v",
        preset.level,
        "-x264-params",
        f"keyint={preset.gop}:min-keyint={preset.gop // 2}"
        + (f":bframes={preset.bframes}" if preset.bframes is not None else ""),
        "-r",
        f"{fps.numerator}/{fps.denominator}",
        "-color_primaries",
        "bt709",
        "-color_trc",
        "bt709",
        "-colorspace",
        "bt709",
        "-c:a",
        "aac",
        "-b:a",
        preset.audio_bitrate,
        "-ar",
        str(preset.sample_rate),
        "-movflags",
        "+faststart",
        "-shortest",
        out,
    ]
    ffmpeg(args, loglevel="warning")
    return Path(out)
