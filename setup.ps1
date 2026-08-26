#!/usr/bin/env pwsh
# Windows setup for Call Analyzer newcomers.
# Run once from the repo root:
#   powershell -ExecutionPolicy Bypass -File .\setup.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "== Call Analyzer setup ==" -ForegroundColor Cyan

function Test-Command($Name) {
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

# --- Chocolatey (optional helper for system deps) ---
if (-not (Test-Command "choco")) {
    Write-Host "Chocolatey not found. Installing (may prompt for admin)..."
    try {
        Set-ExecutionPolicy Bypass -Scope Process -Force
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        Invoke-Expression ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
    } catch {
        Write-Host "Chocolatey install skipped/failed. Install Python, FFmpeg, Ollama manually if needed."
    }
}

# Refresh PATH in this session
$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

# --- System packages ---
if (Test-Command "choco") {
    Write-Host "Installing/updating Python, FFmpeg, Ollama via Chocolatey..."
    choco install -y python ffmpeg ollama
} else {
    if (-not (Test-Command "python")) { throw "Python not found on PATH. Install Python 3.10+ and re-run." }
    if (-not (Test-Command "ffmpeg")) { Write-Host "WARNING: ffmpeg not found. Install it for audio decoding." }
    if (-not (Test-Command "ollama")) { Write-Host "WARNING: ollama not found. Install from https://ollama.com/download" }
}

$env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("Path", "User")

Write-Host "python: $(python --version)"
if (Test-Command "ffmpeg") { ffmpeg -version | Select-Object -First 1 }
if (Test-Command "ollama") { ollama --version }

# --- .env ---
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example — edit DB_* and CLOUD_BASE_URL before running."
    } else {
        throw "No .env or .env.example found."
    }
} else {
    Write-Host ".env already present"
}

# --- Python venv + deps ---
if (-not (Test-Path ".\venv")) {
    Write-Host "Creating venv..."
    python -m venv venv
}

& .\venv\Scripts\python.exe -m pip install --upgrade pip
$req = if (Test-Path ".\requirements.txt") { ".\requirements.txt" } else { ".\requirement.txt" }
& .\venv\Scripts\python.exe -m pip install -r $req

# --- Start Ollama if needed ---
if (Test-Command "ollama") {
    try {
        ollama list | Out-Null
    } catch {
        Write-Host "Starting Ollama serve in background..."
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }

    # Read preferred model from .env
    $model = "llama3.1:8b"
    Get-Content ".env" | ForEach-Object {
        if ($_ -match '^\s*OLLAMA_LOCAL_MODEL\s*=\s*(.+)\s*$') {
            $model = $Matches[1].Trim().Trim('"').Trim("'")
        }
    }
    Write-Host "Ensuring Ollama model '$model' (pull if missing)..."
    try {
        ollama pull $model
    } catch {
        Write-Host "Primary pull failed for '$model'. Trying llama3.1:8b ..."
        ollama pull llama3.1:8b
    }
} else {
    Write-Host "Skip Ollama pull — install Ollama, then re-run setup or just start main.py (it auto-pulls)."
}

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next:"
Write-Host "  1) Edit .env (DB_*, CLOUD_BASE_URL, OLLAMA_LOCAL_MODEL)"
Write-Host "  2) .\venv\Scripts\Activate.ps1"
Write-Host "  3) python .\src\main.py"
Write-Host ""
Write-Host "On first run, Whisper weights download automatically (no HF token needed)."
