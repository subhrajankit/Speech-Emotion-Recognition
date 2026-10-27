"""
Test doubles (fakes and stubs) for unit and integration testing.
Per AG Kit rules and project standards:
Fake engines MUST live in tests/ only, injected explicitly into tests.
They are NEVER accessible or executed in runtime production code.
"""

from typing import Optional, Dict, Any, List
import numpy as np

from ai.inference.types import SpeechResult
from ai.inference.engine import SpeechEngine
from ai.preprocessing.vad import VADResult


class FakeSenseVoiceEngine(SpeechEngine):
    """
    Explicit test double simulating SenseVoiceSmall for testing WebSocket framing,
    event ordering, chunking, and language routing.
    Never claims to perform real deep learning inference.
    """
    def __init__(
        self,
        simulated_transcript: str = "Hello world, this is a simulated transcription.",
        simulated_language: str = "en",
        simulated_emotion: Optional[str] = "neutral",
        simulated_processing_ms: float = 25.0,
    ):
        self._simulated_transcript = simulated_transcript
        self._simulated_language = simulated_language
        self._simulated_emotion = simulated_emotion
        self._simulated_processing_ms = simulated_processing_ms
        self.is_loaded = True

    @property
    def model_version(self) -> str:
        return "FakeSenseVoiceForTests (tests-only double)"

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        language_hint: Optional[str] = None,
        use_itn: bool = True,
        **kwargs
    ) -> SpeechResult:
        chosen_lang = language or language_hint
        lang = chosen_lang if (chosen_lang and chosen_lang != "auto") else self._simulated_language
        return SpeechResult(
            transcript=self._simulated_transcript,
            language=lang,
            emotion=self._simulated_emotion,
            confidence=0.95,
            raw_tags={"mock": True},
            processing_time_ms=self._simulated_processing_ms,
            model_version=self.model_version,
            debug={"status": "fake_test_double", "vad_has_speech": True},
        )


class FakeIndicConformerEngine(SpeechEngine):
    """
    Explicit test double simulating IndicConformer-600m for Hindi/Indic testing.
    Never claims to perform real deep learning inference.
    """
    def __init__(
        self,
        simulated_transcript: str = "नमस्ते, यह एक परीक्षण ट्रांसक्रिप्शन है।",
        simulated_language: str = "hi",
        simulated_processing_ms: float = 30.0,
    ):
        self._simulated_transcript = simulated_transcript
        self._simulated_language = simulated_language
        self._simulated_processing_ms = simulated_processing_ms
        self.is_loaded = True

    @property
    def model_version(self) -> str:
        return "FakeIndicConformerForTests (tests-only double)"

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language: Optional[str] = None,
        language_hint: Optional[str] = None,
        use_itn: bool = True,
        **kwargs
    ) -> SpeechResult:
        chosen_lang = language or language_hint
        return SpeechResult(
            transcript=self._simulated_transcript,
            language=chosen_lang or self._simulated_language,
            emotion=None,  # IndicConformer does NOT do SER
            confidence=0.92,
            raw_tags={"mock": True},
            processing_time_ms=self._simulated_processing_ms,
            model_version=self.model_version,
            debug={"status": "fake_test_double", "vad_has_speech": True},
        )


class SlowLoadingFakeEngine(SpeechEngine):
    """
    Explicit test double simulating a lazy-loading engine with a controlled delay.
    Maintains is_loaded=False until load() is invoked.
    """
    def __init__(
        self,
        load_delay: float = 0.05,
        simulated_transcript: str = "Loaded after delay.",
        simulated_language: str = "en",
    ):
        self._load_delay = load_delay
        self._simulated_transcript = simulated_transcript
        self._simulated_language = simulated_language
        self.is_loaded = False
        self.load_count = 0

    @property
    def model_version(self) -> str:
        return "SlowLoadingFakeEngine (tests-only double)"

    def load(self) -> None:
        import time
        if self._load_delay > 0:
            time.sleep(self._load_delay)
        self.is_loaded = True
        self.load_count += 1

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        **kwargs
    ) -> SpeechResult:
        if not self.is_loaded:
            self.load()
        return SpeechResult(
            transcript=self._simulated_transcript,
            language=self._simulated_language,
            emotion="neutral",
            confidence=0.95,
            processing_time_ms=10.0,
            model_version=self.model_version,
            debug={"status": "fake_slow_engine", "vad_has_speech": True},
        )


class FakeSileroVAD:
    """Explicit test double simulating Silero VAD without ONNX weights."""
    def __init__(self, has_speech: bool = True, speech_probability: float = 0.95):
        self.has_speech = has_speech
        self.speech_probability = speech_probability
        self.is_loaded = True

    def process_chunk(self, chunk: np.ndarray) -> float:
        return self.speech_probability if self.has_speech else 0.01

    def process_utterance(self, audio: np.ndarray) -> VADResult:
        duration_ms = float(len(audio) / 16.0)
        return VADResult(
            has_speech=self.has_speech,
            speech_probability=self.speech_probability,
            speech_duration_ms=duration_ms if self.has_speech else 0.0,
            num_speech_frames=int(duration_ms / 32),
        )

    def reset(self):
        pass


class FakeEmbeddings:
    """Explicit test double for sentence embeddings in unit/integration tests."""
    def __init__(self, model_id: str = "test-double-e5", dimension: int = 384):
        self.model_id = model_id
        self.dimension = dimension
        self.is_loaded = True

    def _embed_str(self, text: str) -> np.ndarray:
        import hashlib
        h = hashlib.sha256(text.encode("utf-8")).digest()
        raw = np.frombuffer(h, dtype=np.uint8).astype(np.float32)
        reps = int(np.ceil(self.dimension / len(raw)))
        vec = np.tile(raw, reps)[:self.dimension]
        norm = np.linalg.norm(vec)
        return (vec / (norm + 1e-9)).astype(np.float32)

    def embed_query(self, query: str) -> np.ndarray:
        return self._embed_str(f"query: {query.strip()}")

    def embed_passages(self, passages: List[str]) -> np.ndarray:
        return np.array([self._embed_str(f"passage: {p.strip()}") for p in passages], dtype=np.float32)

    def embed_documents(self, documents: List[str]) -> np.ndarray:
        return self.embed_passages(documents)

