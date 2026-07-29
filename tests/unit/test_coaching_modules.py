"""Unit tests for the coaching module registry and report provenance.

Deterministic checks on wiring and string generation — no model calls, no GCP.
"""

import pytest

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
