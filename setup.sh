#!/usr/bin/env bash
# One-command setup (Git Bash / Linux / macOS) from repo root:
#   bash setup.sh
#   ./setup.sh
#
# After setup: edit .env, then:
#   venv/bin/python src/main.py
#   # Windows Git Bash: venv/Scripts/python.exe src/main.py

set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

echo "== Call Analyzer setup (one-shot) =="

have() { command -v "$1" >/dev/null 2>&1; }

if have choco; then
  echo "Installing Python, FFmpeg, Ollama via Chocolatey..."
  choco install -y python ffmpeg ollama || true
elif [[ "$OSTYPE" == linux-gnu* ]]; then
  if have apt-get; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip ffmpeg curl
  fi
  if ! have ollama; then
    echo "Install Ollama from https://ollama.com/download then re-run setup (or let main.py pull later)."
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

ENV_CREATED=0
if [[ ! -f .env ]]; then
  if [[ -f .env.example ]]; then
    cp .env.example .env
    ENV_CREATED=1
    echo "Created .env from .env.example"
  else
    echo "Missing .env / .env.example"; exit 1
  fi
else
  echo ".env already present"
fi

if [[ ! -d venv ]]; then
  "$PY" -m venv venv
fi

if [[ -f venv/Scripts/python.exe ]]; then
  PYBIN="venv/Scripts/python.exe"
elif [[ -f venv/bin/python ]]; then
  PYBIN="venv/bin/python"
else
  echo "venv python not found"; exit 1
fi

"$PYBIN" -m pip install --upgrade pip
if [[ -f requirements.txt ]]; then
  "$PYBIN" -m pip install -r requirements.txt
else
  "$PYBIN" -m pip install -r requirement.txt
fi

echo "Building knowledge index..."
"$PYBIN" scripts/build_knowledge_index.py

MODEL="$(grep -E '^\s*OLLAMA_LOCAL_MODEL\s*=' .env 2>/dev/null | tail -n1 | cut -d= -f2- | tr -d '[:space:]\"' || true)"
MODEL="${MODEL:-llama3.1:8b}"

if have ollama; then
  ollama list >/dev/null 2>&1 || (ollama serve >/dev/null 2>&1 & sleep 3)
  echo "Ensuring Ollama model '$MODEL'..."
  ollama pull "$MODEL" || ollama pull llama3.1:8b || true
else
  echo "Ollama not on PATH — main.py will try to pull when you run it."
fi

echo ""
echo "Setup complete."
if [[ "$ENV_CREATED" -eq 1 ]]; then
  echo "Edit .env (DB_* and CLOUD_BASE_URL), then start:"
else
  echo "Start the worker with:"
fi
echo "  $PYBIN src/main.py"
echo "First Whisper download can take a while (no HF token needed)."
