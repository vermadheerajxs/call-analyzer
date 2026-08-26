import os
import json
import re
import tempfile
import time

import ollama
import requests

import ensure_runtime
from ensure_runtime import ensure_ollama_model
from knowledge_rag import get_retriever
from logger import log_line
from models import whisper_model
from paths import load_project_env

load_project_env()

# Download configuration (env-overridable)
DOWNLOAD_TIMEOUT = int(os.getenv("DOWNLOAD_TIMEOUT", "60"))
MAX_FILE_MB = int(os.getenv("MAX_FILE_MB", "50"))

# Preferred model from .env — runtime may remap via ensure_ollama_model()
OLLAMA_LOCAL_MODEL = os.getenv(
    "OLLAMA_LOCAL_MODEL", "llama3.1:8b"
).strip() or "llama3.1:8b"


def _ollama_model() -> str:
    return ensure_runtime.EFFECTIVE_OLLAMA_MODEL or OLLAMA_LOCAL_MODEL

# Transcription tuning
# CALL_LANGUAGE: ISO code (e.g. "en") or "auto"
CALL_LANGUAGE = os.getenv("CALL_LANGUAGE", "en").strip().lower()
# WHISPER_TASK: "auto" | "transcribe" | "translate"
WHISPER_TASK = os.getenv("WHISPER_TASK", "auto").strip().lower()
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
WHISPER_VAD = os.getenv("WHISPER_VAD", "true").strip().lower() in (
    "1",
    "true",
    "yes",
)

# Domain hint reduces proper-noun / sales jargon errors
WHISPER_INITIAL_PROMPT = os.getenv(
    "WHISPER_INITIAL_PROMPT",
    (
        "This is a sales or customer support phone call between an agent "
        "and a customer. Speakers discuss pricing, bookings, follow-ups, "
        "and product details."
    ),
).strip()

# Closed disposition set for consistent analytics
VALID_DISPOSITIONS = (
    "Interested",
    "Not Interested",
    "Follow Up Required",
    "Callback Requested",
    "Closed Won",
    "Closed Lost",
    "No Answer",
    "Wrong Number",
    "Voicemail",
    "Other",
)

# Keep enough transcript for analysis without blowing context/latency
MAX_TRANSCRIPT_CHARS = int(os.getenv("MAX_TRANSCRIPT_CHARS", "12000"))
ANALYZE_MAX_RETRIES = int(os.getenv("ANALYZE_MAX_RETRIES", "3"))


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
            f"DOWNLOAD_OK size_mb={size / (1024 * 1024):.2f} "
            f"time={time.time() - start:.2f}s"
        )

        return tmp.name

    except Exception as e:
        log_line(f"DOWNLOAD_FAIL url={url} error={str(e)}")
        raise


def estimate_tokens(text: str) -> int:
    """Rough token estimate with safe over-estimation."""
    return max(256, len(text) // 3)


def calculate_context(prompt: str, buffer: int = 1024) -> int:
    """Required context size including system prompt + response headroom."""
    return estimate_tokens(prompt) + buffer


def clamp_ctx(ctx: int, min_ctx=2048, max_ctx=8192) -> int:
    """Keep context within model-safe bounds."""
    return max(min_ctx, min(ctx, max_ctx))


def _resolve_whisper_task(lang: str) -> str:
    """
    Prefer native transcription for English (more accurate + faster).
    Translate non-English audio into English for a uniform analysis pipeline.
    """
    if WHISPER_TASK in ("transcribe", "translate"):
        return WHISPER_TASK

    if lang.lower() in ("en", "english"):
        return "transcribe"
    return "translate"


def _format_ts(seconds: float) -> str:
    """MM:SS timestamp for clearer LLM grounding."""
    total = max(0, int(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


def _trim_transcript(transcript: str) -> str:
    """
    Keep head + tail of long calls so disposition cues at both ends survive.
    """
    if len(transcript) <= MAX_TRANSCRIPT_CHARS:
        return transcript

    head = MAX_TRANSCRIPT_CHARS * 2 // 3
    tail = MAX_TRANSCRIPT_CHARS - head - 80
    return (
        transcript[:head]
        + "\n\n...[transcript truncated for analysis]...\n\n"
        + transcript[-tail:]
    )


def _normalize_disposition(raw: str) -> str:
    """Map free-form model output onto the closed disposition set."""
    if not raw:
        return "Other"

    cleaned = re.sub(r"\s+", " ", str(raw)).strip()
    lower = cleaned.lower()

    for d in VALID_DISPOSITIONS:
        if d.lower() == lower:
            return d

    aliases = {
        "interested": "Interested",
        "hot lead": "Interested",
        "not interested": "Not Interested",
        "no interest": "Not Interested",
        "follow up": "Follow Up Required",
        "follow-up": "Follow Up Required",
        "follow up required": "Follow Up Required",
        "callback": "Callback Requested",
        "call back": "Callback Requested",
        "callback requested": "Callback Requested",
        "won": "Closed Won",
        "closed won": "Closed Won",
        "sale": "Closed Won",
        "lost": "Closed Lost",
        "closed lost": "Closed Lost",
        "no answer": "No Answer",
        "did not answer": "No Answer",
        "wrong number": "Wrong Number",
        "voicemail": "Voicemail",
        "voice mail": "Voicemail",
    }

    for key, value in aliases.items():
        if key in lower:
            return value

    return "Other"


def _clamp_rating(value) -> int:
    try:
        rating = int(float(value))
    except (TypeError, ValueError):
        rating = 5
    return max(1, min(10, rating))


def _collect_segments(segments):
    lines = []
    count = 0
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        lines.append(f"[{_format_ts(seg.start)}-{_format_ts(seg.end)}] {text}")
        count += 1
    return lines, count


def _whisper_kwargs(language, task):
    return dict(
        language=language,
        task=task,
        beam_size=WHISPER_BEAM_SIZE,
        best_of=max(1, WHISPER_BEAM_SIZE),
        patience=1.0,
        vad_filter=WHISPER_VAD,
        vad_parameters=dict(
            min_silence_duration_ms=400,
            speech_pad_ms=200,
        ),
        # Reduces looping hallucinations common on telephony audio
        condition_on_previous_text=False,
        initial_prompt=WHISPER_INITIAL_PROMPT or None,
        word_timestamps=False,
    )


def _detect_language_and_task(path):
    """
    Detect spoken language, then pick transcribe vs translate.
    Falls back to English transcription if detection is unavailable.
    """
    try:
        from faster_whisper.audio import decode_audio

        audio = decode_audio(path, sampling_rate=16000)
        lang_info = whisper_model.detect_language(audio)
        if isinstance(lang_info, tuple):
            detected_lang = lang_info[0]
        else:
            detected_lang = str(lang_info)
        return detected_lang, _resolve_whisper_task(detected_lang)
    except Exception as e:
        log_line(f"LANG_DETECT_FALLBACK error={str(e)}")
        return "en", _resolve_whisper_task("en")


def transcribe(path):
    """
    High-accuracy phone-call transcription via faster-whisper.
    Returns timestamped English (or source-language) transcript text.
    """
    start = time.time()

    try:
        if CALL_LANGUAGE in ("", "auto"):
            language, task = _detect_language_and_task(path)
        else:
            language = CALL_LANGUAGE
            task = _resolve_whisper_task(language)

        segments, info = whisper_model.transcribe(
            path, **_whisper_kwargs(language, task)
        )

        lines, count = _collect_segments(segments)
        transcript = "\n".join(lines)
        preview = transcript.replace("\n", " ")[:500]
        detected_lang = getattr(info, "language", language)

        log_line(f"TRANSCRIPTION segments={count} text=\"{preview}\"")
        log_line(
            f"TRANSCRIBE_OK time={time.time() - start:.2f}s "
            f"src_lang={detected_lang} task={task}"
        )

        return transcript

    except Exception as e:
        log_line(f"TRANSCRIBE_FAIL error={str(e)}")
        raise


def analyze(text):
    """
    Analyze transcript for summary, disposition, and call rating.
    Uses strict JSON mode + closed disposition set for reliability.
    Optionally injects retrieved Xtended Space business context (local BM25).
    """
    start = time.time()
    trimmed = _trim_transcript(text)

    disposition_list = ", ".join(VALID_DISPOSITIONS)

    # Local retrieval only — no network, no extra LLM call
    context_block = ""
    try:
        retriever = get_retriever()
        if retriever.ready:
            t0 = time.time()
            hits = retriever.retrieve(trimmed)
            context_block = retriever.format_for_prompt(hits)
            log_line(
                "KNOWLEDGE_RETRIEVE "
                f"count={len(hits)} "
                f"topics={[h.topic for h in hits]} "
                f"time_ms={int((time.time() - t0) * 1000)}"
            )
    except Exception as e:
        log_line(f"KNOWLEDGE_RETRIEVE_FAIL error={type(e).__name__}:{e}")
        context_block = ""

    if context_block:
        context_section = f"""
RELEVANT XTENDED SPACE BUSINESS CONTEXT:
{context_block}

Context rules:
- Use this only to interpret business intent (storage vs relocation vs B2B vs support).
- This is supporting knowledge about Xtended Space, NOT facts about this customer.
- The transcript is authoritative for what actually happened.
- Do not invent prices, cities, bookings, or promises from context that the transcript does not state.
"""
    else:
        context_section = ""

    prompt = f"""Analyze this phone-call transcript carefully.
You are analyzing calls for Xtended Space (storage + packers/movers / logistics).

Return a JSON object with exactly these keys:
- ai_summary: 2-3 factual sentences covering purpose, key points, and outcome
- ai_disposition: MUST be exactly one of [{disposition_list}]
- call_rating: integer 1-10 (1=very poor quality/outcome, 10=excellent)

Rules:
- Base answers only on the transcript; do not invent facts
- Interpret customer intent using business context when provided (household storage vs ghar shift vs warehouse/B2B vs pickup delay/support)
- Support/complaint calls: judge handling quality, not whether a sale closed
- Customer refusal is not automatically a low rating if the agent handled well
- If the call is unclear, short, or mostly silence/voicemail, say so and rate lower
- Prefer the most specific accurate disposition
{context_section}
Transcript:
{trimmed}
"""

    ctx_size = clamp_ctx(calculate_context(prompt))

    log_line(
        f"ANALYZE_ROUTE mode=local model={_ollama_model()} ctx={ctx_size}"
    )

    last_error = None

    for attempt in range(ANALYZE_MAX_RETRIES):
        try:
            resp = ollama.chat(
                model=_ollama_model(),
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are an expert sales/support call analyst. "
                            "Respond with ONLY a valid JSON object. "
                            "No markdown, no code fences, no extra text."
                        ),
                    },
                    {"role": "user", "content": prompt},
                ],
                format="json",
                options={
                    "temperature": 0,
                    "num_ctx": ctx_size,
                    "num_predict": 512,
                },
                keep_alive="10m",
            )

            content = (resp.get("message") or {}).get("content", "").strip()
            if not content:
                raise ValueError("Empty LLM response")

            match = re.search(r"\{[\s\S]*\}", content)
            if not match:
                raise ValueError("No JSON found in LLM output")

            data = json.loads(match.group())

            summary = str(data.get("ai_summary", "")).strip()
            if not summary:
                raise ValueError("Missing ai_summary")

            data["ai_summary"] = summary
            data["ai_disposition"] = _normalize_disposition(
                data.get("ai_disposition", "")
            )
            data["call_rating"] = _clamp_rating(data.get("call_rating", 5))

            log_line(
                "ANALYZE_RESULT "
                f"rating={data['call_rating']} "
                f"disposition=\"{data['ai_disposition']}\" "
                f"summary=\"{data['ai_summary'][:300]}\" "
                f"time={time.time() - start:.2f}s"
            )

            return data

        except Exception as e:
            last_error = e
            err = str(e).lower()
            log_line(
                f"ANALYZE_RETRY attempt={attempt + 1}/{ANALYZE_MAX_RETRIES} "
                f"error={str(e)}"
            )
            # Auto-heal missing model mid-run
            if "not found" in err or "404" in err:
                try:
                    ensure_ollama_model(OLLAMA_LOCAL_MODEL)
                except Exception as pull_err:
                    log_line(f"ANALYZE_PULL_FAIL error={pull_err}")

    log_line(f"ANALYZE_FAIL error={str(last_error)}")
    raise last_error


def warm_ollama():
    """
    Ensure the configured Ollama model exists (download if needed),
    then preload it so the first job is not cold-started.
    """
    try:
        model = ensure_ollama_model(OLLAMA_LOCAL_MODEL)
        ollama.chat(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            options={"num_predict": 1, "temperature": 0},
            keep_alive="10m",
        )
        log_line(f"OLLAMA_WARM model={model}")
        print(f"[setup] Ollama warmed: {model}", flush=True)
    except Exception as e:
        log_line(f"OLLAMA_WARM_FAIL model={OLLAMA_LOCAL_MODEL} error={str(e)}")
        raise RuntimeError(
            f"Ollama model setup failed for '{OLLAMA_LOCAL_MODEL}': {e}"
        ) from e

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

        if not text.strip():
            result = {
                "ai_summary": (
                    "No intelligible speech detected in the recording."
                ),
                "ai_disposition": "No Answer",
                "call_rating": 1,
            }
            log_line("PROCESS_SUCCESS rating=1 empty_transcript=1")
            return result

        result = analyze(text)

        log_line(f"PROCESS_SUCCESS rating={result.get('call_rating')}")
        return result

    except Exception as e:
        log_line(f"PROCESS_FAIL url={url} error={str(e)}")
        raise

    finally:
        if path and os.path.exists(path):
            os.remove(path)
