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
            assert not isinstance(agent, LoopAgent), (
                f"{agent.name} should not be wrapped in a verification loop"
            )
            print(f"  {agent.name}: interactive (no verification loop)")
            continue

        assert isinstance(agent, LoopAgent), f"{agent.name} must be a LoopAgent"
        # >1 is what makes verification corrective rather than advisory: the
        # synthesiser gets to revise against the verification report.
        assert agent.max_iterations > 1, (
            f"{agent.name} has max_iterations={agent.max_iterations}; the "
            f"verification loop cannot correct anything with only one pass"
        )

        (inner,) = agent.sub_agents
        assert isinstance(inner, SequentialAgent), (
            f"{agent.name} must wrap a SequentialAgent"
        )
        synth, verifier = inner.sub_agents
        assert synth.output_key == module.state_key, (
            f"{synth.name} writes {synth.output_key}, expected {module.state_key}"
        )
        assert verifier.output_key == "verification_report"

        print(
            f"  {agent.name}: LoopAgent(max_iterations={agent.max_iterations})"
            f" -> [{synth.name} -> {verifier.name}]"
        )
        print(f"      writes state[{module.state_key!r}]")

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
