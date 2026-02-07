import time
import os
from datetime import datetime

from analyzer import process
from db import fetch_jobs, update_result
from logger import log_line
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Worker configuration
BATCH_SIZE = 50
BASE_DELAY = 5
MAX_DELAY = 300

# Base URL for resolving stored audio paths
CLOUD_BASE_URL = os.getenv("CLOUD_BASE_URL")


def build_full_url(path: str) -> str:
    """
    Converts a stored path into a full downloadable URL.
    If the path is already a URL, it is returned as-is.
    """
    if path.startswith("http"):
        return path

    return f"{CLOUD_BASE_URL.rstrip('/')}/{path.lstrip('/')}"


# Exponential backoff delay (resets on success)
delay = BASE_DELAY


def now():
    """
    Returns the current UTC timestamp as a formatted string.
    """
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


print(f"[{now()}] Worker started...")

# Main worker loop
while True:
    try:
        print(f"\n[{now()}] Fetching up to {BATCH_SIZE} jobs from DB...")

        jobs = fetch_jobs(BATCH_SIZE)

        # If no jobs are available, sleep and retry later
        if not jobs:
            print(f"[{now()}] No jobs found. Sleeping for 10 minutes...")
            time.sleep(600)
            continue

        # Reset backoff delay after successful fetch
        delay = BASE_DELAY

        print(f"[{now()}] Picked {len(jobs)} job(s)")

        batch_start = time.time()

        # Process each job in the batch sequentially
        for i, (job_id, url) in enumerate(jobs, start=1):
            job_start = time.time()

            print(
                f"\n[{now()}] "
                f"Starting job {i}/{len(jobs)} "
                f"(job_id={job_id})"
            )

            try:
                # Build downloadable URL and process the job
                full_url = build_full_url(url)
                result = process(full_url)

                # Persist analysis result back to database
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
                # Handle per-job failure without stopping the batch
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

        batch_time = time.time() - batch_start

        print(
            f"\n[{now()}] "
            f"Batch finished in {batch_time:.2f}s"
        )

    except Exception as e:
        # Handles unexpected worker-level failures
        print(f"\n[{now()}] WORKER FAILURE: {str(e)}")

        log_line(f"WORKER_ERROR {str(e)}")

        # Apply exponential backoff before retrying
        print(f"[{now()}] Backing off for {delay}s...")
        time.sleep(delay)

        delay = min(delay * 2, MAX_DELAY)
        print(f"[{now()}] Resuming work...")