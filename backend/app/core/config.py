"""
Configuration settings for VoiceSense AI Backend.
Loaded via pydantic-settings from environment variables and .env file.
"""

from typing import List, Union
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    APP_ENV: str = "development"
    ENVIRONMENT: str = "development"
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False

    # CORS origins
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    # Logging policy: transcripts and raw audio are never logged at INFO level by default
    LOG_LEVEL: str = "INFO"
    LOG_TRANSCRIPTS: bool = False

    # Security & Auth
    AUTH_REQUIRED: bool = False
    JWT_SECRET: str = "voicesense-insecure-secret-key-change-in-prod"
    SESSION_TIMEOUT_MINUTES: int = 60

    # Database settings
    DATABASE_URL: str = "sqlite:///./database/dev.db"
    STORE_TRANSCRIPTS: bool = True

    # Rate limiting & Quotas
    RATE_LIMIT_UTTERANCES_PER_MINUTE: int = 20
    RATE_LIMIT_AUTH_PER_MINUTE: int = 10
    MAX_UTTERANCE_DURATION_SECONDS: float = 30.0
    MAX_RAG_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit

    # Ingestion & Audio limits
    MAX_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB limit
    ALLOWED_AUDIO_MIME_TYPES: List[str] = [
        "audio/wav",
        "audio/x-wav",
        "audio/wave",
        "audio/mpeg",
        "audio/mp3",
        "audio/ogg",
        "audio/flac",
        "audio/webm",
        "application/octet-stream",
    ]

    # WebSocket limits
    WS_MAX_BUFFER_BYTES: int = 5 * 1024 * 1024  # 5 MB per-connection buffer limit

    # Inference & Concurrency limits
    INFERENCE_CONCURRENCY_LIMIT: int = 2
    VAD_THRESHOLD: float = 0.5
    SENSEVOICE_MODEL_DIR: str = "iic/SenseVoiceSmall"
    SENSEVOICE_DEVICE: str = "cpu"
    SENSEVOICE_THREADS: int = 4
    # English-only MVP gate: disables IndicConformer construction and Tier-2 LID.
    ASR_ENGLISH_ONLY: bool = True
    INDICCONFORMER_MODEL_DIR: str = "ai4bharat/indic-conformer-600m-multilingual"
    INDICCONFORMER_REVISION: str = "2a77d305038dfc502fd9464e7d028b90381976cb"
    INDICCONFORMER_DEVICE: str = "cpu"
    INDICCONFORMER_DECODER_TYPE: str = "ctc"
    LID_CONFIDENCE_THRESHOLD: float = 0.6
    LID_ENABLED: bool = False
    LID_MODEL_DIR: str = "models/voxlingua107"
    LAZY_LOAD_MODELS: bool = True
    PRELOAD_DEFAULT_ENGINE: bool = False

    # Emotion2Vec Settings (Acoustic SER Engine — models/emotion/emotion2vec-plus-base)
    EMOTION2VEC_ENABLED: bool = False  # Disabled by default; feature-flagged for safe integration
    EMOTION2VEC_MODEL_DIR: str = "models/emotion/emotion2vec-plus-base"
    EMOTION2VEC_DEVICE: str = "cpu"
    EMOTION2VEC_THREADS: int = 2
    EMOTION2VEC_CONFIDENCE_THRESHOLD: float = 0.60
    EMOTION_ROUTING_STRATEGY: str = "dedicated_primary"  # "dedicated_primary" | "hybrid_fallback" | "sensevoice_only"

    # LLM Settings (Qwen3 via local llama.cpp)
    LLM_BASE_URL: str = "http://127.0.0.1:8080"
    LLM_MODEL_NAME: str = "qwen3-1.7b"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_TOKENS: int = 120  # Suited for low-latency voice turns
    LLM_TEMPERATURE: float = 0.7
    LLM_REPEAT_PENALTY: float = 1.1  # Conservative repetition penalty
    LLM_FREQUENCY_PENALTY: float = 0.2  # Conservative frequency penalty
    LLM_PRESENCE_PENALTY: float = 0.0
    LLM_ENABLE_THINKING: bool = False
    LLM_HEALTH_CACHE_SECONDS: float = 5.0
    LLM_FAILURE_THRESHOLD: int = 3
    LLM_COOLDOWN_SECONDS: float = 15.0

    # TTS Settings (Indic Parler-TTS — ai4bharat/indic-parler-tts)
    TTS_ENABLED: bool = False  # Explicit gating: default False on this machine per decision rule
    TTS_MODEL_ID: str = "ai4bharat/indic-parler-tts"
    TTS_DEVICE: str = "auto"  # "auto" | "cuda" | "cpu"
    TTS_DTYPE: str = "float16"  # "float32" | "float16" | "bfloat16"
    TTS_SAMPLE_RATE: int = 44100
    TTS_EMOTION_STYLING_ENABLED: bool = False  # Off by default per Phase 8 spec
    TTS_DEFAULT_SPEAKER: str = "Aditi"
    TTS_MAX_SENTENCE_LENGTH: int = 500
    TTS_CONCURRENCY_LIMIT: int = 1
    TTS_SENTENCE_TIMEOUT_SECONDS: float = 30.0
    TTS_COOLDOWN_SECONDS: float = 60.0
    TTS_WORKER_PYTHON: str = ".venv-tts/Scripts/python.exe"


    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            # Split comma-separated string if provided
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        envs = {
            (self.APP_ENV or "").lower(),
            (self.ENVIRONMENT or "").lower(),
        }
        if "production" in envs:
            insecure_defaults = {
                "voicesense-insecure-secret-key-change-in-prod",
                "voicesense-dev-only-secret-change-in-prod-min-32-bytes",
                "senseai-dev-secret-key-change-in-production-32bytesmin",
                "secret",
                "changeme",
            }
            if not self.JWT_SECRET or self.JWT_SECRET in insecure_defaults or len(self.JWT_SECRET) < 32:
                raise ValueError(
                    "APP_ENV/ENVIRONMENT=production refuses to start with missing, default, or weak JWT_SECRET (must be >= 32 characters)."
                )
            if not self.AUTH_REQUIRED:
                raise ValueError(
                    "APP_ENV/ENVIRONMENT=production refuses to start with AUTH_REQUIRED=false; WebSocket authentication must be enforced."
                )
        return self


settings = Settings()
