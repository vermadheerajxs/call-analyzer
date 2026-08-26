# Call Analyzer

Local worker that analyzes Xtended Space call recordings:

**audio → Whisper transcript → business knowledge → Ollama → summary / disposition / rating → Postgres**

No OpenAI. No HF token required for normal use.

---

## Get started (3 steps)

### 1) Install once

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

**Git Bash / Linux / macOS:**
```bash
bash setup.sh
```

This installs Python deps, creates `venv`, copies `.env.example` → `.env` if needed, and tries to pull the Ollama model.

### 2) Edit `.env`

Fill in at least:

```env
DB_HOST=...
DB_NAME=...
DB_USER=...
DB_PASS=...
DB_PORT=5432
CLOUD_BASE_URL=https://your-bucket.s3.amazonaws.com
```

Defaults already set for Whisper, Ollama, knowledge, and logging. See **Config cheatsheet** below.

### 3) Run

```powershell
.\venv\Scripts\Activate.ps1
python .\src\main.py
```

Linux/macOS:
```bash
source venv/bin/activate
python src/main.py
```

First run may **download Whisper weights** (can take several minutes).  
If it sits forever on “downloads weights…”, press `Ctrl+C` and temporarily set:

```env
WHISPER_MODEL=small
```

You already may have `small` cached; switch back to `distil-large-v3` later on a better network/GPU machine.

---

## What it does

```
Postgres (pending CallLog rows)
    → download MP3 from S3 / URL
    → Whisper transcription
    → local Xtended Space knowledge (BM25)
    → Ollama (llama3.1:8b) JSON analysis
    → update aiSummary, aiDisposition, aiCallRating
```

| Output | Meaning |
|--------|---------|
| `aiSummary` | Short factual summary |
| `aiDisposition` | Closed set (Interested, Follow Up Required, …) |
| `aiCallRating` | 1–10 |

---

## Requirements

- Python 3.10+
- FFmpeg
- Ollama
- Reachable PostgreSQL (`CallLog` table)

---

## Config cheatsheet (`.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `WHISPER_MODEL` | `distil-large-v3` | STT model (`small` / `medium` / `distil-large-v3` / `large-v3`) |
| `WHISPER_DEVICE` | `auto` | `cpu` or `cuda` if available |
| `CALL_LANGUAGE` | `auto` | Lock `en` for English-only (faster) |
| `OLLAMA_LOCAL_MODEL` | `llama3.1:8b` | Analysis model (auto-pulled if missing) |
| `PROCESS_ALL_RECORDINGS` | `false` | `true` = re-analyze all URLs; `false` = only `aiSummary IS NULL` |
| `LOG_FULL_TRANSCRIPT` | `true` | Full text under `logs/transcripts/` |
| `KNOWLEDGE_ENABLED` | `true` | Local business context for Ollama |
| `KNOWLEDGE_TOP_K` | `4` | Chunks injected per call |
| `BATCH_SIZE` | `50` | Jobs per DB poll |
| `IDLE_SLEEP_SECONDS` | `60` | Sleep when queue empty |

Full template: `.env.example`

---

## Knowledge base (Xtended Space “brain”)

Human-editable markdown in `knowledge/`.  
Offline BM25 index in `.knowledge_index/` (no network during calls).

```powershell
python scripts/build_knowledge_index.py
python scripts/test_knowledge_retrieval.py
python -m unittest tests.test_knowledge -v
```

Edit a `.md` file → rebuild index → restart worker (or let startup rebuild if hash changed).

---

## Logs

| Path | Contents |
|------|----------|
| `logs/summary-YYYY-MM-DD.log` | Job progress, ratings, short previews |
| `logs/transcripts/*.txt` | **Full** transcripts (when `LOG_FULL_TRANSCRIPT=true`) |

---

## Project layout

```
setup.ps1 / setup.sh     → one-time install
.env.example             → config template
src/main.py              → worker loop
src/analyzer.py          → download / STT / analyze
src/knowledge_rag.py     → local retrieval
src/db.py                → Postgres fetch/update
src/ensure_runtime.py    → auto-download Whisper + Ollama
knowledge/               → business docs
scripts/                 → build/test knowledge index
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Stuck on Whisper download | `Ctrl+C`, set `WHISPER_MODEL=small`, restart |
| `model '…' not found` (Ollama) | `ollama pull llama3.1:8b` or let startup auto-pull |
| No jobs | Check DB; with `PROCESS_ALL_RECORDINGS=false` only NULL summaries are picked |
| Relative recording paths fail | Set `CLOUD_BASE_URL` |
| Knowledge missing | `python scripts/build_knowledge_index.py` |

That’s enough to get a newcomer from clone → running worker.
