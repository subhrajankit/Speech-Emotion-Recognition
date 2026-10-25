"""
Unit tests for Emotion Inference Engine and architectural isolation.
Verifies schema compliance, probability calibration, audio input types,
and strict absence of LLM, RAG, and TTS dependencies.
"""

import ast
from pathlib import Path
import numpy as np
import pytest

from ai.inference.emotion import Wav2Vec2EmotionEngine, EmotionEngine, EmotionResult
from ai.models.emotion.config import EmotionModelConfig


def test_emotion_engine_interface():
    """Verify Wav2Vec2EmotionEngine implements EmotionEngine."""
    engine = Wav2Vec2EmotionEngine(mock=True)
    assert isinstance(engine, EmotionEngine)

    health = engine.check_health()
    assert health["status"] == "ready"
    assert "neutral" in health["classes"]


def test_emotion_inference_numpy_array():
    """Verify emotion inference from 16kHz float32 NumPy array."""
    engine = Wav2Vec2EmotionEngine(mock=True)
    # 1 second of synthetic 16kHz audio
    audio = np.sin(2 * np.pi * 440 * np.linspace(0, 1, 16000)).astype(np.float32)

    res = engine.classify(audio)
    assert isinstance(res, EmotionResult)
    assert res.primary in ["neutral", "happy", "sad", "angry"]
    assert 0.0 <= res.confidence <= 1.0
    assert len(res.scores) == 4
    # Calibrated probabilities sum to 1.0
    assert sum(res.scores.values()) == pytest.approx(1.0, abs=1e-3)
    assert res.processing_time_ms >= 0.0
    assert isinstance(res.to_dict(), dict)


def test_emotion_inference_pcm_bytes():
    """Verify inference accepts raw PCM16 bytes."""
    engine = Wav2Vec2EmotionEngine(mock=True)
    # 0.5s of 16-bit PCM (16000 samples/sec * 0.5s * 2 bytes/sample = 16000 bytes)
    pcm_bytes = b"\x00\x00" * 8000

    res = engine.classify(pcm_bytes)
    assert isinstance(res, EmotionResult)
    assert res.primary in ["neutral", "happy", "sad", "angry"]
    assert sum(res.scores.values()) == pytest.approx(1.0, abs=1e-3)


def test_emotion_inference_empty_audio():
    """Empty or silent audio returns neutral fallback gracefully."""
    engine = Wav2Vec2EmotionEngine(mock=True)
    empty_arr = np.array([], dtype=np.float32)

    res = engine.classify(empty_arr)
    assert res.primary == "neutral"
    assert res.confidence > 0.0
    assert sum(res.scores.values()) == pytest.approx(1.0, abs=1e-3)


def test_strict_architectural_isolation():
    """
    Architectural Invariant:
    ai/inference/emotion.py must NOT import or depend on Qwen3/LLM, RAG, or TTS.
    """
    file_path = Path("ai/inference/emotion.py")
    assert file_path.exists(), "ai/inference/emotion.py does not exist!"

    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    forbidden_tokens = [
        "llm",
        "qwen",
        "rag",
        "vectorstore",
        "faiss",
        "tts",
        "parler",
        "speech_service",
    ]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                for token in forbidden_tokens:
                    assert token not in alias.name.lower(), (
                        f"Forbidden import '{alias.name}' detected in ai/inference/emotion.py! "
                        f"Emotion engine must remain strictly decoupled from {token}."
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for token in forbidden_tokens:
                assert token not in module.lower(), (
                    f"Forbidden import from '{module}' detected in ai/inference/emotion.py! "
                    f"Emotion engine must remain strictly decoupled from {token}."
                )
