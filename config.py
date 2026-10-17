"""Settings shared by every file. Reads your keys from the .env file."""
import os
from dotenv import load_dotenv

load_dotenv()


def setting(name, default):
    """Reads FONY_<name>, or the old HOLDUP_<name> so existing .env files keep working."""
    return os.getenv(f"FONY_{name}") or os.getenv(f"HOLDUP_{name}") or default


# --- Nicrron (the AI models) ---
NICRRON_API_KEY = os.getenv("NICRRON_API_KEY", "")
NICRRON_BASE_URL = "https://api.nicrron.ai/v1"
DEFAULT_MODEL = setting("MODEL", "nicrron/auto")

# --- PRISM (tracing + guardrails) ---
PRISM_HOST = os.getenv("PRISMTRACE_HOST", "https://api.prism.blockconvey.com").rstrip("/")
PRISM_GUARDRAIL_HOST = PRISM_HOST
PRISM_PROJECT_ID = os.getenv("PRISMTRACE_PROJECT_ID", "")
PRISM_API_KEY = os.getenv("PRISMTRACE_API_KEY", "")

# --- Fony ---
AGENT_ID = "fony"
AGENT_NAME = "Fony payment guard"
VERSION = setting("VERSION", "v2")      # "v1" or "v2"
HOLD_THRESHOLD = int(setting("THRESHOLD", "50"))  # risk score 0-100

USE_LLM = bool(NICRRON_API_KEY)
USE_PRISM = bool(PRISM_API_KEY and PRISM_PROJECT_ID)
