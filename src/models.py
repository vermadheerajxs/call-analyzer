import os

from paths import load_project_env
from ensure_runtime import load_whisper_model

load_project_env()

whisper_model, WHISPER_MODEL, device, compute_type = load_whisper_model()
