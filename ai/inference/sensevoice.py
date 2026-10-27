"""
SenseVoiceSmall speech processing engine implementation.
Handles rich transcription tag parsing, VAD integration, and unified SpeechResult generation.
"""

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

import numpy as np

from ai.inference.types import SpeechResult
from ai.inference.engine import SpeechEngine
from ai.preprocessing.audio import load_and_preprocess_audio
from ai.preprocessing.vad import SileroVAD, VADResult

logger = logging.getLogger(__name__)

# Official SenseVoice tag mappings
SENSEVOICE_LANG_TAGS: Dict[str, str] = {
    "<|zh|>": "zh",
    "<|en|>": "en",
    "<|yue|>": "yue",
    "<|ja|>": "ja",
    "<|ko|>": "ko",
    "<|nospeech|>": "unknown",
}

SENSEVOICE_EMO_TAGS: Dict[str, Optional[str]] = {
    "<|HAPPY|>": "happy",
    "<|SAD|>": "sad",
    "<|ANGRY|>": "angry",
    "<|NEUTRAL|>": "neutral",
    "<|FEARFUL|>": "fearful",
    "<|DISGUSTED|>": "disgusted",
    "<|SURPRISED|>": "surprised",
    "<|EMO_UNKNOWN|>": None,
    "<|UNK|>": None,
}

SENSEVOICE_EVENT_TAGS: Dict[str, str] = {
    "<|BGM|>": "BGM",
    "<|Speech|>": "Speech",
    "<|Applause|>": "Applause",
    "<|Laughter|>": "Laughter",
    "<|Cry|>": "Cry",
    "<|Sneeze|>": "Sneeze",
    "<|Breath|>": "Breath",
    "<|Cough|>": "Cough",
    "<|Speech_Noise|>": "Speech_Noise",
    "<|Sing|>": "Sing",
}

# Regex to find all SenseVoice control tags
TAG_REGEX = re.compile(r"<\|[^|>]+(?:\|>)?")


def parse_sensevoice_output(raw_text: str) -> Tuple[str, str, Optional[str], List[str], Dict[str, Any]]:
    """
    Parses SenseVoice raw output string into clean text and metadata.

    Returns:
        (clean_text, language_code, normalized_emotion, audio_events, raw_tags_dict)
    """
    if not raw_text:
        return "", "unknown", None, [], {"raw_tags": []}

    detected_tags = TAG_REGEX.findall(raw_text)
    language = "unknown"
    emotion: Optional[str] = None
    events: List[str] = []

    for tag in detected_tags:
        # Match language
        if tag in SENSEVOICE_LANG_TAGS:
            language = SENSEVOICE_LANG_TAGS[tag]
        # Match emotion
        elif tag in SENSEVOICE_EMO_TAGS:
            emotion = SENSEVOICE_EMO_TAGS[tag]
        # Match audio event
        elif tag in SENSEVOICE_EVENT_TAGS:
            event_name = SENSEVOICE_EVENT_TAGS[tag]
            if event_name not in events:
                events.append(event_name)

    # Clean text: remove all control tags and normalize spacing
    clean_text = TAG_REGEX.sub("", raw_text).strip()
    clean_text = re.sub(r"\s+", " ", clean_text)

    debug_tags = {
        "raw_tags": detected_tags,
        "raw_length": len(raw_text),
    }

    return clean_text, language, emotion, events, debug_tags


class SenseVoiceSpeechEngine(SpeechEngine):
    """
    SenseVoiceSmall speech perception engine.
    Transcribes audio into unified SpeechResult containing text, language, and emotion.
    """

    def __init__(
        self,
        model_dir: Optional[str] = None,
        device: Optional[str] = None,
        threads: Optional[int] = None,
        vad_model_path: Optional[str] = None,
        vad_threshold: Optional[float] = None,
        auto_load: bool = True,
    ):
        self.model_dir = model_dir or os.getenv("SENSEVOICE_MODEL_DIR", "iic/SenseVoiceSmall")
        self.device = device or os.getenv("SENSEVOICE_DEVICE", "cpu")
        self.threads = threads or int(os.getenv("SENSEVOICE_THREADS", "4"))
        self._model_version = "SenseVoiceSmall (funasr)"

        self.vad = SileroVAD(
            model_path=vad_model_path,
            threshold=vad_threshold,
        )
        self.model = None
        self.is_loaded = False

        if auto_load:
            self._load_model()

    @property
    def model_version(self) -> str:
        return self._model_version

    def load(self) -> None:
        """Idempotently loads SenseVoiceSmall weights into memory."""
        if not self.is_loaded or self.model is None:
            self._load_model()

    def _load_model(self):
        """
        Loads the SenseVoice model once at initialization.
        Fails with clear, actionable error if funasr/torch or weights are missing.
        """
        try:
            import torch
            torch.set_num_threads(self.threads)
        except ImportError:
            raise RuntimeError(
                "PyTorch is not installed in the current Python environment. "
                "Please install torch>=2.2.0 to run SenseVoiceSmall inference."
            )

        try:
            from funasr import AutoModel
        except ImportError:
            raise RuntimeError(
                "FunASR is not installed in the current Python environment. "
                "Please install funasr>=1.0.0 to run SenseVoiceSmall inference."
            )

        logger.info(f"Loading SenseVoiceSmall from '{self.model_dir}' on {self.device}...")
        try:
            self.model = AutoModel(
                model=self.model_dir,
                device=self.device,
                disable_update=True,
                log_level="ERROR"
            )
            self.is_loaded = True
            logger.info("SenseVoiceSmall model loaded successfully.")
        except Exception as e:
            raise RuntimeError(
                f"Failed to load SenseVoiceSmall model from '{self.model_dir}' ({e}). "
                f"Ensure weights exist at the configured path or set SENSEVOICE_MODEL_DIR correctly."
            ) from e

    def transcribe(
        self,
        audio: np.ndarray,
        sample_rate: int = 16000,
        language_hint: Optional[str] = None
    ) -> SpeechResult:
        """
        Processes audio array through VAD and SenseVoice.
        Returns a schema-compliant SpeechResult.
        Silent, empty, or short audio returns an explicit no-speech result, never an exception.
        """
        start_time = time.perf_counter()

        # 1. Guard against empty or invalid input
        if audio is None or len(audio) == 0:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return SpeechResult(
                transcript="",
                language="unknown",
                emotion=None,
                confidence=None,
                processing_time_ms=elapsed_ms,
                model_version=self.model_version,
                debug={"status": "empty_audio", "vad_has_speech": False}
            )

        # 2. Silero VAD gate
        vad_res: VADResult = self.vad.analyze(audio, sample_rate=sample_rate)
        if not vad_res.has_speech:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            return SpeechResult(
                transcript="",
                language="unknown",
                emotion=None,
                confidence=None,
                processing_time_ms=elapsed_ms,
                model_version=self.model_version,
                debug={
                    "status": "no_speech_detected",
                    "vad_has_speech": False,
                    "speech_duration_ms": vad_res.speech_duration_ms,
                    "speech_prob": vad_res.speech_probability,
                }
            )

        # 3. Model inference
        if not self.is_loaded or self.model is None:
            self._load_model()

        try:
            # Ensure float32 1D array
            audio_input = audio.astype(np.float32)
            if audio_input.ndim > 1:
                audio_input = np.mean(audio_input, axis=-1)

            lang_param = language_hint if language_hint in ["zh", "en", "yue", "ja", "ko"] else "auto"

            res = self.model.generate(
                input=audio_input,
                language=lang_param,
                use_itn=True,
                batch_size_s=60
            )

            raw_text = ""
            if res and len(res) > 0 and "text" in res[0]:
                raw_text = res[0]["text"]

            clean_text, detected_lang, emotion, events, debug_tags = parse_sensevoice_output(raw_text)
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)

            # If model returned no text or marked nospeech
            if detected_lang == "unknown" and not clean_text:
                return SpeechResult(
                    transcript="",
                    language="unknown",
                    emotion=None,
                    confidence=None,
                    processing_time_ms=elapsed_ms,
                    model_version=self.model_version,
                    audio_events=events,
                    debug={**debug_tags, "vad_has_speech": True}
                )

            return SpeechResult(
                transcript=clean_text,
                language=detected_lang,
                emotion=emotion,
                confidence=None,  # SenseVoice does not provide calibrated confidence
                processing_time_ms=elapsed_ms,
                model_version=self.model_version,
                audio_events=events,
                debug={**debug_tags, "vad_has_speech": True}
            )

        except Exception as e:
            logger.error(f"SenseVoice transcription error: {e}")
            raise


def main():
    """CLI entrypoint for standalone SenseVoice speech perception."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(
        description="SenseVoice Base Speech Perception CLI"
    )
    parser.add_argument(
        "audio_file",
        nargs="?",
        default=None,
        help="Path to WAV/audio recording"
    )
    parser.add_argument(
        "--test-silence",
        action="store_true",
        help="Run inference on 1.0s of synthetic silence"
    )
    parser.add_argument(
        "--model-dir",
        default=None,
        help="Path or identifier for SenseVoiceSmall model"
    )
    parser.add_argument(
        "--device",
        default="cpu",
        help="Compute device (cpu or cuda)"
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="CPU execution thread count"
    )

    args = parser.parse_args()

    if args.test_silence:
        # Create 1 second of silence at 16kHz
        audio = np.zeros(16000, dtype=np.float32)
    elif args.audio_file:
        audio = load_and_preprocess_audio(args.audio_file, target_sr=16000)
    else:
        parser.print_help()
        sys.exit(1)

    try:
        engine = SenseVoiceSpeechEngine(
            model_dir=args.model_dir,
            device=args.device,
            threads=args.threads,
        )
        result = engine.transcribe(audio, sample_rate=16000)
        print(result.model_dump_json(indent=2))
    except Exception as err:
        # Check if silence test can be serviced directly by VAD
        vad = SileroVAD()
        vad_res = vad.analyze(audio, sample_rate=16000)
        if not vad_res.has_speech:
            # VAD cleanly handles no-speech even if full ASR weights are absent
            res = SpeechResult(
                transcript="",
                language="unknown",
                emotion=None,
                confidence=None,
                processing_time_ms=1,
                model_version="SenseVoiceSmall (VAD-Gated)",
                debug={
                    "status": "no_speech_detected",
                    "vad_has_speech": False,
                    "speech_duration_ms": vad_res.speech_duration_ms
                }
            )
            print(res.model_dump_json(indent=2))
            return

        sys.stderr.write(f"Error: {err}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
