import os
import json
from models import whisper_model
import ollama
import requests
import tempfile
import time
import re

from logger import log_line

# Download configuration
DOWNLOAD_TIMEOUT = 30
MAX_FILE_MB = 25

# Ollama model configuration
OLLAMA_LOCAL_MODEL = os.getenv(
    "OLLAMA_LOCAL_MODEL", "phi3:mini"
)


def download_audio(url):
    """
    Downloads audio from a given URL to a temporary file.
    Enforces timeout and maximum file size.
    """
    start = time.time()

    try:
        r = requests.get(url, stream=True, timeout=DOWNLOAD_TIMEOUT)
        r.raise_for_status()

        size = 0
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")

        for chunk in r.iter_content(1024 * 1024):
            size += len(chunk)

            if size > MAX_FILE_MB * 1024 * 1024:
                raise Exception("File too large")

            tmp.write(chunk)

        tmp.close()

        log_line(
            f"DOWNLOAD_OK size_mb={size/(1024*1024):.2f} "
            f"time={time.time()-start:.2f}s"
        )

        return tmp.name

    except Exception as e:
        log_line(f"DOWNLOAD_FAIL url={url} error={str(e)}")
        raise


def estimate_tokens(text: str) -> int:
    """
    Rough token estimation for LLaMA-style models.
    Uses a safe over-estimation strategy.
    """
    return max(256, len(text) // 3)


def calculate_context(prompt: str, buffer: int = 768) -> int:
    """
    Calculates required context size including buffer
    for system prompt and model response.
    """
    estimated = estimate_tokens(prompt)
    return estimated + buffer


def clamp_ctx(ctx: int, min_ctx=1024, max_ctx=8192) -> int:
    """
    Ensures context size stays within model-safe bounds.
    """
    return max(min_ctx, min(ctx, max_ctx))


def transcribe(path):
    """
    Transcribes and translates audio to English using Whisper.
    Returns timestamped transcript text.
    """
    start = time.time()

    try:
        segments, info = whisper_model.transcribe(
            path,
            beam_size=5,
            vad_filter=True,
            task="translate"
        )

        lines = []
        count = 0

        for seg in segments:
            s = int(seg.start)
            e = int(seg.end)
            text = seg.text.strip()

            lines.append(f"[{s:02d}-{e:02d}] {text}")
            count += 1

        transcript = "\n".join(lines)
        preview = transcript.replace("\n", " ")

        log_line(
            f"TRANSCRIPTION "
            f"segments={count} "
            f"text=\"{preview}\""
        )

        log_line(
            f"TRANSCRIBE_OK "
            f"time={time.time() - start:.2f}s "
            f"src_lang={info.language} "
            f"target_lang=en"
        )

        return transcript

    except Exception as e:
        log_line(f"TRANSCRIBE_FAIL error={str(e)}")
        raise


def analyze(text):
    """
    Sends transcription to LLM for summary, disposition,
    and call rating. Ensures strict JSON-only response.
    """
    start = time.time()

    prompt = f"""
    Analyze the following call transcription and provide:
    1. A concise AI summary of the call (2-3 sentences)
    2. Final disposition (e.g., "Interested", "Not Interested", "Follow Up Required", "Closed Won", "Closed Lost", "Callback Requested")
    3. Call rating from 1 to 10 (where 1 is poor and 10 is excellent)

    Call Transcription:
    {text}

    Please respond ONLY in the following JSON format:
    {{
    "ai_summary": "summary text here",
    "ai_disposition": "disposition here",
    "call_rating": "number from 1 to 10"
    }}
    """

    ctx_size = clamp_ctx(calculate_context(prompt))

    log_line(
        f"ANALYZE_ROUTE "
        f"mode=local "
        f"model={OLLAMA_LOCAL_MODEL} "
        f"ctx={ctx_size}"
    )

    for attempt in range(3):
        try:
            resp = ollama.chat(
                model=OLLAMA_LOCAL_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert call analyst. "
                            "Return ONLY valid JSON. "
                            "Do NOT include explanations or text outside JSON."
                        )
                    },
                    {"role": "user", "content": prompt}
                ],
                options={
                    "temperature": 0,
                    "num_ctx": ctx_size
                }
            )

            content = resp["message"]["content"].strip()

            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                raise ValueError("No JSON found in LLM output")

            data = json.loads(match.group())
            data["call_rating"] = int(data.get("call_rating", 0))

            log_line(
                "ANALYZE_RESULT "
                f"rating={data['call_rating']} "
                f"disposition=\"{data['ai_disposition']}\" "
                f"summary=\"{data['ai_summary'][:300]}\" "
                f"time={time.time()-start:.2f}s"
            )

            return data

        except Exception as e:
            log_line(f"ANALYZE_RETRY attempt={attempt+1} error={str(e)}")

            if attempt == 1:
                log_line(f"ANALYZE_FAIL error={str(e)}")
                raise


def process(url):
    """
    Full pipeline: download audio, transcribe, analyze,
    and ensure temporary file cleanup.
    """
    path = None

    try:
        log_line(f"PROCESS_START url={url}")

        path = download_audio(url)
        text = transcribe(path)
        result = analyze(text)

        log_line(
            f"PROCESS_SUCCESS "
            f"rating={result.get('call_rating')}"
        )

        return result

    except Exception as e:
        log_line(f"PROCESS_FAIL url={url} error={str(e)}")
        raise

    finally:
        if path and os.path.exists(path):
            os.remove(path)
