"""
Rate Limiting & Abuse Prevention Module for SenseAI (Phase 11).

Enforces:
1. Max utterances per minute per session (sliding 60-second window).
2. Max audio duration per utterance (30.0s = 960,000 bytes PCM16 mono 16kHz).
3. Max upload file size for RAG ingestion (10 MB).
"""

import time
from collections import defaultdict
from typing import Dict, List

from src.backend.config import settings


class RateLimitError(Exception):
    """Base exception for rate limit violations."""
    pass


class UtteranceRateLimitExceeded(RateLimitError):
    """Raised when a session exceeds allowed utterances in a 60-second window."""
    pass


class AudioDurationLimitExceeded(RateLimitError):
    """Raised when an utterance's accumulated audio exceeds duration caps."""
    pass


class UploadSizeLimitExceeded(RateLimitError):
    """Raised when a RAG document upload exceeds size limits."""
    pass


class SessionRateLimiter:
    """
    In-memory rate limiter tracking session utterance frequencies and audio quotas.
    """

    def __init__(
        self,
        max_utterances_per_minute: int = settings.RATE_LIMIT_UTTERANCES_PER_MINUTE,
        max_utterance_duration_sec: float = settings.MAX_UTTERANCE_DURATION_SECONDS,
        max_upload_size_bytes: int = settings.MAX_RAG_UPLOAD_SIZE_BYTES,
    ):
        self.max_utterances = max_utterances_per_minute
        self.max_duration_sec = max_utterance_duration_sec
        self.max_upload_size = max_upload_size_bytes
        # Map session_id -> list of utterance epoch timestamps
        self._utterance_history: Dict[str, List[float]] = defaultdict(list)

    def record_utterance(self, session_id: str) -> None:
        """
        Record a new utterance attempt for the session.
        Enforces max utterances per 60-second sliding window.
        """
        now = time.time()
        window_start = now - 60.0

        # Prune timestamps older than 60s
        history = [ts for ts in self._utterance_history[session_id] if ts > window_start]
        self._utterance_history[session_id] = history

        if len(history) >= self.max_utterances:
            raise UtteranceRateLimitExceeded(
                f"Session rate limit exceeded: maximum {self.max_utterances} utterances/minute allowed."
            )

        self._utterance_history[session_id].append(now)

    def validate_audio_chunk(
        self,
        accumulated_bytes: int,
        sample_rate: int = 16000,
        sample_width_bytes: int = 2,
    ) -> float:
        """
        Validate accumulated PCM16 audio bytes against maximum utterance duration.

        Returns calculated duration in seconds, or raises AudioDurationLimitExceeded.
        """
        bytes_per_sec = sample_rate * sample_width_bytes  # e.g., 16000 * 2 = 32000 B/s
        duration_sec = accumulated_bytes / float(bytes_per_sec)

        if duration_sec > self.max_duration_sec:
            raise AudioDurationLimitExceeded(
                f"Maximum utterance duration exceeded ({duration_sec:.1f}s > {self.max_duration_sec:.1f}s limit). "
                f"Truncating/aborting buffer to prevent resource exhaustion."
            )
        return duration_sec

    def validate_upload_size(self, size_bytes: int) -> None:
        """
        Validate document file size against max RAG upload size limit.
        """
        if size_bytes > self.max_upload_size:
            raise UploadSizeLimitExceeded(
                f"Document size {size_bytes} bytes exceeds maximum upload size "
                f"of {self.max_upload_size} bytes ({self.max_upload_size / (1024 * 1024):.1f} MB)."
            )

    def reset_session(self, session_id: str) -> None:
        """Clear rate limit history for a session."""
        if session_id in self._utterance_history:
            del self._utterance_history[session_id]


# Global default rate limiter instance
rate_limiter = SessionRateLimiter()
