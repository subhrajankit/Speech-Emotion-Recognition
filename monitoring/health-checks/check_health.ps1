# SenseAI Operational Health and Readiness PowerShell Script
param (
    [string]$BaseUrl = "http://127.0.0.1:8000"
)

$ErrorActionPreference = "Continue"

Write-Host "=================================================================" -ForegroundColor Cyan
Write-Host "  SenseAI Voice Assistant -- Health and Readiness Audit" -ForegroundColor Cyan
Write-Host "  Target: $BaseUrl" -ForegroundColor Cyan
Write-Host "=================================================================" -ForegroundColor Cyan

$allPassed = $true

# 1. Primary Health Check
$healthUrl = "$BaseUrl/health"
Write-Host "`n[1/3] Inspecting Service Health: $healthUrl" -ForegroundColor Yellow
try {
    $healthResponse = Invoke-RestMethod -Uri $healthUrl -Method Get -TimeoutSec 5
    if ($healthResponse.status -eq "healthy") {
        Write-Host "  [PASS] Primary service status is HEALTHY" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Service status is $($healthResponse.status)" -ForegroundColor Red
        $allPassed = $false
    }

    Write-Host "`n  Individual Model and Subsystem Readiness:" -ForegroundColor Yellow
    $subsystems = @(
        @{ Key="silero_vad"; Name="Silero VAD"; Field="loaded" },
        @{ Key="sensevoice_asr"; Name="SenseVoiceSmall ASR"; Field="loaded" },
        @{ Key="indic_conformer"; Name="IndicConformer-600m ASR"; Field="loaded" },
        @{ Key="llama_cpp_llm"; Name="Qwen3-1.7B LLM (llama.cpp)"; Field="connected" },
        @{ Key="indic_parler_tts"; Name="Indic Parler-TTS"; Field="loaded" },
        @{ Key="emotion_analyzer"; Name="SER and Lexical Emotion Analyzer"; Field="loaded" },
        @{ Key="emotion_storage"; Name="SQLite Emotion Storage"; Field="connected" },
        @{ Key="rag_retriever"; Name="FAISS Local Vector Retriever"; Field="loaded" }
    )

    foreach ($s in $subsystems) {
        $k = $s.Key
        $mInfo = $healthResponse.models.$k
        $field = $s.Field
        $isReady = ($mInfo -and $mInfo.$field) -or $healthResponse.mock_mode
        if ($isReady) {
            Write-Host "    [OK]   $($s.Name) : READY" -ForegroundColor Green
        } else {
            Write-Host "    [FAIL] $($s.Name) : NOT READY" -ForegroundColor Red
            $allPassed = $false
        }
    }
} catch {
    Write-Host "  [FAIL] FAILED to connect to $healthUrl : $_" -ForegroundColor Red
    $allPassed = $false
}

# 2. Transport Capabilities Check
$transportUrl = "$BaseUrl/api/transport/capabilities"
Write-Host "`n[2/3] Inspecting Dual Transport Capabilities: $transportUrl" -ForegroundColor Yellow
try {
    $transportResponse = Invoke-RestMethod -Uri $transportUrl -Method Get -TimeoutSec 5
    if ($transportResponse.webtransport -and $transportResponse.websocket) {
        Write-Host "  [PASS] WebTransport (HTTP/3) and WebSocket fallback are both ACTIVE" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Missing transport capabilities: $transportResponse" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "  [FAIL] FAILED to query transport capabilities: $_" -ForegroundColor Red
    $allPassed = $false
}

# 3. Telemetry Collector Check
$benchmarkUrl = "$BaseUrl/api/benchmark/summary"
Write-Host "`n[3/3] Inspecting Benchmark and Telemetry Engine: $benchmarkUrl" -ForegroundColor Yellow
try {
    $benchmarkResponse = Invoke-RestMethod -Uri $benchmarkUrl -Method Get -TimeoutSec 5
    if ($null -ne $benchmarkResponse -and $null -ne $benchmarkResponse.count) {
        $rec = $benchmarkResponse.count
        $cap = if ($benchmarkResponse.capacity) { $benchmarkResponse.capacity } else { 100 }
        Write-Host "  [PASS] Telemetry collector ACTIVE (Recorded: $rec, Capacity: $cap)" -ForegroundColor Green
    } else {
        Write-Host "  [FAIL] Telemetry collector returned invalid response: $benchmarkResponse" -ForegroundColor Red
        $allPassed = $false
    }
} catch {
    Write-Host "  [FAIL] FAILED to query benchmark summary: $_" -ForegroundColor Red
    $allPassed = $false
}

Write-Host "`n=================================================================" -ForegroundColor Cyan
if ($allPassed) {
    Write-Host "  AUDIT RESULT: ALL SYSTEMS OPERATIONAL AND READY (EXIT 0)" -ForegroundColor Green
    Write-Host "=================================================================" -ForegroundColor Cyan
    exit 0
} else {
    Write-Host "  AUDIT RESULT: DEGRADED HEALTH DETECTED (EXIT 1)" -ForegroundColor Red
    Write-Host "=================================================================" -ForegroundColor Cyan
    exit 1
}
