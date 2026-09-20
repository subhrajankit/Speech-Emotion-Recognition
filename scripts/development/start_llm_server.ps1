<#
.SYNOPSIS
    Starts the local llama.cpp server for Qwen3-1.7B-GGUF with optimal low-latency flags.
.DESCRIPTION
    Runs llama-server on 127.0.0.1:8080 offloading 99 layers to GPU.
    Thinking mode is disabled in client requests by default to minimize voice response latency.
.EXAMPLE
    .\scripts\development\start_llm_server.ps1
#>

[CmdletBinding()]
param(
    [string]$Model = "unsloth/Qwen3-1.7B-GGUF:Q4_K_M",
    [int]$Port = 8080,
    [int]$GpuLayers = 99,
    [string]$HostAddress = "127.0.0.1"
)

$ErrorActionPreference = "Stop"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " SenseAI - Starting Local llama.cpp Server (Qwen3-1.7B)" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " Model:       $Model" -ForegroundColor Yellow
Write-Host " Host:        $HostAddress" -ForegroundColor Yellow
Write-Host " Port:        $Port" -ForegroundColor Yellow
Write-Host " GPU Layers:  $GpuLayers" -ForegroundColor Yellow
Write-Host " Note:        Thinking mode is disabled by default in client requests." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan

# Check if llama-server is in PATH
$llamaServerCmd = Get-Command "llama-server" -ErrorAction SilentlyContinue

if (-not $llamaServerCmd) {
    Write-Warning "llama-server executable was not found in system PATH."
    Write-Host "Please ensure llama.cpp is installed and its bin directory is added to your PATH," -ForegroundColor Yellow
    Write-Host "or run llama-server directly from its installation directory." -ForegroundColor Yellow
    Write-Host "Command to execute:" -ForegroundColor Cyan
    Write-Host "llama-server -hf $Model --host $HostAddress --port $Port --n-gpu-layers $GpuLayers" -ForegroundColor White
    exit 1
}

Write-Host "Executing: llama-server -hf $Model --host $HostAddress --port $Port --n-gpu-layers $GpuLayers" -ForegroundColor DarkGray
& llama-server -hf $Model --host $HostAddress --port $Port --n-gpu-layers $GpuLayers
