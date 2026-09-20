#!/usr/bin/env python3
"""
SenseAI Operational Health & Readiness Verification Script
Checks /health endpoint, inspects each model's operational readiness,
and validates transport capabilities.

Exit codes:
  0: All systems healthy and ready
  1: One or more services/models degraded or unreachable
"""

import sys
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Tuple

# Ensure UTF-8 stdout encoding on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

def fetch_json(url: str, timeout: float = 5.0) -> Tuple[bool, Any, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SenseAI-HealthCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as response:
            if response.status != 200:
                return False, None, f"HTTP {response.status}"
            data = json.loads(response.read().decode("utf-8"))
            return True, data, "OK"
    except urllib.error.URLError as e:
        return False, None, str(e.reason)
    except Exception as e:
        return False, None, str(e)

def run_health_checks(base_url: str = DEFAULT_BASE_URL) -> int:
    print("=" * 65)
    print(f"  SenseAI Voice Assistant — Health & Readiness Audit")
    print(f"  Target: {base_url}")
    print("=" * 65)

    all_passed = True

    # 1. Primary Health & Models Check
    health_url = f"{base_url}/health"
    print(f"\n[1/3] Inspecting Service Health: {health_url}")
    ok, health_data, err = fetch_json(health_url)
    if not ok:
        print(f"  [FAIL] Unable to reach {health_url}: {err}")
        return 1

    overall_status = health_data.get("status", "unknown")
    mock_mode = health_data.get("mock_mode", False)
    models = health_data.get("models", {})

    print(f"  * Overall Status: {overall_status.upper()}")
    print(f"  * Mock Mode Active: {mock_mode}")

    if overall_status != "healthy":
        print(f"  [FAIL] Service status reported '{overall_status}' (expected 'healthy')")
        all_passed = False
    else:
        print("  [PASS] Primary service status is HEALTHY")

    print("\n  Individual Model & Subsystem Readiness:")
    required_subsystems = [
        ("silero_vad", "Silero VAD", "loaded"),
        ("sensevoice_asr", "SenseVoiceSmall ASR", "loaded"),
        ("indic_conformer", "IndicConformer-600m ASR", "loaded"),
        ("llama_cpp_llm", "Qwen3-1.7B LLM (llama.cpp)", "connected"),
        ("indic_parler_tts", "Indic Parler-TTS", "loaded"),
        ("emotion_analyzer", "SER + Lexical Emotion Analyzer", "loaded"),
        ("emotion_storage", "SQLite Emotion Storage", "connected"),
        ("rag_retriever", "FAISS Local Vector Retriever", "loaded"),
    ]

    for key, name, status_field in required_subsystems:
        model_info = models.get(key, {})
        is_ready = model_info.get(status_field, False) or mock_mode
        if is_ready:
            extra = " (mock)" if mock_mode else ""
            print(f"    [OK]   {name:<33}: READY{extra}")
        else:
            print(f"    [FAIL] {name:<33}: NOT READY ({status_field}=False)")
            all_passed = False

    # 2. Transport Capabilities Check
    transport_url = f"{base_url}/api/transport/capabilities"
    print(f"\n[2/3] Inspecting Dual Transport Capabilities: {transport_url}")
    ok, transport_data, err = fetch_json(transport_url)
    if not ok:
        print(f"  [FAIL] Unable to query transport capabilities: {err}")
        all_passed = False
    else:
        wt_support = transport_data.get("webtransport", False)
        ws_support = transport_data.get("websocket", False)
        streams = transport_data.get("streams", {})

        if wt_support and ws_support:
            print("  [PASS] WebTransport (HTTP/3) and WebSocket fallback are both ACTIVE")
            print(f"    * Stream A (Audio In): {streams.get('stream_a', 'configured')}")
            print(f"    * Stream B (Control) : {streams.get('stream_b', 'configured')}")
            print(f"    * Stream C (Text Out): {streams.get('stream_c', 'configured')}")
            print(f"    * Stream D (TTS Out) : {streams.get('stream_d', 'configured')}")
        else:
            print(f"  [FAIL] Missing transport protocol support: {transport_data}")
            all_passed = False

    # 3. Observability & Telemetry Pipeline Check
    benchmark_url = f"{base_url}/api/benchmark/summary"
    print(f"\n[3/3] Inspecting Benchmark & Telemetry Engine: {benchmark_url}")
    ok, benchmark_data, err = fetch_json(benchmark_url)
    if not ok:
        print(f"  [FAIL] Telemetry benchmark summary endpoint unreachable: {err}")
        all_passed = False
    else:
        recorded_count = benchmark_data.get("count", 0)
        capacity = benchmark_data.get("capacity", 100)
        print(f"  [PASS] Telemetry collector ACTIVE (Recorded: {recorded_count}, Ring Buffer Capacity: {capacity})")

    print("\n" + "=" * 65)
    if all_passed:
        print("  AUDIT RESULT: ALL SYSTEMS OPERATIONAL AND READY (EXIT 0)")
        print("=" * 65)
        return 0
    else:
        print("  AUDIT RESULT: DEGRADED HEALTH DETECTED (EXIT 1)")
        print("=" * 65)
        return 1

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE_URL
    sys.exit(run_health_checks(target))
