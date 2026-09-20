import pytest
from src.backend.asr.router import LanguageRouter, AudioContext, detect_script, evaluate_hinglish_heuristic
from src.backend.asr.indicconformer import IndicConformerASR
from src.backend.models.asr import SenseVoiceASR

@pytest.fixture
def router():
    sensevoice = SenseVoiceASR(mock=True)
    indicconformer = IndicConformerASR(mock=True)
    return LanguageRouter(sensevoice_asr=sensevoice, indic_conformer=indicconformer)

def test_script_detection():
    assert detect_script("Hello world") == "latin"
    assert detect_script("नमस्ते भारत") == "devanagari"
    assert detect_script("你好世界") == "hanzi"
    assert detect_script("こんにちは") == "japanese"
    assert detect_script("안녕하세요") == "hangul"

def test_route_english_sentence(router):
    english_transcript = "Hello, what is the weather today?"
    ctx = router.route_transcript(english_transcript, detected_lang="en", confidence=0.95)

    assert ctx.language == "en"
    assert ctx.script == "latin"
    assert ctx.mixed_language is False
    assert ctx.model_used == "sensevoice"
    assert ctx.transcript == english_transcript

def test_route_hindi_sentence(router):
    hindi_transcript = "नमस्ते, आज का मौसम कैसा है?"
    ctx = router.route_transcript(hindi_transcript, detected_lang="hi", confidence=0.92)

    assert ctx.language == "hi"
    assert ctx.script == "devanagari"
    assert ctx.mixed_language is False
    assert ctx.model_used == "indicconformer"
    assert ctx.transcript == hindi_transcript

def test_route_hinglish_sentence(router):
    hinglish_transcript = "bhai what is the plan aaj ka?"
    ctx = router.route_transcript(hinglish_transcript, detected_lang="en", confidence=0.70)

    assert ctx.language == "hinglish"
    assert ctx.script == "latin"
    assert ctx.mixed_language is True
    assert ctx.model_used == "hinglish_heuristic"
    assert ctx.transcript == hinglish_transcript

def test_hinglish_heuristic_variations():
    # Another Hinglish example: mixing Hindi interrogatives with English vocabulary
    sample_1 = "kya weather today accha hai?"
    is_mixed, ctx = evaluate_hinglish_heuristic(sample_1, confidence=0.65)
    assert is_mixed is True
    assert ctx.language == "hinglish"
    assert ctx.script == "latin"
    assert ctx.mixed_language is True

    # Pure English should NOT be tagged as Hinglish
    sample_2 = "Please play some music for me"
    is_mixed, _ = evaluate_hinglish_heuristic(sample_2, confidence=0.95)
    assert is_mixed is False
