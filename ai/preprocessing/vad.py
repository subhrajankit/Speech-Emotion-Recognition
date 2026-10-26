"""
Silero VAD v5 ONNX implementation with configurable thresholds and durations.
Guarantees explicit no-speech results for empty, silent, or sub-second audio.
"""

import collections
import logging
import os
from dataclasses import dataclass
from typing import Optional, List, Tuple
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VADResult:
    """Explicit VAD classification outcome."""
    has_speech: bool
    speech_probability: float
    speech_duration_ms: float
    num_speech_frames: int


class SileroVAD:
    """
    Wrapper for Silero VAD v5 ONNX model.
    Processes 16kHz audio in 512-sample (32ms) frames with 64-sample context.
    Configurable via environment variables or constructor arguments.
    """
    def __init__(
        self,
        model_path: Optional[str] = None,
        threshold: Optional[float] = None,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 700,
    ):
        self.model_path = model_path or os.getenv("SILERO_VAD_MODEL_PATH", "models/silero_vad.onnx")
        self.threshold = threshold if threshold is not None else float(os.getenv("SILERO_VAD_THRESHOLD", "0.5"))
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms

        self.session = None
        self.context_size = 64
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, self.context_size), dtype=np.float32)
        self.sr = np.array(16000, dtype=np.int64)
        self.is_loaded = False
        self._load_model()

    def _load_model(self):
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(
                f"Silero VAD ONNX model not found at '{self.model_path}'. "
                "Ensure models/silero_vad.onnx is present."
            )

        try:
            import onnxruntime as ort
            opts = ort.SessionOptions()
            opts.inter_op_num_threads = 1
            opts.intra_op_num_threads = 1
            self.session = ort.InferenceSession(self.model_path, sess_options=opts, providers=['CPUExecutionProvider'])
            self.is_loaded = True
            logger.info(f"Silero VAD ONNX loaded successfully from {self.model_path}.")
        except Exception as e:
            logger.warning(f"Could not load Silero VAD ONNX model ({e}). Using energy fallback.")
            self.is_loaded = False

    def reset(self):
        """Resets the RNN hidden state and context."""
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, self.context_size), dtype=np.float32)

    def process_frame(self, frame_samples: np.ndarray) -> float:
        """
        Processes exactly 512 samples of float32 audio at 16kHz.
        Returns speech probability between 0.0 and 1.0.
        """
        if len(frame_samples) != 512:
            raise ValueError(f"Silero VAD requires exactly 512 samples per frame, received {len(frame_samples)}")

        # Energy-based speech approximation only if session failed to load
        if self.session is None:
            rms = float(np.sqrt(np.mean(np.square(frame_samples))))
            return 1.0 if rms > 0.015 else 0.0

        try:
            x = frame_samples.reshape(1, -1).astype(np.float32)
            # Silero v5 concatenates 64 preceding context samples: [1, 64 + 512] = [1, 576]
            inp = np.concatenate([self.context, x], axis=1)
            outputs = self.session.run(None, {
                'input': inp,
                'state': self.state,
                'sr': self.sr
            })
            prob = float(np.squeeze(outputs[0]))
            self.state = outputs[1]
            self.context = inp[:, -self.context_size:]
            return prob
        except Exception as e:
            logger.error(f"Silero VAD inference error: {e}")
            rms = float(np.sqrt(np.mean(np.square(frame_samples))))
            return 1.0 if rms > 0.015 else 0.0

    def analyze(self, audio: np.ndarray, sample_rate: int = 16000) -> VADResult:
        """
        Analyzes a full audio buffer.
        Empty, silent, or sub-minimum duration audio returns an explicit
        VADResult(has_speech=False, ...), never an exception.
        """
        if audio is None or len(audio) == 0:
            return VADResult(
                has_speech=False,
                speech_probability=0.0,
                speech_duration_ms=0.0,
                num_speech_frames=0
            )

        # Minimum sample requirement: at least 1 frame (512 samples, 32ms)
        frame_size = 512
        if len(audio) < frame_size:
            return VADResult(
                has_speech=False,
                speech_probability=0.0,
                speech_duration_ms=0.0,
                num_speech_frames=0
            )

        # Check total duration against minimum speech duration
        duration_ms = (len(audio) / sample_rate) * 1000.0
        if duration_ms < self.min_speech_duration_ms:
            return VADResult(
                has_speech=False,
                speech_probability=0.0,
                speech_duration_ms=0.0,
                num_speech_frames=0
            )

        self.reset()
        num_frames = len(audio) // frame_size
        speech_frames = 0
        probabilities: List[float] = []

        # Ensure float32 in [-1.0, 1.0]
        if np.issubdtype(audio.dtype, np.integer):
            samples = audio.astype(np.float32) / float(np.iinfo(audio.dtype).max)
        else:
            samples = audio.astype(np.float32)

        for i in range(num_frames):
            frame = samples[i * frame_size : (i + 1) * frame_size]
            prob = self.process_frame(frame)
            probabilities.append(prob)
            if prob >= self.threshold:
                speech_frames += 1

        speech_duration_ms = (speech_frames * frame_size / sample_rate) * 1000.0
        has_speech = speech_duration_ms >= self.min_speech_duration_ms
        avg_prob = float(np.mean(probabilities)) if probabilities else 0.0

        return VADResult(
            has_speech=has_speech,
            speech_probability=round(avg_prob, 3),
            speech_duration_ms=round(speech_duration_ms, 1),
            num_speech_frames=speech_frames
        )

    def classify_buffer(self, pcm_bytes: bytes, threshold: Optional[float] = None) -> bool:
        """
        Classifies an entire audio buffer (raw PCM 16kHz mono).
        Returns True if speech was detected in any frame.
        """
        if not pcm_bytes:
            return False

        th = threshold if threshold is not None else self.threshold
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        
        self.reset()
        frame_size = 512
        num_frames = len(samples) // frame_size
        
        if num_frames == 0:
            return False

        for i in range(num_frames):
            frame = samples[i * frame_size : (i + 1) * frame_size]
            prob = self.process_frame(frame)
            if prob >= th:
                return True
                
        return False


class VADSpeechSegmenter:
    """
    Stream segmenter that accumulates incoming PCM16 audio chunks,
    runs VAD, and detects a complete speech utterance:
      Speech Start -> Active Speech -> Silence Timeout -> Speech End.
    """
    def __init__(
        self,
        vad: SileroVAD,
        silence_timeout_ms: int = 700,
        speech_threshold: float = 0.5,
        sample_rate: int = 16000,
        pre_padding_ms: int = 250
    ):
        self.vad = vad
        self.silence_timeout_ms = silence_timeout_ms
        self.speech_threshold = speech_threshold
        self.sample_rate = sample_rate

        self.frame_size = 512  # 32ms at 16kHz
        self.frame_bytes = self.frame_size * 2  # 1024 bytes per frame

        # Pre-speech buffer ring to preserve initial consonants
        max_pre_frames = max(1, int((pre_padding_ms / 1000.0) * sample_rate / self.frame_size))
        self.pre_buffer = collections.deque(maxlen=max_pre_frames)

        self.silence_frames_threshold = int((silence_timeout_ms / 1000.0) * (sample_rate / self.frame_size))

        self.in_speech = False
        self.silence_frames_count = 0
        self.speech_buffer = bytearray()
        self.remainder_bytes = bytearray()

    def reset(self):
        """Resets segmenter state and buffers."""
        self.in_speech = False
        self.silence_frames_count = 0
        self.speech_buffer.clear()
        self.remainder_bytes.clear()
        self.pre_buffer.clear()
        if self.vad:
            self.vad.reset()

    def process_chunk(self, chunk_bytes: bytes) -> Optional[bytes]:
        """
        Processes a raw PCM16 chunk.
        Returns:
            bytes: Complete utterance PCM audio if speech ended after silence timeout.
            None: Still waiting for speech or speech still ongoing.
        """
        if not chunk_bytes:
            return None

        self.remainder_bytes.extend(chunk_bytes)

        completed_utterance: Optional[bytes] = None

        while len(self.remainder_bytes) >= self.frame_bytes:
            frame_data = bytes(self.remainder_bytes[:self.frame_bytes])
            del self.remainder_bytes[:self.frame_bytes]

            samples = np.frombuffer(frame_data, dtype=np.int16).astype(np.float32) / 32768.0
            prob = self.vad.process_frame(samples)
            is_speech_frame = (prob >= self.speech_threshold)

            if is_speech_frame:
                if not self.in_speech:
                    # Speech began: dump pre-speech padding
                    self.in_speech = True
                    self.speech_buffer.clear()
                    for pre_f in self.pre_buffer:
                        self.speech_buffer.extend(pre_f)
                    logger.debug("VAD: Speech start detected.")

                self.speech_buffer.extend(frame_data)
                self.silence_frames_count = 0

            else:
                if self.in_speech:
                    self.speech_buffer.extend(frame_data)
                    self.silence_frames_count += 1

                    if self.silence_frames_count >= self.silence_frames_threshold:
                        # Full utterance detected: speech start -> speech -> silence timeout!
                        logger.info(f"VAD: Utterance completed (duration: {len(self.speech_buffer)/32000:.2f}s).")
                        completed_utterance = bytes(self.speech_buffer)
                        self.in_speech = False
                        self.silence_frames_count = 0
                        self.speech_buffer.clear()
                        self.pre_buffer.clear()
                        break
                else:
                    # Keep rolling pre-buffer when idle
                    self.pre_buffer.append(frame_data)

        return completed_utterance

    def flush(self) -> Optional[bytes]:
        """Flushes any accumulated speech audio (e.g. on client manual disconnect or forced end)."""
        if self.in_speech and len(self.speech_buffer) > 0:
            data = bytes(self.speech_buffer)
            self.reset()
            return data
        if len(self.pre_buffer) > 0:
            buf = bytearray()
            for frame in self.pre_buffer:
                buf.extend(frame)
            if self.remainder_bytes:
                buf.extend(self.remainder_bytes)
            self.reset()
            return bytes(buf)
        self.reset()
        return None
