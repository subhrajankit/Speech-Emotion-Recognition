import io
import soundfile as sf
import pytest
from src.backend.models.tts import IndicParlerTTS

def test_tts_mock_wav_generation():
    tts = IndicParlerTTS(mock=True)
    assert tts.is_loaded is True

    text = "Hello world"
    wav_bytes = tts.synthesize_wav(text)
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 44  # WAV header is 44 bytes minimum

    # Validate that it can be parsed as a valid WAV audio file
    wav_io = io.BytesIO(wav_bytes)
    data, sample_rate = sf.read(wav_io)
    assert sample_rate in (16000, 24000)
    assert len(data) > 0
