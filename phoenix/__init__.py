import os
from functools import cached_property

from google.adk.models import Gemini
from google.adk.planners import BuiltInPlanner
from google.genai import types as genai_types
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

# Ceiling on a single model call, in milliseconds. Generous, because an
# extractor generating a 40KB report legitimately takes minutes — this exists
# to bound a stall, not to police normal latency.
_REQUEST_TIMEOUT_MS = 600_000

# Region that serves the MODELS, which is not the region the agents are
# deployed to. gemini-3.5/3.6-flash serve only from the global endpoint: they
# appear in us-central1's models.list() but a generate_content call there
# returns 404 NOT_FOUND. GOOGLE_CLOUD_LOCATION stays us-central1 for Agent
# Engine; only model traffic goes global.
_MODEL_LOCATION = os.environ.get("MODEL_LOCATION", "global")


class _TimeoutGemini(Gemini):
    """Gemini with a request timeout.

    ADK builds its client as HttpOptions(headers, retry_options, base_url) and
    never sets a timeout, so a connection that stalls waits indefinitely.
    Observed live: an extraction run sat at 0% CPU for 107 minutes mid-stage
    before being killed. Retries do not help here — there is nothing to retry
    while the original call is still open, which is why the retry_options
    above were not enough on their own.
    """

    @cached_property
    def api_client(self):
        from google.genai import Client

        # _tracking_headers is ADK-internal; degrade rather than break if a
        # future version renames it.
        headers = (
            self._tracking_headers()
            if hasattr(self, "_tracking_headers")
            else None
        )
        return Client(
            vertexai=True,
            project=os.environ.get("GOOGLE_CLOUD_PROJECT") or None,
            location=_MODEL_LOCATION,
            http_options=genai_types.HttpOptions(
                headers=headers,
                retry_options=self.retry_options,
                base_url=self.base_url,
                timeout=_REQUEST_TIMEOUT_MS,
            ),
        )


def _model(name: str) -> Gemini:
    return _TimeoutGemini(model=name, retry_options=_RETRY)


# Surfaces the model's reasoning as separate "thought" parts alongside the
# answer, so a client can show how a conclusion was reached. Attached to every
# agent via the `planner` field.
#
# This is worth having here specifically: the product's value rests on figures
# being defensible, and the thought stream shows which sources a number was
# drawn from and where the model hedged. Whether a given client renders thought
# parts is up to that client — the agent emits them either way.
THINKING = BuiltInPlanner(
    thinking_config=genai_types.ThinkingConfig(include_thoughts=True)
)


# C-Suite Prep Agent Package — Let Agent Engine identify it
MODEL = _model(os.environ.get("PHOENIX_MODEL", "gemini-3.6-flash"))
FLASH_MODEL = _model(os.environ.get("PHOENIX_FLASH_MODEL", "gemini-3.6-flash"))

# The company under analysis and its competitors. Selected by COMPANY_PROFILE.
PROFILE = load_profile()
