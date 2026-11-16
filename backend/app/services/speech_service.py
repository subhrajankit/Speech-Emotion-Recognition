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
from ai.routing.language_identifier import VoxLingua107LanguageIdentifier
from ai.preprocessing.audio import load_and_preprocess_audio
from backend.app.core.config import settings

logger = logging.getLogger("voicesense.speech_service")


class InvalidLanguageHintError(Exception):
    """Raised when a language hint is not allowed by the active ASR policy."""


def normalize_language_hint(language_hint: Optional[str]) -> Optional[str]:
    """
    Validates language hints for English-only MVP mode.
    When ASR_ENGLISH_ONLY is disabled, returns the hint unchanged to preserve
    existing multilingual routing behavior.
    """
    if not settings.ASR_ENGLISH_ONLY:
        return language_hint

    if language_hint is None:
        return None
    if not isinstance(language_hint, str):
        raise InvalidLanguageHintError(
            "language_hint must be a string when ASR_ENGLISH_ONLY=true."
        )

    cleaned = language_hint.strip().lower()
    if cleaned in {"", "auto"}:
        return None
    if cleaned == "en":
        return "en"

    raise InvalidLanguageHintError(
        "English-only ASR mode accepts only language_hint 'en', 'auto', or empty. "
        f"Received: {language_hint!r}"
    )


class SpeechService:
    """
    Manages speech perception inference with bounded concurrency,
    dynamic language routing, and non-blocking execution.
    """

    def __init__(self):
        self._sensevoice: Optional[SenseVoiceSpeechEngine] = None
        self._indicconformer: Optional[IndicConformerSpeechEngine] = None
        self._emotion2vec: Optional[Any] = None
        self._router: Optional[LanguageRouter] = None
        self._engine: Optional[SpeechEngine] = None  # Default engine alias
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._ser_semaphore: Optional[asyncio.Semaphore] = None
        self._is_initialized: bool = False
        self._init_error: Optional[str] = None
        self._indic_init_error: Optional[str] = None
        self._emotion2vec_error: Optional[str] = None

    def initialize(self) -> None:
        """
        Loads the speech engines and language router once during application lifespan startup.
        Never called per-request.
        """
        if self._is_initialized and self._engine is not None:
            return

        logger.info("Initializing SpeechService...")
        auto_load = not settings.LAZY_LOAD_MODELS

        # 1. Initialize SenseVoiceSmall (Global ASR + SER)
        if self._sensevoice is None:
            try:
                self._sensevoice = SenseVoiceSpeechEngine(
                    model_dir=settings.SENSEVOICE_MODEL_DIR,
                    device=settings.SENSEVOICE_DEVICE,
                    threads=settings.SENSEVOICE_THREADS,
                    vad_threshold=settings.VAD_THRESHOLD,
                    auto_load=auto_load,
                )
                self._init_error = None
                logger.info("SenseVoice engine initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize real SenseVoice model ({e}).")
                self._init_error = str(e)
                self._sensevoice = None

        # 2. Initialize IndicConformer-600m (Indic ASR) — skipped in English-only MVP mode
        if settings.ASR_ENGLISH_ONLY:
            self._indicconformer = None
            self._indic_init_error = None
        elif self._indicconformer is None:
            try:
                self._indicconformer = IndicConformerSpeechEngine(
                    model_dir=settings.INDICCONFORMER_MODEL_DIR,
                    model_revision=settings.INDICCONFORMER_REVISION,
                    device=settings.INDICCONFORMER_DEVICE,
                    decoder_type=settings.INDICCONFORMER_DECODER_TYPE,
                    vad_threshold=settings.VAD_THRESHOLD,
                    auto_load=auto_load,
                )
                self._indic_init_error = None
                logger.info("IndicConformer engine initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize real IndicConformer model ({e}).")
                self._indic_init_error = str(e)
                self._indicconformer = None

        # Default engine reference
        self._engine = self._sensevoice

        # 3. Initialize LanguageRouter (Tier-2 spoken LID only when explicitly enabled)
        lid_detector = None
        if settings.LID_ENABLED and not settings.ASR_ENGLISH_ONLY:
            try:
                candidate = VoxLingua107LanguageIdentifier(
                    model_dir=settings.LID_MODEL_DIR,
                    auto_load=auto_load,
                )
                if not candidate.has_required_files():
                    raise RuntimeError(
                        f"LID artifacts missing in '{settings.LID_MODEL_DIR}'."
                    )
                lid_detector = candidate
                logger.info("Tier-2 spoken LID enabled (VoxLingua107).")
            except Exception as e:
                logger.warning(
                    f"LID_ENABLED=true but detector initialization failed ({e}). "
                    "Tier-2 LID disabled; unhinted utterances use the default engine."
                )
                lid_detector = None

        self._router = LanguageRouter(
            default_engine="sensevoice",
            default_language="en",
            lid_confidence_threshold=settings.LID_CONFIDENCE_THRESHOLD,
            lid_detector=lid_detector,
        )

        # 4. Initialize Emotion2Vec (Dedicated SER Engine) if explicitly enabled
        if settings.EMOTION2VEC_ENABLED and self._emotion2vec is None:
            try:
                from ai.inference.emotion2vec import Emotion2VecSpeechEngine
                self._emotion2vec = Emotion2VecSpeechEngine(
                    model_dir=settings.EMOTION2VEC_MODEL_DIR,
                    device=settings.EMOTION2VEC_DEVICE,
                    threads=settings.EMOTION2VEC_THREADS,
                    confidence_threshold=settings.EMOTION2VEC_CONFIDENCE_THRESHOLD,
                    auto_load=auto_load,
                )
                self._emotion2vec_error = None
                logger.info("Emotion2Vec SER engine initialized successfully.")
            except Exception as e:
                logger.warning(f"Failed to initialize Emotion2Vec model ({e}).")
                self._emotion2vec_error = str(e)
                self._emotion2vec = None
        elif not settings.EMOTION2VEC_ENABLED:
            self._emotion2vec = None
            self._emotion2vec_error = None

        # Preload default engine if configured
        if settings.PRELOAD_DEFAULT_ENGINE:
            default_eng = self._sensevoice or self._engine
            if default_eng is not None and hasattr(default_eng, "load"):
                logger.info("PRELOAD_DEFAULT_ENGINE=True: preloading default engine...")
                default_eng.load()

        self._is_initialized = True
        logger.info("SpeechService initialized with unified language routing.")

    def _get_semaphore(self) -> asyncio.Semaphore:
        """Lazily binds semaphore to the running event loop."""
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._semaphore is None or getattr(self, "_sem_loop", None) != curr_loop:
            self._semaphore = asyncio.Semaphore(settings.INFERENCE_CONCURRENCY_LIMIT)
            self._sem_loop = curr_loop
        return self._semaphore

    def _get_ser_semaphore(self) -> asyncio.Semaphore:
        """Lazily binds SER semaphore (concurrency=1 on CPU) to running event loop."""
        try:
            curr_loop = asyncio.get_running_loop()
        except RuntimeError:
            curr_loop = None

        if self._ser_semaphore is None or getattr(self, "_ser_sem_loop", None) != curr_loop:
            self._ser_semaphore = asyncio.Semaphore(1)
            self._ser_sem_loop = curr_loop
        return self._ser_semaphore

    def _get_emotion2vec_engine(self) -> Optional[Any]:
        """Returns or lazily creates the Emotion2Vec engine singleton if enabled."""
        if not settings.EMOTION2VEC_ENABLED:
            return None
        if self._emotion2vec is None and self._emotion2vec_error is None:
            try:
                from ai.inference.emotion2vec import Emotion2VecSpeechEngine
                self._emotion2vec = Emotion2VecSpeechEngine(
                    model_dir=settings.EMOTION2VEC_MODEL_DIR,
                    device=settings.EMOTION2VEC_DEVICE,
                    threads=settings.EMOTION2VEC_THREADS,
                    confidence_threshold=settings.EMOTION2VEC_CONFIDENCE_THRESHOLD,
                    auto_load=False,
                )
                logger.info("Emotion2Vec engine lazily created.")
            except Exception as e:
                logger.warning(f"Lazy Emotion2Vec initialization failed ({e}).")
                self._emotion2vec_error = str(e)
                self._emotion2vec = None
        return self._emotion2vec

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

    @property
    def emotion2vec(self) -> Optional[Any]:
        return self._emotion2vec

    def get_engine_for_utterance(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> tuple[SpeechEngine, str, RoutingDecision]:
        """
        Determines the routing decision and returns the selected speech engine,
        canonical engine name, and the routing decision.
        """
        # English-only MVP: deterministic SenseVoice routing with no router/LID invocation.
        if settings.ASR_ENGLISH_ONLY:
            normalized_hint = normalize_language_hint(language_hint)
            if normalized_hint == "en":
                decision = RoutingDecision(
                    language="en",
                    confidence=1.0,
                    engine="sensevoice",
                    source="hint",
                    debug={"policy": "english_only_explicit_hint"}
                )
            else:
                decision = RoutingDecision(
                    language="en",
                    confidence=None,
                    engine="sensevoice",
                    source="default",
                    debug={"policy": "english_only_default"}
                )
            selected_engine = self._sensevoice or self._engine
            return selected_engine, "sensevoice", decision

        try:
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
        except Exception as route_err:
            logger.error(f"Routing failed ({route_err}). Falling back to default engine.")
            decision = RoutingDecision(
                language=language_hint or "en",
                confidence=None,
                engine="sensevoice",
                source="default",
                debug={"policy": "router_error_fallback", "error": str(route_err)}
            )

        if decision.engine == "indicconformer" and self._indicconformer is not None:
            selected_engine: SpeechEngine = self._indicconformer
            engine_name = "indicconformer"
        else:
            selected_engine = self._sensevoice or self._engine
            engine_name = "sensevoice"

        return selected_engine, engine_name, decision

    async def transcribe_array(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None,
        status_callback: Optional[Any] = None,
    ) -> SpeechResult:
        """
        Runs language routing and inference off the event loop via threadpool
        with bounded concurrency. Notifies status_callback if lazy loading is triggered.
        """
        if not self.is_ready:
            raise RuntimeError("SpeechService is not initialized.")

        # Routing (incl. Tier-2 LID inference) runs off the event loop so a
        # synchronous detector cannot stall other WebSocket sessions.
        selected_engine, engine_name, decision = await asyncio.to_thread(
            self.get_engine_for_utterance,
            audio=audio,
            sample_rate=sample_rate,
            language_hint=language_hint,
        )

        # Notify and perform lazy loading if the engine is not yet resident
        is_loaded = getattr(selected_engine, "is_loaded", True)
        if not is_loaded:
            if status_callback is not None:
                await status_callback("loading_model", engine_name)
            if hasattr(selected_engine, "load"):
                await asyncio.to_thread(selected_engine.load)
            if status_callback is not None:
                await status_callback("model_ready", engine_name)

        sem = self._get_semaphore()
        try:
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

        except Exception as engine_err:
            # Fallback to default engine if IndicConformer or non-default engine fails
            default_engine = self._sensevoice or self._engine
            if selected_engine != default_engine and default_engine is not None:
                logger.warning(
                    f"Selected engine '{decision.engine}' failed ({engine_err}). "
                    f"Falling back to default engine 'sensevoice'."
                )
                async with sem:
                    fallback_res = await asyncio.to_thread(
                        default_engine.transcribe,
                        audio=audio,
                        sample_rate=sample_rate,
                        language_hint="en"
                    )
                    if fallback_res.debug is None:
                        fallback_res.debug = {}
                    fallback_res.debug["routing"] = decision.model_dump()
                    fallback_res.debug["fallback"] = {
                        "from_engine": decision.engine,
                        "to_engine": "sensevoice",
                        "error": str(engine_err)
                    }
                    result = fallback_res
            else:
                raise

        # Acoustic SER (emotion2vec_plus_base) classification
        if settings.EMOTION2VEC_ENABLED:
            ser_engine = self._get_emotion2vec_engine()
            if ser_engine is not None:
                should_run_ser = (
                    settings.EMOTION_ROUTING_STRATEGY == "dedicated_primary"
                    or (settings.EMOTION_ROUTING_STRATEGY == "hybrid_fallback" and result.emotion is None)
                )
                if should_run_ser:
                    ser_sem = self._get_ser_semaphore()
                    try:
                        async with ser_sem:
                            is_ser_loaded = getattr(ser_engine, "is_loaded", True)
                            if not is_ser_loaded:
                                if status_callback is not None:
                                    await status_callback("loading_model", "emotion2vec")
                                if hasattr(ser_engine, "load"):
                                    await asyncio.to_thread(ser_engine.load)
                                if status_callback is not None:
                                    await status_callback("model_ready", "emotion2vec")

                            ser_res = await asyncio.to_thread(
                                ser_engine.classify,
                                audio=audio,
                                sample_rate=sample_rate,
                            )

                            if result.debug is None:
                                result.debug = {}

                            result.emotion = ser_res.primary if ser_res.primary != "unknown" else None
                            result.confidence = ser_res.confidence
                            result.emotion_scores = ser_res.scores
                            result.debug["emotion_source_model"] = ser_res.model_version
                            result.debug["emotion_raw_label"] = getattr(ser_res, "raw_label", None)
                            result.debug["emotion_processing_time_ms"] = ser_res.processing_time_ms
                            result.debug["is_fallback"] = (
                                settings.EMOTION_ROUTING_STRATEGY == "hybrid_fallback"
                            )
                    except Exception as ser_err:
                        logger.warning(
                            f"Emotion2Vec classification failed ({ser_err}). "
                            "Preserving primary ASR result and SenseVoice emotion."
                        )
                        if result.debug is None:
                            result.debug = {}
                        result.debug["emotion_error"] = str(ser_err)
                        result.debug["emotion_source_model"] = "sensevoice_fallback"
                        result.debug["is_fallback"] = True
        else:
            if result.debug is None:
                result.debug = {}
            if "emotion_source_model" not in result.debug:
                result.debug["emotion_source_model"] = "sensevoice"
            if "is_fallback" not in result.debug:
                result.debug["is_fallback"] = False

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
        language_hint: Optional[str] = None,
        status_callback: Optional[Any] = None,
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
            language_hint=language_hint,
            status_callback=status_callback,
        )

    def get_health_status(self) -> Dict[str, Any]:
        """
        Returns per-component status.
        Placeholders for llm, rag, tts, db are 'not_configured'.
        Overall status is 'ok' or 'degraded'; does not fail for optional components.
        """
        is_error = (self._init_error is not None) or (self._indic_init_error is not None)

        if self.is_ready and not is_error:
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

        # Explicit emotion2vec component health if feature-flagged
        if settings.EMOTION2VEC_ENABLED:
            if self._emotion2vec_error:
                emotion_status = "unhealthy"
            elif self._emotion2vec and self._emotion2vec.is_loaded:
                emotion_status = "ok"
            else:
                emotion_status = "ready"

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
            "emotion2vec_enabled": settings.EMOTION2VEC_ENABLED,
            "emotion_routing_strategy": settings.EMOTION_ROUTING_STRATEGY,
            "emotion2vec_loaded": self._emotion2vec.is_loaded if self._emotion2vec else False,
        }
        if self._init_error:
            details["sensevoice_init_warning"] = self._init_error
        if self._indic_init_error:
            details["indicconformer_init_warning"] = self._indic_init_error
        if self._emotion2vec_error:
            details["emotion2vec_init_warning"] = self._emotion2vec_error

        return {
            "status": overall_status,
            "components": components,
            "details": details
        }


# Global singleton instance
speech_service = SpeechService()
