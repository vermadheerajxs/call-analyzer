import os
from datetime import datetime, timezone

from paths import ensure_logs_dir

LOG_DIR = ensure_logs_dir()


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
