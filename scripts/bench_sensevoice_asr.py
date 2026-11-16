"""
SenseVoiceSmall English ASR performance benchmark — SYNTHETIC DIAGNOSTICS ONLY.

Measures cold start, warm inference latency, RTF, decode overhead, sequential
and concurrent service-path latency, and optional RSS memory on the two
synthetic TTS diagnostic clips. Results characterize pipeline mechanics only;
they are NOT human-speech accuracy or production latency guarantees.

Usage:
    .venv/Scripts/python.exe scripts/bench_sensevoice_asr.py --help
    .venv/Scripts/python.exe scripts/bench_sensevoice_asr.py --device cpu \
        --warm-runs 20 --cold-runs 3 --concurrency-rounds 10
    .venv/Scripts/python.exe scripts/bench_sensevoice_asr.py --skip-cold --skip-concurrency

Child-process cold-start mode (used internally, machine-readable via --result-file):
    python scripts/bench_sensevoice_asr.py --child-cold en_5_words_gpu_fp16 \
        --device cpu --result-file cold_result.json
"""

import argparse
import json
import os
import platform
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

CLIPS = {
    "en_5_words_gpu_fp16": "tests/samples/en_5_words_gpu_fp16.wav",
    "en_14_words_gpu_fp16": "tests/samples/en_14_words_gpu_fp16.wav",
}
DATASET_TYPE = "synthetic_diagnostic"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "docs" / "deployment" / "runs"
CHILD_TIMEOUT_SECONDS = 1800
CHILD_OUTPUT_TAIL_LINES = 20
CHILD_OUTPUT_TAIL_CHARS = 4000
REPORT_WRITE_ATTEMPTS = 5
REPORT_WRITE_RETRY_DELAY_S = 0.05


# ---------------------------------------------------------------- pure helpers

def percentile(values, pct):
    """Nearest-rank percentile. Returns None for empty input."""
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    if len(vals) == 1:
        return vals[0]
    rank = max(0, min(len(vals) - 1, int(round((pct / 100.0) * (len(vals) - 1)))))
    return vals[rank]


def aggregate_stats(values):
    """min/median/p50/p95/max over numeric values; preserves failures separately."""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return {"count": 0, "min": None, "median": None, "p50": None,
                "p95": None, "max": None, "mean": None}
    return {
        "count": len(vals),
        "min": min(vals),
        "median": statistics.median(vals),
        "p50": percentile(vals, 50),
        "p95": percentile(vals, 95),
        "max": max(vals),
        "mean": statistics.fmean(vals),
    }


def compute_rtf(engine_ms, audio_duration_s):
    """RTF = engine processing time / audio duration. None if duration <= 0."""
    if not audio_duration_s or audio_duration_s <= 0:
        return None
    return engine_ms / 1000.0 / audio_duration_s


def load_clip(path):
    """Decode + resample clip via the shared preprocessing path."""
    from ai.preprocessing.audio import load_and_preprocess_audio
    return load_and_preprocess_audio(str(path), target_sr=16000)


def clip_duration_s(path):
    import soundfile as sf
    info = sf.info(str(path))
    return info.duration, info.samplerate, info.channels


def _sensevoice_engine_class():
    from ai.inference.sensevoice import SenseVoiceSpeechEngine
    return SenseVoiceSpeechEngine


def _speech_service_class():
    from backend.app.services.speech_service import SpeechService
    return SpeechService


_PATH_TOKEN_RE = re.compile(r"(?<![\w.])(?:[A-Za-z]:[\\/]|\\\\|/)[^\s\"']+")


def sanitize_text(text):
    """Remove absolute filesystem paths from text before it enters the report."""
    if text is None:
        return ""
    text = str(text)
    for base in (REPO_ROOT, Path.home()):
        for variant in {str(base), str(base).replace("\\", "/")}:
            text = text.replace(variant, "<path>")
    return _PATH_TOKEN_RE.sub("<path>", text)


def sanitize_error(exc):
    return {
        "type": type(exc).__name__,
        "message": sanitize_text(str(exc) or type(exc).__name__),
    }


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def record_failure(report, stage, exc):
    report["status"] = "partial"
    report["failed_stage"] = stage
    report["error"] = sanitize_error(exc)
    report["failed_at"] = utc_now_iso()


class ReportPersistenceError(RuntimeError):
    def __init__(self, message, report_path, recovery_path=None,
                 temporary_path=None):
        super().__init__(message)
        self.report_path = Path(report_path)
        self.recovery_path = (Path(recovery_path)
                              if recovery_path is not None else None)
        self.temporary_path = (Path(temporary_path)
                               if temporary_path is not None else None)


def _replace_with_retry(tmp_path, path):
    attempts = REPORT_WRITE_ATTEMPTS
    delay = REPORT_WRITE_RETRY_DELAY_S
    last_exc = None
    for attempt in range(attempts):
        try:
            tmp_path.replace(path)
            return
        except PermissionError as exc:
            last_exc = exc
            if attempt + 1 < attempts:
                time.sleep(delay * (attempt + 1))
    if last_exc is not None:
        raise last_exc


def _preserve_report_payload(path, payload, tmp_path):
    recovery_path = path.with_name(path.name + ".recovery.json")
    preserved_path = None
    if tmp_path is not None and tmp_path.exists():
        try:
            tmp_path.replace(recovery_path)
            preserved_path = recovery_path
        except Exception:
            try:
                shutil.copyfile(tmp_path, recovery_path)
                preserved_path = recovery_path
            except Exception:
                preserved_path = None
    if preserved_path is None:
        try:
            recovery_path.write_text(payload, encoding="utf-8")
            preserved_path = recovery_path
        except Exception:
            preserved_path = (tmp_path
                              if tmp_path is not None and tmp_path.exists()
                              else None)
    if (preserved_path is not None and tmp_path is not None
            and preserved_path != tmp_path and tmp_path.exists()):
        try:
            tmp_path.unlink()
        except OSError:
            pass
    return preserved_path, recovery_path


def write_report(path, report):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(report, indent=2)
    tmp_path = None
    payload_written = False
    try:
        with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=path.name + ".", suffix=".tmp", delete=False) as tmp_file:
            tmp_path = Path(tmp_file.name)
            tmp_file.write(payload)
            tmp_file.flush()
            os.fsync(tmp_file.fileno())
        payload_written = True
        _replace_with_retry(tmp_path, path)
    except Exception as exc:
        preserved_path, recovery_path = _preserve_report_payload(
            path, payload, tmp_path if payload_written else None)
        if preserved_path is None:
            raise ReportPersistenceError(
                f"Failed to persist report {path}; could not preserve "
                f"newest state (recovery target {recovery_path})",
                report_path=path,
                recovery_path=recovery_path,
                temporary_path=tmp_path,
            ) from exc
        raise ReportPersistenceError(
            f"Failed to persist report {path}; newest serialized state "
            f"preserved at {preserved_path}",
            report_path=path,
            recovery_path=(recovery_path
                           if preserved_path == recovery_path else None),
            temporary_path=tmp_path,
        ) from exc
    return path


def resolve_output_path(output):
    if output:
        return Path(output)
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"asr_bench_{stamp}.json"


def _decode_subprocess_output(value):
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _bounded_output_tail(text, max_lines=CHILD_OUTPUT_TAIL_LINES,
                         max_chars=CHILD_OUTPUT_TAIL_CHARS):
    """Return a bounded, sanitized tail of subprocess output for the report."""
    if not text:
        return ""
    lines = [
        sanitize_text(line)
        for line in str(text).splitlines()
        if line.strip()
    ]
    tail = "\n".join(lines[-max_lines:]) if lines else ""
    if len(tail) > max_chars:
        tail = tail[-max_chars:]
    return tail


# ------------------------------------------------------------------ child mode

def run_child_cold(clip_key, device, result_file):
    """Fresh-process cold start: construct engine, time init vs first transcribe."""
    import numpy as np
    from ai.inference.sensevoice import SenseVoiceSpeechEngine

    clip_path = REPO_ROOT / CLIPS[clip_key]
    audio = load_clip(clip_path)

    t0 = time.perf_counter()
    engine = SenseVoiceSpeechEngine(device=device, auto_load=True)
    t_init = time.perf_counter() - t0

    t1 = time.perf_counter()
    result = engine.transcribe(audio, sample_rate=16000, language_hint="en")
    t_first = time.perf_counter() - t1

    out = {
        "clip": clip_key,
        "device": device,
        "init_seconds": round(t_init, 4),
        "first_transcribe_seconds": round(t_first, 4),
        "cold_total_seconds": round(t_init + t_first, 4),
        "processing_time_ms": result.processing_time_ms,
        "transcript": result.transcript,
        "language": result.language,
        "error": None,
    }
    Path(result_file).write_text(json.dumps(out), encoding="utf-8")


# -------------------------------------------------------------------- sections

def env_metadata(device):
    meta = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "logical_cpus": os.cpu_count(),
        "sensevoice_device": device,
        "sensevoice_threads": int(os.environ.get("SENSEVOICE_THREADS", "4")),
        "clips": {},
    }
    try:
        meta["cpu_model"] = platform.processor() or "unknown"
    except Exception:
        meta["cpu_model"] = "unknown"
    try:
        import funasr
        meta["funasr_version"] = getattr(funasr, "__version__", "unknown")
    except Exception:
        meta["funasr_version"] = "unavailable"
    try:
        import torch
        meta["torch_version"] = torch.__version__
    except Exception:
        meta["torch_version"] = "unavailable"
    for key, rel in CLIPS.items():
        p = REPO_ROOT / rel
        dur, sr, ch = clip_duration_s(p)
        meta["clips"][key] = {"path": rel, "duration_s": round(dur, 3),
                              "sample_rate": sr, "channels": ch}
    return meta


def run_cold_trials(device, cold_runs):
    trials = []
    child_env = os.environ.copy()
    child_env["PYTHONFAULTHANDLER"] = "1"
    for clip_key in CLIPS:
        for i in range(cold_runs):
            result_file = Path(os.environ.get("TEMP", ".")) / f"sv_cold_{clip_key}_{i}.json"
            result_file.unlink(missing_ok=True)
            cmd = [sys.executable, str(Path(__file__).resolve()),
                   "--child-cold", clip_key, "--device", device,
                   "--result-file", str(result_file)]
            timed_out = False
            t0 = time.perf_counter()
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=CHILD_TIMEOUT_SECONDS, env=child_env)
                returncode = proc.returncode
                stdout = _decode_subprocess_output(getattr(proc, "stdout", None))
                stderr = _decode_subprocess_output(getattr(proc, "stderr", None))
            except subprocess.TimeoutExpired as exc:
                timed_out = True
                returncode = None
                stdout = _decode_subprocess_output(
                    getattr(exc, "stdout", None) or getattr(exc, "output", None))
                stderr = _decode_subprocess_output(getattr(exc, "stderr", None))
            duration_seconds = round(time.perf_counter() - t0, 3)

            trial = {
                "clip": clip_key,
                "trial": i,
                "returncode": returncode,
                "duration_seconds": duration_seconds,
                "stdout_tail": _bounded_output_tail(stdout),
                "stderr_tail": _bounded_output_tail(stderr),
            }
            if timed_out:
                trial["timed_out"] = True
            if result_file.exists():
                try:
                    trial.update(json.loads(result_file.read_text(encoding="utf-8")))
                except Exception as e:
                    trial["parse_error"] = sanitize_text(str(e))
                result_file.unlink(missing_ok=True)
            else:
                trial["error"] = "timed out; no result file" if timed_out else "no result file"
            trials.append(trial)
    return {
        "method": "fresh subprocess per trial; init timed from engine "
                  "construction through first successful transcription",
        "trials": trials,
        "init_seconds": aggregate_stats([t.get("init_seconds") for t in trials]),
        "first_transcribe_seconds": aggregate_stats(
            [t.get("first_transcribe_seconds") for t in trials]),
        "cold_total_seconds": aggregate_stats(
            [t.get("cold_total_seconds") for t in trials]),
    }


def run_warm_inference(engine, warm_runs):
    """Warm-up + measured inference timings per clip."""
    warm = {}
    for clip_key, rel in CLIPS.items():
        path = REPO_ROOT / rel
        audio = load_clip(path)
        dur, _, _ = clip_duration_s(path)

        # labelled warm-up (reported separately, not in aggregates)
        warmup = engine.transcribe(audio, sample_rate=16000, language_hint="en")

        runs = []
        for _ in range(warm_runs):
            t0 = time.perf_counter()
            res = engine.transcribe(audio, sample_rate=16000, language_hint="en")
            wall_ms = (time.perf_counter() - t0) * 1000.0
            runs.append({
                "wall_ms": round(wall_ms, 3),
                "engine_processing_time_ms": res.processing_time_ms,
                "rtf": compute_rtf(res.processing_time_ms, dur),
                "transcript": res.transcript,
            })

        warm[clip_key] = {
            "audio_duration_s": round(dur, 3),
            "warmup": {"wall_ms": None,
                       "engine_processing_time_ms": warmup.processing_time_ms,
                       "note": "warm-up run, excluded from aggregates"},
            "runs": runs,
            "wall_ms": aggregate_stats([r["wall_ms"] for r in runs]),
            "engine_processing_time_ms": aggregate_stats(
                [r["engine_processing_time_ms"] for r in runs]),
            "rtf": aggregate_stats([r["rtf"] for r in runs]),
        }
    return warm


def run_decode_preprocessing(warm_runs):
    """Decode-only timings per clip."""
    decode = {}
    for clip_key, rel in CLIPS.items():
        path = REPO_ROOT / rel
        dec_runs = []
        for _ in range(warm_runs):
            t0 = time.perf_counter()
            load_clip(path)
            dec_runs.append(round((time.perf_counter() - t0) * 1000.0, 3))
        decode[clip_key] = {
            "runs_ms": dec_runs,
            "ms": aggregate_stats(dec_runs),
            "note": "load_and_preprocess_audio only; excludes engine inference",
        }
    return decode


def run_warm_and_decode(engine, warm_runs):
    """Compatibility wrapper preserving the original combined result shape."""
    return {
        "warm_inference": run_warm_inference(engine, warm_runs),
        "decode_preprocessing": run_decode_preprocessing(warm_runs),
    }


def _speech_service_with_engine(engine):
    """Build a SpeechService bound to an already-loaded engine without reloading."""
    service_cls = _speech_service_class()
    service = service_cls()
    service._sensevoice = engine
    service._engine = engine
    service._is_initialized = True
    service._init_error = None
    service._indic_init_error = None
    if not getattr(engine, "is_loaded", True) and hasattr(engine, "load"):
        engine.load()
    return service


def prepare_service_path(engine):
    """Reuse the warm-inference SenseVoice engine inside SpeechService."""
    service = _speech_service_with_engine(engine)
    if not getattr(service, "is_ready", False):
        raise RuntimeError("SpeechService failed to initialize SenseVoice engine.")

    arrays = {k: load_clip(REPO_ROOT / rel) for k, rel in CLIPS.items()}
    durs = {k: clip_duration_s(REPO_ROOT / rel)[0] for k, rel in CLIPS.items()}
    return {"service": service, "arrays": arrays, "durations": durs}


async def _service_one(ctx, key):
    t0 = time.perf_counter()
    res = await ctx["service"].transcribe_array(
        audio=ctx["arrays"][key], sample_rate=16000, language_hint="en")
    return {"wall_ms": round((time.perf_counter() - t0) * 1000.0, 3),
            "engine_processing_time_ms": res.processing_time_ms,
            "rtf": compute_rtf(res.processing_time_ms, ctx["durations"][key]),
            "transcript": res.transcript}


def run_sequential_service(ctx, warm_runs, on_run=None, on_start=None):
    """Sequential SpeechService.transcribe_array measurements."""
    import asyncio

    seq = {
        key: {
            "runs": [],
            "wall_ms": aggregate_stats([]),
            "rtf": aggregate_stats([]),
            "note": "SpeechService path incl. routing + semaphore; "
                    "queue wait not separately instrumented",
        }
        for key in CLIPS
    }
    for key in CLIPS:
        for run_index in range(warm_runs):
            if on_start is not None:
                on_start(key, run_index, seq)
            run = asyncio.run(_service_one(ctx, key))
            seq[key]["runs"].append(run)
            seq[key]["wall_ms"] = aggregate_stats(
                [r["wall_ms"] for r in seq[key]["runs"]])
            seq[key]["rtf"] = aggregate_stats(
                [r["rtf"] for r in seq[key]["runs"]])
            if on_run is not None:
                on_run(key, run_index, run, seq)
    return seq


def run_concurrent_service(ctx, concurrency_rounds, skip_concurrency,
                           on_round=None, on_start=None):
    """Concurrent SpeechService.transcribe_array measurements."""
    import asyncio

    conc = {"note": "semaphore wait not isolated; batch wall time includes queueing",
            "levels": {}}
    if skip_concurrency:
        return conc

    async def _run_gather(keys):
        return await asyncio.gather(*[_service_one(ctx, k) for k in keys])

    for level in (2, 4):
        rounds = []
        level_key = str(level)
        for round_index in range(concurrency_rounds):
            keys = [list(CLIPS)[i % len(CLIPS)] for i in range(level)]
            if on_start is not None:
                on_start(level_key, round_index, conc)
            t0 = time.perf_counter()
            results = asyncio.run(_run_gather(keys))
            batch_ms = (time.perf_counter() - t0) * 1000.0
            round_result = {
                "batch_wall_ms": round(batch_ms, 3),
                "task_latencies_ms": [r["wall_ms"] for r in results],
            }
            rounds.append(round_result)
            conc["levels"][level_key] = {
                "rounds": rounds,
                "batch_wall_ms": aggregate_stats(
                    [r["batch_wall_ms"] for r in rounds]),
            }
            if on_round is not None:
                on_round(level_key, round_index, round_result, conc)
    return conc


def run_service_path(engine, warm_runs, concurrency_rounds, skip_concurrency):
    """Compatibility wrapper for sequential + concurrent service measurements."""
    ctx = prepare_service_path(engine)
    return {
        "sequential_service": run_sequential_service(ctx, warm_runs),
        "concurrent_service": run_concurrent_service(
            ctx, concurrency_rounds, skip_concurrency),
    }


def memory_snapshot():
    try:
        import psutil
        return {"rss_bytes": psutil.Process().memory_info().rss,
                "method": "psutil RSS snapshot"}
    except ImportError:
        return {"skipped": True,
                "reason": "psutil not installed; no dependency added"}


def build_report(args, report_path=None):
    device = args.device
    report = {
        "benchmark": "sensevoice_asr",
        "dataset_type": DATASET_TYPE,
        "status": "running",
        "completed_stages": [],
        "interruption": {
            "pid": os.getpid(),
            "current_stage": None,
            "last_update": utc_now_iso(),
            "current_clip": None,
            "run_index": None,
            "concurrency_level": None,
            "round_index": None,
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "disclaimer": ("Synthetic TTS diagnostic clips only. These metrics "
                       "characterize pipeline mechanics, NOT human-speech "
                       "accuracy or production latency guarantees."),
        "metric_definitions": {
            "init_seconds": "engine construction through load completion",
            "first_transcribe_seconds": "first generate() call incl. warmup",
            "wall_ms": "caller-observed wall time around transcribe()",
            "engine_processing_time_ms": "engine-internal timer (VAD gate + generate)",
            "rtf": "engine_processing_time_ms / 1000 / audio_duration_s",
            "decode_ms": "load_and_preprocess_audio only",
            "service_wall_ms": "SpeechService.transcribe_array incl. routing/semaphore",
        },
        "limitations": [
            "synthetic TTS audio; not representative of human speech",
            "single machine, CPU inference; no GPU measurements",
            "semaphore queue wait not instrumented separately",
            "memory = RSS snapshots only if psutil available; no peak claim",
            "no network/WebSocket overhead measured",
        ],
        "environment": env_metadata(device),
        "memory": {"before": memory_snapshot()},
    }
    if report_path is not None:
        write_report(report_path, report)

    def persist_service_section(section_key, section):
        report["service_path"][section_key] = section
        report["interruption"]["pid"] = os.getpid()
        report["interruption"]["last_update"] = utc_now_iso()
        if report_path is not None:
            write_report(report_path, report)

    def clear_inflight():
        report["interruption"]["current_clip"] = None
        report["interruption"]["run_index"] = None
        report["interruption"]["concurrency_level"] = None
        report["interruption"]["round_index"] = None
        report["interruption"]["last_update"] = utc_now_iso()

    def start_sequential(clip_key, run_index, seq):
        report["service_path"]["sequential_service"] = seq
        report["interruption"]["current_clip"] = clip_key
        report["interruption"]["run_index"] = run_index
        report["interruption"]["concurrency_level"] = None
        report["interruption"]["round_index"] = None
        report["interruption"]["last_update"] = utc_now_iso()
        if report_path is not None:
            write_report(report_path, report)

    def finish_sequential(clip_key, run_index, run, seq):
        clear_inflight()
        persist_service_section("sequential_service", seq)

    def start_concurrent(level_key, round_index, conc):
        report["service_path"]["concurrent_service"] = conc
        report["interruption"]["current_clip"] = None
        report["interruption"]["run_index"] = None
        report["interruption"]["concurrency_level"] = int(level_key)
        report["interruption"]["round_index"] = round_index
        report["interruption"]["last_update"] = utc_now_iso()
        if report_path is not None:
            write_report(report_path, report)

    def finish_concurrent(level_key, round_index, round_result, conc):
        clear_inflight()
        persist_service_section("concurrent_service", conc)

    def run_stage(stage, func, apply):
        report["interruption"]["pid"] = os.getpid()
        report["interruption"]["current_stage"] = stage
        report["interruption"]["last_update"] = utc_now_iso()
        if report_path is not None:
            write_report(report_path, report)
        try:
            result = func()
            apply(result)
        except Exception as exc:
            record_failure(report, stage, exc)
            report["interruption"]["last_update"] = utc_now_iso()
            if report_path is not None:
                try:
                    write_report(report_path, report)
                except Exception as persist_exc:
                    detail = (getattr(persist_exc, "recovery_path", None)
                              or getattr(persist_exc, "temporary_path", None))
                    note = "Report persistence also failed"
                    if detail is not None:
                        note += f"; newest state at {detail}"
                    try:
                        exc.add_note(note)
                    except Exception:
                        pass
            raise
        report["completed_stages"].append(stage)
        report["interruption"]["current_stage"] = None
        report["interruption"]["last_update"] = utc_now_iso()
        if report_path is not None:
            write_report(report_path, report)
        return result

    cold_runs = getattr(args, "cold_runs", None)
    run_cold = (
        not getattr(args, "skip_cold", False)
        and isinstance(cold_runs, int)
        and cold_runs > 0
    )
    if run_cold:
        run_stage(
            "cold_start",
            lambda: run_cold_trials(device, args.cold_runs),
            lambda result: report.__setitem__("cold_start", result),
        )

    engine = run_stage(
        "model_load",
        lambda: _sensevoice_engine_class()(device=device, auto_load=True),
        lambda eng: report["memory"].__setitem__(
            "after_model_load", memory_snapshot()),
    )

    run_stage(
        "warm_inference",
        lambda: run_warm_inference(engine, args.warm_runs),
        lambda result: report.__setitem__("warm_inference", result),
    )
    run_stage(
        "decode_preprocessing",
        lambda: run_decode_preprocessing(args.warm_runs),
        lambda result: report.__setitem__("decode_preprocessing", result),
    )

    service_ctx = run_stage(
        "service_path",
        lambda: prepare_service_path(engine),
        lambda ctx: report.__setitem__("service_path", {}),
    )
    run_stage(
        "sequential_service",
        lambda: run_sequential_service(
            service_ctx,
            args.warm_runs,
            on_run=finish_sequential,
            on_start=start_sequential,
        ),
        lambda result: report["service_path"].__setitem__(
            "sequential_service", result),
    )
    run_stage(
        "concurrent_service",
        lambda: run_concurrent_service(
            service_ctx,
            args.concurrency_rounds,
            args.skip_concurrency,
            on_round=finish_concurrent,
            on_start=start_concurrent,
        ),
        lambda result: report["service_path"].__setitem__(
            "concurrent_service", result),
    )

    report["memory"]["after_benchmark"] = memory_snapshot()
    report["status"] = "complete"
    report["completed_at"] = utc_now_iso()
    report["interruption"]["current_stage"] = None
    report["interruption"]["last_update"] = utc_now_iso()
    if report_path is not None:
        write_report(report_path, report)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--warm-runs", type=int, default=20)
    parser.add_argument(
        "--cold-runs", type=int, default=None,
        help="cold-start trials per clip (opt-in; omit to skip cold start)")
    parser.add_argument("--concurrency-rounds", type=int, default=10)
    parser.add_argument("--skip-cold", action="store_true")
    parser.add_argument("--skip-concurrency", action="store_true")
    parser.add_argument("--output", default=None)
    parser.add_argument("--child-cold", default=None, metavar="CLIP_KEY")
    parser.add_argument("--result-file", default=None)
    args = parser.parse_args(argv)

    if args.child_cold:
        if not args.result_file:
            parser.error("--child-cold requires --result-file")
        run_child_cold(args.child_cold, args.device, args.result_file)
        return 0

    out_path = resolve_output_path(args.output)
    try:
        build_report(args, out_path)
    except Exception:
        print(f"Benchmark incomplete; partial report: {out_path}",
              file=sys.stderr)
        raise
    print(f"Report written: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
