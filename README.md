# Call Recording AI Analyzer

Local worker: download call audio → Whisper transcription → Ollama analysis → PostgreSQL update.

## Quick start (new machine)

### Windows (recommended)

```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
# edit .env (DB_*, CLOUD_BASE_URL, OLLAMA_LOCAL_MODEL)
.\venv\Scripts\Activate.ps1
python .\src\main.py
```

### Git Bash / Linux / macOS

```bash
bash setup.sh
# edit .env
source venv/Scripts/activate   # Windows Git Bash
# source venv/bin/activate     # Linux/macOS
python src/main.py
```

## What happens automatically

| Dependency | Behavior |
|------------|----------|
| Whisper model (`WHISPER_MODEL`) | Downloaded on first run (no Hugging Face token) |
| Ollama model (`OLLAMA_LOCAL_MODEL`) | Pulled on startup if missing; falls back to `llama3.1:8b` / `phi3:mini` if the env tag 404s |
| Incomplete Whisper cache | Cleared and retried once |
| `.env` | Loaded from project root whether you run from root or `src/` |

You do **not** need an HF token.

## Environment

Copy `.env.example` → `.env` (setup does this if missing).

Important keys:

```env
DB_HOST=...
DB_NAME=...
DB_USER=...
DB_PASS=...
DB_PORT=5432
CLOUD_BASE_URL=https://your-bucket.s3.amazonaws.com
WHISPER_MODEL=small
OLLAMA_LOCAL_MODEL=llama3.1:8b
```

Use a real Ollama tag (`ollama list` / Hub names). Prefer `llama3.1:8b` over invented tags like `llama3.1:8b-instruct` (often 404).

## Pipeline

```
Audio URL → download → faster-whisper → Ollama JSON (summary, disposition, rating) → CallLog update
```

Only rows with `aiSummary IS NULL` are processed.

## Requirements

- Python 3.10+
- FFmpeg
- Ollama
- PostgreSQL reachable with the `.env` credentials

## Logs

Daily files under `logs/summary-YYYY-MM-DD.log`.
