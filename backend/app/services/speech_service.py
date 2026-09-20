"""
Speech service wrapping perception engines (SenseVoiceSmall and IndicConformer-600m).
Handles:
- Singleton lifecycle (loads once at application startup)
- Dynamic language routing via LanguageRouter
- Threadpool execution with bounded concurrency limit
- In-memory decoding with zero disk persistence
- Component health reporting
"""

import asyncio
import logging
from typing import Optional, Dict, Any
import numpy as np

from ai.inference.types import SpeechResult
from ai.inference.engine import SpeechEngine
from ai.inference.sensevoice import SenseVoiceSpeechEngine
from ai.inference.indicconformer import IndicConformerSpeechEngine
from ai.routing.language_router import LanguageRouter, RoutingDecision
from ai.preprocessing.audio import load_and_preprocess_audio
from backend.app.core.config import settings

logger = logging.getLogger("voicesense.speech_service")


class SpeechService:
    """
    Manages speech perception inference with bounded concurrency,
    dynamic language routing, and non-blocking execution.
    """

    def __init__(self):
        self._sensevoice: Optional[SenseVoiceSpeechEngine] = None
        self._indicconformer: Optional[IndicConformerSpeechEngine] = None
        self._router: Optional[LanguageRouter] = None
        self._engine: Optional[SpeechEngine] = None  # Default engine alias
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._is_initialized: bool = False
        self._init_error: Optional[str] = None
        self._indic_init_error: Optional[str] = None

    def initialize(self) -> None:
        """
        Loads the speech engines and language router once during application lifespan startup.
        Never called per-request.
        """
        if self._is_initialized and self._engine is not None:
            return

        logger.info(f"Initializing SpeechService (mock={settings.MOCK_MODELS})...")

        # 1. Initialize SenseVoiceSmall (Global ASR + SER)
        try:
            self._sensevoice = SenseVoiceSpeechEngine(
                model_dir=settings.SENSEVOICE_MODEL_DIR,
                device=settings.SENSEVOICE_DEVICE,
                threads=settings.SENSEVOICE_THREADS,
                vad_threshold=settings.VAD_THRESHOLD,
                mock=settings.MOCK_MODELS,
                auto_load=not settings.MOCK_MODELS,
            )
            self._init_error = None
            logger.info("SenseVoice engine initialized successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialize real SenseVoice model ({e}). Falling back to mock engine.")
            self._init_error = str(e)
            self._sensevoice = SenseVoiceSpeechEngine(
                model_dir=settings.SENSEVOICE_MODEL_DIR,
                device=settings.SENSEVOICE_DEVICE,
                threads=settings.SENSEVOICE_THREADS,
                vad_threshold=settings.VAD_THRESHOLD,
                mock=True,
                auto_load=False,
            )

        # 2. Initialize IndicConformer-600m (Indic ASR)
        try:
            self._indicconformer = IndicConformerSpeechEngine(
                model_dir=settings.INDICCONFORMER_MODEL_DIR,
                device=settings.INDICCONFORMER_DEVICE,
                decoder_type=settings.INDICCONFORMER_DECODER_TYPE,
                vad_threshold=settings.VAD_THRESHOLD,
                mock=settings.MOCK_MODELS,
                auto_load=not settings.MOCK_MODELS,
            )
            self._indic_init_error = None
            logger.info("IndicConformer engine initialized successfully.")
        except Exception as e:
            logger.warning(f"Failed to initialize real IndicConformer model ({e}). Falling back to mock engine.")
            self._indic_init_error = str(e)
            self._indicconformer = IndicConformerSpeechEngine(
                model_dir=settings.INDICCONFORMER_MODEL_DIR,
                device=settings.INDICCONFORMER_DEVICE,
                decoder_type=settings.INDICCONFORMER_DECODER_TYPE,
                vad_threshold=settings.VAD_THRESHOLD,
                mock=True,
                auto_load=False,
            )

        # Default engine reference
        self._engine = self._sensevoice

        # 3. Initialize LanguageRouter
        self._router = LanguageRouter(
            default_engine="sensevoice",
            default_language="en",
            lid_confidence_threshold=settings.LID_CONFIDENCE_THRESHOLD,
        )

        self._is_initialized = True
        logger.info("SpeechService initialized with unified language routing.")

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily binds semaphore to the running event loop."""
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.INFERENCE_CONCURRENCY_LIMIT)
        return self._semaphore

    @property
    def is_ready(self) -> bool:
        return self._is_initialized and self._sensevoice is not None

    @property
    def router(self) -> Optional[LanguageRouter]:
        return self._router

    @property
    def indicconformer(self) -> Optional[IndicConformerSpeechEngine]:
        return self._indicconformer

    @property
    def sensevoice(self) -> Optional[SenseVoiceSpeechEngine]:
        return self._sensevoice

    async def transcribe_array(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Runs language routing and inference off the event loop via threadpool
        with bounded concurrency.
        """
        if not self.is_ready:
            raise RuntimeError("SpeechService is not initialized.")

        # 1. Determine routing decision
        if self._router is not None:
            decision: RoutingDecision = self._router.route(
                audio=audio,
                sample_rate=sample_rate,
                language_hint=language_hint
            )
        else:
            decision = RoutingDecision(
                language=language_hint or "en",
                confidence=None,
                engine="sensevoice",
                source="default",
                debug={"policy": "no_router_fallback"}
            )

        # 2. Select speech engine according to routing decision
        if decision.engine == "indicconformer" and self._indicconformer is not None:
            selected_engine: SpeechEngine = self._indicconformer
        else:
            selected_engine = self._sensevoice or self._engine

        sem = self._get_semaphore()
        async with sem:
            result = await asyncio.to_thread(
                selected_engine.transcribe,
                audio=audio,
                sample_rate=sample_rate,
                language_hint=decision.language
            )

            # Enrich result debug payload with routing telemetry
            if result.debug is not None:
                result.debug["routing"] = decision.model_dump()

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
        sv_mock = self._sensevoice.mock if self._sensevoice else False
        ic_mock = self._indicconformer.mock if self._indicconformer else False
        is_error = (self._init_error is not None) or (self._indic_init_error is not None)

        if self.is_ready and not is_error and not sv_mock and not ic_mock:
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
            "model_version": self._sensevoice.model_version if self._sensevoice else "none",
            "indic_model_version": self._indicconformer.model_version if self._indicconformer else "none",
            "concurrency_limit": settings.INFERENCE_CONCURRENCY_LIMIT,
        }
        if self._init_error:
            details["sensevoice_init_warning"] = self._init_error
        if self._indic_init_error:
            details["indicconformer_init_warning"] = self._indic_init_error

        return {
            "status": overall_status,
            "components": components,
            "details": details
        }


# Global singleton instance
speech_service = SpeechService()
