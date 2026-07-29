import os

from google.adk.models import Gemini
from google.genai.types import HttpRetryOptions

from company_profiles import load_profile


# A single 429 previously killed an entire extraction run — the batch pipeline
# makes hundreds of model calls, and ADK raises _ResourceExhaustedError before
# any callback can intervene, so the fixed inter-call delay in callbacks.py
# cannot recover from one. Retry with exponential backoff at the HTTP layer.
_RETRY = HttpRetryOptions(
    attempts=6,
    initial_delay=2.0,
    max_delay=120.0,
    exp_base=2.0,
    jitter=0.3,
    http_status_codes=[429, 500, 502, 503, 504],
)


def _model(name: str) -> Gemini:
    return Gemini(model=name, retry_options=_RETRY)


MODEL = _model(os.environ.get("PHOENIX_MODEL", "gemini-2.5-pro"))
FLASH_MODEL = _model(os.environ.get("PHOENIX_FLASH_MODEL", "gemini-2.5-flash"))

# The company under analysis and its competitors. Selected by COMPANY_PROFILE.
PROFILE = load_profile()
