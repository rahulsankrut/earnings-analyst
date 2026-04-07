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
Phoenix (Root Orchestrator)
└── BriefingPipeline (SequentialAgent)
    ├── BriefingSynthesizer (LlmAgent with Structured Output)
    └── VerificationLoop (LoopAgent, max_iterations=1)
        └── VerificationAgent (LlmAgent)
```

### Key ADK Primitives Used

#### 1. `SequentialAgent` (Guaranteed Ordering)
The `BriefingPipeline` uses a `SequentialAgent` to orchestrate the creation and auditing of the prep guide.
*   **How it works**: It guarantees that the `BriefingSynthesizer` runs first to create the draft, and only *after* it completes does the `VerificationLoop` begin.
*   **Benefit**: This is a deterministic flow. No LLM routing is needed to decide what to do next; step B *must* follow step A.

#### 2. `Structured Output` (Pydantic Enforcement)
The `BriefingSynthesizer` uses the `output_schema` parameter in ADK, mapped to the `EarningsBriefing` Pydantic model (defined in `schemas.py`).
*   **How it works**: It forces the model to output a strictly typed JSON object matching lists of specific lengths (e.g., exactly 5 Tier 1 questions) and validated Enums for threat levels.
*   **Benefit**: This ensures the report is programmatically parseable and can be rendered beautifully in a front-end GUI (as carousels or cards) rather than dumping a wall of text.

#### 3. `VerificationAgent` (The Auditor Pattern)
The final step in the pipeline is a fact-checker.
*   **How it works**: It reads the draft briefing produced by the synthesizer, extracts every numerical claim, and independently re-queries the data stores to verify them.
*   **Benefit**: It protects the executive from quoting hallucinated or approximated numbers on live calls.

---

## Summary of Data Flow

1.  **Search**: Sub-agents use `search_historical_documents` and `search_competitor_documents` to query Vertex AI Search.
2.  **Persist**: `save_intelligence_report` stores massive markdown files in GCS.
3.  **Serve**: Main agent uses `read_intelligence_report` to instantly load the context at session start.
