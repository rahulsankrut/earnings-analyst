import logging
import time

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest

logger = logging.getLogger(__name__)

# Minimum seconds between model calls — keeps us under gemini-2.5-pro's
# per-minute quota on Vertex AI (typically 60 RPM = 1 RPS).
# Set to 2s to stay comfortably under the limit.
MIN_CALL_INTERVAL = 2.0


def rate_limit_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """Enforces a minimum interval between model calls to avoid 429s.

    gemini-2.5-pro on Vertex AI has a low RPM quota. A fixed minimum
    delay is more reliable than a token-bucket approach since 429s from
    ADK are thrown as exceptions (not returned as responses) and cannot
    be caught by after_model_callback.
    """
    now = time.time()
    last_call = callback_context.state.get("last_model_call_at", 0)
    elapsed = now - last_call

    if elapsed < MIN_CALL_INTERVAL:
        sleep_time = MIN_CALL_INTERVAL - elapsed
        logger.debug("Rate limiter sleeping %.2fs before model call", sleep_time)
        time.sleep(sleep_time)

    callback_context.state["last_model_call_at"] = time.time()
