"""
Unit tests for Silero VAD implementation and guarantees.
"""

from pathlib import Path
import numpy as np
import pytest

from ai.preprocessing.vad import SileroVAD, VADSpeechSegmenter, VADResult
from ai.preprocessing.audio import load_and_preprocess_audio, decode_audio


def test_silero_vad_onnx_model_loaded():
    """Verifies Silero VAD ONNX model loads successfully on CPU."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.5)
    assert vad.is_loaded is True
    assert vad.session is not None


def test_silero_vad_synthetic_silence_explicit_no_speech():
    """Synthetic silence must return VADResult(has_speech=False) with probability near 0."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.5)
    silent_audio = np.zeros(16000, dtype=np.float32)  # 1 second of silence
    res: VADResult = vad.analyze(silent_audio, sample_rate=16000)

    assert isinstance(res, VADResult)
    assert res.has_speech is False
    assert res.speech_probability < 0.1
    assert res.num_speech_frames == 0


def test_silero_vad_empty_audio_returns_no_speech():
    """Empty or None audio must return explicit no-speech, never an exception."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.5)

    res_empty = vad.analyze(np.array([], dtype=np.float32))
    assert res_empty.has_speech is False
    assert res_empty.speech_probability == 0.0

    res_none = vad.analyze(None)
    assert res_none.has_speech is False


def test_silero_vad_sub_minimum_duration_returns_no_speech():
    """Clips shorter than min_speech_duration_ms return explicit no-speech."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", min_speech_duration_ms=250)
    # 100ms at 16kHz = 1600 samples
    short_clip = np.ones(1600, dtype=np.float32) * 0.5
    res = vad.analyze(short_clip, sample_rate=16000)

    assert res.has_speech is False
    assert res.speech_probability == 0.0


def test_silero_vad_real_speech_sample_detected():
    """Real speech sample must be classified with has_speech=True."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.5)
    sample_path = Path("tests/samples/sample_chinese_speech.wav")
    assert sample_path.exists()

    audio = load_and_preprocess_audio(sample_path, target_sr=16000)
    res = vad.analyze(audio, sample_rate=16000)

    assert res.has_speech is True
    assert res.speech_probability > 0.4
    assert res.speech_duration_ms > 1000.0


def test_vad_classify_buffer_compatibility():
    """Ensures legacy classify_buffer method functions correctly."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.5)
    silent_pcm = np.zeros(16000, dtype=np.int16).tobytes()
    assert vad.classify_buffer(silent_pcm) is False


def test_vad_speech_segmenter_stream():
    """Verifies VADSpeechSegmenter stream accumulation and silence timeout detection."""
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.4)
    segmenter = VADSpeechSegmenter(vad=vad, silence_timeout_ms=500, speech_threshold=0.4)

    frame_size = 512
    silent_frame = np.zeros(frame_size, dtype=np.int16).tobytes()

    # Load genuine speech samples
    sample_path = Path("tests/samples/sample_chinese_speech.wav")
    assert sample_path.exists()
    speech_data, _ = decode_audio(sample_path)
    # Convert middle segment of speech to PCM16 bytes
    speech_pcm = (speech_data[16000:32000] * 32767).astype(np.int16).tobytes()

    # Initial silence yields None
    for _ in range(5):
        assert segmenter.process_chunk(silent_frame) is None

    # Feed speech chunks (each frame_size * 2 = 1024 bytes)
    frame_bytes = frame_size * 2
    num_speech_chunks = len(speech_pcm) // frame_bytes
    for i in range(min(15, num_speech_chunks)):
        chunk = speech_pcm[i * frame_bytes : (i + 1) * frame_bytes]
        segmenter.process_chunk(chunk)
    assert segmenter.in_speech is True

    # Trailing silence triggers utterance completion
    emitted = None
    for _ in range(30):
        res = segmenter.process_chunk(silent_frame)
        if res is not None:
            emitted = res
            break

    assert emitted is not None
    assert len(emitted) > 0
    assert segmenter.in_speech is False


class _ScriptedStreamingVAD:
    """Deterministic per-frame VAD double for VADSpeechSegmenter tests."""
    def __init__(self, probs):
        self._probs = list(probs)

    def process_frame(self, frame_samples):
        return self._probs.pop(0) if self._probs else 0.0

    def reset(self):
        pass


def _frame_bytes() -> bytes:
    return b"\x01\x00" * 512  # 1024 bytes = one 32ms PCM16 frame


def test_segmenter_flush_while_idle_returns_none():
    """Stop while idle: the non-speech pre-buffer must NOT be returned for ASR."""
    segmenter = VADSpeechSegmenter(
        vad=_ScriptedStreamingVAD([0.0] * 40),
        silence_timeout_ms=500,
        speech_threshold=0.5,
    )
    for _ in range(20):
        assert segmenter.process_chunk(_frame_bytes()) is None
    assert segmenter.in_speech is False
    assert segmenter.flush() is None


def test_segmenter_flush_during_speech_returns_audio():
    """Stop mid-utterance: genuine in-progress speech is still flushed."""
    segmenter = VADSpeechSegmenter(
        vad=_ScriptedStreamingVAD([0.9] * 20),
        silence_timeout_ms=500,
        speech_threshold=0.5,
    )
    for _ in range(10):
        segmenter.process_chunk(_frame_bytes())
    assert segmenter.in_speech is True

    flushed = segmenter.flush()
    assert flushed is not None
    assert len(flushed) > 0
    assert segmenter.in_speech is False
    # Repeated flush after reset is a no-op.
    assert segmenter.flush() is None


def test_segmenter_flush_after_completed_segment_returns_none():
    """Regression: after a VAD-completed utterance plus trailing silence,
    stop-flush must not resubmit the idle pre-buffer as a phantom segment."""
    # 10 speech frames, then enough silence (>500ms = 16 frames) to complete.
    segmenter = VADSpeechSegmenter(
        vad=_ScriptedStreamingVAD([0.9] * 10 + [0.0] * 40),
        silence_timeout_ms=500,
        speech_threshold=0.5,
    )
    completed = None
    for _ in range(26):
        res = segmenter.process_chunk(_frame_bytes())
        if res is not None:
            completed = res
            break
    assert completed is not None
    assert segmenter.in_speech is False

    # Trailing idle frames accumulate only in the pre-buffer.
    for _ in range(10):
        assert segmenter.process_chunk(_frame_bytes()) is None
    assert segmenter.flush() is None
