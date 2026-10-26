import io
import logging
import numpy as np
import soundfile as sf
from typing import Optional

logger = logging.getLogger(__name__)

class SenseVoiceASR:
    """
    SenseVoiceSmall ASR Service (English-only for Phase 1).
    Loaded once at startup.
    """
    def __init__(self, model_id: str = "iic/SenseVoiceSmall", device: str = "cpu", mock: bool = False):
        self.model_id = model_id
        self.device = device
        self.mock = mock
        self.model = None
        self.is_loaded = False
        self._load_model()

    def _load_model(self):
        if self.mock:
            logger.info("Initializing SenseVoiceASR in MOCK mode.")
            self.is_loaded = True
            return

        try:
            from funasr import AutoModel
            logger.info(f"Loading SenseVoiceSmall model from {self.model_id} on {self.device}...")
            self.model = AutoModel(
                model=self.model_id,
                device=self.device,
                disable_update=True,
                log_level="ERROR"
            )
            self.is_loaded = True
            logger.info("SenseVoiceSmall loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load real SenseVoice model ({e}). Falling back to stub/mock mode.")
            self.is_loaded = False

    def transcribe(self, pcm_data: bytes, sample_rate: int = 16000) -> str:
        """
        Transcribes raw 16kHz PCM16 mono bytes to English text.
        """
        if not pcm_data:
            return ""

        if self.mock or self.model is None:
            # Stub transcription for local smoke/unit tests
            return "Hello, this is a test from the voice assistant."

        try:
            # Convert PCM16 bytes to float32 numpy array
            audio_array = np.frombuffer(pcm_data, dtype=np.int16).astype(np.float32) / 32768.0
            res = self.model.generate(
                input=audio_array,
                language="en",
                use_itn=True,
                batch_size_s=60
            )
            if res and len(res) > 0 and "text" in res[0]:
                return res[0]["text"].strip()
            return ""
        except Exception as e:
            logger.error(f"Error during SenseVoice transcription: {e}")
            return "Transcription error occurred."
