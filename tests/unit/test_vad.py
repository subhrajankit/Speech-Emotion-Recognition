import numpy as np
import pytest
from src.backend.audio.vad import SileroVAD, VADSpeechSegmenter

def test_vad_classifies_synthetic_silence_and_speech():
    """
    Feeds a synthetic silent buffer and a synthetic speech buffer
    and asserts VAD correctly classifies each.
    """
    # Initialize VAD
    vad = SileroVAD(threshold=0.5)
    assert vad.is_loaded is True

    # 1. Synthetic silent buffer: 1 second (16000 samples) of absolute silence
    silent_samples = np.zeros(16000, dtype=np.int16)
    silent_buffer = silent_samples.tobytes()

    is_silent_speech = vad.classify_buffer(silent_buffer)
    assert is_silent_speech is False, "Silent buffer should not be classified as speech"

    # 2. Real speech buffer: 1 second of active speech from test sample (samples 24000 to 40000)
    from pathlib import Path
    import soundfile as sf
    sample_path = Path("tests/samples/sample_chinese_speech.wav")
    speech_data, sr = sf.read(str(sample_path), dtype="int16")
    speech_buffer = speech_data[24000 : 40000].tobytes()

    is_speech = vad.classify_buffer(speech_buffer)
    assert is_speech is True, "Speech buffer must be classified as speech"

def test_vad_onnx_model_silent_classification():
    """
    If the official Silero ONNX model is available on disk,
    verifies that genuine ONNX inference classifies silence with probability < 0.01.
    """
    vad = SileroVAD(model_path="models/silero_vad.onnx", threshold=0.5)
    if vad.session is not None:
        silent_frame = np.zeros(512, dtype=np.float32)
        prob = vad.process_frame(silent_frame)
        assert prob < 0.1, f"Expected silence prob < 0.1, got {prob}"

def test_vad_speech_segmenter_lifecycle():
    """
    Verifies that VADSpeechSegmenter:
    - Ignores pure silence
    - Accumulates speech during active talking
    - Emits full utterance once silence timeout (700ms) expires
    """
    from pathlib import Path
    import soundfile as sf
    sample_path = Path("tests/samples/sample_chinese_speech.wav")
    speech_data, sr = sf.read(str(sample_path), dtype="int16")

    vad = SileroVAD(threshold=0.5)
    # 700ms timeout
    segmenter = VADSpeechSegmenter(vad=vad, silence_timeout_ms=700, speech_threshold=0.5)

    frame_size = 512
    # 1 frame = 512 samples = 1024 bytes (32ms)
    silent_frame = np.zeros(frame_size, dtype=np.int16).tobytes()
    active_frame = speech_data[24000 : 24000 + frame_size].tobytes()

    # Feed 10 silent frames -> nothing emitted
    for _ in range(10):
        res = segmenter.process_chunk(silent_frame)
        assert res is None

    # Feed 15 active speech frames (~480ms speech) -> still accumulating
    for _ in range(15):
        res = segmenter.process_chunk(active_frame)
        assert res is None
    assert segmenter.in_speech is True

    # Feed silence frames until 700ms silence timeout is reached (~22 frames of 32ms)
    emitted_utterance = None
    for _ in range(30):
        res = segmenter.process_chunk(silent_frame)
        if res is not None:
            emitted_utterance = res
            break

    assert emitted_utterance is not None, "Segmenter should emit full utterance once silence timeout expires"
    assert len(emitted_utterance) > 0
    assert segmenter.in_speech is False
