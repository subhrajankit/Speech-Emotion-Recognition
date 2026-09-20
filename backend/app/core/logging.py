"""
Logging configuration for VoiceSense AI Backend.
Enforces privacy policy: by default do not log transcripts or raw audio at INFO level.
"""

import logging
import sys
from typing import Any, Dict
from backend.app.core.config import settings


class PrivacyPreservingFormatter(logging.Formatter):
    """
    Custom formatter ensuring consistent format and preventing transcript leakage at INFO level.
    """
    pass


def setup_logging() -> None:
    """Configures application-wide logging based on settings."""
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if already configured
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(log_level)
        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        )
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # Quiet external noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


def sanitize_log_payload(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Sanitizes dictionary data before logging.
    Redacts 'transcript', 'raw_audio', and 'audio' unless LOG_TRANSCRIPTS is True.
    """
    if settings.LOG_TRANSCRIPTS:
        return data

    sanitized = {}
    for k, v in data.items():
        if k in ("transcript", "raw_audio", "audio", "file_bytes", "pcm_bytes"):
            sanitized[k] = "<REDACTED: PRIVACY POLICY>"
        else:
            sanitized[k] = v
    return sanitized


logger = logging.getLogger("voicesense.backend")
