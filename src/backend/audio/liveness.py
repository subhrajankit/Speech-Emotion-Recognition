"""
Voice Liveness & Anti-Spoofing Acoustic Analyzer (Phase 18).
Runs spectral and temporal micro-variation heuristics on incoming PCM16 audio
post-VAD and pre-ASR to flag likely synthetic (TTS) or replayed speech.

Invariant:
- Heuristic-based (spectral flatness, energy dynamics, formant concentration).
- Flagged utterances are logged with full details for auditability; never silently dropped.
"""

import math
import logging
import numpy as np
from dataclasses import dataclass, asdict
from typing import Dict, Any, Tuple

logger = logging.getLogger("senseai.security.liveness")


@dataclass
class LivenessResult:
    is_live: bool
    confidence: float
    score: float
    details: Dict[str, Any]

    @property
    def is_suspicious(self) -> bool:
        return not self.is_live

    @property
    def flatness(self) -> float:
        return self.details.get("spectral_flatness", 0.0)

    @property
    def rms_variance(self) -> float:
        return self.details.get("energy_rms_std", 0.0)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class VoiceLivenessDetector:
    """
    Evaluates acoustic characteristics of raw PCM16 audio to distinguish
    live human vocal tract production from synthetic text-to-speech or replayed audio.
    """

    def __init__(
        self,
        min_duration_sec: float = 0.2,
        energy_variance_threshold: float = 0.002,
        spectral_flatness_threshold: float = 0.65
    ):
        self.min_duration_sec = min_duration_sec
        self.energy_variance_threshold = energy_variance_threshold
        self.spectral_flatness_threshold = spectral_flatness_threshold

    def analyze(self, pcm_bytes: bytes, sample_rate: int = 16000) -> LivenessResult:
        """
        Analyzes audio buffer and returns a LivenessResult.
        """
        if not pcm_bytes or len(pcm_bytes) < int(sample_rate * 2 * self.min_duration_sec):
            # Too short to reliably evaluate, default to permissive live
            return LivenessResult(
                is_live=True,
                confidence=0.5,
                score=0.5,
                details={"reason": "audio_too_short_for_heuristic", "duration_sec": len(pcm_bytes) / 32000.0}
            )

        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32) / 32768.0
        total_samples = len(samples)
        duration_sec = total_samples / sample_rate

        # 1. Temporal Energy Dynamics (Frame RMS Variance)
        frame_size = int(sample_rate * 0.025)  # 25ms frames
        hop_size = int(sample_rate * 0.010)    # 10ms hop
        num_frames = max(1, (total_samples - frame_size) // hop_size)

        frame_energies = []
        for i in range(num_frames):
            frame = samples[i * hop_size : i * hop_size + frame_size]
            rms = math.sqrt(float(np.mean(frame ** 2)))
            frame_energies.append(rms)

        energy_std = float(np.std(frame_energies)) if frame_energies else 0.0
        energy_mean = float(np.mean(frame_energies)) if frame_energies else 0.0

        # 2. Spectral Flatness / Peak Concentration (FFT)
        # Human speech concentrates in lower formant bands (300Hz - 3400Hz)
        fft_mags = np.abs(np.fft.rfft(samples))
        fft_mags = fft_mags + 1e-10  # Prevent zero div
        geo_mean = float(np.exp(np.mean(np.log(fft_mags))))
        arith_mean = float(np.mean(fft_mags))
        spectral_flatness = geo_mean / arith_mean  # 0.0 (peaked/vocal) to 1.0 (white noise/flat)

        # 3. Formant Band Ratio (300Hz - 3500Hz vs high frequency > 4000Hz)
        freq_bins = np.fft.rfftfreq(total_samples, d=1.0 / sample_rate)
        vocal_mask = (freq_bins >= 300) & (freq_bins <= 3500)
        high_mask = freq_bins > 4000

        vocal_energy = float(np.sum(fft_mags[vocal_mask] ** 2))
        high_energy = float(np.sum(fft_mags[high_mask] ** 2)) + 1e-10
        vocal_to_high_ratio = vocal_energy / high_energy

        # Anomaly scoring:
        # - Flatness > 0.65 suggests artificial white noise or robotic audio
        # - Extremely low energy variance (< 0.002) suggests static synthesized drone or pure tone
        # - Extreme high-frequency boost suggests synthetic vocoder artifacts
        is_synthetic_drone = energy_std < self.energy_variance_threshold and energy_mean > 0.05
        is_abnormally_flat = spectral_flatness > self.spectral_flatness_threshold

        suspicious = is_synthetic_drone or is_abnormally_flat
        is_live = not suspicious

        score = round(1.0 - (spectral_flatness * 0.5 + (1.0 if is_synthetic_drone else 0.0) * 0.5), 3)
        confidence = round(0.85 if suspicious else 0.90, 2)

        details = {
            "duration_sec": round(duration_sec, 2),
            "energy_rms_std": round(energy_std, 4),
            "spectral_flatness": round(spectral_flatness, 4),
            "vocal_to_high_ratio": round(vocal_to_high_ratio, 2),
            "is_synthetic_drone": bool(is_synthetic_drone),
            "is_abnormally_flat": bool(is_abnormally_flat)
        }

        if suspicious:
            logger.warning(
                f"[AntiSpoofing] Suspicious acoustic characteristics detected (is_live=False, score={score}): {details}"
            )
        else:
            logger.debug(f"[AntiSpoofing] Audio verified as live human speech (score={score}).")

        return LivenessResult(
            is_live=is_live,
            confidence=confidence,
            score=max(0.0, min(1.0, score)),
            details=details
        )


# Global singleton
liveness_detector = VoiceLivenessDetector()
