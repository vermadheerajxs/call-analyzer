import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow `python src/main.py` from repo root and `python main.py` from src/
_SRC = Path(__file__).resolve().parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from paths import load_project_env

load_project_env()

from analyzer import process, warm_ollama
from db import fetch_jobs, update_result, process_all_recordings
from knowledge_rag import init_knowledge
from logger import log_line

BATCH_SIZE = int(os.getenv("BATCH_SIZE", "50"))
BASE_DELAY = int(os.getenv("BASE_DELAY", "5"))
MAX_DELAY = int(os.getenv("MAX_DELAY", "300"))
IDLE_SLEEP_SECONDS = int(os.getenv("IDLE_SLEEP_SECONDS", "60"))
CLOUD_BASE_URL = (os.getenv("CLOUD_BASE_URL") or "").strip()


def build_full_url(path: str) -> str:
    if path.startswith("http"):
        return path

    if not CLOUD_BASE_URL:
        raise ValueError(
            "CLOUD_BASE_URL is required for relative recording paths. "
            "Set it in the project .env file."
        )

    return f"{CLOUD_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


delay = BASE_DELAY


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


print(f"[{now()}] Worker started...")
_mode = "ALL recordings" if process_all_recordings() else "unprocessed only"
print(f"[{now()}] Job mode: {_mode} (PROCESS_ALL_RECORDINGS)")
log_line(f"JOB_MODE process_all={process_all_recordings()}")
print(f"[{now()}] Loading Xtended Space knowledge index...")
_kr = init_knowledge(require=False)
if _kr.ready:
    print(
        f"[{now()}] Knowledge ready method={_kr.method} "
        f"chunks={_kr.chunk_count} hash={_kr.source_hash}"
    )
    log_line(
        f"KNOWLEDGE_LOADED method={_kr.method} "
        f"chunks={_kr.chunk_count} hash={_kr.source_hash}"
    )
else:
    print(
        f"[{now()}] Knowledge unavailable "
        f"({_kr.load_error}); analysis will continue without context"
    )
    log_line(f"KNOWLEDGE_LOAD_FAIL error={_kr.load_error}")

print(f"[{now()}] Ensuring Ollama model from .env (auto-download if missing)...")
warm_ollama()

while True:
    try:
        print(f"\n[{now()}] Fetching up to {BATCH_SIZE} jobs from DB...")

        jobs = fetch_jobs(BATCH_SIZE)

        if not jobs:
            print(
                f"[{now()}] No jobs found. "
                f"Sleeping for {IDLE_SLEEP_SECONDS}s..."
            )
            time.sleep(IDLE_SLEEP_SECONDS)
            continue

        delay = BASE_DELAY
        print(f"[{now()}] Picked {len(jobs)} job(s)")
        batch_start = time.time()

        for i, (job_id, url) in enumerate(jobs, start=1):
            job_start = time.time()
            print(
                f"\n[{now()}] "
                f"Starting job {i}/{len(jobs)} "
                f"(job_id={job_id})"
            )

            try:
                full_url = build_full_url(url)
                result = process(full_url, job_id=str(job_id))
                update_result(job_id, result)
                duration = time.time() - job_start

                print(
                    f"[{now()}] "
                    f"Job {job_id} completed "
                    f"in {duration:.2f}s "
                    f"| rating={result['call_rating']}"
                )
                log_line(
                    f"SUCCESS job_id={job_id} "
                    f"rating={result['call_rating']} "
                    f"time={duration:.2f}s"
                )

            except Exception as e:
                duration = time.time() - job_start
                print(
                    f"[{now()}] "
                    f"Job {job_id} FAILED "
                    f"after {duration:.2f}s "
                    f"| error={str(e)}"
                )
                log_line(
                    f"ERROR job_id={job_id} "
                    f"time={duration:.2f}s "
                    f"error={str(e)}"
                )

        print(
            f"\n[{now()}] "
            f"Batch finished in {time.time() - batch_start:.2f}s"
        )

    except Exception as e:
        print(f"\n[{now()}] WORKER FAILURE: {str(e)}")
        log_line(f"WORKER_ERROR {str(e)}")
        print(f"[{now()}] Backing off for {delay}s...")
        time.sleep(delay)
        delay = min(delay * 2, MAX_DELAY)
        print(f"[{now()}] Resuming work...")
