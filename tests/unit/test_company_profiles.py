"""Unit tests for company profile loading and competitor prompt generation.

These are deterministic checks on parsing and string generation — no model
calls. Agent *behaviour* belongs in tests/eval, not here.
"""

import pytest

from company_profiles import available_profiles, load_profile
from company_profiles.profile import CompanyProfile, ProfileError
from intelligence_extractor.competitor_prompt import (
    build_competitor_prompt,
    competitor_search_count,
)


def _profile(**overrides) -> CompanyProfile:
    data = {
        "company_name": "Test Co",
        "sector": "widgets",
        "sector_themes": ["theme one", "theme two"],
        "competitors": [{"name": "Rival", "segments": ["Segment A"]}],
    }
    data.update(overrides)
    return CompanyProfile.from_dict(data, source="test")


def test_shipped_profiles_load():
    for name in available_profiles():
        assert load_profile(name).company_name


def test_alphabet_profile_shape():
    p = load_profile("alphabet")
    assert p.company_name == "Alphabet"
    assert p.competitor_names == ("Microsoft", "Amazon")
    assert p.customer_label == "alphabet"
    assert all(c.segments for c in p.competitors)


@pytest.mark.parametrize(
    "names,expected",
    [
        (["Solo"], "Solo"),
        (["A", "B"], "A and B"),
        (["A", "B", "C"], "A, B and C"),
    ],
)
def test_competitor_list_phrasing(names, expected):
    p = _profile(competitors=[{"name": n} for n in names])
    assert p.competitor_list == expected


def test_empty_competitors_rejected():
    """A profile with no competitors is a misconfiguration, not a valid state.

    The competitor pipeline would run an empty search plan and produce an
    empty report, so fail at load time instead.
    """
    with pytest.raises(ProfileError, match="missing required field"):
        _profile(competitors=[])


def test_competitor_list_degrades_gracefully_if_constructed_empty():
    # Reachable only by bypassing from_dict validation.
    bare = CompanyProfile(
        company_name="X", sector="y", customer_label="x",
        sector_themes=(), competitors=(),
    )
    assert bare.competitor_list == "the competitor set"


def test_customer_label_defaults_to_slug():
    assert _profile(company_name="Acme Widgets Inc").customer_label == "acme-widgets-inc"


def test_search_count_matches_original_plan():
    """The generated plan must reproduce the original hand-written budget.

    The pre-refactor prompt hardcoded 33 searches for one competitor with
    five segments and six sector themes. Regression guard on the formula.
    """
    legacy = _profile(
        sector_themes=[f"t{i}" for i in range(6)],
        competitors=[{"name": "Carrier", "segments": [f"s{i}" for i in range(5)]}],
    )
    assert competitor_search_count(legacy) == 33


def test_search_count_scales_with_competitors():
    one = competitor_search_count(_profile())
    two = competitor_search_count(
        _profile(
            competitors=[
                {"name": "Rival", "segments": ["Segment A"]},
                {"name": "Other", "segments": ["Segment B"]},
            ]
        )
    )
    # Each extra competitor adds its own fixed queries plus its segments.
    assert two > one


def test_prompt_names_every_competitor_and_numbers_continuously():
    p = _profile(
        competitors=[
            {"name": "Alpha", "segments": ["Seg1"]},
            {"name": "Beta", "segments": ["Seg2"]},
        ]
    )
    prompt = build_competitor_prompt(p)
    assert "Alpha" in prompt and "Beta" in prompt
    total = competitor_search_count(p)
    # Numbering runs 1..total with no restart between competitors.
    assert f"{total}. " in prompt
    assert f"{total + 1}. " not in prompt
    assert f"Execute ALL {total} searches" in prompt


def test_prompt_carries_no_legacy_hardcoding():
    prompt = build_competitor_prompt(load_profile("alphabet"))
    for stale in ("Carrier", "Trane", "HVAC", "JCI"):
        assert stale not in prompt


def test_unknown_profile_raises():
    with pytest.raises(ProfileError, match="No profile named"):
        load_profile("does-not-exist")


def test_missing_required_fields_raise():
    with pytest.raises(ProfileError, match="missing required field"):
        CompanyProfile.from_dict({"company_name": "X"}, source="test")


def test_competitor_without_name_raises():
    with pytest.raises(ProfileError, match="non-empty 'name'"):
        _profile(competitors=[{"segments": ["a"]}])
