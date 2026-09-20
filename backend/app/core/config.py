"""
Configuration settings for VoiceSense AI Backend.
Loaded via pydantic-settings from environment variables and .env file.
"""

from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # Server settings
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = False

    # CORS origins
    CORS_ORIGINS: Union[str, List[str]] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
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
    INDICCONFORMER_MODEL_DIR: str = "ai4bharat/indicconformer_stt_indic_hybrid_ctc_large"
    INDICCONFORMER_DEVICE: str = "cpu"
    INDICCONFORMER_DECODER_TYPE: str = "ctc"
    LID_CONFIDENCE_THRESHOLD: float = 0.6
    MOCK_MODELS: bool = False

    # LLM Settings (Qwen3 via local llama.cpp)
    LLM_BASE_URL: str = "http://127.0.0.1:8080"
    LLM_MODEL_NAME: str = "qwen3-1.7b"
    LLM_TIMEOUT_SECONDS: float = 30.0
    LLM_MAX_TOKENS: int = 256
    LLM_ENABLE_THINKING: bool = False
    LLM_HEALTH_CACHE_SECONDS: float = 5.0
    LLM_FAILURE_THRESHOLD: int = 3
    LLM_COOLDOWN_SECONDS: float = 15.0

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            # Split comma-separated string if provided
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v


settings = Settings()
