"""Unit tests for the coaching module registry and report provenance.

Deterministic checks on wiring and string generation — no model calls, no GCP.
"""

import pytest
from google.adk.agents import LoopAgent, SequentialAgent

from phoenix.agent import phoenix_agent
from phoenix.sub_agents.modules import MODULES, MODULES_BY_KEY, menu_markdown
from phoenix.tools import intelligence_store
from phoenix.tools.intelligence_store import _provenance_banner, _report_age_days
from intelligence_extractor.tools import storage_tools


# ---------------------------------------------------------------------------
# Module registry
# ---------------------------------------------------------------------------


def test_module_keys_are_unique():
    keys = [m.key for m in MODULES]
    assert len(keys) == len(set(keys))


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.key)
def test_module_is_fully_specified(module):
    assert module.title
    assert module.menu_summary
    assert module.recommend_when
    assert module.focus.strip()


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.key)
def test_state_key_avoids_reserved_adk_prefixes(module):
    """ADK reserves app:, user: and temp: — a colon key invites confusion."""
    assert ":" not in module.state_key
    assert module.state_key.startswith("module_")


@pytest.mark.parametrize("module", MODULES, ids=lambda m: m.key)
def test_every_module_has_at_least_one_tool(module):
    """A module with no tools has nothing to ground its output in."""
    assert module.tools


def test_menu_lists_every_module():
    menu = menu_markdown()
    for module in MODULES:
        assert module.title in menu
        assert module.menu_summary in menu


def test_registry_lookup_matches():
    for key, module in MODULES_BY_KEY.items():
        assert module.key == key


# ---------------------------------------------------------------------------
# Reviser: the fix for "the loop's last output was never verified"
#
# LoopAgent(synthesise, verify) always ends on a synthesise step, so without a
# step after the loop, the draft the executive actually reads was never
# fact-checked. Each verified module is Sequential(verify_loop, reviser) so
# the reviser — which reads the newest draft and the newest findings — has
# the final word.
# ---------------------------------------------------------------------------


def _verified_module_agent(module_key):
    agent = next(a for a in phoenix_agent.sub_agents if a.name.startswith(module_key))
    assert isinstance(agent, SequentialAgent), (
        f"{agent.name} is {type(agent).__name__}, expected SequentialAgent — "
        f"has the reviser-after-loop fix regressed?"
    )
    loop, reviser = agent.sub_agents
    return loop, reviser


def _verifier_agent(module_key):
    loop, _ = _verified_module_agent(module_key)
    (inner,) = loop.sub_agents
    _, verifier = inner.sub_agents
    return verifier


class _FakeReadonlyContext:
    """Minimal stand-in for ADK's ReadonlyContext — just needs .state."""

    def __init__(self, state: dict):
        self.state = state


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_reviser_runs_after_the_loop_not_inside_it(module):
    loop, reviser = _verified_module_agent(module.key)
    assert isinstance(loop, LoopAgent)
    # The reviser must not be one of the agents the loop iterates — it runs
    # exactly once, after the loop has finished, not on every iteration.
    (inner,) = loop.sub_agents
    loop_members = {a.name for a in inner.sub_agents}
    assert reviser.name not in loop_members


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_reviser_has_the_final_word(module):
    """The reviser must write the module's real output key.

    If it wrote anything else, the loop's last (unverified) synthesiser draft
    would remain in state and reach the executive unchecked.
    """
    _, reviser = _verified_module_agent(module.key)
    assert reviser.output_key == module.state_key


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_reviser_has_no_tools(module):
    """No tools means no new unverified claims can enter at the last step."""
    _, reviser = _verified_module_agent(module.key)
    assert not reviser.tools


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_reviser_instruction_is_state_aware(module):
    """A static string could not read the draft or verification findings —
    the instruction must be a callable that reads ctx.state."""
    _, reviser = _verified_module_agent(module.key)
    assert callable(reviser.instruction)


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_verifier_instruction_is_state_aware(module):
    """The verifier must read the draft's actual text out of state, not just
    describe where it lives in prose. A model told "the draft is in
    state[...]" cannot reliably find it in its own conversation history —
    live testing showed it sometimes asks the user to supply the draft
    instead, stalling the loop entirely."""
    verifier = _verifier_agent(module.key)
    assert callable(verifier.instruction)


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_instruction_callables_actually_return_text(module):
    """Calls the instruction callables directly, the way ADK would.

    Guards against exactly the bug this suite exists to catch: a callable
    that is present and correctly typed but returns None because its inner
    function was defined and never returned. That bug does not fail an
    isinstance/callable check — it only surfaces as a pydantic ValidationError
    deep in Agent construction, or silently at runtime.
    """
    _, reviser = _verified_module_agent(module.key)
    verifier = _verifier_agent(module.key)

    ctx = _FakeReadonlyContext(
        {module.state_key: "Draft text.", "verification_report": "Some findings."}
    )
    for name, instruction in (("reviser", reviser.instruction), ("verifier", verifier.instruction)):
        result = instruction(ctx)
        assert isinstance(result, str) and result.strip(), (
            f"{module.key} {name} instruction returned {result!r} instead of text"
        )


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_verifier_embeds_the_actual_draft_text(module):
    """The regression this test targets directly: does calling the verifier's
    instruction with a draft in state produce a prompt containing that draft's
    actual text, not just a reference to where it should be found?"""
    verifier = _verifier_agent(module.key)
    marker = "UNIQUE-DRAFT-CONTENT-Q3-REVENUE-4POINT19-BILLION"
    ctx = _FakeReadonlyContext({module.state_key: marker})
    prompt = verifier.instruction(ctx)
    assert marker in prompt


@pytest.mark.parametrize(
    "module", [m for m in MODULES if m.verified], ids=lambda m: m.key
)
def test_verifier_handles_missing_draft_without_crashing(module):
    """An empty or missing draft must not raise — it is a real (if unlikely)
    state, since the verifier always runs after the synthesiser but a future
    change could break that ordering."""
    verifier = _verifier_agent(module.key)
    ctx = _FakeReadonlyContext({})
    result = verifier.instruction(ctx)
    assert isinstance(result, str) and result.strip()


# ---------------------------------------------------------------------------
# Report provenance and namespacing
# ---------------------------------------------------------------------------


def test_report_paths_are_namespaced_by_profile():
    """Two companies must not collide in one INTELLIGENCE_BUCKET."""
    assert intelligence_store.REPORT_PREFIX.startswith("reports/")
    assert intelligence_store.REPORT_PREFIX != "reports/"


def test_reader_and_writer_agree_on_paths():
    """The path constants are duplicated across two modules — keep them in step.

    The extractor writes these paths and Phoenix reads them; if they drift,
    Phoenix silently reports no intelligence at all.
    """
    assert intelligence_store.INTELLIGENCE_REPORT_PATH == storage_tools.INTELLIGENCE_REPORT_PATH
    assert intelligence_store.ANALYST_REPORT_PATH == storage_tools.ANALYST_REPORT_PATH
    assert intelligence_store.COMPETITOR_REPORT_PATH == storage_tools.COMPETITOR_REPORT_PATH
    assert intelligence_store.METADATA_PATH == storage_tools.METADATA_PATH


def _banner(**meta):
    base = {
        "intelligence_extracted_at": "2099-01-01T00:00:00+00:00",
        "profile": intelligence_store.load_profile().profile_name,
        "company_name": "Test Co",
    }
    base.update(meta)
    return _provenance_banner(base, "intelligence_extracted_at", "Intelligence report")


def test_banner_names_the_company_and_date():
    out = _banner()
    assert "Test Co" in out
    assert "MISMATCH" not in out


def test_banner_flags_profile_mismatch():
    """The failure mode this exists to prevent: briefing on another company."""
    out = _banner(profile="some-other-company")
    assert "PROFILE MISMATCH" in out
    assert "DIFFERENT COMPANY" in out


def test_banner_flags_stale_reports():
    out = _banner(intelligence_extracted_at="2020-01-01T00:00:00+00:00")
    assert "STALE" in out


def test_banner_survives_unparseable_timestamp():
    """Missing or malformed timestamps must not break report reading."""
    out = _banner(intelligence_extracted_at="unknown")
    assert "Intelligence report" in out
    assert "STALE" not in out


def test_report_age_returns_none_for_garbage():
    assert _report_age_days("not-a-date") is None
    assert _report_age_days(None) is None
