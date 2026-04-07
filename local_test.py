from dotenv import load_dotenv
from phoenix.agent import phoenix_agent

def main():
    load_dotenv()
    print("--- Phoenix Agent Local Initialization Test ---")
    print(f"Name: {phoenix_agent.name}")
    print(f"Model: {phoenix_agent.model}")

    # Verify tools
    tool_names = [getattr(t, 'name', getattr(t, '__name__', str(t))) for t in phoenix_agent.tools]
    print(f"\nTools: {tool_names}")
    expected_tools = {
        "read_intelligence_report",
        "read_analyst_report",
        "read_competitor_report",
        "search_historical_documents",
        "search_competitor_documents",
    }
    actual_tools = set(tool_names)
    assert expected_tools == actual_tools, (
        f"Expected tools {expected_tools}, got {actual_tools}"
    )

    # Verify sub-agents
    sub_agent_names = [sa.name for sa in phoenix_agent.sub_agents]
    print(f"Sub-Agents: {sub_agent_names}")
    assert sub_agent_names == ["briefing_pipeline"], (
        f"Expected [briefing_pipeline], got {sub_agent_names}"
    )

    # Verify briefing_pipeline (SequentialAgent) structure
    pipeline = phoenix_agent.sub_agents[0]
    pipeline_sub_names = [sa.name for sa in pipeline.sub_agents]
    print(f"\n  briefing_pipeline sub-agents: {pipeline_sub_names}")
    assert pipeline_sub_names == ["briefing_synthesizer", "verification_loop"], (
        f"Expected [briefing_synthesizer, verification_loop], got {pipeline_sub_names}"
    )

    # Verify BriefingSynthesizer has output_key (no output_schema — flexible output)
    synthesizer = pipeline.sub_agents[0]
    print(f"\n    briefing_synthesizer:")
    print(f"      output_key={synthesizer.output_key}")
    assert synthesizer.output_key == "briefing_draft"

    # Verify VerificationLoop (LoopAgent) structure
    loop = pipeline.sub_agents[1]
    print(f"\n    verification_loop:")
    print(f"      max_iterations={loop.max_iterations}")
    verification_agent = loop.sub_agents[0]
    print(f"      verification_agent output_key={verification_agent.output_key}")
    vtool_names = [getattr(t, 'name', getattr(t, '__name__', str(t))) for t in verification_agent.tools]
    print(f"      verification_agent tools: {vtool_names}")
    assert loop.max_iterations == 1
    assert verification_agent.output_key == "verification_report"

    print("\n--- All checks passed! ---")
    print("\nArchitecture:")
    print("  Phoenix (LlmAgent, root)")
    print("  │  Tools: read_intelligence_report, read_analyst_report,")
    print("  │         read_competitor_report, search_historical_documents,")
    print("  │         search_competitor_documents")
    print("  └── briefing_pipeline (SequentialAgent)")
    print("      ├── briefing_synthesizer (output_key=briefing_draft)")
    print("      └── verification_loop (LoopAgent, max_iterations=1)")
    print("          └── verification_agent (output_key=verification_report)")
    print("\nExtraction pipeline (run before Phoenix to pre-populate GCS reports):")
    print("  adk run intelligence_extractor   # CLI runner")
    print("  adk web .                        # Web UI (select intelligence_extractor)")
    print("\nLocal development:")
    print("  adk web .        # Web UI (select phoenix)")
    print("  adk run phoenix  # CLI runner")

if __name__ == "__main__":
    main()
