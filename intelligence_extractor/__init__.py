import os

from google.adk.models import Gemini

from company_profiles import load_profile

# Model transport config is shared with Phoenix rather than duplicated. Two
# copies of these settings drifted apart once already; the retry values matter
# too much to maintain twice.
#
# _RETRY: a single 429 previously killed an entire extraction run — the batch
# pipeline makes hundreds of model calls, and ADK raises
# _ResourceExhaustedError before any callback can intervene, so the fixed
# inter-call delay in callbacks.py cannot recover from one.
#
# _TimeoutGemini: retries alone still left a run hung for 107 minutes at 0%
# CPU, because ADK never sets an HTTP timeout and a stalled call is never
# retried — it just stays open.
from phoenix import _RETRY, _TimeoutGemini


def _model(name: str) -> Gemini:
    return _TimeoutGemini(model=name, retry_options=_RETRY)


MODEL = _model(os.environ.get("PHOENIX_MODEL", "gemini-2.5-pro"))
FLASH_MODEL = _model(os.environ.get("PHOENIX_FLASH_MODEL", "gemini-2.5-flash"))

# The company under analysis and its competitors. Selected by COMPANY_PROFILE.
PROFILE = load_profile()
