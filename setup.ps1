#!/usr/bin/env pwsh
# Windows setup for Call Analyzer newcomers — ONE command from repo root:
#   .\setup.ps1
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1
#   setup.cmd
#
# After setup: edit .env, then start with:
#   .\venv\Scripts\python.exe .\src\main.py

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== Call Analyzer setup (one-shot) ==" -ForegroundColor Cyan

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# --- Chocolatey (optional helper for system deps) ---
if (-not (Test-Command "choco")) {
    Write-Host "Chocolatey not found. Trying install (may need admin)..."
    try {
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    } catch {
        Write-Host "Chocolatey skipped. Ensure Python 3.10+, FFmpeg, and Ollama are installed."
    }
}

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

if (Test-Command "choco") {
    Write-Host "Installing/updating Python, FFmpeg, Ollama via Chocolatey..."
    choco install -y python ffmpeg ollama
} else {
    if (-not (Test-Command "python")) { throw "Python not found on PATH. Install Python 3.10+ and re-run." }
    if (-not (Test-Command "ffmpeg")) { Write-Host "WARNING: ffmpeg not found." }
    if (-not (Test-Command "ollama")) { Write-Host "WARNING: ollama not found — https://ollama.com/download" }
}

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "python: $(python --version)"

# --- .env ---
$envCreated = $false
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        $envCreated = $true
        Write-Host "Created .env from .env.example"
    } else {
        throw "No .env or .env.example found."
    }
} else {
    Write-Host ".env already present"
}

# --- venv + pip ---
if (-not (Test-Path ".\venv")) {
    Write-Host "Creating venv..."
    python -m venv venv
}

& .\venv\Scripts\python.exe -m pip install --upgrade pip
$req = if (Test-Path ".\requirements.txt") { ".\requirements.txt" } else { ".\requirement.txt" }
& .\venv\Scripts\python.exe -m pip install -r $req

# --- Knowledge index (offline BM25) ---
Write-Host "Building knowledge index..."
& .\venv\Scripts\python.exe .\scripts\build_knowledge_index.py

# --- Ollama ---
if (Test-Command "ollama") {
    try {
        ollama list | Out-Null
    } catch {
        Write-Host "Starting Ollama serve..."
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }

    $model = "llama3.1:8b"
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*OLLAMA_LOCAL_MODEL\s*=\s*(.+)\s*$') {
            $model = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    Write-Host "Ensuring Ollama model '$model'..."
    try {
        ollama pull $model
    } catch {
        Write-Host "Primary pull failed. Trying llama3.1:8b ..."
        ollama pull llama3.1:8b
    }
} else {
    Write-Host "Ollama not on PATH — main.py will try to pull later."
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
if ($envCreated) {
    Write-Host "Edit .env (DB_HOST, DB_NAME, DB_USER, DB_PASS, CLOUD_BASE_URL), then start:" -ForegroundColor Yellow
} else {
    Write-Host "Start the worker with:"
}
Write-Host "  .\venv\Scripts\python.exe .\src\main.py"
Write-Host "First Whisper download can take a while (no HF token needed)."
