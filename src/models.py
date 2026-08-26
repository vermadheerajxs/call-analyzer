"""
Load faster-whisper once at import time (weights download on first use).

Model name / device come from .env via ensure_runtime.load_whisper_model().
"""
import os

from paths import load_project_env
from ensure_runtime import load_whisper_model

load_project_env()

whisper_model, WHISPER_MODEL, device, compute_type = load_whisper_model()
