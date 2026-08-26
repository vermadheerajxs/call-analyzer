"""Project paths and .env loading (works from repo root or src/)."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

_SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _SRC_DIR.parent


def load_project_env() -> Path:
    """
    Load .env from project root, then optional local overrides.
    Safe to call multiple times.
    """
    # Quiet HF Windows symlink spam for newcomers
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

    root_env = PROJECT_ROOT / ".env"
    load_dotenv(root_env, override=False)
    load_dotenv(override=False)  # cwd .env if present
    return root_env


def ensure_logs_dir() -> Path:
    logs = PROJECT_ROOT / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    return logs
