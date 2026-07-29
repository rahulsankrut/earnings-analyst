"""Unit tests for the extraction safety net.

Calling save_intelligence_report is model discretion. Observed live: the
company stage produced a complete report as its final text, escalated, and
never called the tool — the pipeline reported success while Phoenix kept
serving the previous run's report. These tests pin the recovery logic.

The decision is subtle enough to be worth testing directly, because getting
it backwards actively destroys data: state[output_key] holds the full report
when the tool was NOT called, but only a short "saved it" confirmation when
it WAS. Persisting unconditionally would overwrite good reports with that
sentence.
"""

from unittest.mock import patch

import pytest

from intelligence_extractor.agent import _ensure_report_saved, _MIN_REPORT_CHARS
from intelligence_extractor.tools.storage_tools import report_saved_flag


class _Ctx:
    def __init__(self, state):
        self.state = state


REPORT = "# INTELLIGENCE REPORT\n\n" + ("Real report body with numbers. " * 200)
CONFIRMATION = "I have completed all processing. The report has been saved to Cloud Storage."


def _run(state):
    """Runs the callback, returning what it persisted (or None).

    Invoked with the `callback_context` KEYWORD, exactly as ADK does. Calling
    it positionally hides a real defect: a callback whose parameter is named
    anything else passes a positional test and then dies in production with
    "unexpected keyword argument 'callback_context'". That is precisely what
    happened before this was pinned.
    """
    callback = _ensure_report_saved("intelligence", "intelligence_report")
    with patch(
        "intelligence_extractor.agent.persist_report",
        return_value="Successfully saved",
    ) as persist:
        callback(callback_context=_Ctx(state))
    return persist.call_args[0] if persist.called else None


def test_callback_accepts_adks_keyword_argument():
    """ADK calls after_agent_callback(callback_context=...) by keyword.

    Asserted on the signature directly so the requirement is visible, not
    implied. A mismatch here does not surface until a live run — and only
    after a full extraction stage has already burned through its searches.
    """
    import inspect

    callback = _ensure_report_saved("intelligence", "intelligence_report")
    params = inspect.signature(callback).parameters
    assert "callback_context" in params, (
        f"callback takes {list(params)}; ADK passes callback_context by keyword"
    )


def test_persists_report_when_model_skipped_the_tool():
    """The exact bug this exists for: full report in state, never saved."""
    call = _run({"intelligence_report": REPORT})
    assert call is not None, "safety net did not fire when the tool was skipped"
    content, report_type = call
    # The callback strips surrounding whitespace before persisting.
    assert content == REPORT.strip()
    assert report_type == "intelligence"


def test_does_nothing_when_the_tool_already_saved():
    """Must not overwrite a real report with the agent's closing sentence."""
    state = {
        "intelligence_report": CONFIRMATION,
        report_saved_flag("intelligence"): True,
    }
    assert _run(state) is None


def test_does_not_persist_a_short_confirmation_even_without_the_flag():
    """Belt and braces: if the flag were ever lost, length alone still
    prevents writing a status message over a real report."""
    assert _run({"intelligence_report": CONFIRMATION}) is None


def test_does_nothing_when_state_is_empty():
    assert _run({}) is None


@pytest.mark.parametrize(
    "length,should_persist",
    [(_MIN_REPORT_CHARS - 1, False), (_MIN_REPORT_CHARS + 1, True)],
)
def test_length_threshold_boundary(length, should_persist):
    call = _run({"intelligence_report": "x" * length})
    assert (call is not None) is should_persist


def test_each_report_type_uses_its_own_flag_and_key():
    """A shared flag would make one stage's save suppress another's rescue."""
    for report_type, state_key in (
        ("intelligence", "intelligence_report"),
        ("analyst", "analyst_report"),
        ("competitor", "competitor_report"),
    ):
        callback = _ensure_report_saved(report_type, state_key)
        # Flag set for a DIFFERENT type must not suppress this one.
        state = {state_key: REPORT, report_saved_flag("some_other_type"): True}
        with patch(
            "intelligence_extractor.agent.persist_report",
            return_value="Successfully saved",
        ) as persist:
            callback(callback_context=_Ctx(state))
        assert persist.called, f"{report_type} was suppressed by an unrelated flag"
        assert persist.call_args[0][1] == report_type
