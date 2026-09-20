"""
Unit tests for SenseVoice output tag parsing and normalization.
"""

import pytest
from ai.inference.sensevoice import parse_sensevoice_output


def test_parse_english_happy_speech():
    raw = "<|en|><|HAPPY|><|Speech|><|withitn|>Good morning! How are you today?"
    text, lang, emo, events, debug = parse_sensevoice_output(raw)

    assert text == "Good morning! How are you today?"
    assert lang == "en"
    assert emo == "happy"
    assert events == ["Speech"]
    assert "<|en|>" in debug["raw_tags"]


def test_parse_chinese_neutral_applause():
    raw = "<|zh|><|NEUTRAL|><|Applause|><|Speech|>非常感谢大家的聆听"
    text, lang, emo, events, _ = parse_sensevoice_output(raw)

    assert text == "非常感谢大家的聆听"
    assert lang == "zh"
    assert emo == "neutral"
    assert events == ["Applause", "Speech"]


def test_parse_all_emotions():
    emotions = [
        ("<|HAPPY|>", "happy"),
        ("<|SAD|>", "sad"),
        ("<|ANGRY|>", "angry"),
        ("<|NEUTRAL|>", "neutral"),
        ("<|FEARFUL|>", "fearful"),
        ("<|DISGUSTED|>", "disgusted"),
        ("<|SURPRISED|>", "surprised"),
        ("<|EMO_UNKNOWN|>", None),
        ("<|UNK|>", None),
    ]

    for tag, expected in emotions:
        raw = f"<|en|>{tag}<|Speech|>Test message"
        _, _, emo, _, _ = parse_sensevoice_output(raw)
        assert emo == expected, f"Failed for tag {tag}: expected {expected}, got {emo}"


def test_parse_all_languages():
    languages = [
        ("<|zh|>", "zh"),
        ("<|en|>", "en"),
        ("<|yue|>", "yue"),
        ("<|ja|>", "ja"),
        ("<|ko|>", "ko"),
        ("<|nospeech|>", "unknown"),
    ]

    for tag, expected in languages:
        raw = f"{tag}<|NEUTRAL|><|Speech|>Test"
        _, lang, _, _, _ = parse_sensevoice_output(raw)
        assert lang == expected, f"Failed for tag {tag}: expected {expected}, got {lang}"


def test_parse_events_deduplication():
    raw = "<|en|><|NEUTRAL|><|BGM|><|Speech|><|BGM|>Music playing in background"
    text, _, _, events, _ = parse_sensevoice_output(raw)

    assert text == "Music playing in background"
    assert events == ["BGM", "Speech"]


def test_parse_empty_and_tagless():
    empty_text, empty_lang, empty_emo, empty_events, _ = parse_sensevoice_output("")
    assert empty_text == ""
    assert empty_lang == "unknown"
    assert empty_emo is None
    assert empty_events == []

    plain = "Just plain text without any tags."
    p_text, p_lang, p_emo, p_events, _ = parse_sensevoice_output(plain)
    assert p_text == "Just plain text without any tags."
    assert p_lang == "unknown"
    assert p_emo is None
    assert p_events == []
