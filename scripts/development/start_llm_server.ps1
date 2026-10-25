<#
.SYNOPSIS
    Starts the local llama.cpp server for Qwen3-1.7B-GGUF with optimal low-latency flags.
.DESCRIPTION
    Runs llama-server on 127.0.0.1:8080 offloading 99 layers to GPU with a 2048 token context
    and --jinja template formatting. Points directly to the cached GGUF model (-m) to prevent
    unnecessary downloads.
.EXAMPLE
    .\scripts\development\start_llm_server.ps1
#>

[CmdletBinding()]
param(
    [string]$ModelPath = "",
    [int]$Port = 8080,
    [int]$GpuLayers = 99,
    [int]$ContextSize = 2048,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

# Auto-locate cached Qwen3-1.7B-Q4_K_M.gguf if ModelPath not explicitly provided
if (-not $ModelPath) {
    $hfHub = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
    $found = Get-ChildItem -Path $hfHub -Filter "Qwen3-1.7B-Q4_K_M.gguf" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($found) {
        $ModelPath = $found.FullName
    } else {
        $foundAny = Get-ChildItem -Path $hfHub -Filter "*qwen*1.7b*.gguf" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($foundAny) {
            $ModelPath = $foundAny.FullName
        }
    }
}

if (-not $ModelPath -or -not (Test-Path $ModelPath)) {
    Write-Error "Could not locate cached Qwen3-1.7B GGUF model. Please specify -ModelPath explicitly."
    exit 1
}

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SenseAI - Starting Local llama.cpp Server (Qwen3-1.7B)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Model:       $ModelPath" -ForegroundColor Yellow
Write-Host " Host:        $HostAddress" -ForegroundColor Yellow
Write-Host " Port:        $Port" -ForegroundColor Yellow
Write-Host " Context:     $ContextSize" -ForegroundColor Yellow
Write-Host " GPU Layers:  $GpuLayers" -ForegroundColor Yellow
Write-Host " Jinja:       Enabled (--jinja)" -ForegroundColor Yellow
Write-Host " Note:        Thinking mode is suppressed in client requests." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

# Check if llama-server is in PATH
$llamaServerCmd = Get-Command "llama-server" -ErrorAction SilentlyContinue

if (-not $llamaServerCmd) {
    Write-Warning "llama-server executable was not found in system PATH."
    Write-Host "Please ensure llama.cpp is installed and its bin directory is added to your PATH," -ForegroundColor Yellow
    Write-Host "or run llama-server directly from its installation directory." -ForegroundColor Yellow
    Write-Host "Command to execute:" -ForegroundColor Cyan
    Write-Host "llama-server -m `"$ModelPath`" --host $HostAddress --port $Port -c $ContextSize --n-gpu-layers $GpuLayers --jinja" -ForegroundColor White
    exit 1
}

Write-Host "Executing: llama-server -m `"$ModelPath`" --host $HostAddress --port $Port -c $ContextSize --n-gpu-layers $GpuLayers --jinja" -ForegroundColor DarkGray
& llama-server -m "$ModelPath" --host $HostAddress --port $Port -c $ContextSize --n-gpu-layers $GpuLayers --jinja
