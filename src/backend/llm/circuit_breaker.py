"""
Circuit Breaker and Resilience Exceptions for LLM & Downstream Service Invocations.
Prevents pipeline hangs during downstream outages by failing fast after consecutive failures.
"""
import time
import logging
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"        # Normal operation: requests pass through
    OPEN = "OPEN"            # Tripped: downstream is failing, fail-fast without calling
    HALF_OPEN = "HALF_OPEN"  # Cooldown expired: probe request allowed to test recovery


class CircuitBreakerOpenException(Exception):
    """Raised when an operation is attempted while the circuit breaker is OPEN."""
    def __init__(self, message: str = "Service is temporarily unavailable (circuit breaker open).", cooldown_remaining: float = 0.0):
        super().__init__(message)
        self.cooldown_remaining = max(0.0, round(cooldown_remaining, 2))


class LLMServiceUnavailableException(Exception):
    """Raised when LLM calls fail repeatedly after all retries are exhausted."""
    pass


class CircuitBreaker:
    """
    State machine tracking failures and enforcing cooldowns for downstream services (e.g. llama.cpp).
    """
    def __init__(
        self,
        name: str = "llama_cpp",
        failure_threshold: int = 3,
        cooldown_seconds: float = 15.0
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.time()

    def can_execute(self) -> bool:
        """
        Determines whether a call to the downstream service can proceed.
        Returns True if CLOSED or HALF_OPEN (after cooldown expiration).
        Returns False if OPEN and cooldown has not yet elapsed.
        """
        now = time.time()
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            elapsed = now - self.last_failure_time
            if elapsed >= self.cooldown_seconds:
                logger.info(f"[CircuitBreaker:{self.name}] Cooldown of {self.cooldown_seconds}s elapsed. Transitioning from OPEN to HALF_OPEN probe.")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow trial probe
            return True

        return True

    def get_remaining_cooldown(self) -> float:
        """Returns seconds remaining before next probe attempt is allowed."""
        if self.state != CircuitState.OPEN:
            return 0.0
        elapsed = time.time() - self.last_failure_time
        return max(0.0, self.cooldown_seconds - elapsed)

    def record_success(self):
        """Records a successful operation, resetting failure counter and closing circuit."""
        if self.state != CircuitState.CLOSED:
            logger.info(f"[CircuitBreaker:{self.name}] Probe succeeded. Circuit transition to CLOSED.")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def record_failure(self, error: Optional[Exception] = None):
        """Records a failure. Trips circuit to OPEN if threshold reached or if in HALF_OPEN state."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.state == CircuitState.HALF_OPEN:
            logger.warning(f"[CircuitBreaker:{self.name}] Probe failed ({error}). Circuit immediately tripped back to OPEN.")
            self.state = CircuitState.OPEN
            self.last_state_change = self.last_failure_time
        elif self.failure_count >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                logger.warning(
                    f"[CircuitBreaker:{self.name}] Failure threshold ({self.failure_threshold}) reached "
                    f"(consecutive errors={self.failure_count}, last error: {error}). Circuit tripped to OPEN for {self.cooldown_seconds}s."
                )
            self.state = CircuitState.OPEN
            self.last_state_change = self.last_failure_time
        else:
            logger.warning(
                f"[CircuitBreaker:{self.name}] Recorded failure ({self.failure_count}/{self.failure_threshold}). Error: {error}"
            )

    def reset(self):
        """Resets the circuit breaker to clean CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = 0.0
        self.last_state_change = time.time()
