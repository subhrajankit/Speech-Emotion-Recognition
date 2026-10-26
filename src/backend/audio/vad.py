import collections
import logging
import os
from typing import Optional, List, Tuple
import numpy as np

logger = logging.getLogger(__name__)

class SileroVAD:
    """
    Wrapper for Silero VAD v5 ONNX model.
    Loaded once at startup (module-level singleton).
    Processes 16kHz audio in 512-sample (32ms) frames with 64-sample context.
    """
    def __init__(self, model_path: str = "models/silero_vad.onnx", threshold: float = 0.5, mock: bool = False):
        self.model_path = model_path
        self.threshold = threshold
        self.mock = mock
        self.session = None
        self.context_size = 64
        self.state = np.zeros((2, 1, 128), dtype=np.float32)
        self.context = np.zeros((1, self.context_size), dtype=np.float32)
        self.sr = np.array(16000, dtype=np.int64)
        self.is_loaded = False
        self._load_model()

    def _load_model(self):
        if self.mock:
            logger.info("SileroVAD initialized in MOCK mode.")
            self.is_loaded = True
            return

        if not os.path.exists(self.model_path):
            logger.warning(f"Silero VAD model not found at {self.model_path}. Falling back to energy-based VAD.")
            self.is_loaded = False
            return

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

        # Energy-based speech approximation for mock or fallback
        if self.session is None or self.mock:
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

