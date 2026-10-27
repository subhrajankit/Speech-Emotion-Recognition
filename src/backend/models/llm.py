import asyncio
import json
import httpx
import logging
from typing import Optional, Any, List, Dict, AsyncGenerator

logger = logging.getLogger(__name__)

class LlamaCppClient:
    """
    Client for local llama.cpp server exposing OpenAI-compatible /v1/chat/completions.
    Binds strictly to 127.0.0.1.
    """
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080/v1",
        model_name: str = "qwen3-1.7b",
        timeout: float = 30.0,
        mock: bool = False,
        max_retries: int = 2,
        backoff_factor: float = 0.2,
        circuit_breaker: Optional[Any] = None,
        enable_thinking: Optional[bool] = None
    ):
        self.base_url = base_url.rstrip("/")
        self.model_name = model_name
        self.timeout = timeout
        self.mock = mock
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        from ..llm.circuit_breaker import CircuitBreaker
        self.circuit_breaker = circuit_breaker or CircuitBreaker(
            name="llama_cpp",
            failure_threshold=3,
            cooldown_seconds=15.0
        )
        if enable_thinking is not None:
            self.enable_thinking = enable_thinking
        else:
            try:
                from ..config import settings
                self.enable_thinking = getattr(settings, "LLM_ENABLE_THINKING", False)
            except Exception:
                self.enable_thinking = False
        self.is_loaded = False
        self._check_health_sync()

    def _check_health_sync(self):
        if self.mock:
            self.is_loaded = True
            return

        try:
            with httpx.Client(timeout=3.0) as client:
                res = client.get(f"{self.base_url}/models")
                if res.status_code == 200:
                    self.is_loaded = True
                    self.circuit_breaker.record_success()
                    logger.info(f"Connected to local llama.cpp server at {self.base_url}.")
                else:
                    self.is_loaded = False
                    logger.warning(f"llama.cpp server returned status {res.status_code}.")
        except Exception as e:
            self.is_loaded = False
            logger.warning(f"llama.cpp server at {self.base_url} is unreachable ({e}). Using mock/fallback mode.")

    async def check_health(self) -> bool:
        if self.mock:
            return True
        if not self.circuit_breaker.can_execute():
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.base_url}/models")
                healthy = (res.status_code == 200)
                if healthy:
                    self.circuit_breaker.record_success()
                    self.is_loaded = True
                else:
                    self.circuit_breaker.record_failure()
                    self.is_loaded = False
                return healthy
        except Exception as e:
            self.circuit_breaker.record_failure(e)
            self.is_loaded = False
            return False

    def _build_messages(
        self,
        prompt: str,
        emotion: Optional[Any] = None,
        language: str = "en",
        mixed_language: bool = False,
        messages: Optional[list] = None
    ) -> list:
        if messages is not None:
            return messages
        from ..llm.prompts import format_qwen_chat_messages
        return format_qwen_chat_messages(
            transcript=prompt,
            emotion=emotion,
            language=language,
            mixed_language=mixed_language
        )

    def _get_fallback_text(
        self,
        prompt: str,
        messages: list,
        emotion: Optional[Any] = None
    ) -> str:
        if messages and len(messages) > 1 and "BEGIN RETRIEVED VERIFIED KNOWLEDGE" in messages[1]["content"]:
            import re
            user_msg = messages[1]["content"]
            doc_name = "retrieved documents"
            doc_match = re.search(r"Based on ([^:]+):", user_msg)
            if doc_match:
                doc_name = doc_match.group(1).strip()
            lines = [
                line.strip() for line in user_msg.splitlines()
                if line.strip() and not line.startswith("---") and not line.startswith("[") and not line.startswith("User Question:") and not line.startswith("Instructions:")
            ]
            content_snippet = lines[0] if lines else "Verified information from documentation."
            return f"Based on {doc_name}: {content_snippet}"

        prefix = ""
        if emotion:
            prim = emotion.primary if hasattr(emotion, "primary") else (emotion.get("primary", "") if isinstance(emotion, dict) else "")
            if prim and prim != "neutral":
                prefix = f"[{prim.capitalize()} tone acknowledged] "
        return f"{prefix}I heard you say: '{prompt}'. Local llama.cpp is not connected yet, but the voice loop is functioning!"

    async def stream_response(
        self,
        prompt: str,
        emotion: Optional[Any] = None,
        language: str = "en",
        mixed_language: bool = False,
        messages: Optional[list] = None,
        enable_thinking: Optional[bool] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens asynchronously from the local llama.cpp server
        using Server-Sent Events (SSE) over /v1/chat/completions.
        """
        if not prompt and not messages:
            yield "I did not receive any input."
            return

        built_messages = self._build_messages(
            prompt=prompt,
            emotion=emotion,
            language=language,
            mixed_language=mixed_language,
            messages=messages
        )

        # In mock mode, stream fallback text token by token
        if self.mock:
            fallback_text = self._get_fallback_text(prompt, built_messages, emotion)
            tokens = fallback_text.split(" ")
            for i, token in enumerate(tokens):
                separator = " " if i > 0 else ""
                yield separator + token
                await asyncio.sleep(0.01)  # Micro-delay for async pipelining simulation
            return

        # Check circuit breaker before making downstream call
        if not self.circuit_breaker.can_execute():
            rem = self.circuit_breaker.get_remaining_cooldown()
            logger.warning(f"[LlamaCppClient] Circuit breaker is OPEN ({rem}s cooldown remaining). Fast-failing.")
            yield "The language reasoning service is temporarily unavailable. Please try again shortly."
            return

        use_thinking = self.enable_thinking if enable_thinking is None else enable_thinking
        payload = {
            "model": self.model_name,
            "messages": built_messages,
            "temperature": 0.7,
            "max_tokens": 120,
            "stream": True,
            "chat_template_kwargs": {
                "enable_thinking": use_thinking
            }
        }

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    async with client.stream("POST", f"{self.base_url}/chat/completions", json=payload) as response:
                        response.raise_for_status()
                        self.circuit_breaker.record_success()
                        self.is_loaded = True
                        async for line in response.aiter_lines():
                            line = line.strip()
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data_str = line[6:].strip()
                                if data_str == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data_str)
                                    choices = chunk.get("choices", [])
                                    if choices:
                                        delta = choices[0].get("delta", {})
                                        content = delta.get("content")
                                        if content:
                                            yield content
                                except json.JSONDecodeError:
                                    continue
                        return
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = self.backoff_factor * (2 ** attempt)
                    logger.warning(
                        f"[LlamaCppClient] Stream attempt {attempt + 1}/{self.max_retries + 1} failed ({e}). "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"[LlamaCppClient] Stream failed after {self.max_retries + 1} attempts: {e}")

        # All retries exhausted: record failure on circuit breaker and fail fast
        self.circuit_breaker.record_failure(last_error)
        self.is_loaded = False
        yield "The language reasoning service is temporarily unavailable. Please try again shortly."

    async def generate_response(
        self,
        prompt: str,
        emotion: Optional[Any] = None,
        language: str = "en",
        mixed_language: bool = False,
        messages: Optional[list] = None,
        enable_thinking: Optional[bool] = None
    ) -> str:
        """
        Sends prompt with structured emotional and linguistic context to local llama.cpp server
        and returns complete response text (aggregating stream).
        """
        tokens = []
        async for token in self.stream_response(
            prompt=prompt,
            emotion=emotion,
            language=language,
            mixed_language=mixed_language,
            messages=messages,
            enable_thinking=enable_thinking
        ):
            tokens.append(token)
        return "".join(tokens).strip()


