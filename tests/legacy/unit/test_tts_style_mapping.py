import io
import pytest
import soundfile as sf
from src.backend.emotion.emotion import EmotionState
from src.backend.tts.indic_parler import (
    EMOTION_STYLE_MAPPING,
    DEFAULT_STYLE,
    get_tts_style_description,
    IndicParlerTTS
)

def test_emotion_style_mapping_table_keys():
    """Verify that all core Phase 5 emotions exist in the style mapping table."""
    expected_emotions = ["neutral", "sad", "happy", "angry", "fearful", "disgusted", "surprised", "excited"]
    for emotion in expected_emotions:
        assert emotion in EMOTION_STYLE_MAPPING, f"Missing style mapping for emotion: {emotion}"
        assert isinstance(EMOTION_STYLE_MAPPING[emotion], str)
        assert len(EMOTION_STYLE_MAPPING[emotion]) > 10

def test_prompt_specified_style_descriptions():
    """
    Verify the specific prompt requirements:
    - sad -> slow, calm, gentle
    - happy -> energetic, bright, faster
    - angry -> calm, slow, de-escalating
    """
    sad_style = EMOTION_STYLE_MAPPING["sad"].lower()
    assert "slow" in sad_style
    assert "calm" in sad_style
    assert "gentle" in sad_style

    happy_style = EMOTION_STYLE_MAPPING["happy"].lower()
    assert "energetic" in happy_style
    assert "bright" in happy_style
    assert "faster" in happy_style

    angry_style = EMOTION_STYLE_MAPPING["angry"].lower()
    assert "calm" in angry_style
    assert "slow" in angry_style
    assert "de-escalating" in angry_style

def test_get_tts_style_description_with_emotion_state():
    """Verify get_tts_style_description correctly extracts style from EmotionState."""
    state_sad = EmotionState(
        primary="sad",
        confidence=0.9,
        valence=-0.7,
        arousal=-0.4,
        lexical_polarity=-0.5
    )
    desc_sad = get_tts_style_description(state_sad)
    assert desc_sad == EMOTION_STYLE_MAPPING["sad"]

    state_angry = EmotionState(
        primary="angry",
        confidence=0.85,
        valence=-0.6,
        arousal=0.8,
        lexical_polarity=-0.7
    )
    desc_angry = get_tts_style_description(state_angry)
    assert desc_angry == EMOTION_STYLE_MAPPING["angry"]

def test_get_tts_style_description_variations():
    """Verify dictionary, string, None, and unknown emotion handling."""
    # Dict
    desc_happy = get_tts_style_description({"primary": "happy"})
    assert desc_happy == EMOTION_STYLE_MAPPING["happy"]

    # String
    desc_fearful = get_tts_style_description("fearful")
    assert desc_fearful == EMOTION_STYLE_MAPPING["fearful"]

    # None -> fallback to default neutral
    desc_none = get_tts_style_description(None)
    assert desc_none == DEFAULT_STYLE

    # Unknown label -> fallback to default neutral
    desc_unknown = get_tts_style_description("mysterious")
    assert desc_unknown == DEFAULT_STYLE

    # Explicit custom style override
    custom = "A deep whispered voice."
    desc_custom = get_tts_style_description("happy", custom_style=custom)
    assert desc_custom == custom

def test_indic_parler_synthesize_wav_with_emotion_mock():
    """Verify that synthesize_wav works with emotion styling in mock/fallback mode."""
    tts = IndicParlerTTS(mock=True)
    state = EmotionState(
        primary="happy",
        confidence=0.95,
        valence=0.8,
        arousal=0.6,
        lexical_polarity=0.8
    )

    wav_bytes = tts.synthesize_wav("Great job!", emotion=state)
    assert isinstance(wav_bytes, bytes)
    assert len(wav_bytes) > 44

    wav_io = io.BytesIO(wav_bytes)
    data, sample_rate = sf.read(wav_io)
    assert sample_rate == 16000
    assert len(data) > 0
