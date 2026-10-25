"""
Qwen3 / LLM Service layer for VoiceSense AI.
Provides clean HTTP client interface to local llama.cpp server with typed failures,
health check caching, failure cool-down, thinking-mode suppression, and streaming.
"""

import asyncio
import json
import logging
import re
import time
from typing import AsyncGenerator, Dict, Any, List, Optional, Union

import httpx

from backend.app.core.config import settings

logger = logging.getLogger("voicesense.llm")


# ==============================================================================
# Typed Exceptions
# ==============================================================================

class LLMError(Exception):
    """Base exception for all LLM service failures."""
    pass


class LLMUnavailable(LLMError):
    """Raised when the LLM service is unreachable, down, or in cool-down."""
    pass


class LLMTimeout(LLMError):
    """Raised when the LLM server times out."""
    pass


class LLMResponseError(LLMError):
    """Raised when the LLM server returns an invalid or non-200 HTTP response."""
    pass


# ==============================================================================
# Thinking Tag Filter Helper
# ==============================================================================

class ThinkingFilter:
    """
    Stateful filter that strips <think>...</think> blocks from streamed token chunks
    before they reach UI or TTS.
    """

    def __init__(self):
        self.in_think = False
        self.buffer = ""

    def process_chunk(self, chunk: str) -> str:
        """
        Processes an incoming chunk and returns only non-thinking text.
        Handles thinking blocks spanning across multiple chunks.
        """
        if not chunk:
            return ""

        self.buffer += chunk
        output = []

        while self.buffer:
            if not self.in_think:
                # Check for start of <think>
                start_idx = self.buffer.find("<think>")
                if start_idx != -1:
                    # Everything before <think> is normal output
                    if start_idx > 0:
                        output.append(self.buffer[:start_idx])
                    self.buffer = self.buffer[start_idx + len("<think>"):]
                    self.in_think = True
                else:
                    # Check for partial prefix like "<thi" at the end of buffer
                    partial_match = False
                    for i in range(1, len("<think>")):
                        if self.buffer.endswith("<think>"[:i]):
                            # Keep partial match in buffer for next chunk
                            output.append(self.buffer[:-i])
                            self.buffer = self.buffer[-i:]
                            partial_match = True
                            break
                    if not partial_match:
                        output.append(self.buffer)
                        self.buffer = ""
                    break
            else:
                # Currently inside <think>
                end_idx = self.buffer.find("</think>")
                if end_idx != -1:
                    # Found closing tag; skip everything up to </think>
                    self.buffer = self.buffer[end_idx + len("</think>"):]
                    self.in_think = False
                else:
                    # Still inside think block; discard buffer except potential partial </think>
                    partial_match = False
                    for i in range(1, len("</think>")):
                        if self.buffer.endswith("</think>"[:i]):
                            self.buffer = self.buffer[-i:]
                            partial_match = True
                            break
                    if not partial_match:
                        self.buffer = ""
                    break

        return "".join(output)

    def flush(self) -> str:
        """Flushes any remaining non-thinking buffered text."""
        if self.in_think:
            self.buffer = ""
            return ""
        out = self.buffer
        self.buffer = ""
        return out


def strip_thinking_tags(text: str) -> str:
    """Strips <think>...</think> blocks from completed text."""
    if not text:
        return ""
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Also clean unclosed <think> if any
    cleaned = re.sub(r"<think>.*", "", cleaned, flags=re.DOTALL)
    return cleaned.strip()


# ==============================================================================
# LLM Service Implementation
# ==============================================================================

class LLMService:
    """
    Decoupled service communicating with local llama.cpp server over HTTP.
    Features:
    - Typed exceptions (LLMUnavailable, LLMTimeout, LLMResponseError)
    - Short-cached health checks (<5s) with automatic cool-down
    - Streaming SSE token emission and non-streaming completion
    - Thinking mode suppression and <think> token stripping
    - Strict localhost / config boundaries
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: Optional[float] = None,
        max_tokens: Optional[int] = None,
        enable_thinking: Optional[bool] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        self._base_url = (base_url or settings.LLM_BASE_URL).rstrip("/")
        self._model_name = model_name or settings.LLM_MODEL_NAME
        self._timeout = timeout if timeout is not None else settings.LLM_TIMEOUT_SECONDS
        self._max_tokens = max_tokens if max_tokens is not None else settings.LLM_MAX_TOKENS
        self._enable_thinking = enable_thinking if enable_thinking is not None else settings.LLM_ENABLE_THINKING
        self._custom_client = client

        # Health check caching & cool-down state
        self._health_cache_ttl = settings.LLM_HEALTH_CACHE_SECONDS
        self._failure_threshold = settings.LLM_FAILURE_THRESHOLD
        self._cooldown_duration = settings.LLM_COOLDOWN_SECONDS

        self._last_health_check_time: float = 0.0
        self._last_health_status: bool = False
        self._consecutive_failures: int = 0
        self._cooldown_until: float = 0.0

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def model_name(self) -> str:
        return self._model_name

    def _resolve_url(self, path: str) -> str:
        """Resolves full endpoint URL correctly with or without /v1 base path."""
        path = path.lstrip("/")
        if self._base_url.endswith("/v1"):
            if path.startswith("v1/"):
                path = path[3:]
            return f"{self._base_url}/{path}"
        else:
            if not path.startswith("v1/"):
                path = f"v1/{path}"
            return f"{self._base_url}/{path}"

    def _get_client(self, timeout: Optional[float] = None) -> httpx.AsyncClient:
        """Returns an AsyncClient instance (custom injected or fresh)."""
        if self._custom_client is not None:
            return self._custom_client
        total_timeout = timeout or self._timeout
        http_timeout = httpx.Timeout(timeout=total_timeout, connect=2.0)
        return httpx.AsyncClient(timeout=http_timeout)

    def is_in_cooldown(self) -> bool:
        """Returns True if the service is currently cooling down after repeated failures."""
        return time.time() < self._cooldown_until

    def _record_success(self):
        """Resets failure count and cool-down on successful response."""
        self._consecutive_failures = 0
        self._cooldown_until = 0.0
        self._last_health_status = True
        self._last_health_check_time = time.time()

    def _record_failure(self, exc: Exception):
        """Records a failure and triggers cool-down if threshold reached."""
        self._consecutive_failures += 1
        self._last_health_status = False
        self._last_health_check_time = time.time()

        if self._consecutive_failures >= self._failure_threshold:
            self._cooldown_until = time.time() + self._cooldown_duration
            logger.warning(
                f"[LLMService] Trip cool-down for {self._cooldown_duration}s "
                f"after {self._consecutive_failures} consecutive failures. (Reason: {exc})"
            )
        else:
            logger.warning(
                f"[LLMService] Request failure ({self._consecutive_failures}/{self._failure_threshold}): {exc}"
            )

    async def check_health(self, force: bool = False) -> bool:
        """
        Lightweight health check against local llama.cpp server.
        Uses a short cache (5s) and avoids redundant network calls.
        """
        now = time.time()
        if not force and (now - self._last_health_check_time < self._health_cache_ttl):
            return self._last_health_status

        if self.is_in_cooldown():
            return False

        url = self._resolve_url("models")
        client = self._get_client(timeout=3.0)
        close_client = (client != self._custom_client)

        try:
            res = await client.get(url)
            if res.status_code == 200:
                self._record_success()
                return True
            else:
                self._record_failure(LLMResponseError(f"HTTP {res.status_code} from {url}"))
                return False
        except (httpx.ConnectError, httpx.NetworkError) as e:
            self._record_failure(LLMUnavailable(f"Connection refused at {url}: {e}"))
            return False
        except httpx.TimeoutException as e:
            self._record_failure(LLMTimeout(f"Health check timed out: {e}"))
            return False
        except Exception as e:
            self._record_failure(e)
            return False
        finally:
            if close_client:
                await client.aclose()

    def get_health_status(self) -> Dict[str, Any]:
        """Returns structured health report for /api/health."""
        in_cd = self.is_in_cooldown()
        remaining_cd = max(0.0, self._cooldown_until - time.time()) if in_cd else 0.0

        if self._last_health_status and not in_cd:
            status_str = "ok"
        elif in_cd or self._consecutive_failures > 0:
            status_str = "unhealthy"
        else:
            status_str = "degraded"

        return {
            "status": status_str,
            "endpoint": self._base_url,
            "model": self._model_name,
            "in_cooldown": in_cd,
            "cooldown_remaining_sec": round(remaining_cd, 1),
            "consecutive_failures": self._consecutive_failures,
        }

    async def generate(
        self,
        messages: List[Dict[str, str]],
        *,
        emotion: Optional[str] = None,
        language: Optional[str] = None,
        stream: bool = True,
        max_tokens: Optional[int] = None,
        timeout: Optional[float] = None,
    ) -> Union[str, AsyncGenerator[str, None]]:
        """
        Generates completion from local llama.cpp server.
        If stream=True: returns AsyncGenerator yielding stripped token strings.
        If stream=False: returns the complete stripped response string.
        """
        if self.is_in_cooldown():
            rem = max(0.0, self._cooldown_until - time.time())
            raise LLMUnavailable(
                f"LLM service is temporarily unavailable (cooldown active, {rem:.1f}s remaining)."
            )

        endpoint_url = self._resolve_url("chat/completions")
        request_timeout = timeout or self._timeout
        token_limit = max_tokens or self._max_tokens

        payload: Dict[str, Any] = {
            "model": self._model_name,
            "messages": messages,
            "max_tokens": token_limit,
            "stream": stream,
            "temperature": 0.7,
            # Explicitly disable thinking mode for low voice latency
            "chat_template_kwargs": {
                "enable_thinking": self._enable_thinking
            }
        }

        if stream:
            return self._stream_generator(endpoint_url, payload, request_timeout)
        else:
            return await self._generate_non_stream(endpoint_url, payload, request_timeout)

    async def _generate_non_stream(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: float,
    ) -> str:
        client = self._get_client(timeout=timeout)
        close_client = (client != self._custom_client)
        try:
            res = await client.post(url, json=payload)
            if res.status_code != 200:
                err_msg = f"LLM server returned status {res.status_code}: {res.text}"
                if res.status_code >= 500:
                    raise LLMUnavailable(err_msg)
                raise LLMResponseError(err_msg)

            data = res.json()
            choices = data.get("choices", [])
            if not choices:
                raise LLMResponseError("LLM response contained no choices")

            raw_text = choices[0].get("message", {}).get("content", "")
            self._record_success()
            return strip_thinking_tags(raw_text)

        except (httpx.ConnectError, httpx.NetworkError) as e:
            self._record_failure(e)
            raise LLMUnavailable(f"Cannot connect to local LLM server at {url}: {e}") from e
        except httpx.TimeoutException as e:
            self._record_failure(e)
            raise LLMTimeout(f"LLM request timed out after {timeout}s: {e}") from e
        except LLMError as e:
            self._record_failure(e)
            raise
        except Exception as e:
            self._record_failure(e)
            raise LLMError(f"Unexpected LLM generation error: {e}") from e
        finally:
            if close_client:
                await client.aclose()

    async def _stream_generator(
        self,
        url: str,
        payload: Dict[str, Any],
        timeout: float,
    ) -> AsyncGenerator[str, None]:
        client = self._get_client(timeout=timeout)
        close_client = (client != self._custom_client)
        thinking_filter = ThinkingFilter()

        try:
            async with client.stream("POST", url, json=payload) as response:
                if response.status_code != 200:
                    err_text = await response.aread()
                    err_msg = f"LLM streaming endpoint returned status {response.status_code}: {err_text.decode('utf-8', errors='ignore')}"
                    if response.status_code >= 500:
                        raise LLMUnavailable(err_msg)
                    raise LLMResponseError(err_msg)

                self._record_success()

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data:"):
                        continue

                    data_str = line[5:].strip()
                    if data_str == "[DONE]":
                        break

                    try:
                        chunk = json.loads(data_str)
                        choices = chunk.get("choices", [])
                        if choices:
                            delta = choices[0].get("delta", {})
                            content = delta.get("content")
                            if content:
                                clean_text = thinking_filter.process_chunk(content)
                                if clean_text:
                                    yield clean_text
                    except json.JSONDecodeError:
                        continue

                # Final flush of any non-thinking remainder
                remainder = thinking_filter.flush()
                if remainder:
                    yield remainder

        except asyncio.CancelledError:
            logger.info("LLM stream cancelled by client request.")
            raise
        except (httpx.ConnectError, httpx.NetworkError) as e:
            self._record_failure(e)
            raise LLMUnavailable(f"Cannot connect to local LLM server at {url}: {e}") from e
        except httpx.TimeoutException as e:
            self._record_failure(e)
            raise LLMTimeout(f"LLM stream timed out after {timeout}s: {e}") from e
        except LLMError as e:
            self._record_failure(e)
            raise
        except Exception as e:
            self._record_failure(e)
            raise LLMError(f"Unexpected LLM streaming error: {e}") from e
        finally:
            if close_client:
                await client.aclose()


# Singleton instance loaded once at module level
llm_service = LLMService()
