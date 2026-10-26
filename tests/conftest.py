"""
Global Pytest Configuration for SenseAI Canonical Test Suite.

Ensures all tests across backend, ai, and rag suites run consistently
with standardized environment settings and sys.path configuration.
Does not import from legacy src/.
"""

import math
import os
import struct
import sys
from pathlib import Path

# Enforce 1 OpenBLAS thread to prevent memory allocation failures on Windows
os.environ["OPENBLAS_NUM_THREADS"] = "1"

# Ensure repo root is at the head of sys.path, and tests dir does not shadow root packages
_repo_root = str(Path(__file__).parent.parent.resolve())
_tests_dir = str(Path(__file__).parent.resolve())
while _tests_dir in sys.path:
    sys.path.remove(_tests_dir)
while _repo_root in sys.path:
    sys.path.remove(_repo_root)
sys.path.insert(0, _repo_root)

import pytest


@pytest.fixture
def synthetic_speech_audio() -> bytes:
    """
    Generates 1.0 second (32,000 bytes) of synthetic 16kHz mono PCM16 audio
    containing a 440Hz tone simulating an active speech utterance.
    """
    sample_rate = 16000
    duration_sec = 1.0
    num_samples = int(sample_rate * duration_sec)
    frequency = 440.0
    amplitude = 16000  # PCM16 range: -32768 to 32767

    raw_bytes = bytearray()
    for i in range(num_samples):
        val = int(amplitude * math.sin(2.0 * math.pi * frequency * (i / sample_rate)))
        raw_bytes.extend(struct.pack("<h", val))

    return bytes(raw_bytes)
