"""Settings shared by every file. Reads your keys from the .env file."""
import os
from dotenv import load_dotenv

load_dotenv()

# --- Nicrron (the AI models) ---
NICRRON_API_KEY = os.getenv("NICRRON_API_KEY", "")
NICRRON_BASE_URL = "https://api.nicrron.ai/v1"
DEFAULT_MODEL = os.getenv("HOLDUP_MODEL", "nicrron/auto")

# --- PRISM (tracing + guardrails) ---
PRISM_HOST = os.getenv("PRISMTRACE_HOST", "https://prism.blockconvey.com")
PRISM_GUARDRAIL_HOST = "https://api.prism.blockconvey.com"
PRISM_PROJECT_ID = os.getenv("PRISMTRACE_PROJECT_ID", "")
PRISM_API_KEY = os.getenv("PRISMTRACE_API_KEY", "")

# --- HoldUp ---
AGENT_ID = "holdup"
AGENT_NAME = "HoldUp payment guard"
VERSION = os.getenv("HOLDUP_VERSION", "v1")      # "v1" or "v2"
HOLD_THRESHOLD = int(os.getenv("HOLDUP_THRESHOLD", "50"))  # risk score 0-100

USE_LLM = bool(NICRRON_API_KEY)
USE_PRISM = bool(PRISM_API_KEY and PRISM_PROJECT_ID)
