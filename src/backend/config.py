import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    HOST: str = "127.0.0.1"
    PORT: int = 8000
    DEBUG: bool = True
    
    # llama.cpp server configuration
    LLAMA_CPP_URL: str = "http://127.0.0.1:8080/v1"
    LLAMA_MODEL_NAME: str = "qwen3-1.7b"
    LLAMA_TIMEOUT_SECONDS: float = 30.0
    LLM_ENABLE_THINKING: bool = False


    # Silero VAD configuration
    VAD_MODEL_PATH: str = "models/silero_vad.onnx"
    VAD_THRESHOLD: float = 0.5
    SILENCE_TIMEOUT_MS: int = 700
    
    # SenseVoiceSmall configuration
    SENSEVOICE_MODEL_ID: str = "iic/SenseVoiceSmall"
    SENSEVOICE_DEVICE: str = "cpu"

    # IndicConformer configuration
    INDIC_CONFORMER_MODEL_ID: str = "ai4bharat/indic-conformer-600m-multilingual"
    INDIC_CONFORMER_DEVICE: str = "cpu"
    
    # Indic Parler-TTS configuration
    PARLER_TTS_MODEL_ID: str = "ai4bharat/indic-parler-tts"
    PARLER_TTS_DEVICE: str = "cpu"
    
    # Database configuration
    DATABASE_PATH: str = "database/dev.db"

    # RAG & Retrieval configuration
    RAG_MODEL_ID: str = "intfloat/multilingual-e5-small"
    RAG_INDEX_DIR: str = "data/index"
    RAG_DOCS_DIR: str = "data/documents"
    RAG_TOP_K: int = 3

    # Testing & Fallback Flag
    MOCK_MODELS: bool = False

    # Security & Auth Configuration (Phase 11)
    JWT_SECRET: str = "senseai-dev-secret-key-change-in-production-32bytesmin"
    JWT_ALGORITHM: str = "HS256"
    REQUIRE_AUTH: bool = False  # Set to True to enforce JWT handshake on WS/WebTransport
    SESSION_TIMEOUT_MINUTES: int = 60
    
    # Rate Limiting & Resource Quotas
    RATE_LIMIT_UTTERANCES_PER_MINUTE: int = 20
    MAX_UTTERANCE_DURATION_SECONDS: float = 30.0
    MAX_RAG_UPLOAD_SIZE_BYTES: int = 10 * 1024 * 1024  # 10 MB

    # Resilience & Error Handling (Phase 14)
    LLM_MAX_RETRIES: int = 2
    LLM_BACKOFF_FACTOR: float = 0.2
    LLM_CIRCUIT_BREAKER_FAILURES: int = 3
    LLM_CIRCUIT_BREAKER_COOLDOWN_SECONDS: float = 15.0
    TTS_MAX_RETRIES: int = 2
    MAX_CONCURRENT_GPU_CALLS: int = 2

    # Optional Cloud LLM Fallback (Phase 17)
    LLM_PROVIDER: str = "local"  # "local" | "cloud"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL_NAME: str = "gemini-2.5-flash"

    # Cybersecurity & Cryptography (Phase 18)
    DATABASE_ENCRYPTION_KEY: str = "Wwd7xrp9M6xNeeZ83gaigH1-DwKbDRUFlgI0SGl5L_o="
    AUDIT_LOG_PATH: str = "logs/audit.log"

    model_config = {
        "env_file": ".env",
        "extra": "ignore"
    }

settings = Settings()
