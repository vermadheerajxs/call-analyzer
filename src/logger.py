import os
from datetime import datetime, timezone
from pathlib import Path

from paths import ensure_logs_dir, load_project_env

load_project_env()

LOG_DIR = ensure_logs_dir()
TRANSCRIPT_DIR = LOG_DIR / "transcripts"
TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)


def _log_full_transcript_enabled() -> bool:
    return (os.getenv("LOG_FULL_TRANSCRIPT") or "true").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def log_line(message: str):
    """
    Appends a timestamped log line to a daily rotating log file.
    A new file is created automatically for each UTC day.
    """
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    path = LOG_DIR / f"summary-{today}.log"
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {message}\n")


def save_full_transcript(
    transcript: str,
    *,
    job_id: str | None = None,
    src_lang: str = "",
    task: str = "",
    segments: int = 0,
) -> Path | None:
    """
    Write the complete transcript to logs/transcripts/.
    Controlled by LOG_FULL_TRANSCRIPT (default true).
    """
    if not _log_full_transcript_enabled():
        return None

    now = datetime.now(timezone.utc)
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    safe_id = (job_id or "nojid").replace("/", "_").replace("\\", "_")
    path = TRANSCRIPT_DIR / f"{stamp}_{safe_id}.txt"

    header = (
        f"job_id={job_id or ''}\n"
        f"saved_at_utc={now.isoformat()}\n"
        f"src_lang={src_lang}\n"
        f"task={task}\n"
        f"segments={segments}\n"
        f"chars={len(transcript)}\n"
        f"{'=' * 60}\n"
    )
    path.write_text(header + (transcript or ""), encoding="utf-8")
    log_line(
        f"TRANSCRIPT_SAVED path={path} chars={len(transcript or '')} "
        f"segments={segments}"
    )
    return path
