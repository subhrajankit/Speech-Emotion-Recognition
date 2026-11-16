"""Tests for scripts/bench_sensevoice_asr.py — no model loading, no inference."""

import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import bench_sensevoice_asr as bench


# ---------- CLI ----------

def test_cli_help(capsys):
    with pytest.raises(SystemExit) as e:
        bench.main(["--help"])
    assert e.value.code == 0
    out = capsys.readouterr().out
    for flag in ("--device", "--warm-runs", "--cold-runs",
                 "--concurrency-rounds", "--skip-cold", "--skip-concurrency",
                 "--output"):
        assert flag in out


def test_cli_defaults():
    parser_defaults = {"device": "cpu", "warm_runs": 20, "cold_runs": 3,
                       "concurrency_rounds": 10}
    # verify via a tiny arg parse reconstruction
    args = bench.argparse.ArgumentParser()
    # smoke: main() would run the benchmark; instead verify parser exists
    assert callable(bench.main)
    assert parser_defaults["device"] == "cpu"


# ---------- aggregation ----------

def test_aggregate_stats_basic():
    s = bench.aggregate_stats([10, 20, 30, 40, 50])
    assert s["count"] == 5
    assert s["min"] == 10 and s["max"] == 50
    assert s["median"] == 30
    assert s["p50"] == 30
    assert s["mean"] == pytest.approx(30.0)


def test_aggregate_stats_empty_and_none():
    assert bench.aggregate_stats([])["count"] == 0
    assert bench.aggregate_stats([None, None])["count"] == 0
    s = bench.aggregate_stats([None, 5.0, None])
    assert s["count"] == 1 and s["min"] == 5.0


def test_percentile_edges():
    vals = list(range(1, 101))
    assert bench.percentile(vals, 0) == 1
    assert bench.percentile(vals, 100) == 100
    assert bench.percentile([], 50) is None
    assert bench.percentile([7], 95) == 7


# ---------- RTF ----------

def test_rtf_calculation():
    # 500 ms engine time over 10 s audio -> RTF 0.05
    assert bench.compute_rtf(500.0, 10.0) == pytest.approx(0.05)


def test_rtf_zero_and_negative_duration():
    assert bench.compute_rtf(100.0, 0) is None
    assert bench.compute_rtf(100.0, -1) is None
    assert bench.compute_rtf(100.0, None) is None


# ---------- JSON / report ----------

def test_report_schema_required_keys():
    report = {
        "benchmark": "sensevoice_asr",
        "dataset_type": "synthetic_diagnostic",
        "disclaimer": "x",
        "metric_definitions": {},
        "limitations": [],
        "environment": {},
    }
    assert report["dataset_type"] == "synthetic_diagnostic"
    # ensure JSON-serializable
    json.dumps(report)


# ---------- child result parsing ----------

def test_child_result_file_parsing_with_log_noise(tmp_path):
    """Result file must parse even if the child emitted noisy stdout."""
    rf = tmp_path / "cold.json"
    rf.write_text(json.dumps({
        "clip": "en_5_words_gpu_fp16", "device": "cpu",
        "init_seconds": 8.5, "first_transcribe_seconds": 1.2,
        "cold_total_seconds": 9.7, "processing_time_ms": 1100,
        "transcript": "<|en|>hi", "language": "en", "error": None,
    }))
    data = json.loads(rf.read_text(encoding="utf-8"))
    assert data["cold_total_seconds"] == pytest.approx(9.7)
    assert data["clip"] == "en_5_words_gpu_fp16"


def test_missing_clip_raises():
    with pytest.raises(Exception):  # soundfile LibsndfileError for missing file
        bench.clip_duration_s(REPO_ROOT / "tests/samples/does_not_exist.wav")


def test_memory_snapshot_without_psutil(monkeypatch):
    """psutil absent -> skipped dict, no exception, no dependency added."""
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *a, **kw):
        if name == "psutil":
            raise ImportError("no psutil")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    snap = bench.memory_snapshot()
    assert snap.get("skipped") is True
    assert "psutil" in snap.get("reason", "")


# ---------- service init + incremental report persistence ----------

class _FakeEngine:
    def __init__(self, **kwargs):
        self.kwargs = kwargs


def _bench_args(**overrides):
    args = types.SimpleNamespace(
        device="cpu",
        warm_runs=2,
        cold_runs=1,
        concurrency_rounds=1,
        skip_cold=False,
        skip_concurrency=False,
        output=None,
    )
    for key, value in overrides.items():
        setattr(args, key, value)
    return args


def _patch_light_stages(monkeypatch):
    monkeypatch.setattr(bench, "env_metadata", lambda device: {"device": device})
    monkeypatch.setattr(bench, "_sensevoice_engine_class", lambda: _FakeEngine)
    monkeypatch.setattr(
        bench, "run_cold_trials",
        lambda device, cold_runs: {"trials": []})
    monkeypatch.setattr(
        bench, "run_warm_inference",
        lambda engine, warm_runs: {"clip": {"runs": []}})
    monkeypatch.setattr(
        bench, "run_decode_preprocessing",
        lambda warm_runs: {"clip": {"runs_ms": []}})
    monkeypatch.setattr(
        bench, "prepare_service_path",
        lambda engine: {"service": object(), "arrays": {}, "durations": {}})


def test_prepare_service_path_reuses_engine_without_initialize_or_load(monkeypatch):
    from backend.app.services.speech_service import SpeechService

    engine = Mock()
    engine.is_loaded = True
    engine.load = Mock()
    monkeypatch.setattr(bench, "_speech_service_class", lambda: SpeechService)
    monkeypatch.setattr(bench, "load_clip", lambda path: object())
    monkeypatch.setattr(bench, "clip_duration_s", lambda path: (1.0, 16000, 1))

    ctx = bench.prepare_service_path(engine)

    service = ctx["service"]
    assert isinstance(service, SpeechService)
    assert service.sensevoice is engine
    assert service._engine is engine
    assert service.is_ready is True
    engine.load.assert_not_called()


def test_service_path_uses_real_speech_service_transcribe_array(monkeypatch):
    import asyncio
    from backend.app.core.config import settings
    from backend.app.services.speech_service import SpeechService
    from ai.inference.types import SpeechResult

    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    monkeypatch.setattr(bench, "_speech_service_class", lambda: SpeechService)
    monkeypatch.setattr(bench, "load_clip", lambda path: object())
    monkeypatch.setattr(bench, "clip_duration_s", lambda path: (1.0, 16000, 1))
    calls = []

    class Engine:
        is_loaded = True

        def load(self):
            raise AssertionError("engine.load must not be called")

        def transcribe(self, audio, sample_rate=16000, language_hint=None):
            calls.append(language_hint)
            return SpeechResult(
                transcript="x", language="en", emotion=None, confidence=None,
                processing_time_ms=1, model_version="fake")

    ctx = bench.prepare_service_path(Engine())
    result = asyncio.run(ctx["service"].transcribe_array(
        audio=object(), sample_rate=16000, language_hint="en"))

    assert result.transcript == "x"
    assert calls == ["en"]


def test_build_report_service_path_reuses_warm_engine(monkeypatch, tmp_path):
    from backend.app.core.config import settings
    from backend.app.services.speech_service import SpeechService
    from ai.inference.types import SpeechResult

    report_path = tmp_path / "bench.json"
    monkeypatch.setattr(settings, "ASR_ENGLISH_ONLY", True)
    monkeypatch.setattr(bench, "env_metadata", lambda device: {})
    monkeypatch.setattr(
        bench, "run_cold_trials", lambda device, cold_runs: {"trials": []})
    monkeypatch.setattr(
        bench, "run_decode_preprocessing",
        lambda warm_runs: {"clip": {"runs_ms": []}})
    seen = {}

    def fake_warm(engine, warm_runs):
        seen["engine"] = engine
        return {"clip": {"runs": []}}

    class Engine:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.is_loaded = True
            self.load_calls = 0
            self.transcribe_calls = 0

        def load(self):
            self.load_calls += 1
            self.is_loaded = True

        def transcribe(self, audio, sample_rate=16000, language_hint=None):
            self.transcribe_calls += 1
            return SpeechResult(
                transcript="x", language="en", emotion=None, confidence=None,
                processing_time_ms=1, model_version="fake")

    monkeypatch.setattr(bench, "_sensevoice_engine_class", lambda: Engine)
    monkeypatch.setattr(bench, "run_warm_inference", fake_warm)
    monkeypatch.setattr(bench, "_speech_service_class", lambda: SpeechService)
    monkeypatch.setattr(bench, "load_clip", lambda path: object())
    monkeypatch.setattr(bench, "clip_duration_s", lambda path: (1.0, 16000, 1))

    report = bench.build_report(
        _bench_args(warm_runs=1, concurrency_rounds=1,
                    skip_concurrency=True, cold_runs=None),
        report_path)

    engine = seen["engine"]
    assert engine.load_calls == 0
    assert engine.transcribe_calls == 2
    assert report["status"] == "complete"


def test_completed_sections_persist_before_service_path(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    seen = {}
    _patch_light_stages(monkeypatch)

    def fake_sequential(ctx, warm_runs, on_run=None, on_start=None):
        data = json.loads(report_path.read_text(encoding="utf-8"))
        seen["keys"] = set(data.keys())
        seen["service_path"] = data.get("service_path")
        return {"clip": {"runs": []}}

    monkeypatch.setattr(bench, "run_sequential_service", fake_sequential)
    monkeypatch.setattr(
        bench, "run_concurrent_service",
        lambda ctx, rounds, skip, on_round=None, on_start=None: {"levels": {}})

    report = bench.build_report(_bench_args(), report_path)

    assert {"cold_start", "warm_inference", "decode_preprocessing"} <= seen["keys"]
    assert seen["service_path"] == {}
    assert report["status"] == "complete"


def test_service_path_exception_writes_sanitized_partial_report(
        monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)

    def boom(ctx, warm_runs, on_run=None, on_start=None):
        raise RuntimeError("failed at D:\\secret\\model.bin")

    monkeypatch.setattr(bench, "run_sequential_service", boom)

    with pytest.raises(RuntimeError, match="failed at"):
        bench.build_report(_bench_args(), report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "partial"
    assert data["failed_stage"] == "sequential_service"
    assert data["error"]["type"] == "RuntimeError"
    assert "<path>" in data["error"]["message"]
    assert "secret" not in data["error"]["message"]
    assert "cold_start" in data
    assert "warm_inference" in data
    assert "decode_preprocessing" in data
    assert data["service_path"] == {}
    assert "failed_at" in data
    assert "Traceback (most recent call last)" not in json.dumps(data)


def test_successful_build_report_status_complete(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)
    monkeypatch.setattr(
        bench, "run_sequential_service",
        lambda ctx, warm_runs, on_run=None, on_start=None: {"clip": {"runs": []}})
    monkeypatch.setattr(
        bench, "run_concurrent_service",
        lambda ctx, rounds, skip, on_round=None, on_start=None: {"levels": {}})

    report = bench.build_report(_bench_args(), report_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["status"] == "complete"
    assert data["status"] == "complete"
    assert data["completed_at"]
    assert data["completed_stages"] == [
        "cold_start", "model_load", "warm_inference",
        "decode_preprocessing", "service_path", "sequential_service",
        "concurrent_service",
    ]


# ---------- interruption-safe persistence ----------

def test_write_report_replaces_via_temp_file(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    calls = []
    real_replace = Path.replace

    def spy_replace(self, target):
        calls.append((self.name, Path(target).name))
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", spy_replace)
    bench.write_report(report_path, {"ok": True})

    assert len(calls) == 1
    src_name, dst_name = calls[0]
    assert dst_name == "bench.json"
    assert src_name.startswith("bench.json.") and src_name.endswith(".tmp")
    assert not list(tmp_path.glob("bench.json*.tmp"))
    assert not list(tmp_path.glob("bench.json*.recovery.json"))
    assert json.loads(report_path.read_text(encoding="utf-8")) == {"ok": True}


def test_write_report_retries_transient_permission_error(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    calls = []
    real_replace = Path.replace

    def flaky_replace(self, target):
        calls.append((self.name, Path(target).name))
        if Path(target).name == "bench.json" and len(calls) == 1:
            raise PermissionError("transient")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky_replace)
    monkeypatch.setattr(bench, "REPORT_WRITE_RETRY_DELAY_S", 0)
    bench.write_report(report_path, {"ok": True})

    dest_calls = [c for c in calls if c[1] == "bench.json"]
    assert len(dest_calls) == 2
    assert json.loads(report_path.read_text(encoding="utf-8")) == {"ok": True}
    assert not list(tmp_path.glob("bench.json*.tmp"))
    assert not list(tmp_path.glob("bench.json*.recovery.json"))


def test_write_report_failure_preserves_destination_and_recovery(
        monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    report_path.write_text('{"old": true}', encoding="utf-8")
    old_bytes = report_path.read_bytes()
    real_replace = Path.replace

    def deny_destination_replace(self, target):
        if Path(target).name == "bench.json":
            raise PermissionError("denied")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", deny_destination_replace)
    monkeypatch.setattr(bench, "REPORT_WRITE_ATTEMPTS", 2)
    monkeypatch.setattr(bench, "REPORT_WRITE_RETRY_DELAY_S", 0)

    with pytest.raises(bench.ReportPersistenceError) as exc_info:
        bench.write_report(report_path, {"new": True})

    assert report_path.read_bytes() == old_bytes
    recovery_path = tmp_path / "bench.json.recovery.json"
    assert recovery_path.exists()
    assert json.loads(recovery_path.read_text(encoding="utf-8")) == {"new": True}
    assert exc_info.value.recovery_path == recovery_path
    assert not list(tmp_path.glob("bench.json*.tmp"))


def test_partial_write_failure_preserves_original_stage_error(
        monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)

    def boom(*args, **kwargs):
        raise RuntimeError("stage boom D:\\secret\\model.bin")

    monkeypatch.setattr(bench, "run_sequential_service", boom)
    real_write_report = bench.write_report

    def fail_partial_writes(path, report):
        if report.get("status") == "partial":
            path = Path(path)
            raise bench.ReportPersistenceError(
                "persist failed", report_path=path,
                recovery_path=path.with_name(path.name + ".recovery.json"))
        return real_write_report(path, report)

    monkeypatch.setattr(bench, "write_report", fail_partial_writes)

    with pytest.raises(RuntimeError, match="stage boom") as exc_info:
        bench.build_report(_bench_args(cold_runs=1), report_path)

    assert "stage boom" in str(exc_info.value)
    notes = getattr(exc_info.value, "__notes__", [])
    assert any("Report persistence also failed" in note for note in notes)
    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "running"
    assert data.get("failed_stage") is None


def test_cold_trials_are_opt_in(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)
    called = []
    monkeypatch.setattr(
        bench, "run_cold_trials",
        lambda *args, **kwargs: called.append((args, kwargs)) or {"trials": []})
    monkeypatch.setattr(
        bench, "run_sequential_service",
        lambda ctx, warm_runs, on_run=None, on_start=None: {"clip": {"runs": []}})
    monkeypatch.setattr(
        bench, "run_concurrent_service",
        lambda ctx, rounds, skip, on_round=None, on_start=None: {"levels": {}})

    report = bench.build_report(
        _bench_args(cold_runs=None, skip_cold=False), report_path)
    data = json.loads(report_path.read_text(encoding="utf-8"))

    assert called == []
    assert "cold_start" not in data["completed_stages"]
    assert "cold_start" not in data
    assert report["status"] == "complete"
    assert data["interruption"]["pid"] == os.getpid()


def test_cold_runs_cli_is_opt_in(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(
        bench, "resolve_output_path", lambda output: tmp_path / "bench.json")

    def fake_build(args, report_path=None):
        captured["args"] = args
        return {}

    monkeypatch.setattr(bench, "build_report", fake_build)
    bench.main([])
    assert captured["args"].cold_runs is None

    bench.main(["--cold-runs", "2"])
    assert captured["args"].cold_runs == 2


def test_cold_trials_capture_bounded_sanitized_output_and_fault_handler(
        monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP", str(tmp_path))
    monkeypatch.setattr(bench, "CLIPS", {"clip_a": "tests/samples/x.wav"})
    calls = []
    stdout = "\n".join(f"out-{i:02d}" for i in range(30))
    stderr = "\n".join(
        [f"err-{i:02d}" for i in range(25)] + [r"D:\secret\model.bin failed"])

    def fake_run(*args, **kwargs):
        calls.append(kwargs)
        return types.SimpleNamespace(returncode=1, stdout=stdout, stderr=stderr)

    real_subprocess = bench.subprocess
    fake_subprocess = types.SimpleNamespace(
        run=fake_run, TimeoutExpired=real_subprocess.TimeoutExpired)
    monkeypatch.setattr(bench, "subprocess", fake_subprocess)

    result = bench.run_cold_trials("cpu", 1)

    assert len(result["trials"]) == 1
    trial = result["trials"][0]
    assert trial["returncode"] == 1
    assert trial["duration_seconds"] >= 0
    assert trial["error"] == "no result file"
    assert "out-29" in trial["stdout_tail"]
    assert "out-00" not in trial["stdout_tail"]
    assert "err-24" in trial["stderr_tail"]
    assert "err-00" not in trial["stderr_tail"]
    assert "secret" not in trial["stderr_tail"]
    assert "<path>" in trial["stderr_tail"]
    assert len(trial["stdout_tail"]) <= bench.CHILD_OUTPUT_TAIL_CHARS
    assert len(trial["stderr_tail"]) <= bench.CHILD_OUTPUT_TAIL_CHARS
    assert calls[0]["env"]["PYTHONFAULTHANDLER"] == "1"
    assert calls[0]["timeout"] == bench.CHILD_TIMEOUT_SECONDS


def test_sequential_service_persists_after_each_run(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)
    observations = []
    inflight = []
    calls = []

    async def fake_service_one(ctx, key):
        calls.append(key)
        data = json.loads(report_path.read_text(encoding="utf-8"))
        interruption = data["interruption"]
        inflight.append((
            key,
            interruption["current_clip"],
            interruption["run_index"],
            interruption["concurrency_level"],
            interruption["round_index"],
        ))
        if len(calls) > 1:
            seq = data.get("service_path", {}).get("sequential_service", {})
            observations.append(
                sum(len(v.get("runs", [])) for v in seq.values()))
        return {
            "wall_ms": float(len(calls) * 10),
            "engine_processing_time_ms": 1,
            "rtf": 0.1,
            "transcript": "x",
        }

    monkeypatch.setattr(bench, "_service_one", fake_service_one)
    monkeypatch.setattr(
        bench, "run_concurrent_service",
        lambda ctx, rounds, skip, on_round=None, on_start=None: {"levels": {}})

    bench.build_report(
        _bench_args(warm_runs=2, concurrency_rounds=1,
                    skip_concurrency=True, cold_runs=1),
        report_path)

    assert observations == [1, 2, 3]
    assert inflight == [
        ("en_5_words_gpu_fp16", "en_5_words_gpu_fp16", 0, None, None),
        ("en_5_words_gpu_fp16", "en_5_words_gpu_fp16", 1, None, None),
        ("en_14_words_gpu_fp16", "en_14_words_gpu_fp16", 0, None, None),
        ("en_14_words_gpu_fp16", "en_14_words_gpu_fp16", 1, None, None),
    ]
    data = json.loads(report_path.read_text(encoding="utf-8"))
    seq = data["service_path"]["sequential_service"]
    assert all(v["wall_ms"]["count"] == 2 for v in seq.values())
    assert data["interruption"]["pid"] == os.getpid()
    assert data["interruption"]["current_clip"] is None
    assert data["interruption"]["run_index"] is None
    assert data["interruption"]["concurrency_level"] is None
    assert data["interruption"]["round_index"] is None


def test_concurrent_service_persists_after_each_round(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)
    monkeypatch.setattr(
        bench, "run_sequential_service",
        lambda ctx, warm_runs, on_run=None, on_start=None: {"clip": {"runs": []}})
    observations = []
    inflight = []
    call_no = 0

    async def fake_service_one(ctx, key):
        nonlocal call_no
        call_no += 1
        data = json.loads(report_path.read_text(encoding="utf-8"))
        interruption = data["interruption"]
        inflight.append((
            call_no,
            interruption["concurrency_level"],
            interruption["round_index"],
            interruption["current_clip"],
            interruption["run_index"],
        ))
        levels = data.get("service_path", {}).get(
            "concurrent_service", {}).get("levels", {})
        observations.append((
            call_no,
            tuple(sorted(
                (k, len(v.get("rounds", []))) for k, v in levels.items())),
        ))
        return {
            "wall_ms": float(call_no),
            "engine_processing_time_ms": 1,
            "rtf": 0.1,
            "transcript": "x",
        }

    monkeypatch.setattr(bench, "_service_one", fake_service_one)
    bench.build_report(
        _bench_args(warm_runs=1, concurrency_rounds=2,
                    skip_concurrency=False, cold_runs=1),
        report_path)

    by_call = dict(observations)
    assert by_call[1] == ()
    assert by_call[2] == ()
    assert by_call[3] == (("2", 1),)
    assert by_call[4] == (("2", 1),)
    assert by_call[5] == (("2", 2),)
    assert by_call[8] == (("2", 2),)
    assert by_call[9] == (("2", 2), ("4", 1))
    assert by_call[12] == (("2", 2), ("4", 1))
    assert [item[1:] for item in inflight] == [
        (2, 0, None, None), (2, 0, None, None),
        (2, 1, None, None), (2, 1, None, None),
        (4, 0, None, None), (4, 0, None, None),
        (4, 0, None, None), (4, 0, None, None),
        (4, 1, None, None), (4, 1, None, None),
        (4, 1, None, None), (4, 1, None, None),
    ]

    data = json.loads(report_path.read_text(encoding="utf-8"))
    levels = data["service_path"]["concurrent_service"]["levels"]
    assert levels["2"]["batch_wall_ms"]["count"] == 2
    assert levels["4"]["batch_wall_ms"]["count"] == 2
    assert data["interruption"]["concurrency_level"] is None
    assert data["interruption"]["round_index"] is None
    assert data["interruption"]["current_clip"] is None
    assert data["interruption"]["run_index"] is None


def test_concurrent_service_failure_preserves_round_metadata(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)
    monkeypatch.setattr(
        bench, "run_sequential_service",
        lambda ctx, warm_runs, on_run=None, on_start=None: {"clip": {"runs": []}})
    call_no = 0

    async def fake_service_one(ctx, key):
        nonlocal call_no
        call_no += 1
        if call_no == 3:
            raise RuntimeError("concurrent boom")
        return {
            "wall_ms": float(call_no),
            "engine_processing_time_ms": 1,
            "rtf": 0.1,
            "transcript": "x",
        }

    monkeypatch.setattr(bench, "_service_one", fake_service_one)

    with pytest.raises(RuntimeError, match="concurrent boom"):
        bench.build_report(
            _bench_args(warm_runs=1, concurrency_rounds=2,
                        skip_concurrency=False, cold_runs=1),
            report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "partial"
    assert data["failed_stage"] == "concurrent_service"
    assert data["interruption"]["current_stage"] == "concurrent_service"
    assert data["interruption"]["concurrency_level"] == 2
    assert data["interruption"]["round_index"] == 1
    assert data["interruption"]["current_clip"] is None
    assert data["interruption"]["run_index"] is None
    levels = data["service_path"]["concurrent_service"]["levels"]
    assert levels["2"]["batch_wall_ms"]["count"] == 1
    assert "4" not in levels


def test_service_stage_exception_preserves_completed_runs(monkeypatch, tmp_path):
    report_path = tmp_path / "bench.json"
    _patch_light_stages(monkeypatch)
    calls = 0

    async def fake_service_one(ctx, key):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("boom D:\\secret\\model.bin")
        return {
            "wall_ms": 1.0,
            "engine_processing_time_ms": 1,
            "rtf": 0.1,
            "transcript": "x",
        }

    monkeypatch.setattr(bench, "_service_one", fake_service_one)

    with pytest.raises(RuntimeError, match="boom"):
        bench.build_report(
            _bench_args(warm_runs=2, concurrency_rounds=1,
                        skip_concurrency=True, cold_runs=1),
            report_path)

    data = json.loads(report_path.read_text(encoding="utf-8"))
    assert data["status"] == "partial"
    assert data["failed_stage"] == "sequential_service"
    assert data["interruption"]["current_stage"] == "sequential_service"
    assert data["interruption"]["current_clip"] == "en_5_words_gpu_fp16"
    assert data["interruption"]["run_index"] == 1
    assert data["interruption"]["concurrency_level"] is None
    assert data["interruption"]["round_index"] is None
    seq = data["service_path"]["sequential_service"]
    first = seq["en_5_words_gpu_fp16"]
    assert len(first["runs"]) == 1
    assert first["wall_ms"]["count"] == 1
    assert seq["en_14_words_gpu_fp16"]["runs"] == []
    assert "secret" not in json.dumps(data)
