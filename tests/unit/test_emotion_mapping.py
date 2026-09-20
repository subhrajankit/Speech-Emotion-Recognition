import os
import pytest
from src.backend.emotion.emotion import (
    SENSEVOICE_EMOTION_COORDINATES,
    calculate_lexical_polarity,
    extract_sensevoice_emotion_label,
    EmotionAnalyzer,
    EmotionState
)
from src.backend.llm.prompts import (
    format_qwen_chat_messages,
    format_qwen_prompt,
    QWEN_SYSTEM_PROMPT
)
from src.backend.database.storage import EmotionStorage

def test_sensevoice_emotion_coordinates():
    """Verify coordinate lookup table for SenseVoice emotion labels."""
    expected_emotions = ["neutral", "happy", "sad", "angry", "fearful", "disgusted", "surprised", "excited"]
    for emo in expected_emotions:
        assert emo in SENSEVOICE_EMOTION_COORDINATES
        valence, arousal = SENSEVOICE_EMOTION_COORDINATES[emo]
        assert -1.0 <= valence <= 1.0
        assert -1.0 <= arousal <= 1.0

    # Specific affect quadrant checks (Russell's circumplex model)
    assert SENSEVOICE_EMOTION_COORDINATES["neutral"] == (0.0, 0.0)
    assert SENSEVOICE_EMOTION_COORDINATES["happy"][0] > 0.5   # positive valence
    assert SENSEVOICE_EMOTION_COORDINATES["sad"][0] < -0.5     # negative valence
    assert SENSEVOICE_EMOTION_COORDINATES["angry"][1] > 0.5   # high arousal

def test_extract_sensevoice_emotion_label():
    """Verify stripping and normalization of SenseVoice SER tags."""
    assert extract_sensevoice_emotion_label("<|HAPPY|>") == "happy"
    assert extract_sensevoice_emotion_label("<|sad|>") == "sad"
    assert extract_sensevoice_emotion_label("ANGRY") == "angry"
    assert extract_sensevoice_emotion_label("<|NEUTRAL|>") == "neutral"
    assert extract_sensevoice_emotion_label("<|unknown_tag|>") == "neutral"
    assert extract_sensevoice_emotion_label("") == "neutral"

def test_calculate_lexical_polarity():
    """Verify quick lexicon-based sentiment analysis."""
    pos_text = "I am so happy, this is wonderful and great!"
    assert calculate_lexical_polarity(pos_text) > 0.5

    neg_text = "This is terrible, completely broken and useless."
    assert calculate_lexical_polarity(neg_text) < -0.5

    neutral_text = "Set a timer for 10 minutes in the kitchen."
    assert calculate_lexical_polarity(neutral_text) == 0.0

    # Hindi / Hinglish lexical sentiment checks
    hinglish_pos = "Ye bahut accha aur badhiya hai, shukriya!"
    assert calculate_lexical_polarity(hinglish_pos) > 0.0

    hinglish_neg = "Ye bahut kharab aur ganda hai, main pareshan hoon."
    assert calculate_lexical_polarity(hinglish_neg) < 0.0

def test_emotion_analyzer_fusion():
    """Verify acoustic SER and lexical text polarity fusion."""
    analyzer = EmotionAnalyzer()

    # 1. Pure acoustic emotion with neutral text
    state_happy = analyzer.analyze(raw_emotion="<|HAPPY|>", confidence=0.9, transcript="Turn on the desk lamp.")
    assert state_happy.primary == "happy"
    assert state_happy.confidence == 0.9
    assert state_happy.valence > 0.4
    assert state_happy.arousal > 0.4

    # 2. Acoustic neutral modulated by strongly positive text
    state_pos_shift = analyzer.analyze(raw_emotion="neutral", confidence=0.8, transcript="Thank you so much, amazing job!")
    assert state_pos_shift.primary == "happy"
    assert state_pos_shift.valence > 0.3

    # 3. Acoustic neutral modulated by strongly negative text
    state_neg_shift = analyzer.analyze(raw_emotion="neutral", confidence=0.8, transcript="I am really frustrated and upset.")
    assert state_neg_shift.primary == "sad"
    assert state_neg_shift.valence < -0.3

    # 4. Acoustic sad fused with slightly positive words
    state_sad_fused = analyzer.analyze(raw_emotion="sad", confidence=0.85, transcript="I hope things get better, thank you.")
    assert state_sad_fused.primary == "sad"
    assert state_sad_fused.valence < 0.0

def test_qwen_prompt_formatting():
    """Verify structured context injection into Qwen3 prompt template."""
    emotion = EmotionState(
        primary="frustrated",
        confidence=0.88,
        valence=-0.6,
        arousal=0.7,
        lexical_polarity=-0.5
    )
    messages = format_qwen_chat_messages(
        transcript="Why is the internet connection failing again?",
        emotion=emotion,
        language="en",
        mixed_language=False
    )

    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert "empathetic" in messages[0]["content"].lower()
    assert "concise" in messages[0]["content"].lower()
    assert "no reasoning chains" in messages[0]["content"].lower()

    assert messages[1]["role"] == "user"
    assert "frustrated" in messages[1]["content"]
    assert "valence=-0.60" in messages[1]["content"]
    assert "Why is the internet connection failing again?" in messages[1]["content"]

    raw_prompt = format_qwen_prompt(
        transcript="Why is the internet connection failing again?",
        emotion=emotion,
        language="en"
    )
    assert "<|im_start|>system" in raw_prompt
    assert "<|im_start|>user" in raw_prompt
    assert "<|im_start|>assistant" in raw_prompt

def test_emotion_storage_sqlite(tmp_path):
    """Verify persistence of emotion history in SQLite database."""
    test_db = str(tmp_path / "test_emotion.db")
    storage = EmotionStorage(db_path=test_db)

    # Insert events across two conversations
    row1 = storage.save_emotion_event(
        conversation_id="conv_123",
        primary_emotion="happy",
        confidence=0.92,
        valence=0.75,
        arousal=0.60,
        raw_transcript="I am having a wonderful day!"
    )
    assert row1 > 0

    row2 = storage.save_emotion_event(
        conversation_id="conv_123",
        primary_emotion="neutral",
        confidence=0.80,
        valence=0.05,
        arousal=0.10,
        raw_transcript="What is the time right now?"
    )
    assert row2 > 0

    row3 = storage.save_emotion_event(
        conversation_id="conv_999",
        primary_emotion="angry",
        confidence=0.85,
        valence=-0.60,
        arousal=0.80,
        raw_transcript="This is unacceptable!"
    )
    assert row3 > 0

    # Retrieve history for conv_123
    history = storage.get_history(conversation_id="conv_123", limit=10)
    assert len(history) == 2
    # Latest first
    assert history[0]["primary_emotion"] == "neutral"
    assert history[0]["raw_transcript"] == "What is the time right now?"
    assert history[1]["primary_emotion"] == "happy"
    assert history[1]["confidence"] == 0.92

    # Verify isolation from other conversations
    history_999 = storage.get_history(conversation_id="conv_999", limit=10)
    assert len(history_999) == 1
    assert history_999[0]["primary_emotion"] == "angry"
