import os
from datetime import datetime

# Directory where daily log files are stored
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)


def log_line(message: str):
    """
    Appends a timestamped log line to a daily rotating log file.
    A new file is created automatically for each UTC day.
    """
    today = datetime.utcnow().strftime("%Y-%m-%d")
    path = f"{LOG_DIR}/summary-{today}.log"

    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"{timestamp} | {message}\n")
