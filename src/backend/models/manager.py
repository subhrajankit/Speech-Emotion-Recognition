import logging
from typing import Dict, Any
from .asr import SenseVoiceASR
from .llm import LlamaCppClient
from .tts import IndicParlerTTS
from ..audio.vad import SileroVAD
from ..asr.indicconformer import IndicConformerASR
from ..asr.router import LanguageRouter
from ..emotion.emotion import EmotionAnalyzer
from ..database.storage import EmotionStorage
from ..rag.retriever import RAGRetriever
from ..config import settings

logger = logging.getLogger(__name__)

class ModelManager:
    """
    Singleton manager holding all loaded models.
    Initialized once at application startup.
    """
    _instance = None

    def __init__(self):
        self.vad: SileroVAD = None
        self.asr: SenseVoiceASR = None
        self.indic_conformer: IndicConformerASR = None
        self.language_router: LanguageRouter = None
        self.llm: LlamaCppClient = None
        self.tts: IndicParlerTTS = None
        self.emotion_analyzer: EmotionAnalyzer = None
        self.emotion_storage: EmotionStorage = None
        self.retriever: RAGRetriever = None
        self.initialized = False

    @classmethod
    def get_instance(cls) -> "ModelManager":
        if cls._instance is None:
            cls._instance = ModelManager()
        return cls._instance

    def initialize(self):
        if self.initialized:
            return

        logger.info("Initializing ModelManager: loading singletons once at startup...")
        
        # 0. Silero VAD
        self.vad = SileroVAD(
            model_path=settings.VAD_MODEL_PATH,
            threshold=settings.VAD_THRESHOLD
        )

        # 1. SenseVoiceSmall ASR
        self.asr = SenseVoiceASR(
            model_id=settings.SENSEVOICE_MODEL_ID,
            device=settings.SENSEVOICE_DEVICE,
            mock=settings.MOCK_MODELS
        )

        # 2. IndicConformer ASR (with graceful degradation)
        try:
            self.indic_conformer = IndicConformerASR(
                model_id=settings.INDIC_CONFORMER_MODEL_ID,
                device=settings.INDIC_CONFORMER_DEVICE,
                mock=settings.MOCK_MODELS
            )
            if not self.indic_conformer.is_loaded and not settings.MOCK_MODELS:
                logger.warning(
                    "[ModelManager] IndicConformer failed to load. Graceful degradation active: "
                    "system will serve English and global languages via SenseVoice."
                )
        except Exception as e:
            logger.warning(
                f"[ModelManager] Exception initializing IndicConformer ({e}). "
                f"Graceful degradation active: system will serve English and global languages via SenseVoice."
            )
            self.indic_conformer = None

        # 3. Language Router
        self.language_router = LanguageRouter(
            sensevoice_asr=self.asr,
            indic_conformer=self.indic_conformer
        )

        # 4. llama.cpp client (with circuit breaker & retry-with-backoff)
        self.llm = LlamaCppClient(
            base_url=settings.LLAMA_CPP_URL,
            model_name=settings.LLAMA_MODEL_NAME,
            timeout=settings.LLAMA_TIMEOUT_SECONDS,
            mock=settings.MOCK_MODELS,
            max_retries=settings.LLM_MAX_RETRIES,
            backoff_factor=settings.LLM_BACKOFF_FACTOR
        )

        # 5. Indic Parler-TTS (with retry & synthesized fallback)
        self.tts = IndicParlerTTS(
            model_id=settings.PARLER_TTS_MODEL_ID,
            device=settings.PARLER_TTS_DEVICE,
            mock=settings.MOCK_MODELS,
            max_retries=settings.TTS_MAX_RETRIES
        )

        # 6. Emotion Analyzer
        self.emotion_analyzer = EmotionAnalyzer()

        # 7. Emotion Storage (SQLite)
        self.emotion_storage = EmotionStorage(db_path=settings.DATABASE_PATH)

        # 8. RAG Retriever (multilingual-e5-small + FAISS)
        self.retriever = RAGRetriever(
            index_dir=settings.RAG_INDEX_DIR,
            mock=settings.MOCK_MODELS
        )

        self.initialized = True
        logger.info("ModelManager initialization complete.")

    async def get_health_status(self) -> Dict[str, Any]:
        llm_ready = await self.llm.check_health() if self.llm else False
        return {
            "status": "healthy" if (self.initialized and (self.asr and self.asr.is_loaded or settings.MOCK_MODELS)) else "degraded",
            "models": {
                "silero_vad": {
                    "loaded": self.vad.is_loaded if self.vad else False,
                    "model_path": settings.VAD_MODEL_PATH,
                    "threshold": settings.VAD_THRESHOLD
                },
                "sensevoice_asr": {
                    "loaded": self.asr.is_loaded if self.asr else False,
                    "model_id": settings.SENSEVOICE_MODEL_ID,
                    "device": settings.SENSEVOICE_DEVICE
                },
                "indic_conformer": {
                    "loaded": self.indic_conformer.is_loaded if self.indic_conformer else False,
                    "model_id": settings.INDIC_CONFORMER_MODEL_ID,
                    "device": settings.INDIC_CONFORMER_DEVICE
                },
                "llama_cpp_llm": {
                    "connected": llm_ready,
                    "endpoint": settings.LLAMA_CPP_URL,
                    "model_name": settings.LLAMA_MODEL_NAME
                },
                "indic_parler_tts": {
                    "loaded": self.tts.is_loaded if self.tts else False,
                    "model_id": settings.PARLER_TTS_MODEL_ID,
                    "device": settings.PARLER_TTS_DEVICE
                },
                "emotion_analyzer": {
                    "loaded": self.emotion_analyzer is not None,
                    "mapping": "fixed_valence_arousal_lookup"
                },
                "emotion_storage": {
                    "connected": self.emotion_storage is not None,
                    "database": settings.DATABASE_PATH
                },
                "rag_retriever": {
                    "loaded": self.retriever.is_loaded if self.retriever else False,
                    "chunks_count": len(self.retriever.chunks) if self.retriever else 0,
                    "index_dir": settings.RAG_INDEX_DIR
                }
            },
            "mock_mode": settings.MOCK_MODELS
        }



# Module-level singleton instance
model_manager = ModelManager.get_instance()
