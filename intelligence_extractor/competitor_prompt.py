"""Builds the competitor extraction prompt from a company profile.

The search plan is generated rather than templated: the prompt body contains
literal markdown braces, so str.format() is not safe here, and the number of
searches depends on how many competitors and segments the profile declares.

Search budget per competitor is 22 fixed queries plus one per declared segment;
sector themes are searched once and shared across all competitors. A profile
with one competitor and five segments reproduces the original 33-search plan.
"""

from __future__ import annotations

from company_profiles import CompanyProfile

# Query suffixes applied to every competitor name, grouped into the passes the
# extractor works through in order.
_PASSES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Broad Discovery", ("", "earnings", "results")),
    (
        "Analyst Dynamics",
        ("analyst questions", "Q&A transcript", "analyst follow-up", "management response"),
    ),
    (
        "Financial Metrics",
        (
            "operating margin",
            "revenue growth",
            "EBITDA",
            "free cash flow",
            "earnings per share",
            "segment operating profit",
        ),
    ),
    ("Forward-Looking", ("guidance outlook", "forecast targets", "long term framework")),
    (
        "Strategic Moves",
        (
            "acquisition divestiture",
            "capital allocation buyback dividend",
            "restructuring cost savings",
            "market share competitive position",
            "backlog orders",
            "organic growth",
        ),
    ),
)


def competitor_search_count(profile: CompanyProfile) -> int:
    """Total number of searches the generated plan will instruct."""
    per_competitor = sum(len(suffixes) for _, suffixes in _PASSES)
    return sum(
        per_competitor + len(c.segments) for c in profile.competitors
    ) + len(profile.sector_themes)


def _search_plan(profile: CompanyProfile) -> str:
    """Renders the numbered search plan, numbering continuously throughout."""
    lines: list[str] = []
    n = 0

    for competitor in profile.competitors:
        name = competitor.name
        lines.append(f"\n### {name}")
        for pass_name, suffixes in _PASSES:
            lines.append(f"\n**Pass: {pass_name}**")
            for suffix in suffixes:
                n += 1
                query = f"{name} {suffix}".strip()
                lines.append(f'{n}. "{query}"')
        if competitor.segments:
            lines.append("\n**Pass: Segment Deep Dives**")
            for segment in competitor.segments:
                n += 1
                lines.append(f'{n}. "{segment}"')

    if profile.sector_themes:
        lines.append("\n### Sector Themes (shared across all competitors)")
        for theme in profile.sector_themes:
            n += 1
            lines.append(f'{n}. "{theme}"')

    return "\n".join(lines)


def _report_skeleton(profile: CompanyProfile) -> str:
    """Renders the report structure, with per-competitor subsections."""
    names = profile.competitor_list
    per_competitor = "\n".join(
        f"### {c.name}\n"
        f"- Revenue by quarter and segment\n"
        f"- Operating margins by segment\n"
        f"- Guidance and whether they beat/missed\n"
        f"- Cash flow and capital allocation\n"
        f"- Any notable one-time items"
        for c in profile.competitors
    )
    asking = "\n".join(f"### {c.name}" for c in profile.competitors)

    return f"""# COMPETITOR INTELLIGENCE REPORT: {names.upper()}

## SECTION 1: What Analysts Are Asking

Cover each competitor separately.

{asking}

For each question found:
- The specific question (quote or closely paraphrase)
- How management responded — what landed well vs. drew follow-ups
- Which questions could spill over to our call ("{profile.competitors[0].name} \
guided down on X — are you seeing the same?")

## SECTION 2: Financial Snapshot

Key metrics for comparison, per competitor:

{per_competitor}

## SECTION 3: Competitive Landmines

Situations where a competitor's results create questions for us:
- **Who disclosed it**: which competitor
- **What they disclosed**: specific data or commentary
- **The question it triggers for us**: framed as an analyst would ask
- **Recommended response**: acknowledge, pivot to differentiation

## SECTION 4: Sector Themes Floating Across Calls

Themes analysts probe in {profile.sector}:
- Theme name and evidence from competitor transcripts
- How each competitor handled it
- Threat level (CRITICAL / HIGH / MEDIUM) for our call
- Recommended framing for our management

## SECTION 5: Competitive Question Bank (10-15 Questions)

**GROUP A — "Are you seeing the same?" (5-8 questions)**
Triggered by competitor headwinds or tailwinds.

**GROUP B — "Why not you?" (5-7 questions)**
Triggered by competitor outperformance or strategic moves.

For each: name the competitor, cite their context with specific numbers, rate
threat level, and suggest a management response."""


def build_competitor_prompt(profile: CompanyProfile) -> str:
    """Builds the full competitor extractor instruction for a profile."""
    total = competitor_search_count(profile)
    names = profile.competitor_list

    return f"""You are the Competitor Intelligence Extractor — performing exhaustive \
extraction of competitive intelligence on {names}, the competitors of \
{profile.company_name}.

You have a `search_competitor_documents` tool that queries the competitor data \
store (returns up to 10 results per query). Your job is to make MANY targeted \
searches.

**MANDATORY SEARCH PLAN — Execute ALL of these searches in order:**
{_search_plan(profile)}

Execute ALL {total} searches. Do NOT skip any.

After completing all searches, if critical sections are empty, run additional \
targeted searches. When done:
1. Call `save_intelligence_report` with `report_type="competitor"` and the FULL \
report as `report`.
2. Then escalate to signal completion.

Do NOT fabricate data. If a search returns no results, state: "No data found \
for this query." Only include information from the search tool.

Synthesize ALL results into:

---

{_report_skeleton(profile)}

---

Deliver the FULL report. Do NOT truncate. Be specific — cite each competitor's \
numbers when found, and always attribute a number to the competitor it came from.
"""
