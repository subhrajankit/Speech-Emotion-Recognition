"""
Gemini 3 Flash Cloud LLM Client.
Optional comparison / demo fallback alongside the local Qwen3-1.7B model.
Streams tokens asynchronously via Google Gemini REST API Server-Sent Events (SSE).
"""

import asyncio
import json
import httpx
import logging
from typing import Optional, Any, List, Dict, AsyncGenerator

from ..config import settings
from .prompts import format_qwen_chat_messages

logger = logging.getLogger(__name__)

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


class GeminiClient:
    """
    Cloud LLM client calling Google Gemini (Gemini 3 Flash / 2.5 Flash).
    Matches the exact interface of LlamaCppClient / QwenClient.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        timeout: float = 30.0,
        mock: Optional[bool] = None
    ):
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model_name = model_name or settings.GEMINI_MODEL_NAME
        self.timeout = timeout
        self.mock = mock if mock is not None else settings.MOCK_MODELS
        self.is_loaded = True if (self.mock or bool(self.api_key)) else False

    def check_health(self) -> bool:
        """Returns True if the client is ready (mock mode or API key present)."""
        if self.mock:
            return True
        return bool(self.api_key and self.api_key.strip())

    def _build_payload(
        self,
        prompt: str,
        emotion: Optional[Any] = None,
        language: str = "en",
        mixed_language: bool = False,
        messages: Optional[list] = None
    ) -> Dict[str, Any]:
        """
        Converts OpenAI-style messages into Gemini API contents structure.
        """
        if messages is None:
            messages = format_qwen_chat_messages(
                transcript=prompt,
                emotion=emotion,
                language=language,
                mixed_language=mixed_language
            )

        system_instruction_text = ""
        user_parts = []

        for msg in messages:
            role = msg.get("role")
            content = msg.get("content", "")
            if role == "system":
                system_instruction_text += content + "\n"
            else:
                user_parts.append({"text": content})

        if not user_parts and prompt:
            user_parts.append({"text": prompt})

        payload: Dict[str, Any] = {
            "contents": [
                {
                    "role": "user",
                    "parts": user_parts
                }
            ],
            "generationConfig": {
                "temperature": 0.7,
                "maxOutputTokens": 150
            }
        }

        if system_instruction_text.strip():
            payload["systemInstruction"] = {
                "parts": [{"text": system_instruction_text.strip()}]
            }

        return payload

    async def stream_response(
        self,
        prompt: str,
        emotion: Optional[Any] = None,
        language: str = "en",
        mixed_language: bool = False,
        messages: Optional[list] = None
    ) -> AsyncGenerator[str, None]:
        """
        Streams response tokens asynchronously from Gemini 3 Flash.
        Yields token strings matching the SentenceBoundaryChunker expectations.
        """
        if not prompt and not messages:
            yield "I did not receive any input."
            return

        # Mock / Offline Fallback if MOCK_MODELS=True or API key missing
        if self.mock or not self.api_key or not self.api_key.strip():
            if not self.api_key:
                logger.info("[GeminiClient] GEMINI_API_KEY not set. Using mock cloud response.")
            
            prefix = "[Gemini 3 Flash] "
            if emotion:
                prim = emotion.primary if hasattr(emotion, "primary") else (emotion.get("primary", "") if isinstance(emotion, dict) else "")
                if prim and prim != "neutral":
                    prefix += f"[{prim.capitalize()} acknowledged] "

            fallback_text = f"{prefix}I heard: '{prompt}'. Responding via cloud Gemini 3 Flash."
            tokens = fallback_text.split(" ")
            for i, token in enumerate(tokens):
                separator = " " if i > 0 else ""
                yield separator + token
                await asyncio.sleep(0.01)
            return

        url = f"{GEMINI_API_BASE}/models/{self.model_name}:streamGenerateContent?key={self.api_key}&alt=sse"
        payload = self._build_payload(prompt, emotion, language, mixed_language, messages)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                async with client.stream("POST", url, json=payload) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            continue
                        if line.startswith("data: "):
                            data_str = line[6:].strip()
                            try:
                                chunk = json.loads(data_str)
                                candidates = chunk.get("candidates", [])
                                if candidates:
                                    content = candidates[0].get("content", {})
                                    parts = content.get("parts", [])
                                    for part in parts:
                                        text = part.get("text", "")
                                        if text:
                                            yield text
                            except json.JSONDecodeError:
                                continue
        except Exception as e:
            logger.error(f"[GeminiClient] Cloud inference failed ({e}). Falling back to error notification.")
            yield "The cloud reasoning service encountered an error. Please check your API key and connection."

    async def generate_response(
        self,
        prompt: str,
        emotion: Optional[Any] = None,
        language: str = "en",
        mixed_language: bool = False,
        messages: Optional[list] = None
    ) -> str:
        """Collects the full streamed response text."""
        tokens = []
        async for token in self.stream_response(
            prompt=prompt,
            emotion=emotion,
            language=language,
            mixed_language=mixed_language,
            messages=messages
        ):
            tokens.append(token)
        return "".join(tokens).strip()


def get_gemini_client() -> GeminiClient:
    """Helper function to instantiate or retrieve configured GeminiClient."""
    return GeminiClient()
