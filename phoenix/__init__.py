import os

from google.adk.models import Gemini
from google.genai.types import HttpRetryOptions

from company_profiles import load_profile

# See intelligence_extractor/__init__.py — ADK raises _ResourceExhaustedError
# before any callback can intervene, so 429s must be retried at the HTTP layer.
# Kept in step with the extractor's settings deliberately.
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


# C-Suite Prep Agent Package — Let Agent Engine identify it
MODEL = _model(os.environ.get("PHOENIX_MODEL", "gemini-2.5-pro"))
FLASH_MODEL = _model(os.environ.get("PHOENIX_FLASH_MODEL", "gemini-2.5-flash"))

# The company under analysis and its competitors. Selected by COMPANY_PROFILE.
PROFILE = load_profile()
