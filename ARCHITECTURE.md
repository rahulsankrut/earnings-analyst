# Phoenix Earnings Analyst Agent — Architecture Documentation

This document provides a detailed breakdown of the multi-agent architecture implemented in the Phoenix Earnings Analyst Agent project. It highlights the use of Google Agent Development Kit (ADK) primitives to create a robust, two-stage financial intelligence pipeline.

---

## High-Level Architecture: Two-Stage Pipeline

To overcome challenges with real-time search latency and API rate limits during live executive interactions, the system is split into two distinct stages:

1.  **Batch Extraction Stage (Offline/Prep)**: A heavy-duty background pipeline that performs deep searches across data stores, synthesizes findings, and persists them as reports in Cloud Storage.
2.  **Interactive Serving Stage (Online/Live)**: The user-facing agent that reads the pre-computed reports instantly at session start and provides a highly structured briefing and interactive coaching to the executive.

---

## Stage 1: Intelligence Extraction Pipeline

The `intelligence_extractor` package contains a standalone ADK agent system designed for exhaustive data mining.

### Architecture Topology
```text
IntelligenceExtractor (Root Agent)
└── IntelligenceGathering (SequentialAgent)
    ├── CompanyExtractionLoop (LoopAgent, max_iterations=2)
    │   └── CompanyIntelligenceExtractor (LlmAgent)
    ├── AnalystExtractionLoop (LoopAgent, max_iterations=2)
    │   └── AnalystProfilerExtractor (LlmAgent)
    └── CompetitorExtractionLoop (LoopAgent, max_iterations=2)
        └── CompetitorIntelligenceExtractor (LlmAgent)
```

### Key ADK Primitives Used

#### 1. `LoopAgent` (Iterative Gap Filling)
The extraction process uses `LoopAgent` for all three specialist extractors (Company, Analyst, Competitor) with `max_iterations=2`.
*   **How it works**: 
    *   **Pass 1**: The agent executes a mandatory, extensive search plan (ranging from 26 to 35 targeted queries) to build a broad picture.
    *   **Pass 2**: The agent reviews the findings from the first pass. If it identifies data gaps (e.g., missing specific quarters or analyst names), it uses the second iteration to run targeted follow-up queries to fill those gaps.
*   **Benefit**: Guarantees a much higher level of completeness and factual density than a single-shot prompt.

#### 2. `SequentialAgent` (Rate Limit Management)
While initially conceived as running in parallel, the three extraction loops are sequenced using a `SequentialAgent` named `IntelligenceGathering`.
*   **How it works**: It ensures that `CompanyExtractionLoop` finishes completely before `AnalystExtractionLoop` begins, followed by `CompetitorExtractionLoop`.
*   **Benefit**: This helps manage the project's API quotas and mitigates `429 Resource Exhausted` errors by spreading the heavy load of ~94 total searches over time rather than bursting all at once.

### Data Flow
Each specialist extractor uses the `save_intelligence_report` tool upon completion to write its full markdown report directly to the `INTELLIGENCE_BUCKET` in Google Cloud Storage.

---

## Stage 2: Phoenix Serving Agent

The `phoenix` package contains the interactive agent that the C-Suite executive communicates with via the Gemini Enterprise UI or local runners.

### Architecture Topology
```text
Phoenix (Root Orchestrator — recommends, routes, narrates)
├── guidance_credibility_module ┐
├── analyst_ambush_module       │ LoopAgent(max_iterations=3)
├── competitor_landmines_module │   └── SequentialAgent
├── financial_deep_dive_module  ┘         ├── <key>_synthesizer  → state["module_<key>"]
│                                          └── <key>_verifier     → state["verification_report"]
└── qa_drill_module (LlmAgent — interactive, unverified by design)
```

Phoenix does not produce one monolithic briefing. It recommends a starting
module from what it observes in the current quarter's report, then routes to
whichever modules the executive chooses.

### Key ADK Primitives Used

#### 1. Modules as sub-agents (Scoped Context)
Each coaching module is an ADK sub-agent holding **only the tools it needs** —
the analyst module reads the analyst report and nothing else.
*   **How it works**: ADK's built-in agent transfer does the routing; there is no hand-written dispatcher.
*   **Benefit**: Context stays bounded as competitors are added. Previously a single synthesiser loaded all three uncapped reports at once.

#### 2. `LoopAgent` + `SequentialAgent` (The Corrective Auditor)
Each verified module loops synthesise → fact-check → revise, up to three passes.
*   **How it works**: The `SequentialAgent` guarantees the synthesiser runs before the verifier. The verifier escalates — exiting the loop — **only** when no claim is left unresolved. Otherwise the loop runs again and the synthesiser rewrites against `state["verification_report"]`.
*   **Benefit**: Verification findings are acted on. An earlier design ran verification once with `max_iterations=1` and nothing ever consumed its output, so a `DISCREPANCY` could still reach the executive. Claims that remain unconfirmable are carried through marked `[UNVERIFIED]`.

#### 3. Profile-namespaced reports (Multi-tenancy Safety)
Reports live under `reports/{profile}/` and are stamped with the profile that produced them.
*   **How it works**: `_provenance_banner` prepends the company, extraction date, and — when they disagree — a loud mismatch warning that Phoenix is instructed to surface immediately.
*   **Benefit**: Pointing a second company at an existing bucket cannot silently serve the first company's intelligence.

---

## Summary of Data Flow

1.  **Search**: Sub-agents use `search_historical_documents` and `search_competitor_documents` to query Vertex AI Search.
2.  **Persist**: `save_intelligence_report` stores markdown reports in GCS under `reports/{profile}/`.
3.  **Serve**: Phoenix reads the reports, recommends a starting module, and routes to it.
4.  **Verify**: Each module fact-checks and revises its own section before it reaches the executive.
