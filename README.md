# Call Recording AI Analyzer

A local, automated system for processing call recordings and generating AI-powered insights such as summaries, dispositions, and call quality ratings.
The system uses **faster-whisper** for speech-to-text transcription and **Ollama (Llama 3)** for local LLM-based analysis.

No paid APIs are required. All processing happens locally.

---

## Overview

The pipeline performs the following steps:

1. Downloads call recordings from a URL
2. Transcribes audio using faster-whisper
3. Analyzes transcripts using Llama 3 via Ollama
4. Stores structured AI results in PostgreSQL

The worker runs continuously and processes un-analyzed call records from the database.

---

## Architecture

```
Audio URL
   ↓
Download Audio
   ↓
faster-whisper Transcription
   ↓
Llama 3 Analysis (Ollama - Local)
   ↓
PostgreSQL Update
```

---

## Key Features

* Fully local processing (privacy-friendly)
* Faster transcription using faster-whisper
* Structured JSON output from Llama 3
* Automatic retries and logging
* Minimal hardware requirements

---

## Prerequisites

Ensure the following are installed:

* Python 3.10+
* PostgreSQL
* FFmpeg
* Ollama
* Minimum 8 GB RAM (16 GB recommended)

---

## System Dependencies

### Python

```bash
python --version
```

Download if needed:
[https://www.python.org/downloads/](https://www.python.org/downloads/)

---

### FFmpeg

Required for audio decoding.

**Linux**

```bash
sudo apt update
sudo apt install ffmpeg
```

**macOS**

```bash
brew install ffmpeg
```

**Windows**

* Download from [https://ffmpeg.org/download.html](https://ffmpeg.org/download.html)
* Add `bin` directory to PATH

Verify:

```bash
ffmpeg -version
```

---

### Ollama

Install Ollama for local LLM inference:

[https://ollama.com/download](https://ollama.com/download)

Verify:

```bash
ollama --version
```

Start the service if needed:

```bash
ollama serve
```

---

## LLM Model Setup

Pull the Llama 3 model:

```bash
ollama pull llama3:8b-instruct
```

Verify:

```bash
ollama list
```

Test:

```bash
ollama run llama3 "Summarize a short customer call"
```

---

## Python Environment Setup

Create and activate a virtual environment:

```bash
python -m venv venv
source venv/bin/activate
```

Windows:

```bash
venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

---

## Required Python Packages

Example `requirements.txt`:

```txt
faster-whisper>=0.10.0
psycopg2-binary>=2.9.9
requests>=2.31.0
python-dotenv>=1.0.0
ollama>=0.1.0
```

---

## Database Setup

The system expects a PostgreSQL table similar to:

```sql
CREATE TABLE "CallLog" (
    id UUID PRIMARY KEY,
    recordingUrl TEXT NOT NULL,
    aiSummary TEXT,
    aiDisposition TEXT,
    aiCallRating INTEGER,
    updatedAt TIMESTAMP,
    createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Unprocessed calls are identified where AI fields are NULL.

---

## Environment Configuration

Create a `.env` file in the project root:

```env
DB_HOST=localhost
DB_NAME=your_db
DB_USER=your_user
DB_PASS=your_password
DB_PORT=5432

OLLAMA_LOCAL_MODEL=llama3.1:8b-instruct
```

Do not commit `.env` to version control.

---

## Running the Worker

Start the worker:

```bash
python main.py
```

The worker will:

* Poll the database
* Download audio recordings
* Transcribe calls
* Analyze transcripts
* Update AI results and timestamps
* Continue running until stopped

---

## Logging

Logs are written to the `logs/` directory and include:

* Transcription previews
* AI summaries and dispositions
* Call ratings
* Processing time
* Errors and retries

View logs in real time:

```bash
tail -f logs/summary-YYYY-MM-DD.log
```

---

## Performance Notes

* faster-whisper is 5–10x faster than standard Whisper
* Llama 3 (8B) runs well on CPU
* Typical 10-minute call:

  * Transcription: 1–3 minutes
  * Analysis: 5–15 seconds

---

## Next Steps

Planned additions:

* Simple setup script (`setup.sh` or `setup.py`)
* Automatic database migrations
* Chunking for very long calls
* Graceful shutdown and health checks

---

## Technology Stack

* Python
* faster-whisper
* Ollama
* Llama 3
* PostgreSQL
* FFmpeg

