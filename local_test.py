"""Structural smoke test for the Phoenix agent tree.

Verifies wiring only — no model calls, no credentials needed. Behaviour belongs
in tests/eval.

    python local_test.py
"""

from dotenv import load_dotenv

from google.adk.agents import LoopAgent, SequentialAgent

from phoenix.agent import phoenix_agent
from phoenix.sub_agents.modules import MODULES, MODULES_BY_KEY


def main():
    load_dotenv()
    print("--- Phoenix Agent Local Initialization Test ---")
    print(f"Name: {phoenix_agent.name}")
    print(f"Model: {phoenix_agent.model}")

    tool_names = [
        getattr(t, "name", getattr(t, "__name__", str(t)))
        for t in phoenix_agent.tools
    ]
    print(f"\nTools: {tool_names}")
    expected_tools = {
        "read_intelligence_report",
        "read_analyst_report",
        "read_competitor_report",
        "search_historical_documents",
        "search_competitor_documents",
    }
    assert expected_tools == set(tool_names), (
        f"Expected tools {expected_tools}, got {set(tool_names)}"
    )

    # One sub-agent per coaching module, in registry order.
    sub_agent_names = [sa.name for sa in phoenix_agent.sub_agents]
    expected_modules = [m.agent_name for m in MODULES]
    print(f"\nCoaching modules: {sub_agent_names}")
    assert sub_agent_names == expected_modules, (
        f"Expected {expected_modules}, got {sub_agent_names}"
    )

    print("\nModule structure:")
    for agent in phoenix_agent.sub_agents:
        module = MODULES_BY_KEY[agent.name.removesuffix("_module")]

        if not module.verified:
            # Interactive modules are conversational — no verification loop.
            assert not isinstance(agent, (LoopAgent, SequentialAgent)), (
                f"{agent.name} should not be wrapped in a verification loop"
            )
            print(f"  {agent.name}: interactive (no verification loop)")
            continue

        # A LoopAgent alone always ends on its last sub-agent, which here is
        # the synthesiser — so the final draft would never itself be
        # fact-checked. The module is therefore Sequential(LoopAgent, reviser):
        # the loop iterates synthesise/verify, and the reviser has the final
        # word, applying the newest findings to the newest draft.
        assert isinstance(agent, SequentialAgent), (
            f"{agent.name} must be Sequential(verify_loop, reviser), got "
            f"{type(agent).__name__}"
        )
        loop, reviser = agent.sub_agents

        assert isinstance(loop, LoopAgent), f"{loop.name} must be a LoopAgent"
        assert loop.max_iterations > 1, (
            f"{loop.name} has max_iterations={loop.max_iterations}; the "
            f"verification loop cannot correct anything with only one pass"
        )

        (inner,) = loop.sub_agents
        assert isinstance(inner, SequentialAgent), (
            f"{loop.name} must wrap a SequentialAgent"
        )
        synth, verifier = inner.sub_agents
        assert synth.output_key == module.state_key, (
            f"{synth.name} writes {synth.output_key}, expected {module.state_key}"
        )
        assert verifier.output_key == "verification_report"

        # The reviser must write the same state key as the synthesiser — it
        # is the last writer, so its output is what the executive reads.
        assert reviser.output_key == module.state_key, (
            f"{reviser.name} writes {reviser.output_key}, expected "
            f"{module.state_key} — the reviser must have the final word"
        )
        assert not reviser.tools, (
            f"{reviser.name} has tools; it should only edit the existing "
            f"draft, not perform new searches that bypass verification"
        )

        print(
            f"  {agent.name}: Sequential("
            f"LoopAgent(max_iterations={loop.max_iterations})"
            f"[{synth.name} -> {verifier.name}], {reviser.name})"
        )
        print(f"      final output in state[{module.state_key!r}]")

    print("\n--- All checks passed! ---")
    print("\nArchitecture:")
    print("  Phoenix (LlmAgent, root)")
    print("  │  Tools: read_intelligence_report, read_analyst_report,")
    print("  │         read_competitor_report, search_historical_documents,")
    print("  │         search_competitor_documents")
    for module in MODULES:
        kind = "interactive" if not module.verified else "verified loop"
        print(f"  ├── {module.agent_name} ({kind})")
    print("\nExtraction pipeline (run before Phoenix to pre-populate GCS reports):")
    print("  adk run intelligence_extractor")
    print("\nLocal development:")
    print("  adk web .        # Web UI (select phoenix)")
    print("  adk run phoenix  # CLI runner")


if __name__ == "__main__":
    main()
