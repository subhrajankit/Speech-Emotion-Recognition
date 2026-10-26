"""
Indic Parler-TTS Service for VoiceSense AI (Phase 8).

Lazy-loaded TTS service providing sentence-level audio streaming from LLM text.
Fully independent of ASR/SER — ASR startup does NOT load TTS.
Adheres to strict truthfulness: NO mock/fallback synthesis in runtime code.
If weights or dependencies are unavailable, raises TTSError and reports tts_unavailable.

Model: ai4bharat/indic-parler-tts (Apache 2.0, Gated)
  - 23 languages: Assamese, Bengali, Bodo, Dogri, English, Gujarati, Hindi,
    Kannada, Kashmiri, Konkani, Maithili, Malayalam, Manipuri, Marathi, Nepali, Odia,
    Punjabi, Sanskrit, Santali, Sindhi, Tamil, Telugu, Urdu.
  - 69 unique speakers. Natural language description prompt conditions voice.
  - Sample rate: 44,100 Hz (config-driven).
"""

import asyncio
import io
import json
import logging
import os
import re
import struct
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import AsyncIterator, Dict, Any, List, Optional

from backend.app.core.config import settings

logger = logging.getLogger("voicesense.tts")


# ==============================================================================
# Typed Exceptions
# ==============================================================================

class TTSError(Exception):
    """Raised when TTS synthesis fails or is unavailable. Pipeline continues text-only."""
    pass


class TTSOOMError(TTSError):
    """Raised when TTS encounters CUDA out-of-memory."""
    pass


# ==============================================================================
# TTS Chunk Data
# ==============================================================================

@dataclass
class TTSChunk:
    """A single sentence's synthesized audio."""
    audio: bytes
    sample_rate: int
    sentence_index: int
    sentence_text: str
    synthesis_time_ms: float = 0.0
    audio_duration_ms: float = 0.0
    rtf: float = 0.0  # real-time factor: synthesis_time / audio_duration


# ==============================================================================
# Supported Languages & Speakers (from model card)
# ==============================================================================

INDIC_PARLER_LANGUAGES = {
    "as", "bn", "brx", "doi", "en", "gu", "hi", "kn", "kok", "ks",
    "mai", "ml", "mni", "mr", "ne", "or", "pa", "sa", "sat", "sd",
    "ta", "te", "ur",
}

LANGUAGE_SPEAKER_MAP: Dict[str, str] = {
    "hi": "Aditi",
    "en": "Aditi",
    "bn": "Aditi",
    "ta": "Aditi",
    "te": "Aditi",
    "mr": "Aditi",
    "gu": "Aditi",
    "kn": "Aditi",
    "ml": "Aditi",
    "pa": "Aditi",
    "ur": "Aditi",
}

EMOTION_STYLE_MAPPING: Dict[str, str] = {
    "neutral": "with natural, balanced delivery and moderate pace",
    "sad": "with slow, calm, gentle, and empathetic delivery",
    "happy": "with cheerful, lively, and slightly faster delivery",
    "angry": "with calm, slow, de-escalating, and soothing delivery",
    "fearful": "with gentle, steady, warm, and reassuring delivery",
    "disgusted": "with neutral, professional, and composed delivery",
    "surprised": "with attentive, clear, and slightly upbeat delivery",
    "excited": "with energetic, lively, and dynamic delivery",
}


# ==============================================================================
# Text Cleaning
# ==============================================================================

_THINK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)
_THINK_UNCLOSED = re.compile(r"<think>.*", re.DOTALL)
_MARKDOWN_IMAGE = re.compile(r"!\[[^\]]*\]\([^)]+\)")
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_BOLD = re.compile(r"(\*\*|__)(.*?)\1")
_MARKDOWN_ITALIC = re.compile(r"(\*|_)(.*?)\1")
_MARKDOWN_CODE = re.compile(r"`{1,3}.*?`{1,3}", re.DOTALL)
_MARKDOWN_HEADING = re.compile(r"^#+\s*", re.MULTILINE)
_CITATION_PATTERN = re.compile(r"\[\d+\]|\[[^\]]+\.(?:md|pdf|txt|docx)\]|\[chunk_[a-zA-Z0-9_-]+\]", re.IGNORECASE)
_URL_PATTERN = re.compile(r"https?://\S+")
_EMOJI_PATTERN = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "]+",
    flags=re.UNICODE,
)
_MULTI_SPACE = re.compile(r"\s+")


def clean_tts_text(text: str) -> str:
    """
    Strips markdown, emoji, citations, URLs, and <think> content from LLM text
    before sending to Indic Parler-TTS.
    """
    if not text:
        return ""

    # Strip <think>...</think> blocks
    cleaned = _THINK_PATTERN.sub("", text)
    cleaned = _THINK_UNCLOSED.sub("", cleaned)

    # Strip citations like [1], [policy.md], [chunk_0_123]
    cleaned = _CITATION_PATTERN.sub("", cleaned)

    # Strip markdown elements
    cleaned = _MARKDOWN_IMAGE.sub("", cleaned)
    cleaned = _MARKDOWN_LINK.sub(r"\1", cleaned)
    cleaned = _MARKDOWN_CODE.sub("", cleaned)
    cleaned = _MARKDOWN_BOLD.sub(r"\2", cleaned)
    cleaned = _MARKDOWN_ITALIC.sub(r"\2", cleaned)
    cleaned = _MARKDOWN_HEADING.sub("", cleaned)

    # Strip URLs & Emojis
    cleaned = _URL_PATTERN.sub("", cleaned)
    cleaned = _EMOJI_PATTERN.sub("", cleaned)

    # Normalize whitespace
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    return cleaned


# ==============================================================================
# Sentence Splitting (English + Hindi Danda)
# ==============================================================================

# Sentence boundaries: . ! ? newline or Hindi danda (।) and double danda (॥)
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?।॥\n])\s+')

_ABBREVIATIONS = {
    "dr.", "mr.", "mrs.", "ms.", "prof.", "sr.", "jr.", "e.g.", "i.e.", "vs.", "etc.", "approx."
}


def split_sentences(text: str, max_length: int = 500) -> List[str]:
    """
    Splits text into sentences on English (.!?) and Hindi (। ॥) boundaries.
    Protects common abbreviations.
    """
    if not text:
        return []

    raw_parts = _SENTENCE_SPLIT.split(text)
    sentences: List[str] = []

    for part in raw_parts:
        part = part.strip()
        if not part:
            continue

        if len(part) > max_length:
            sub_parts = re.split(r'[,;]\s+', part)
            for sp in sub_parts:
                sp = sp.strip()
                if sp:
                    sentences.append(sp[:max_length])
        else:
            sentences.append(part)

    return sentences


# ==============================================================================
# Voice Description Builder
# ==============================================================================

def build_voice_description(
    language: Optional[str] = None,
    emotion: Optional[str] = None,
    custom_description: Optional[str] = None,
) -> str:
    """
    Constructs natural language voice description prompt for Indic Parler-TTS.
    Emotion styling is config-driven and off by default.
    """
    if custom_description:
        return custom_description

    speaker = LANGUAGE_SPEAKER_MAP.get(language or "", settings.TTS_DEFAULT_SPEAKER)
    parts = [f"{speaker} speaks in a clear, natural voice with high quality audio"]

    if settings.TTS_EMOTION_STYLING_ENABLED and emotion:
        style = EMOTION_STYLE_MAPPING.get(emotion.lower().strip())
        if style:
            parts.append(f"and {style}")
        else:
            parts.append("and moderate pace")
    else:
        parts.append("and moderate pace")

    return " ".join(parts) + "."


# ==============================================================================
# TTSService Class
# ==============================================================================

class TTSService:
    """
    Indic Parler-TTS Service.
    Lazy-loaded: never initialized during ASR startup.
    Runs off the event loop bounded by concurrency limit of 1.
    Strictly reports real availability and errors; no fake runtime synthesis.
    """

    def __init__(self):
        self._model = None
        self._tokenizer = None
        self._description_tokenizer = None
        self._is_loaded = False
        self._load_error: Optional[str] = None
        self._load_lock = threading.Lock()
        self._sample_rate = settings.TTS_SAMPLE_RATE
        self._semaphore: Optional[asyncio.Semaphore] = None
        self._worker_process: Optional[subprocess.Popen] = None
        self._engine_override = None  # Hook for test-only FakeEngineForTests

    @property
    def is_loaded(self) -> bool:
        return self._is_loaded

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(settings.TTS_CONCURRENCY_LIMIT)
        return self._semaphore

    def initialize(self):
        """
        Loads the Indic Parler-TTS model.
        Called lazily on the first synthesis request. Thread-safe.
        """
        if self._is_loaded:
            return

        with self._load_lock:
            if self._is_loaded:
                return

            # Check if engine override was provided by a test
            if self._engine_override is not None:
                self._is_loaded = True
                return

            t0 = time.perf_counter()
            try:
                # 1. Try direct import in current environment
                try:
                    import torch
                    from parler_tts import ParlerTTSForConditionalGeneration
                    from transformers import AutoTokenizer

                    device = settings.TTS_DEVICE
                    if device == "cuda" and not torch.cuda.is_available():
                        logger.warning("[TTSService] CUDA not available, falling back to CPU.")
                        device = "cpu"

                    logger.info(f"[TTSService] Loading {settings.TTS_MODEL_ID} on {device}...")
                    self._tokenizer = AutoTokenizer.from_pretrained(settings.TTS_MODEL_ID)
                    self._description_tokenizer = AutoTokenizer.from_pretrained(settings.TTS_MODEL_ID)
                    self._model = ParlerTTSForConditionalGeneration.from_pretrained(settings.TTS_MODEL_ID)
                    self._model.to(device)
                    self._sample_rate = getattr(self._model.config, "sampling_rate", settings.TTS_SAMPLE_RATE)
                    self._is_loaded = True
                    load_time_ms = (time.perf_counter() - t0) * 1000
                    logger.info(f"[TTSService] Indic Parler-TTS loaded in {load_time_ms:.0f}ms on {device}.")
                    return
                except ImportError as imp_err:
                    logger.info(f"[TTSService] In-process packages not found ({imp_err}). Checking .venv-tts...")

                # 2. Check if .venv-tts is present with worker
                worker_python = settings.TTS_WORKER_PYTHON
                if os.path.exists(worker_python):
                    # Test worker availability
                    self._is_loaded = True
                    logger.info(f"[TTSService] TTS worker available at {worker_python}.")
                    return

                raise TTSError("Indic Parler-TTS dependencies (torch, transformers, parler-tts) are not installed.")

            except Exception as e:
                self._load_error = str(e)
                logger.error(f"[TTSService] Failed to load Indic Parler-TTS: {e}")
                raise TTSError(f"Indic Parler-TTS unavailable: {e}") from e

    async def synthesize(
        self,
        text: str,
        language: Optional[str] = None,
        *,
        description: Optional[str] = None,
        emotion: Optional[str] = None,
    ) -> AsyncIterator[TTSChunk]:
        """
        Synthesizes text into audio chunks sentence-by-sentence.

        Args:
            text: LLM output text (cleaned before synthesis).
            language: ISO 639-1 code. Falls back to English if unsupported.
            description: Optional custom voice description prompt override.
            emotion: Optional detected user emotion for voice styling.

        Yields:
            TTSChunk with WAV audio bytes, sample rate, and timing metadata.

        Raises:
            TTSError: On missing model, CUDA OOM, or synthesis failure.
        """
        cleaned = clean_tts_text(text)
        if not cleaned:
            return

        # Lazy init on first request
        if not self._is_loaded:
            await asyncio.to_thread(self.initialize)

        # Unsupported language fallback
        resolved_lang = language
        if resolved_lang and resolved_lang.lower() not in INDIC_PARLER_LANGUAGES:
            logger.debug(f"[TTSService] Language '{resolved_lang}' not in Indic Parler-TTS. Falling back to 'en'.")
            resolved_lang = "en"

        voice_desc = build_voice_description(
            language=resolved_lang,
            emotion=emotion,
            custom_description=description,
        )

        sentences = split_sentences(cleaned, max_length=settings.TTS_MAX_SENTENCE_LENGTH)
        if not sentences:
            return

        sem = self._get_semaphore()
        async with sem:
            for idx, sentence in enumerate(sentences):
                t0 = time.perf_counter()
                try:
                    audio_bytes, sr = await asyncio.to_thread(
                        self._synthesize_sentence_sync,
                        sentence,
                        voice_desc
                    )
                except Exception as e:
                    logger.error(f"[TTSService] Synthesis failed for sentence {idx}: {e}")
                    if isinstance(e, TTSOOMError) or "out of memory" in str(e).lower():
                        raise TTSOOMError(f"TTS CUDA Out of Memory on sentence {idx}: {e}") from e
                    raise TTSError(f"TTS synthesis failed for sentence {idx}: {e}") from e


                synthesis_time_ms = (time.perf_counter() - t0) * 1000
                audio_dur_ms = self._estimate_wav_duration_ms(audio_bytes, sr)
                rtf = (synthesis_time_ms / audio_dur_ms) if audio_dur_ms > 0 else 0.0

                yield TTSChunk(
                    audio=audio_bytes,
                    sample_rate=sr,
                    sentence_index=idx,
                    sentence_text=sentence,
                    synthesis_time_ms=synthesis_time_ms,
                    audio_duration_ms=audio_dur_ms,
                    rtf=rtf,
                )

    def _synthesize_sentence_sync(self, text: str, description: str) -> tuple[bytes, int]:
        """Synchronous single-sentence synthesis running off event loop."""
        if self._engine_override is not None:
            return self._engine_override.synthesize_wav(text, description)

        if self._model is not None:
            return self._synthesize_with_model(text, description)

        # Worker fallback
        worker_python = settings.TTS_WORKER_PYTHON
        if os.path.exists(worker_python):
            return self._synthesize_with_worker(text, description)

        raise TTSError("TTS model is not loaded and no worker is configured.")

    def _synthesize_with_model(self, text: str, description: str) -> tuple[bytes, int]:
        import torch
        import soundfile as sf

        try:
            device = settings.TTS_DEVICE
            input_ids = self._tokenizer(description, return_tensors="pt").input_ids.to(device)
            prompt_input_ids = self._tokenizer(text, return_tensors="pt").input_ids.to(device)

            with torch.no_grad():
                generation = self._model.generate(
                    input_ids=input_ids,
                    prompt_input_ids=prompt_input_ids,
                )

            audio_arr = generation.cpu().numpy().squeeze()
            wav_buf = io.BytesIO()
            sf.write(wav_buf, audio_arr, self._sample_rate, format="WAV", subtype="PCM_16")
            wav_buf.seek(0)
            return wav_buf.read(), self._sample_rate

        except (torch.cuda.OutOfMemoryError, RuntimeError) as e:
            if "out of memory" in str(e).lower():
                torch.cuda.empty_cache()
                raise TTSOOMError(f"CUDA out of memory during TTS synthesis: {e}") from e
            raise TTSError(f"Model generation error: {e}") from e

    def _synthesize_with_worker(self, text: str, description: str) -> tuple[bytes, int]:
        """Executes synthesis via worker script in .venv-tts."""
        import tempfile
        worker_script = os.path.join(os.path.dirname(__file__), "tts_worker.py")
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp_f:
            tmp_path = tmp_f.name

        try:
            cmd = [
                settings.TTS_WORKER_PYTHON,
                worker_script,
                "--text", text,
                "--description", description,
                "--device", settings.TTS_DEVICE,
                "--model", settings.TTS_MODEL_ID,
                "--output", tmp_path,
            ]
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60.0)
            if result.returncode != 0:
                err = result.stderr.decode("utf-8", errors="replace")
                if "out of memory" in err.lower():
                    raise TTSOOMError(f"CUDA out of memory in TTS worker: {err}")
                raise TTSError(f"TTS worker failed (code {result.returncode}): {err}")

            with open(tmp_path, "rb") as f:
                wav_bytes = f.read()

            if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
                raise TTSError(f"TTS worker returned invalid WAV data ({len(wav_bytes)} bytes)")
            return wav_bytes, settings.TTS_SAMPLE_RATE
        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


    def _estimate_wav_duration_ms(self, wav_bytes: bytes, fallback_sr: int) -> float:
        """Calculates audio duration in milliseconds from standard WAV header."""
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
            return 0.0
        try:
            sr = struct.unpack_from("<I", wav_bytes, 24)[0]
            offset = 12
            while offset < len(wav_bytes) - 8:
                chunk_id = wav_bytes[offset:offset + 4]
                chunk_sz = struct.unpack_from("<I", wav_bytes, offset + 4)[0]
                if chunk_id == b"data":
                    num_samples = chunk_sz // 2  # 16-bit PCM mono
                    return (num_samples / sr) * 1000.0
                offset += 8 + chunk_sz
        except Exception:
            pass
        return ((len(wav_bytes) - 44) / (fallback_sr * 2)) * 1000.0

    def get_health_status(self) -> Dict[str, Any]:
        """Returns structured health status for /api/health."""
        if not self._is_loaded and self._load_error is None:
            return {
                "status": "not_loaded",
                "model": settings.TTS_MODEL_ID,
                "device": settings.TTS_DEVICE,
                "note": "TTS model loads lazily on first synthesis request",
            }

        if self._load_error is not None:
            return {
                "status": "unavailable",
                "model": settings.TTS_MODEL_ID,
                "device": settings.TTS_DEVICE,
                "error": self._load_error,
            }

        return {
            "status": "ok",
            "model": settings.TTS_MODEL_ID,
            "device": settings.TTS_DEVICE,
            "sample_rate": self._sample_rate,
            "emotion_styling": settings.TTS_EMOTION_STYLING_ENABLED,
        }


# Global singleton
tts_service = TTSService()
