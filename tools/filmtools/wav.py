"""PCM/WAV helpers. Audio is float32 in memory and 24-bit WAV on disk, at 48 kHz."""
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 48000


def pcm16_to_float(b: bytes, channels: int = 1) -> np.ndarray:
    x = np.frombuffer(b, dtype="<i2").astype(np.float32) / 32768.0
    return x.reshape(-1, channels) if channels > 1 else x


def write_wav(path: Path, samples: np.ndarray, sr: int = SR) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), np.asarray(samples, dtype=np.float32), sr, subtype="PCM_24")


def read_wav(path: Path, mono: bool = True) -> tuple[np.ndarray, int]:
    x, sr = sf.read(str(path), dtype="float32", always_2d=False)
    if mono and x.ndim == 2:
        x = x.mean(axis=1)
    return x, sr
