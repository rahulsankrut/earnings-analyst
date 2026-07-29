"""Coaching modules — the units of the earnings-prep journey.

Phoenix previously produced one monolithic briefing, which forced all three
intelligence reports into context and handed the executive a wall of markdown.
Each module here is instead a small, focused unit that reads only what it needs.
Scoping tools per module is what bounds context — no new read tools required.

Every synthesis module runs as:

    LoopAgent(max_iterations=3)
      └── SequentialAgent
            ├── <module>_synthesizer   -> state["module_<key>"]
            └── <module>_verifier      -> state["verification_report"]

The verifier escalates only when nothing is unresolved, so the loop iterates and
the synthesiser revises against the verification report. Output written to
state["module_<key>"] is what the PDF export later compiles.
"""

from dataclasses import dataclass, field
from typing import Callable

from google.adk.agents import Agent, LoopAgent, SequentialAgent

from .. import FLASH_MODEL, THINKING
from ..callbacks import rate_limit_callback
from ..tools.document_tools import (
    search_historical_documents,
    search_competitor_documents,
)
from ..tools.intelligence_store import (
    read_intelligence_report,
    read_analyst_report,
    read_competitor_report,
)
from .verification_agent import build_verification_agent

# ---------------------------------------------------------------------------
# Shared response contract
# ---------------------------------------------------------------------------

# Applied to every module so the journey reads as one product rather than five
# differently-shaped documents. Gemini Enterprise renders markdown, so this is
# a markdown contract — there is no rich-component renderer in play.
RESPONSE_CONTRACT = """
## Response format

These are rules about **presentation, not length**. Cover everything the
executive needs — completeness matters more than brevity, because a question
you left out is a question they face unprepared. Your job is to make all of it
readable under pressure.

**Open with the headline.** Start with `## What matters` — the things the
executive must walk away with, each stated as a single clear sentence, most
important first. No preamble before it.

**Then the detail**, under `###` subheadings that name what they contain, so
the page can be navigated by scanning the headings alone.

**Use tables for anything enumerable.** Predicted questions, metric
comparisons, threat rankings — tables, never prose lists:

| Question | Threat | Recommended response |
|---|---|---|
| ... | CRITICAL | ... |

**Sources go in a footer, not in sentences.** Do not interrupt prose with
`[SOURCE: ...]`. End each `###` section with one line:

`_Sources: pre-extracted analyst report; Q3 10-Q_`

Use `[UNVERIFIED]` inline where a claim failed verification — that one belongs
next to the number, because it changes how the executive may use it.

**Make long material scannable.** Short paragraphs, one idea each. Bold the
numbers and terms that carry weight. Break a long section into subsections
rather than letting it run as unbroken prose. Length is fine; a wall of text
is not.

**Voice.** Executive-level. Direct. No hedging ("perhaps", "it seems"), no
filler, no restating the question back.

**Do not render a menu of next steps.** Phoenix handles navigation; end with
your content.
"""


# ---------------------------------------------------------------------------
# Module definitions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoachingModule:
    """One unit of the coaching journey."""

    key: str
    title: str
    menu_summary: str  # one line, shown in the menu
    recommend_when: str  # helps Phoenix decide what to recommend
    focus: str  # module-specific synthesis instructions
    tools: tuple = field(default_factory=tuple)
    verified: bool = True  # False for interactive modules

    @property
    def agent_name(self) -> str:
        return f"{self.key}_module"

    @property
    def state_key(self) -> str:
        # Deliberately not "module:<key>" — ADK reserves the app:, user: and
        # temp: state prefixes, so a colon-delimited key invites confusion.
        return f"module_{self.key}"


MODULES: tuple = (
    CoachingModule(
        key="guidance_credibility",
        title="Guidance Credibility",
        menu_summary="How your guidance track record will be scrutinised, and where you are exposed.",
        recommend_when="The quarter revised, raised, lowered, or reaffirmed guidance, or missed a prior target.",
        tools=(read_intelligence_report,),
        focus="""Assess how credible this management team's forward guidance looks
right now, from the outside.

Cover: the guidance track record across available quarters (set vs. delivered);
where the current quarter's guidance departs from the prior trend; the specific
credibility attacks an analyst can mount from that record; and the strongest
honest framing for each.""",
    ),
    CoachingModule(
        key="analyst_ambush",
        title="Analyst Ambush Prep",
        menu_summary="Who will ask what, in what style, and how each one escalates.",
        recommend_when="Always valuable. Strongest when the executive is unsure who will be on the call.",
        tools=(read_analyst_report,),
        focus="""Prepare the executive for the specific people on the call.

Cover: the analysts most likely to speak, ranked by likely aggressiveness this
quarter; each one's core obsessions and questioning style; the exact opening
question each is likely to use; and how each escalates when unsatisfied. Include
the follow-up, not just the first question — the follow-up is where executives
get caught.""",
    ),
    CoachingModule(
        key="competitor_landmines",
        title="Competitor Landmines",
        menu_summary="What competitors disclosed that creates questions for you.",
        recommend_when="A competitor has already reported this quarter, or the executive asks about positioning.",
        tools=(read_competitor_report,),
        focus="""Surface the competitive setups that turn into questions.

Cover, per competitor: what they disclosed that invites a comparison; the
question it triggers, phrased as an analyst would actually ask it; and a
recommended response that acknowledges the fact and pivots to differentiation.
Always attribute a number to the competitor it came from.""",
    ),
    CoachingModule(
        key="financial_deep_dive",
        title="Financial Deep Dive",
        menu_summary="The numbers behind the quarter and the trends analysts will probe.",
        recommend_when="The executive wants command of the underlying metrics, or the quarter has an unusual line item.",
        tools=(read_intelligence_report, search_historical_documents),
        focus="""Build the executive's command of their own numbers.

Cover: the metrics that moved most and why; multi-quarter trends an analyst
could frame unfavourably; any one-time or non-recurring items and how to
characterise them; and the derived ratios analysts compute themselves. Search
the historical data store for anything the pre-extracted report does not
cover.""",
    ),
    CoachingModule(
        key="qa_drill",
        title="Q&A Drill",
        menu_summary="Interactive practice — I ask, you answer, I critique.",
        recommend_when="Offer once at least one other module is complete, as the way to rehearse.",
        tools=(search_historical_documents,),
        verified=False,
        focus="""Run an interactive drill. This is a conversation, not a document.

Ask ONE question at a time, in the voice and style of a specific named analyst
drawn from the completed modules in session state. Wait for the executive's
answer. Then critique it: what landed, what a hostile analyst does with the
weak part, and a stronger formulation. Then ask the follow-up that analyst would
actually ask.

Escalate difficulty as they improve. Never ask the next question before
critiquing the previous answer. Keep each turn short — this is a drill, not a
briefing.""",
    ),
)

MODULES_BY_KEY = {m.key: m for m in MODULES}


# ---------------------------------------------------------------------------
# Agent construction
# ---------------------------------------------------------------------------


def _synthesizer_prompt(module: CoachingModule) -> str:
    return f"""You are the {module.title} specialist within Phoenix, the C-Suite
earnings prep advisor.

{module.focus}

## Working method

Load your source material with the tools available to you. Ground every claim in
what you read — this is the executive's real earnings call, and a fabricated
number is worse than an omission. If the intelligence does not cover something,
say so and flag it as an open item for the IR team rather than filling the gap.

The executive may also have provided the current quarter's report in the
conversation. Where it is present, contrast it against the historical
intelligence — the delta is where the hard questions live.

## Revision

If `state["verification_report"]` exists, a fact-checker has already reviewed
your previous draft. Rewrite it now, applying every "Action needed": correct the
figures it corrected, remove what it says to remove, and mark as `[UNVERIFIED]`
anything it could not confirm. Do not silently keep a disputed number.

{RESPONSE_CONTRACT}
"""


def _reviser_instruction(module: CoachingModule) -> Callable:
    """Builds the reviser's instruction, reading the draft and findings from state.

    A callable rather than a static string so the navigation footer can name
    what the executive has actually completed this session.
    """

    def _build(ctx) -> str:
        state = ctx.state
        draft = str(state.get(module.state_key, "")).strip()
        findings = str(state.get("verification_report", "")).strip()

        done = [m.title for m in MODULES if str(state.get(m.state_key, "")).strip()]
        remaining = [m.title for m in MODULES if m.title not in done]

        findings_block = (
            f"## Verification findings\n\n{findings}"
            if findings
            else "## Verification findings\n\nNone were recorded for this draft. "
            "Say so in the confidence line rather than implying it was checked."
        )

        return f"""You are the final editor for the {module.title} module. You produce
what the executive actually reads — nothing runs after you.

## The draft

{draft}

{findings_block}

## Your job

1. Apply **every** "Action needed" from the findings above. Correct the figures
   it corrected. Remove what it says to remove. Anything it could not confirm
   keeps an inline `[UNVERIFIED]` next to the number — never quietly drop the
   marker, and never present a disputed figure as settled.
2. Otherwise preserve the draft. You are an editor, not a re-writer: keep its
   structure, tables, headings and source footers intact.
3. Add a short confidence line directly under the `## What matters` block,
   stating how many claims were checked and how many remain unverified.
4. End with exactly this navigation block, and nothing after it:

---
**Completed:** {', '.join(done) or 'this module'}
**Still available:** {', '.join(remaining) or 'none — you have covered everything'}

Tell me which you would like next, or say you are done and I will close out
with what matters most.

## Rules

Output the finished section only. No preamble, no commentary on your editing,
no meta-explanation. Do not invent numbers — you have no search tools, so
anything not in the draft or the findings cannot be added.
"""

    return _build


def _build_module_agent(module: CoachingModule):
    """Builds one module: a verified pipeline, or a plain interactive agent."""
    synthesizer = Agent(
        name=f"{module.key}_synthesizer",
        model=FLASH_MODEL,
        description=module.menu_summary,
        instruction=_synthesizer_prompt(module),
        tools=list(module.tools),
        output_key=module.state_key,
        planner=THINKING,
        before_model_callback=rate_limit_callback,
    )

    if not module.verified:
        # Interactive modules are conversational; there is no static draft to
        # fact-check, so they are not wrapped in the verification loop.
        synthesizer.name = module.agent_name
        return synthesizer

    # A LoopAgent over (synthesise, verify) always *ends* on a synthesise step,
    # so the last thing produced was never fact-checked — which defeats the
    # point. The reviser runs after the loop and has the final word, applying
    # the newest findings to the newest draft. It has no tools, so it is cheap
    # and cannot introduce new unverified claims.
    reviser = Agent(
        name=f"{module.key}_reviser",
        model=FLASH_MODEL,
        description=f"Applies verification findings to the {module.title} section.",
        instruction=_reviser_instruction(module),
        output_key=module.state_key,
        planner=THINKING,
        before_model_callback=rate_limit_callback,
    )

    return SequentialAgent(
        name=module.agent_name,
        description=module.menu_summary,
        sub_agents=[
            LoopAgent(
                name=f"{module.key}_verify_loop",
                max_iterations=2,
                description=f"Synthesise and fact-check the {module.title} section.",
                sub_agents=[
                    SequentialAgent(
                        name=f"{module.key}_synthesis_pass",
                        sub_agents=[
                            synthesizer,
                            build_verification_agent(module.key, module.state_key),
                        ],
                        description=(
                            f"Synthesises the {module.title} section, then "
                            f"fact-checks it."
                        ),
                    )
                ],
            ),
            reviser,
        ],
    )


def build_module_agents() -> list:
    """All coaching modules, as sub-agents for Phoenix to route between."""
    return [_build_module_agent(m) for m in MODULES]


def menu_markdown() -> str:
    """The module menu, rendered once and embedded in Phoenix's prompt.

    Includes `recommend_when`, which is guidance for Phoenix's own routing
    decisions and is not meant for the executive — use capabilities_markdown()
    for anything user-facing.
    """
    return "\n".join(
        f"{i}. **{m.title}** — {m.menu_summary}\n"
        f"   _Recommend when:_ {m.recommend_when}"
        for i, m in enumerate(MODULES, start=1)
    )


def capabilities_markdown(prefix: str = "") -> str:
    """What Phoenix can do, phrased for the executive.

    Derived from the same registry as the routing menu so the two cannot drift
    — an opening message that advertises a module which no longer exists is
    worse than no opening message at all.

    Args:
        prefix: Prepended to each line. Pass "> " when embedding inside a
            markdown blockquote, so the list does not break out of it.
    """
    return "\n".join(f"{prefix}- **{m.title}** — {m.menu_summary}" for m in MODULES)
