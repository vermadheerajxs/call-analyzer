"""
Ensure runtime dependencies exist before the worker processes jobs.

- Ollama: use OLLAMA_LOCAL_MODEL from .env; pull automatically if missing
- Whisper: download via faster-whisper; repair incomplete HF cache and retry
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import ollama

from paths import PROJECT_ROOT, load_project_env

load_project_env()

# Effective model may be remapped if the env tag does not exist on Ollama Hub
EFFECTIVE_OLLAMA_MODEL = (
    os.getenv("OLLAMA_LOCAL_MODEL", "llama3.1:8b").strip() or "llama3.1:8b"
)

# Tried in order when the configured tag cannot be pulled
_OLLAMA_FALLBACKS = (
    "llama3.1:8b",
    "llama3:8b",
    "llama3.2:3b",
    "phi3:mini",
)


def _print(msg: str) -> None:
    print(msg, flush=True)


def _model_names_from_list(payload) -> set[str]:
    names: set[str] = set()
    models = []
    if isinstance(payload, dict):
        models = payload.get("models") or []
    else:
        models = getattr(payload, "models", None) or []

    for m in models:
        if isinstance(m, dict):
            name = m.get("model") or m.get("name") or ""
        else:
            name = getattr(m, "model", None) or getattr(m, "name", "") or ""
        name = str(name).strip()
        if name:
            names.add(name)
            # ollama often returns "llama3.1:8b" — also accept bare family match helpers
            if ":" in name:
                names.add(name.split(":")[0])
    return names


def _has_model(model: str) -> bool:
    try:
        names = _model_names_from_list(ollama.list())
    except Exception:
        return False

    model = model.strip()
    if model in names:
        return True
    # Match "llama3.1:8b" against listed "llama3.1:8b" / tags with digest suffixes
    for n in names:
        if n == model or n.startswith(model + "/") or n.startswith(model + ":"):
            return True
        if model.startswith(n + ":"):
            return True
    return False


def _ensure_ollama_running() -> None:
    try:
        ollama.list()
        return
    except Exception:
        pass

    _print("[setup] Ollama not reachable — trying to start it...")
    try:
        if os.name == "nt":
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            subprocess.Popen(
                ["ollama", "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
    except FileNotFoundError as e:
        raise RuntimeError(
            "Ollama is not installed or not on PATH. "
            "Run setup.ps1 / setup.sh first, then reopen the terminal."
        ) from e

    for _ in range(30):
        time.sleep(1)
        try:
            ollama.list()
            _print("[setup] Ollama is up")
            return
        except Exception:
            continue

    raise RuntimeError(
        "Could not connect to Ollama. Start it manually (`ollama serve`) and retry."
    )


def _pull_model(model: str) -> None:
    _print(f"[setup] Downloading Ollama model '{model}' (first time only, may take a while)...")
    # Stream progress if client supports it
    try:
        stream = ollama.pull(model, stream=True)
        last = ""
        for event in stream:
            if isinstance(event, dict):
                status = str(event.get("status") or "")
                if status and status != last:
                    _print(f"  {status}")
                    last = status
            else:
                status = str(getattr(event, "status", "") or "")
                if status and status != last:
                    _print(f"  {status}")
                    last = status
    except TypeError:
        ollama.pull(model)

    if not _has_model(model):
        # Some servers need a moment after pull
        time.sleep(1)
    if not _has_model(model):
        raise RuntimeError(f"Pull finished but model '{model}' still not listed")


def _candidates(preferred: str) -> list[str]:
    preferred = (preferred or "").strip()
    out: list[str] = []
    if preferred:
        out.append(preferred)
        if preferred.endswith("-instruct"):
            out.append(preferred[: -len("-instruct")])
        if preferred.endswith(":instruct"):
            out.append(preferred.replace(":instruct", ":8b"))
    for fb in _OLLAMA_FALLBACKS:
        if fb not in out:
            out.append(fb)
    return out


def ensure_ollama_model(preferred: str | None = None) -> str:
    """
    Ensure an Ollama chat model is installed locally.
    Uses .env OLLAMA_LOCAL_MODEL; pulls it if missing; falls back to known tags.
    Returns the model name that should be used for inference.
    """
    global EFFECTIVE_OLLAMA_MODEL

    preferred = (preferred or os.getenv("OLLAMA_LOCAL_MODEL", "llama3.1:8b") or "llama3.1:8b").strip()
    _ensure_ollama_running()

    errors: list[str] = []
    for model in _candidates(preferred):
        try:
            if _has_model(model):
                EFFECTIVE_OLLAMA_MODEL = model
                _print(f"[setup] Ollama model ready: {model}")
                return model
            _pull_model(model)
            EFFECTIVE_OLLAMA_MODEL = model
            _print(f"[setup] Ollama model ready: {model}")
            return model
        except Exception as e:
            errors.append(f"{model}: {e}")
            _print(f"[setup] Could not use '{model}': {e}")

    raise RuntimeError(
        "Failed to download any Ollama model. Last errors:\n- "
        + "\n- ".join(errors)
    )


def _whisper_cache_dir(model_name: str) -> Path:
    hub = Path.home() / ".cache" / "huggingface" / "hub"
    # faster-whisper uses Systran/faster-whisper-{size}
    safe = model_name.replace("/", "--")
    return hub / f"models--Systran--faster-whisper-{safe}"


def _clear_incomplete_whisper_cache(model_name: str) -> None:
    cache = _whisper_cache_dir(model_name)
    if cache.exists():
        _print(f"[setup] Clearing incomplete Whisper cache: {cache}")
        shutil.rmtree(cache, ignore_errors=True)


def load_whisper_model():
    """
    Load faster-whisper with automatic download.
    On corrupt/partial cache (missing model.bin), clear and retry once.
    """
    from faster_whisper import WhisperModel

    load_project_env()

    model_name = os.getenv("WHISPER_MODEL", "small").strip() or "small"
    device_pref = os.getenv("WHISPER_DEVICE", "auto").strip().lower() or "auto"
    compute_pref = os.getenv("WHISPER_COMPUTE_TYPE", "").strip()

    device = device_pref
    if device == "auto":
        try:
            import ctranslate2

            device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        except Exception:
            device = "cpu"

    compute_type = compute_pref or ("float16" if device == "cuda" else "int8")

    _print("Loading faster-whisper model (once)...")
    _print(f"Using Whisper model={model_name} device={device} compute_type={compute_type}")
    _print("[setup] First run downloads weights from Hugging Face (no token required).")

    last_err = None
    for attempt in range(1, 3):
        try:
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                download_root=str(PROJECT_ROOT / ".whisper_cache"),
            )
            _print("Faster-whisper model ready")
            return model, model_name, device, compute_type
        except Exception as e:
            last_err = e
            msg = str(e).lower()
            _print(f"[setup] Whisper load failed (attempt {attempt}/2): {e}")
            if attempt == 1 and (
                "model.bin" in msg
                or "unable to open" in msg
                or "timed out" in msg
                or "timeout" in msg
                or "incomplete" in msg
            ):
                _clear_incomplete_whisper_cache(model_name)
                # also clear local download_root partials
                local = PROJECT_ROOT / ".whisper_cache"
                if local.exists():
                    shutil.rmtree(local, ignore_errors=True)
                continue
            break

    raise RuntimeError(
        "Failed to load Whisper model. Check internet access to huggingface.co "
        f"and retry. Last error: {last_err}"
    ) from last_err
