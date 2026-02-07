import os
from dotenv import load_dotenv
from faster_whisper import WhisperModel

# Load environment variables from .env file
load_dotenv()

# Whisper model name (configurable via environment)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")

# Log model initialization once at startup
print("Loading fast-whisper model (once)...")
print(f"Using Whisper model: {WHISPER_MODEL}")

# Initialize Whisper model
# device controls CPU or GPU usage
# compute_type controls precision and performance trade-offs
whisper_model = WhisperModel(
    WHISPER_MODEL,
    device="cpu",
    compute_type="int8"
)

print("Fast-whisper model ready")
