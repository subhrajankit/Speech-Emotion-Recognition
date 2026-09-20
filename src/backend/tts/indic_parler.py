"""
Indic Parler-TTS with Emotion Style Conditioning.
Translates acoustic and text emotion states from Phase 5 into natural
voice delivery style prompts for Indic Parler-TTS.
"""
import io
import logging
import numpy as np
import soundfile as sf
from typing import Optional, Dict, Any, Union

logger = logging.getLogger(__name__)

# Configurable Emotion-to-Voice Delivery Style Mapping Table
# Maps detected user emotional state to Parler-TTS prompt style descriptions.
# Designed for empathy and conversational de-escalation.
EMOTION_STYLE_MAPPING: Dict[str, str] = {
    "neutral": "A clean, clear voice with natural, balanced delivery and moderate pace.",
    "sad": "A soft, gentle voice with slow, calm, gentle, and empathetic delivery.",
    "happy": "An energetic, bright, faster voice with cheerful and lively delivery.",
    "angry": "A calm, slow, de-escalating, and soothing voice with reassuring delivery.",
    "fearful": "A warm, comforting voice with gentle, steady, and reassuring delivery.",
    "disgusted": "A neutral, professional, and composed voice with polite delivery.",
    "surprised": "An attentive, clear voice with engaging and slightly upbeat delivery.",
    "excited": "An energetic, lively, faster voice with dynamic and enthusiastic delivery."
}

DEFAULT_STYLE = EMOTION_STYLE_MAPPING["neutral"]


def get_tts_style_description(
    emotion: Optional[Union[str, Dict[str, Any], Any]] = None,
    custom_style: Optional[str] = None
) -> str:
    """
    Derives an Indic Parler-TTS style description string based on user emotion.
    
    Args:
        emotion: Can be an EmotionState dataclass, a dict with 'primary', a string label, or None.
        custom_style: If explicitly provided, overrides the table lookup.
    
    Returns:
        A style description string suitable for Parler-TTS prompt conditioning.
    """
    if custom_style:
        return custom_style

    if emotion is None:
        return DEFAULT_STYLE

    # Extract primary emotion string
    primary_label = ""
    if hasattr(emotion, "primary"):
        primary_label = str(emotion.primary).lower()
    elif isinstance(emotion, dict):
        primary_label = str(emotion.get("primary", "")).lower()
    elif isinstance(emotion, str):
        primary_label = emotion.lower()

    if not primary_label:
        return DEFAULT_STYLE

    return EMOTION_STYLE_MAPPING.get(primary_label, DEFAULT_STYLE)


class IndicParlerTTS:
    """
    Indic Parler-TTS Service with Emotion Style Conditioning.
    Loaded once at startup as a singleton.
    Synthesizes speech to PCM/WAV format conditioned on emotion delivery prompts.
    """
    def __init__(
        self,
        model_id: str = "ai4bharat/indic-parler-tts",
        device: str = "cpu",
        mock: bool = False,
        max_retries: int = 2,
        backoff_ms: float = 50.0
    ):
        self.model_id = model_id
        self.device = device
        self.mock = mock
        self.max_retries = max_retries
        self.backoff_ms = backoff_ms
        self.model = None
        self.tokenizer = None
        self.description_tokenizer = None
        self.sample_rate = 24000
        self.is_loaded = False
        self._load_model()

    def _load_model(self):
        if self.mock:
            logger.info("Initializing IndicParlerTTS in MOCK mode.")
            self.is_loaded = True
            return

        try:
            from transformers import AutoTokenizer
            from parler_tts import ParlerTTSForConditionalGeneration

            logger.info(f"Loading Indic Parler-TTS model from {self.model_id} on {self.device}...")
            self.tokenizer = AutoTokenizer.from_pretrained(self.model_id)
            self.model = ParlerTTSForConditionalGeneration.from_pretrained(self.model_id)
            self.model.to(self.device)
            self.sample_rate = getattr(self.model.config, "sampling_rate", 24000)
            self.is_loaded = True
            logger.info("Indic Parler-TTS loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load real Indic Parler-TTS ({e}). Falling back to synthesized tone/mock mode.")
            self.is_loaded = False

    def synthesize_wav(
        self,
        text: str,
        emotion: Optional[Any] = None,
        description: Optional[str] = None
    ) -> bytes:
        """
        Synthesizes text into a standard WAV byte stream conditioned on emotion style.
        Includes bounded retry-with-backoff on neural synthesis errors before failing
        fast to harmonic tone fallback.
        """
        if not text:
            text = "I have nothing to say."

        style_prompt = get_tts_style_description(emotion=emotion, custom_style=description)

        if self.mock or self.model is None or self.tokenizer is None:
            return self._generate_fallback_audio_wav(text, style_prompt=style_prompt, emotion=emotion)

        import time
        for attempt in range(self.max_retries + 1):
            try:
                import torch
                input_ids = self.tokenizer(style_prompt, return_tensors="pt").input_ids.to(self.device)
                prompt_input_ids = self.tokenizer(text, return_tensors="pt").input_ids.to(self.device)

                with torch.no_grad():
                    generation = self.model.generate(
                        input_ids=input_ids,
                        prompt_input_ids=prompt_input_ids
                    )

                audio_arr = generation.cpu().numpy().squeeze()
                wav_buffer = io.BytesIO()
                sf.write(wav_buffer, audio_arr, self.sample_rate, format='WAV', subtype='PCM_16')
                wav_buffer.seek(0)
                return wav_buffer.read()
            except Exception as e:
                if attempt < self.max_retries:
                    logger.warning(f"Indic Parler-TTS attempt {attempt + 1}/{self.max_retries + 1} failed ({e}). Retrying in {self.backoff_ms}ms...")
                    time.sleep(self.backoff_ms / 1000.0)
                else:
                    logger.error(f"Indic Parler-TTS synthesis failed after {self.max_retries + 1} attempts ({e}). Failing fast to synthesized fallback audio.")
                    return self._generate_fallback_audio_wav(text, style_prompt=style_prompt, emotion=emotion)

    def _generate_fallback_audio_wav(
        self,
        text: str,
        style_prompt: str = "",
        emotion: Optional[Any] = None
    ) -> bytes:
        """
        Generates harmonic tone sequences modulated by emotion style
        when real neural model weights are not loaded locally.
        """
        sample_rate = 16000
        duration = min(max(0.5, len(text) * 0.02), 1.6)

        # Modulate frequency and envelope by emotion style
        prim = ""
        if hasattr(emotion, "primary"):
            prim = str(emotion.primary).lower()
        elif isinstance(emotion, dict):
            prim = str(emotion.get("primary", "")).lower()
        elif isinstance(emotion, str):
            prim = emotion.lower()

        if prim == "happy" or "bright" in style_prompt:
            base_freq, harmonic_freq = 523.25, 659.25  # C5 + E5 (bright major third)
            duration *= 0.85  # slightly faster pace
        elif prim == "sad" or "slow, calm, gentle" in style_prompt:
            base_freq, harmonic_freq = 329.63, 392.00  # E4 + G4 (soft minor third)
            duration *= 1.25  # slower pace
        elif prim == "angry" or "de-escalating" in style_prompt:
            base_freq, harmonic_freq = 349.23, 440.00  # F4 + A4 (calm, warm low chord)
            duration *= 1.15  # calm, steady pace
        else:
            base_freq, harmonic_freq = 440.00, 660.00  # standard A4 + E5

        t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
        envelope = np.exp(-2.8 * t / duration)
        signal = 0.3 * np.sin(2 * np.pi * base_freq * t) + 0.2 * np.sin(2 * np.pi * harmonic_freq * t)
        audio = (signal * envelope).astype(np.float32)

        wav_buffer = io.BytesIO()
        sf.write(wav_buffer, audio, sample_rate, format='WAV', subtype='PCM_16')
        wav_buffer.seek(0)
        return wav_buffer.read()
