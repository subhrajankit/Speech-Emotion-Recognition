"""
Backward-compatibility forwarder for Silero VAD.
Canonical implementation is now located at ai.preprocessing.vad.
"""

from ai.preprocessing.vad import SileroVAD, VADSpeechSegmenter, VADResult

__all__ = ["SileroVAD", "VADSpeechSegmenter", "VADResult"]
