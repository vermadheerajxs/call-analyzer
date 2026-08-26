#!/usr/bin/env bash
# Cross-platform-ish setup (Git Bash on Windows, or Linux/macOS).
# Prefer setup.ps1 on native Windows PowerShell.

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "== Call Analyzer setup =="

have() { command -v "$1" >/dev/null 2>&1; }

# Windows Git Bash: use Chocolatey when available
if have choco; then
  echo "Installing Python, FFmpeg, Ollama via Chocolatey..."
  choco install -y python ffmpeg ollama || true
elif [[ "$OSTYPE" == linux-gnu* ]]; then
  if have apt-get; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl
  fi
  if ! have ollama; then
    echo "Install Ollama from https://ollama.com/download then re-run setup."
  fi
elif [[ "$OSTYPE" == darwin* ]]; then
  if have brew; then
    brew install python ffmpeg || true
    brew install --cask ollama || true
  fi
fi

PY=python3
have python3 || PY=python
have "$PY" || { echo "Python not found"; exit 1; }

if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    echo "Created .env from .env.example — edit DB_* and CLOUD_BASE_URL."
  else
    echo "Missing .env / .env.example"; exit 1
  fi
fi

if [[ ! -d venv ]]; then
  "$PY" -m venv venv
fi

# shellcheck disable=SC1091
if [[ -f venv/Scripts/activate ]]; then
  # Git Bash on Windows
  source venv/Scripts/activate
else
  source venv/bin/activate
fi

python -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  pip install -r requirements.txt
else
  pip install -r requirement.txt
fi

MODEL="$(grep -E '^\s*OLLAMA_LOCAL_MODEL\s*=' .env | tail -n1 | cut -d= -f2- | tr -d '[:space:]\"' )"
MODEL="${MODEL:-llama3.1:8b}"

if have ollama; then
  ollama list >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 & sleep 3)
  echo "Ensuring Ollama model '$MODEL'..."
  ollama pull "$MODEL" || ollama pull llama3.1:8b || true
else
  echo "Ollama not on PATH yet — main.py will try to pull when you run it."
fi

echo ""
echo "Setup complete."
echo "Next:"
echo "  1) Edit .env"
echo "  2) source venv (Scripts/activate or bin/activate)"
echo "  3) python src/main.py"
echo "Whisper downloads automatically on first run (no HF token)."
