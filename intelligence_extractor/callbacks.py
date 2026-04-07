import logging
import time

from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest

logger = logging.getLogger(__name__)

# Minimum seconds between model calls.
# The extractor makes many sequential LLM calls across 3 agents × 2 loop
# iterations. 1.5s keeps us well under gemini-2.5-flash's quota while
# not making the batch pipeline excessively slow.
# Note: 429s from ADK are thrown as _ResourceExhaustedError exceptions
# before after_model_callback fires, so preemptive spacing is the only
# reliable mitigation within the callback framework.
MIN_CALL_INTERVAL = 1.5


def rate_limit_callback(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> None:
    """Enforces a minimum interval between model calls to avoid 429s."""
    now = time.time()
    last_call = callback_context.state.get("last_model_call_at", 0)
    elapsed = now - last_call

    if elapsed < MIN_CALL_INTERVAL:
        sleep_time = MIN_CALL_INTERVAL - elapsed
        logger.debug("Rate limiter sleeping %.2fs before model call", sleep_time)
        time.sleep(sleep_time)

    callback_context.state["last_model_call_at"] = time.time()
