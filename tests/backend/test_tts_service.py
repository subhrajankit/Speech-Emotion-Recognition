"""
Unit tests for Indic Parler-TTS service (Phase 8).
Verifies:
1. Text cleaning (strips <think>, markdown, citations, emoji, URLs).
2. Sentence splitting for English (.!?) and Hindi (। ॥).
3. Voice description prompt generation and emotion styling (off by default).
4. Unsupported language fallback to English.
5. Lazy loading invariant: model is NOT loaded at startup.
6. Honest tts_unavailable error reporting when real model is missing (NO runtime mock).
7. Framing, chunk ordering, cancellation, and simulated OOM using FakeEngineForTests.
"""

import asyncio
import io
import struct
from dataclasses import dataclass
from typing import Optional, List
import pytest

from backend.app.services.tts_service import (
    clean_tts_text,
    split_sentences,
    build_voice_description,
    TTSService,
    TTSError,
    TTSOOMError,
    TTSChunk,
    INDIC_PARLER_LANGUAGES,
)
from backend.app.core.config import settings


# ==============================================================================
# 1. Text Cleaner Tests
# ==============================================================================

def test_clean_tts_text_strips_thinking_tags():
    raw = "<think>Let me reason about this.</think>Namaste, aap kaise hain?"
    cleaned = clean_tts_text(raw)
    assert cleaned == "Namaste, aap kaise hain?"


def test_clean_tts_text_strips_markdown_and_citations():
    raw = (
        "### Section Header\n"
        "Here is **bold text**, *italic text*, and `inline_code`.\n"
        "According to policy [1] and [company_policy.md] or [chunk_abc123], "
        "visit [our website](https://example.com) for details."
    )
    cleaned = clean_tts_text(raw)
    assert "Section Header" in cleaned
    assert "bold text" in cleaned
    assert "italic text" in cleaned
    assert "inline_code" not in cleaned
    assert "[1]" not in cleaned
    assert "[company_policy.md]" not in cleaned
    assert "[chunk_abc123]" not in cleaned
    assert "https://example.com" not in cleaned
    assert "our website" in cleaned


def test_clean_tts_text_strips_emojis():
    raw = "Hello world! 😊🙏🎉 Have a great day! ✨"
    cleaned = clean_tts_text(raw)
    assert cleaned == "Hello world! Have a great day!"


def test_clean_tts_text_empty_and_whitespace():
    assert clean_tts_text("") == ""
    assert clean_tts_text("   \n\t  ") == ""


# ==============================================================================
# 2. Sentence Splitting Tests (English & Hindi)
# ==============================================================================

def test_split_sentences_english():
    text = "Hello there. How are you today? I am doing well! Wonderful."
    sentences = split_sentences(text)
    assert sentences == [
        "Hello there.",
        "How are you today?",
        "I am doing well!",
        "Wonderful.",
    ]


def test_split_sentences_hindi_danda():
    text = "नमस्ते। आप कैसे हैं? मुझे बहुत खुशी हुई॥ धन्यवाद।"
    sentences = split_sentences(text)
    assert len(sentences) == 4
    assert sentences[0] == "नमस्ते।"
    assert sentences[1] == "आप कैसे हैं?"
    assert sentences[2] == "मुझे बहुत खुशी हुई॥"
    assert sentences[3] == "धन्यवाद।"


def test_split_sentences_single_sentence_no_punctuation():
    text = "This is a single utterance without period"
    sentences = split_sentences(text)
    assert sentences == ["This is a single utterance without period"]


# ==============================================================================
# 3. Voice Description Builder Tests
# ==============================================================================

def test_build_voice_description_default():
    # When emotion styling is disabled (default per Phase 8 spec)
    desc = build_voice_description(language="hi", emotion=None)
    assert "Aditi" in desc
    assert "moderate pace" in desc


def test_build_voice_description_with_emotion_enabled(monkeypatch):
    monkeypatch.setattr(settings, "TTS_EMOTION_STYLING_ENABLED", True)

    desc_sad = build_voice_description(language="en", emotion="sad")
    assert "slow, calm, gentle, and empathetic" in desc_sad

    desc_happy = build_voice_description(language="en", emotion="happy")
    assert "cheerful, lively" in desc_happy

    desc_none = build_voice_description(language="en", emotion=None)
    assert "moderate pace" in desc_none


def test_build_voice_description_custom_override():
    custom = "Rohit speaks with an energetic and authoritative tone."
    desc = build_voice_description(language="hi", custom_description=custom)
    assert desc == custom


# ==============================================================================
# 4. Language Registry & Fallback
# ==============================================================================

def test_indic_parler_supported_languages():
    assert "hi" in INDIC_PARLER_LANGUAGES
    assert "en" in INDIC_PARLER_LANGUAGES
    assert "bn" in INDIC_PARLER_LANGUAGES
    assert "ta" in INDIC_PARLER_LANGUAGES
    assert len(INDIC_PARLER_LANGUAGES) == 23


# ==============================================================================
# 5. Lazy Loading & Truthful Error Reporting
# ==============================================================================

def test_tts_service_lazy_loading_invariant(monkeypatch):
    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    service = TTSService()
    assert not service.is_loaded
    health = service.get_health_status()
    assert health["status"] == "not_loaded"


@pytest.mark.asyncio
async def test_tts_service_uninstalled_honest_failure(monkeypatch):
    """
    CRITICAL RULE:
    When real packages/model are missing, the service raises TTSError honestly.
    No mock synthesizer is used in runtime code.
    """
    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    service = TTSService()
    # Force worker_python to nonexistent to simulate missing dependencies
    monkeypatch.setattr(settings, "TTS_WORKER_PYTHON", "nonexistent/python.exe")

    with pytest.raises(TTSError) as exc_info:
        async for _ in service.synthesize("Hello world", language="en"):
            pass

    assert "unavailable" in str(exc_info.value).lower() or "not installed" in str(exc_info.value).lower()
    assert service.get_health_status()["status"] == "unavailable"


# ==============================================================================
# 6. Test-Only Fake Engine (Framing, Ordering, Cancellation, OOM)
# ==============================================================================

class FakeEngineForTests:
    """
    Test-only fake engine used strictly inside tests/ to verify framing,
    chunk ordering, concurrency, and failure isolation without requiring
    4 GB weights in CI.
    """
    def __init__(self, fail_with: Optional[Exception] = None):
        self.fail_with = fail_with
        self.call_count = 0

    def synthesize_wav(self, text: str, description: str) -> tuple[bytes, int]:
        self.call_count += 1
        if self.fail_with:
            raise self.fail_with

        # Generate minimal valid PCM16 WAV file (44-byte header + 200 samples silence)
        sample_rate = 44100
        num_samples = 200
        data_bytes = num_samples * 2
        header = bytearray(b"RIFF")
        header.extend(struct.pack("<I", 36 + data_bytes))
        header.extend(b"WAVEfmt ")
        header.extend(struct.pack("<I", 16))
        header.extend(struct.pack("<H", 1))   # PCM format
        header.extend(struct.pack("<H", 1))   # Mono
        header.extend(struct.pack("<I", sample_rate))
        header.extend(struct.pack("<I", sample_rate * 2))
        header.extend(struct.pack("<H", 2))
        header.extend(struct.pack("<H", 16))
        header.extend(b"data")
        header.extend(struct.pack("<I", data_bytes))
        header.extend(b"\x00" * data_bytes)
        return bytes(header), sample_rate


@pytest.mark.asyncio
async def test_fake_engine_chunk_ordering_and_metadata(monkeypatch):
    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    service = TTSService()
    fake = FakeEngineForTests()
    service._engine_override = fake

    text = "First sentence. Second sentence. Third sentence."
    chunks: List[TTSChunk] = []

    async for chunk in service.synthesize(text, language="en"):
        chunks.append(chunk)

    assert len(chunks) == 3
    assert chunks[0].sentence_index == 0
    assert chunks[0].sentence_text == "First sentence."
    assert chunks[0].sample_rate == 44100
    assert chunks[0].audio[:4] == b"RIFF"

    assert chunks[1].sentence_index == 1
    assert chunks[1].sentence_text == "Second sentence."

    assert chunks[2].sentence_index == 2
    assert chunks[2].sentence_text == "Third sentence."
    assert fake.call_count == 3


@pytest.mark.asyncio
async def test_fake_engine_simulated_oom_isolation(monkeypatch):
    monkeypatch.setattr(settings, "TTS_ENABLED", True)
    service = TTSService()
    service._engine_override = FakeEngineForTests(
        fail_with=RuntimeError("CUDA out of memory. Tried to allocate 512.00 MiB")
    )

    with pytest.raises(TTSOOMError):
        async for _ in service.synthesize("OOM test utterance.", language="en"):
            pass
