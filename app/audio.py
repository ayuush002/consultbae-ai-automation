"""Validation and metadata extraction for PCM WAV uploads."""
from __future__ import annotations

import audioop
import math
import wave
from pathlib import Path


class AudioValidationError(ValueError):
    pass


def inspect_wav(path: Path) -> dict:
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_width = audio.getsampwidth()
            sample_rate = audio.getframerate()
            frame_count = audio.getnframes()
            compression = audio.getcomptype()
            frames = audio.readframes(frame_count)
    except (wave.Error, EOFError) as error:
        raise AudioValidationError("The uploaded file is not a valid PCM WAV file.") from error

    if compression != "NONE" or sample_width not in {1, 2, 3, 4}:
        raise AudioValidationError("Only uncompressed PCM WAV audio is supported.")
    if not frames or sample_rate <= 0:
        raise AudioValidationError("The WAV file contains no playable audio.")

    duration = frame_count / sample_rate
    rms = audioop.rms(frames, sample_width)
    full_scale = float(2 ** (sample_width * 8 - 1))
    loudness = 20 * math.log10(rms / full_scale) if rms else -96.0
    peak = audioop.max(frames, sample_width) / full_scale

    if peak >= 0.99:
        quality = "Possible clipping"
    elif loudness < -45:
        quality = "Too quiet"
    elif loudness > -3:
        quality = "Very loud"
    else:
        quality = "Good level"

    return {
        "duration_seconds": round(duration, 3),
        "sample_rate_hz": sample_rate,
        "bitrate_kbps": round(sample_rate * sample_width * 8 * channels / 1000, 1),
        "loudness_dbfs": round(loudness, 2),
        "channels": channels,
        "quality_estimate": quality,
    }
