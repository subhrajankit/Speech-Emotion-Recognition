"""Model-free thread-safety tests for ai.preprocessing.vad.SileroVAD.analyze()."""

import threading
import time

import numpy as np
import pytest

from ai.preprocessing.vad import SileroVAD, VADResult


def _make_vad(monkeypatch, min_speech_duration_ms=1, threshold=0.5):
    def fake_load(self):
        self.session = object()
        self.is_loaded = True

    monkeypatch.setattr(SileroVAD, "_load_model", fake_load)
    return SileroVAD(
        model_path="unused",
        threshold=threshold,
        min_speech_duration_ms=min_speech_duration_ms,
    )


def test_analyze_serializes_stateful_section_on_same_instance(monkeypatch):
    vad = _make_vad(monkeypatch)
    audio = np.ones(2048, dtype=np.float32) * 0.1

    active = 0
    max_active = 0
    active_lock = threading.Lock()
    thread_ids = []

    def fake_process_frame(self, frame):
        nonlocal active, max_active
        with active_lock:
            active += 1
            max_active = max(max_active, active)
            thread_ids.append(threading.get_ident())
        try:
            time.sleep(0.02)
            return 1.0
        finally:
            with active_lock:
                active -= 1

    monkeypatch.setattr(SileroVAD, "process_frame", fake_process_frame)

    results = []
    errors = []

    def worker():
        try:
            results.append(vad.analyze(audio, sample_rate=16000))
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert len(results) == 2
    assert all(isinstance(result, VADResult) for result in results)
    assert max_active == 1
    assert len(set(thread_ids)) == 2


def test_analyze_does_not_serialize_across_instances(monkeypatch):
    vad_a = _make_vad(monkeypatch)
    vad_a._test_tag = "a"
    vad_b = _make_vad(monkeypatch)
    vad_b._test_tag = "b"
    audio = np.ones(1024, dtype=np.float32) * 0.1

    barrier = threading.Barrier(2)
    first_frame_tags = set()
    first_frame_lock = threading.Lock()

    def fake_process_frame(self, frame):
        tag = getattr(self, "_test_tag", "unknown")
        with first_frame_lock:
            is_first = tag not in first_frame_tags
            if is_first:
                first_frame_tags.add(tag)
        if is_first:
            barrier.wait(timeout=5)
        return 1.0

    monkeypatch.setattr(SileroVAD, "process_frame", fake_process_frame)

    results = []
    errors = []

    def worker(vad):
        try:
            results.append(vad.analyze(audio, sample_rate=16000))
        except Exception as exc:  # pragma: no cover - failure path
            errors.append(exc)

    threads = [
        threading.Thread(target=worker, args=(vad_a,)),
        threading.Thread(target=worker, args=(vad_b,)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)

    assert errors == []
    assert len(results) == 2
    assert vad_a._lock is not vad_b._lock
    assert first_frame_tags == {"a", "b"}


def test_analyze_releases_lock_after_exception(monkeypatch):
    vad = _make_vad(monkeypatch)
    audio = np.ones(1024, dtype=np.float32) * 0.1
    calls = {"count": 0, "failed": False}

    def fake_process_frame(self, frame):
        calls["count"] += 1
        if not calls["failed"]:
            calls["failed"] = True
            raise RuntimeError("vad boom")
        return 1.0

    monkeypatch.setattr(SileroVAD, "process_frame", fake_process_frame)

    with pytest.raises(RuntimeError, match="vad boom"):
        vad.analyze(audio, sample_rate=16000)

    assert vad._lock.locked() is False

    result = vad.analyze(audio, sample_rate=16000)
    assert isinstance(result, VADResult)
    assert result.has_speech is True


def test_analyze_output_shape_and_early_returns_unchanged(monkeypatch):
    vad = _make_vad(monkeypatch, min_speech_duration_ms=250, threshold=0.5)

    empty = vad.analyze(np.array([], dtype=np.float32))
    assert empty.has_speech is False
    assert empty.speech_probability == 0.0

    short = vad.analyze(np.ones(1600, dtype=np.float32) * 0.5, sample_rate=16000)
    assert short.has_speech is False
    assert short.speech_probability == 0.0

    monkeypatch.setattr(SileroVAD, "process_frame", lambda self, frame: 0.1)
    audio = np.ones(4096, dtype=np.float32) * 0.1
    result = vad.analyze(audio, sample_rate=16000)

    assert isinstance(result, VADResult)
    assert result.has_speech is False
    assert result.speech_probability == 0.1
    assert result.speech_duration_ms == 0.0
    assert result.num_speech_frames == 0
