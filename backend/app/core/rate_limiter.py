"""
Rate Limiting & Abuse Prevention Module for VoiceSense AI.
Ported from src/backend/security/rate_limiter.py with configuration injection via Settings.

Enforces:
1. Max utterances per minute per session (sliding 60-second window).
2. Max audio duration per utterance (30.0s = 960,000 bytes PCM16 mono 16kHz).
3. Max upload file size for RAG ingestion (10 MB).
4. Client IP rate limiting for authentication endpoints.
"""

import time
from collections import defaultdict
from typing import Dict, List, Optional
from fastapi import Request, HTTPException, status

from backend.app.core.config import settings


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
        max_utterances_per_minute: Optional[int] = None,
        max_utterance_duration_sec: Optional[float] = None,
        max_upload_size_bytes: Optional[int] = None,
    ):
        self.max_utterances = (
            max_utterances_per_minute
            if max_utterances_per_minute is not None
            else settings.RATE_LIMIT_UTTERANCES_PER_MINUTE
        )
        self.max_duration_sec = (
            max_utterance_duration_sec
            if max_utterance_duration_sec is not None
            else settings.MAX_UTTERANCE_DURATION_SECONDS
        )
        self.max_upload_size = (
            max_upload_size_bytes
            if max_upload_size_bytes is not None
            else settings.MAX_UPLOAD_SIZE_BYTES
        )
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

    def refund_utterance(self, session_id: str) -> None:
        """
        Remove the most recently recorded utterance for the session.

        Used when an attempt recorded before inference is confirmed to
        contain no speech, so confirmed silence does not consume the
        rate-limit budget. Session utterances are processed sequentially on
        the WebSocket event loop and each session_id owns its history list,
        so popping the newest timestamp can only refund the attempt that was
        just recorded — never a different session's or a later utterance's.
        """
        history = self._utterance_history.get(session_id)
        if history:
            history.pop()

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
                f"limit of {self.max_upload_size} bytes."
            )

    def reset(self):
        """Clears all utterance history (used in tests)."""
        self._utterance_history.clear()


# Global singleton for session and audio rate limiting
session_rate_limiter = SessionRateLimiter()


class IPRateLimiter:
    """
    Sliding window rate limiter for REST endpoints keyed by client IP or identifier.
    """

    def __init__(self, limit: int = 20, window_seconds: float = 60.0):
        self.limit = limit
        self.window_seconds = window_seconds
        self._records: Dict[str, List[float]] = defaultdict(list)

    def is_allowed(self, client_key: str) -> bool:
        now = time.time()
        start = now - self.window_seconds
        valid_records = [t for t in self._records[client_key] if t > start]
        self._records[client_key] = valid_records

        if len(valid_records) >= self.limit:
            return False

        self._records[client_key].append(now)
        return True

    def check(self, request: Request, custom_key: Optional[str] = None):
        key = custom_key or (request.client.host if request.client else "unknown_client")
        if not self.is_allowed(key):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded: maximum {self.limit} requests per {int(self.window_seconds)}s."
            )

    def reset(self):
        self._records.clear()


auth_rate_limiter = IPRateLimiter(limit=settings.RATE_LIMIT_AUTH_PER_MINUTE, window_seconds=60.0)
