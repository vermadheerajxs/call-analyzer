# Call Analyzer

Local worker that analyzes Xtended Space call recordings:

**audio → Whisper transcript → business knowledge → Ollama → summary / disposition / rating → Postgres**

No OpenAI. No HF token required for normal use.

---

## One-command setup (after `git clone`)

From the **repo root**:

### Windows CMD
```bat
setup.cmd
```

### Windows PowerShell
```powershell
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

### Git Bash / Linux / macOS
```bash
bash setup.sh
```

That installs everything required:

1. Python / FFmpeg / Ollama (when possible)
2. `venv` + Python packages
3. `.env` from `.env.example` (if missing)
4. Local knowledge index
5. Ollama model pull

### Then edit `.env` once

Set `DB_*` and `CLOUD_BASE_URL`.

### Then start the worker

```powershell
.\venv\Scripts\python.exe .\src\main.py
```

Linux/macOS:
```bash
venv/bin/python src/main.py
```

---

## Summary

```text
git clone <repo-url>
cd call-analyzer
setup.cmd                 # or setup.ps1 / bash setup.sh
# edit .env
venv\Scripts\python.exe src\main.py
```

First run may **download Whisper weights** (can take several minutes).  
If it sits forever on “downloads weights…”, press `Ctrl+C` and temporarily set:

```env
WHISPER_MODEL=small
```

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

---

## Logs

| Path | Contents |
|------|----------|
| `logs/summary-YYYY-MM-DD.log` | Job progress, ratings, short previews |
| `logs/transcripts/*.txt` | **Full** transcripts (when `LOG_FULL_TRANSCRIPT=true`) |

---

## Project layout

```
setup.cmd / setup.ps1 / setup.sh   → one-command install
.env.example                       → config template
src/main.py                        → worker (python src/main.py)
src/analyzer.py                    → download / STT / analyze
src/knowledge_rag.py               → local retrieval
src/db.py                          → Postgres fetch/update
src/ensure_runtime.py              → auto-download Whisper + Ollama
knowledge/                         → business docs
scripts/                           → build/test knowledge index
```

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Stuck on Whisper download | `Ctrl+C`, set `WHISPER_MODEL=small`, restart |
| `model '…' not found` (Ollama) | `ollama pull llama3.1:8b` or re-run setup |
| No jobs | Check DB; with `PROCESS_ALL_RECORDINGS=false` only NULL summaries are picked |
| Relative recording paths fail | Set `CLOUD_BASE_URL` |
| Knowledge missing | `python scripts/build_knowledge_index.py` |
| `venv missing` | Run `setup.cmd` / `setup.ps1` / `bash setup.sh` first |
