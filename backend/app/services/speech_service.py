"""
Speech service wrapping the Phase 1 perception engine (SenseVoiceSmall).
Handles:
- Singleton lifecycle (loads once at startup)
- Threadpool execution with bounded concurrency limit
- In-memory decoding with zero disk persistence
- Component health reporting
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import numpy as np

from ai.inference.types import SpeechResult
from ai.inference.sensevoice import SenseVoiceSpeechEngine
from ai.preprocessing.audio import load_and_preprocess_audio
from backend.app.core.config import settings

logger = logging.getLogger("voicesense.speech_service")


class SpeechService:
    """
    Manages speech perception inference with bounded concurrency and non-blocking execution.
    """

    def __init__(self):
        self._engine: Optional[SenseVoiceSpeechEngine] = None
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._is_initialized: bool = False
        self._init_error: Optional[str] = None

    def initialize(self) -> None:
        """
        Loads the speech engine once during application lifespan startup.
        Never called per-request.
        """
        if self._is_initialized and self._engine is not None:
            return

        logger.info(f"Initializing SpeechService (mock={settings.MOCK_MODELS})...")
        try:
            self._engine = SenseVoiceSpeechEngine(
                model_dir=settings.SENSEVOICE_MODEL_DIR,
                device=settings.SENSEVOICE_DEVICE,
                threads=settings.SENSEVOICE_THREADS,
                vad_threshold=settings.VAD_THRESHOLD,
                mock=settings.MOCK_MODELS,
                auto_load=not settings.MOCK_MODELS,
            )
            self._is_initialized = True
            self._init_error = None
            logger.info("SpeechService initialized successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialize real SenseVoice model ({e}). Falling back to mock engine.")
            self._init_error = str(e)
            # Fallback to mock so the application can start degraded rather than crashing
            self._engine = SenseVoiceSpeechEngine(
                model_dir=settings.SENSEVOICE_MODEL_DIR,
                device=settings.SENSEVOICE_DEVICE,
                threads=settings.SENSEVOICE_THREADS,
                vad_threshold=settings.VAD_THRESHOLD,
                mock=True,
                auto_load=False,
            )
            self._is_initialized = True

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily binds semaphore to the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.INFERENCE_CONCURRENCY_LIMIT)
        return self._semaphore

    @property
    def is_ready(self) -> bool:
        return self._is_initialized and self._engine is not None

    async def transcribe_array(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Runs inference off the event loop via threadpool with bounded concurrency.
        """
        if not self.is_ready:
            raise RuntimeError("SpeechService is not initialized.")

        sem = self._get_semaphore()
        async with sem:
            result = await asyncio.to_thread(
                self._engine.transcribe,
                audio=audio,
                sample_rate=sample_rate,
                language_hint=language_hint
            )
            return result

    async def transcribe_audio_bytes(
        self,
        audio_bytes: bytes,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Decodes audio bytes entirely in memory and executes bounded inference.
        Stores zero audio on disk.
        """
        if not audio_bytes:
            raise ValueError("Audio bytes are empty.")

        # Decode entirely in memory
        try:
            audio_array = load_and_preprocess_audio(audio_bytes, target_sr=sample_rate)
        except Exception as e:
            logger.error(f"In-memory audio decode error: {e}")
            raise ValueError(f"Could not decode audio data: {e}") from e

        if audio_array is None or len(audio_array) == 0:
            raise ValueError("Decoded audio contains zero samples.")

        return await self.transcribe_array(
            audio=audio_array,
            sample_rate=sample_rate,
            language_hint=language_hint
        )

    async def transcribe_pcm16_bytes(
        self,
        pcm_bytes: bytes,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Converts raw 16kHz PCM16 bytes to float32 in memory and executes inference.
        """
        if not pcm_bytes:
            raise ValueError("PCM bytes are empty.")

        # 16-bit signed integer conversion
        int16_data = np.frombuffer(pcm_bytes, dtype=np.int16)
        if len(int16_data) == 0:
            raise ValueError("PCM data contains zero samples.")

        float32_data = int16_data.astype(np.float32) / 32768.0
        return await self.transcribe_array(
            audio=float32_data,
            sample_rate=sample_rate,
            language_hint=language_hint
        )

    def get_health_status(self) -> Dict[str, Any]:
        """
        Returns per-component status.
        Placeholders for llm, rag, tts, db are 'not_configured'.
        Overall status is 'ok' or 'degraded'; does not fail for optional components.
        """
        is_mock = self._engine.mock if self._engine else False
        is_error = self._init_error is not None

        if self.is_ready and not is_error and not is_mock:
            asr_status = "ok"
            emotion_status = "ok"
            overall_status = "ok"
        elif self.is_ready:
            asr_status = "degraded"
            emotion_status = "degraded"
            overall_status = "degraded"
        else:
            asr_status = "unhealthy"
            emotion_status = "unhealthy"
            overall_status = "degraded"

        components = {
            "asr": asr_status,
            "emotion": emotion_status,
            "llm": "not_configured",
            "rag": "not_configured",
            "tts": "not_configured",
            "db": "not_configured",
        }

        details = {
            "model_version": self._engine.model_version if self._engine else "none",
            "concurrency_limit": settings.INFERENCE_CONCURRENCY_LIMIT,
        }
        if self._init_error:
            details["asr_init_warning"] = self._init_error

        return {
            "status": overall_status,
            "components": components,
            "details": details
        }


# Global singleton instance
speech_service = SpeechService()
