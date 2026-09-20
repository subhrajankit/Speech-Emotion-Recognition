"""
GPU Concurrency Limiter & Queueing Backpressure for Shared Voice Sessions.
Protects constrained GPU VRAM and compute resources by bounding concurrent LLM and TTS tasks.
"""
import asyncio
import logging
from typing import Optional
from ..config import settings

logger = logging.getLogger(__name__)


class GPUConcurrencyLimiter:
    """
    Asynchronous semaphore gating access to GPU-intensive operations (LLM generation & TTS synthesis).
    Prevents Out-Of-Memory (OOM) and driver crashes on shared hardware (e.g. RTX 2050 4GB).
    """
    _instance: Optional["GPUConcurrencyLimiter"] = None

    def __init__(self, max_concurrent: Optional[int] = None):
        self.max_concurrent = max_concurrent or settings.MAX_CONCURRENT_GPU_CALLS
        self._semaphore: Optional[asyncio.Semaphore] = None
        self.active_calls: int = 0
        self.queued_calls: int = 0
        self.total_acquired: int = 0

    @classmethod
    def get_instance(cls) -> "GPUConcurrencyLimiter":
        if cls._instance is None:
            cls._instance = GPUConcurrencyLimiter()
        return cls._instance

    @property
    def semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self.max_concurrent)
        return self._semaphore

    async def acquire(self):
        """Acquires a slot in the GPU concurrency queue."""
        self.queued_calls += 1
        if self.active_calls >= self.max_concurrent:
            logger.info(
                f"[GPUConcurrencyLimiter] Concurrency limit reached ({self.active_calls}/{self.max_concurrent}). "
                f"Session queued ({self.queued_calls} waiting)."
            )
        await self.semaphore.acquire()
        self.queued_calls = max(0, self.queued_calls - 1)
        self.active_calls += 1
        self.total_acquired += 1

    def release(self):
        """Releases the held slot in the GPU concurrency queue."""
        self.active_calls = max(0, self.active_calls - 1)
        self.semaphore.release()

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.release()

    def get_stats(self) -> dict:
        return {
            "max_concurrent": self.max_concurrent,
            "active_calls": self.active_calls,
            "queued_calls": self.queued_calls,
            "total_acquired": self.total_acquired
        }


# Singleton limiter
gpu_limiter = GPUConcurrencyLimiter()
