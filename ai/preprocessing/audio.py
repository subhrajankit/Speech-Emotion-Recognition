"""
Audio preprocessing pipeline: decode → mono → 16 kHz float32 → normalize.
"""

import io
from pathlib import Path
from typing import Union, Tuple
import numpy as np
import soundfile as sf


def to_mono(audio: np.ndarray) -> np.ndarray:
    """
    Downmixes multi-channel audio to single-channel mono.
    Supports shapes (samples,), (samples, channels), or (channels, samples).
    """
    if audio.ndim == 1:
        return audio

    if audio.ndim == 2:
        # If shape is (channels, samples) where channels <= 8 and samples > channels
        if audio.shape[0] <= 8 and audio.shape[1] > audio.shape[0]:
            return np.mean(audio, axis=0)
        # Otherwise assume (samples, channels)
        return np.mean(audio, axis=-1)

    raise ValueError(f"Unsupported audio shape for mono conversion: {audio.shape}")


def resample_audio(audio: np.ndarray, orig_sr: int, target_sr: int = 16000) -> np.ndarray:
    """
    Resamples 1D audio array from orig_sr to target_sr using linear interpolation.
    """
    if orig_sr == target_sr:
        return audio

    if len(audio) == 0:
        return np.array([], dtype=audio.dtype)

    num_target_samples = int(round(len(audio) * target_sr / orig_sr))
    if num_target_samples <= 0:
        return np.array([], dtype=audio.dtype)

    orig_indices = np.linspace(0, len(audio) - 1, num=len(audio))
    target_indices = np.linspace(0, len(audio) - 1, num=num_target_samples)
    resampled = np.interp(target_indices, orig_indices, audio)
    return resampled.astype(audio.dtype)


def normalize_audio(audio: np.ndarray, peak: float = 0.95) -> np.ndarray:
    """
    Converts audio to float32 in [-1.0, 1.0] and scales peak amplitude to `peak`.
    If maximum amplitude is near zero (silence), returns unmodified zeroed array.
    """
    if len(audio) == 0:
        return np.array([], dtype=np.float32)

    # Cast integer formats to float32
    if np.issubdtype(audio.dtype, np.integer):
        max_val = float(np.iinfo(audio.dtype).max)
        audio_float = audio.astype(np.float32) / max_val
    else:
        audio_float = audio.astype(np.float32)

    max_abs = float(np.max(np.abs(audio_float)))
    if max_abs > 1e-6:
        # Scale to target peak to maintain consistent dynamic range
        scale = min(peak / max_abs, 10.0)
        audio_float = audio_float * scale

    # Hard clamp to strictly [-1.0, 1.0]
    return np.clip(audio_float, -1.0, 1.0)


def decode_audio(
    audio_input: Union[str, Path, bytes, np.ndarray],
    sample_rate: int = 16000
) -> Tuple[np.ndarray, int]:
    """
    Decodes audio input from path, raw bytes, or array into (samples, orig_sr).
    """
    if isinstance(audio_input, (str, Path)):
        path = Path(audio_input)
        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")
        if path.stat().st_size == 0:
            return np.array([], dtype=np.float32), sample_rate
        data, sr = sf.read(str(path), dtype="float32")
        return data, sr

    if isinstance(audio_input, bytes):
        if len(audio_input) == 0:
            return np.array([], dtype=np.float32), sample_rate

        # Try reading as containerized audio format (e.g. WAV, OGG, FLAC)
        try:
            with io.BytesIO(audio_input) as bio:
                data, sr = sf.read(bio, dtype="float32")
                return data, sr
        except Exception:
            # Fallback: treat as raw 16-bit PCM at given sample_rate
            samples = np.frombuffer(audio_input, dtype=np.int16).astype(np.float32) / 32768.0
            return samples, sample_rate

    if isinstance(audio_input, np.ndarray):
        return audio_input, sample_rate

    raise TypeError(f"Unsupported audio input type: {type(audio_input)}")


def load_and_preprocess_audio(
    audio_input: Union[str, Path, bytes, np.ndarray],
    target_sr: int = 16000,
    peak_norm: float = 0.95
) -> np.ndarray:
    """
    Full preprocessing pipeline:
    1. Decode from file, bytes, or ndarray
    2. Convert to mono
    3. Resample to target_sr (default 16000 Hz)
    4. Normalize float32 to [-1.0, 1.0]
    """
    data, orig_sr = decode_audio(audio_input, sample_rate=target_sr)

    if len(data) == 0:
        return np.array([], dtype=np.float32)

    mono = to_mono(data)
    resampled = resample_audio(mono, orig_sr, target_sr)
    normalized = normalize_audio(resampled, peak=peak_norm)
    return normalized
