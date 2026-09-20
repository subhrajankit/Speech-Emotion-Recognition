import numpy as np
import pytest
from src.backend.models.asr import SenseVoiceASR

def test_sensevoice_mock_mode():
    asr = SenseVoiceASR(mock=True)
    assert asr.is_loaded is True

    # 1 second of 16kHz silent PCM16 audio
    silence_pcm = np.zeros(16000, dtype=np.int16).tobytes()
    transcript = asr.transcribe(silence_pcm)
    assert isinstance(transcript, str)
    assert len(transcript) > 0

def test_sensevoice_empty_audio():
    asr = SenseVoiceASR(mock=True)
    transcript = asr.transcribe(b"")
    assert transcript == ""
