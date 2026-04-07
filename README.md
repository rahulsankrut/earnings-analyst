# Phoenix: C-Suite Earnings Prep Agent

Phoenix is a Google ADK multi-agent system that prepares C-Suite executives for earnings calls. It works in two stages:

1. **Intelligence Extractor** (batch, runs offline) — mines historical earnings transcripts, 10-Ks, and 10-Qs from Vertex AI Search, builds deep analyst behavioral profiles and a competitor intelligence report, and saves everything to Cloud Storage.

2. **Phoenix** (interactive, live during prep) — reads the pre-extracted intelligence, analyzes the current quarter's financials that the executive uploads, generates a tiered question bank with defensible responses, and coaches the executive through interactive Q&A simulation.

---

## Architecture

```
Intelligence Extractor (batch pipeline)
└── intelligence_gathering (SequentialAgent)
    ├── company_extraction_loop (LoopAgent, 2 passes, 26 searches)
    │   └── company_intelligence_extractor  → saves intelligence_report.md to GCS
    ├── analyst_extraction_loop (LoopAgent, 2 passes, 35 searches)
    │   └── analyst_profiler_extractor      → saves analyst_report.md to GCS
    └── competitor_extraction_loop (LoopAgent, 2 passes, 33 searches)
        └── competitor_intelligence_extractor → saves competitor_report.md to GCS

Phoenix (C-Suite advisor)
├── Tools: read_intelligence_report, read_analyst_report, read_competitor_report
│         search_historical_documents, search_competitor_documents
└── briefing_pipeline (SequentialAgent)
    ├── briefing_synthesizer  → structured question bank + coaching guide
    └── verification_loop     → fact-checks every cited number
```

Both agents deploy independently to Vertex AI Agent Engine and can be triggered on demand.

---

## Prerequisites

- Google Cloud project with billing enabled
- `gcloud` CLI installed and authenticated
- Python 3.10+
- `poetry` installed (`pip install poetry`)

---

## Deployment Guide

### Step 1: Enable required Google Cloud APIs

```bash
gcloud config set project YOUR_PROJECT_ID

gcloud services enable \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  storage.googleapis.com \
  iam.googleapis.com
```

### Step 2: Create a service account

The agents run under a dedicated service account both during deployment and at runtime on Agent Engine.

```bash
gcloud iam service-accounts create earnings-analyst-sa \
  --display-name="Earnings Analyst Agent SA"

SA_EMAIL="earnings-analyst-sa@YOUR_PROJECT_ID.iam.gserviceaccount.com"
```

Grant the service account the required roles:

```bash
# Vertex AI — required for the agent to call Gemini models at runtime
# (Note: The user deploying the agent needs higher permissions like roles/aiplatform.admin)
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/aiplatform.user"

# Vertex AI Search — read data stores
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/discoveryengine.viewer"

# Cloud Storage — read/write intelligence reports
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/storage.objectAdmin"

# Service Usage — required by Agent Engine runtime
gcloud projects add-iam-policy-binding YOUR_PROJECT_ID \
  --member="serviceAccount:$SA_EMAIL" \
  --role="roles/serviceusage.serviceUsageConsumer"
```

### Step 3: Create Cloud Storage buckets

Four buckets are needed — two for Agent Engine staging (one per agent, required to avoid deployment conflicts), one for intelligence reports, and one for source PDF documents.

```bash
PROJECT_ID=YOUR_PROJECT_ID
REGION=us-central1

# Agent Engine staging buckets (one per agent — must be separate)
gcloud storage buckets create gs://$PROJECT_ID-phoenix-staging \
  --location=$REGION --project=$PROJECT_ID

gcloud storage buckets create gs://$PROJECT_ID-ie-staging \
  --location=$REGION --project=$PROJECT_ID

# Intelligence reports bucket (Intelligence Extractor writes here, Phoenix reads)
gcloud storage buckets create gs://$PROJECT_ID-intelligence \
  --location=$REGION --project=$PROJECT_ID

# Source PDF documents bucket (your earnings transcripts and filings go here)
gcloud storage buckets create gs://$PROJECT_ID-earnings-docs \
  --location=$REGION --project=$PROJECT_ID
```

### Step 4: Create Vertex AI Search data stores

You need two data stores: one for the company's historical documents, one for competitor documents.

#### 4a. Create the data store app in the Cloud Console

1. Go to **Vertex AI Search** in the Cloud Console (`Discovery Engine` in the API)
2. Click **Create app** → **Search** → **Generic**
3. For the company data store:
   - App name: `earnings-historical`
   - Data store name: `earnings-historical-documents`
   - Content type: **Unstructured documents**
4. Repeat for the competitor data store:
   - App name: `competitor-data`
   - Data store name: `competitor-data`

Record the **data store IDs** shown after creation — they look like `earnings-historical-documents_1234567890`.

#### 4b. Upload documents to the source bucket

Place your PDF documents (earnings call transcripts, 10-Ks, 10-Qs) in the `reports/` directory, then upload:

```bash
# Configure in .env first (see Step 5), then:
python upload_to_gcs.py
```

Use `SKIP_PATTERN` in `.env` to exclude specific files by filename substring.

#### 4c. Ingest documents into Vertex AI Search

1. Open each data store in the Cloud Console
2. Click **Import data** → **Cloud Storage**
3. Point to your documents bucket (e.g., `gs://YOUR_PROJECT_ID-earnings-docs/*.pdf`)
4. Run the import and wait for completion (can take 10-30 minutes)

### Step 5: Configure environment variables

Copy the example file and fill in your values:

```bash
cp .env.example .env
```

Edit `.env`:

```bash
# ── Google Cloud Project ──────────────────────────────────────────────────
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=1

# ── Agent Engine Deployment ───────────────────────────────────────────────
# Staging buckets (must exist, must be separate — see Step 3)
GOOGLE_CLOUD_STORAGE_BUCKET=your-project-id-phoenix-staging
IE_STAGING_BUCKET=your-project-id-ie-staging
AGENT_SERVICE_ACCOUNT=earnings-analyst-sa@your-project-id.iam.gserviceaccount.com

# ── Vertex AI Search Data Stores ──────────────────────────────────────────
EARNINGS_DATA_STORE_ID=earnings-historical-documents_1234567890
COMPETITOR_DATA_STORE_ID=competitor-data_1234567890
DATA_STORE_LOCATION=global

# ── GCS Buckets ───────────────────────────────────────────────────────────
INTELLIGENCE_BUCKET=your-project-id-intelligence
DOCUMENT_BUCKET=your-project-id-earnings-docs
SKIP_PATTERN=                  # leave blank to upload all PDFs

# ── Models ────────────────────────────────────────────────────────────────
PHOENIX_MODEL=gemini-2.5-pro
PHOENIX_FLASH_MODEL=gemini-2.5-flash


```

### Step 6: Set up the Python environment

```bash
python -m venv venv
source venv/bin/activate

pip install poetry
poetry install
```

### Step 7: Build the deployment package

Agent Engine requires a wheel that packages both agents:

```bash
poetry build
```

This creates `dist/earnings_analyst-0.1-py3-none-any.whl`. The `deployment/deploy.py` script references this path — do not rename or move it.

### Step 8: Deploy both agents

```bash
source venv/bin/activate
python -m deployment.deploy
```

This deploys two separate agents to Vertex AI Agent Engine:

- **Phoenix C-Suite Agent** — the interactive advisor (uses `your-project-id-phoenix-staging` bucket)
- **Intelligence Extractor** — the batch pipeline (uses `your-project-id-ie-staging` bucket)

Deployment takes 5-10 minutes per agent. When complete, you'll see:

```
--- Deploying Phoenix (C-Suite Earnings Prep) ---
  ✅ Phoenix deployed: projects/.../reasoningEngines/123456789
  ✅ Label 'customer: trane' added

--- Deploying Intelligence Extractor (Batch Pipeline) ---
  ✅ Intelligence Extractor deployed: projects/.../reasoningEngines/987654321
  ✅ Label 'customer: trane' added

✅ All agents deployed.
```

Record the resource names — you'll need them to trigger the agents.

## Deleting deployed agents

If you need to delete a deployed agent from Vertex AI Agent Engine, you can use the Python SDK. 

Because agents often have active sessions, standard deletion might fail. You must use the `vertexai.Client` to force deletion of the agent and its child resources:

```python
import vertexai

client = vertexai.Client(project="YOUR_PROJECT_ID", location="us-central1")
client.agent_engines.delete(
    name="projects/YOUR_PROJECT_ID/locations/us-central1/reasoningEngines/YOUR_AGENT_ID",
    force=True, # Forces deletion of child resources (sessions)
)
print("Deleted successfully")
```

Alternatively, you can delete it directly in the Google Cloud Console under **Vertex AI** -> **Agent Engine**.

---

## Running the agents

### Run the Intelligence Extractor (first time and periodically)

The Intelligence Extractor is a batch job. Run it once before using Phoenix, then re-run whenever you add new documents to the data store.

**Option A — trigger via Agent Engine API:**

```python
import vertexai
from vertexai import agent_engines

vertexai.init(project="YOUR_PROJECT_ID", location="us-central1")

agent = agent_engines.get("projects/YOUR_PROJECT_ID/locations/us-central1/reasoningEngines/INTELLIGENCE_EXTRACTOR_ID")
session = agent.create_session(user_id="batch")
response = agent.stream_query(
    session_id=session["id"],
    message="Run the full intelligence extraction pipeline."
)
for chunk in response:
    print(chunk, end="", flush=True)
```

**Option B — run locally** (faster for testing):

```bash
source venv/bin/activate
adk run intelligence_extractor
# or with the web UI:
adk web .
```

The extractor runs 94 searches (26 company, 35 analyst, 33 competitor) across two passes each and uploads three reports to your `INTELLIGENCE_BUCKET`:

```
gs://your-intelligence-bucket/reports/intelligence_report.md
gs://your-intelligence-bucket/reports/analyst_report.md
gs://your-intelligence-bucket/reports/competitor_report.md
```

Extraction takes 15-30 minutes depending on data store size.

### Run Phoenix (interactive prep sessions)

**Via Gemini Enterprise / Vertex AI Agent Builder:**

Register the Phoenix agent's resource name in your Gemini Enterprise configuration. Users interact through the standard chat UI.

**Via Agent Engine API:**

```python
import vertexai
from vertexai import agent_engines

vertexai.init(project="YOUR_PROJECT_ID", location="us-central1")

agent = agent_engines.get("projects/YOUR_PROJECT_ID/locations/us-central1/reasoningEngines/PHOENIX_ID")
session = agent.create_session(user_id="executive-1")

# Start a session
response = agent.stream_query(
    session_id=session["id"],
    message="Hello"
)
for chunk in response:
    print(chunk, end="", flush=True)
```

**Via the ADK web UI (local testing):**

```bash
source venv/bin/activate
adk web .
# Open http://localhost:8000 and select "phoenix"
```

---

## Local development

For iterating on prompts or tools without deploying:

```bash
# Authenticate
gcloud auth application-default login

source venv/bin/activate

# Run Phoenix interactively (terminal)
adk run phoenix

# Run Intelligence Extractor interactively
adk run intelligence_extractor

# Web UI for both (select agent in dropdown)
adk web .

# Run the local test script
python local_test.py
```

---

## Updating documents

When new earnings documents are released:

1. Add PDFs to the `reports/` directory
2. Upload to GCS: `python upload_to_gcs.py`
3. Re-ingest into Vertex AI Search via the Cloud Console (Import data → Cloud Storage)
4. Re-run the Intelligence Extractor to refresh the reports in GCS
5. Phoenix will automatically use the updated reports on the next session

---

## Troubleshooting

**`KeyError: GOOGLE_CLOUD_PROJECT` during deployment**
All variables in `.env` must be set before running `deploy.py`. Run `python -m deployment.deploy` (not `python deployment/deploy.py` directly) from the `earnings_analyst/` directory so `load_dotenv()` picks up the `.env` file.

**`400 Invalid bucket name` during deployment**
The two staging buckets (`GOOGLE_CLOUD_STORAGE_BUCKET` and `IE_STAGING_BUCKET`) must be different buckets. Agent Engine hardcodes the path `agent_engine/agent_engine.pkl` inside each bucket — if both agents share a bucket, the second deployment overwrites the first.

**`403` errors from Vertex AI Search at runtime**
The service account needs `roles/discoveryengine.viewer` and `roles/serviceusage.serviceUsageConsumer`. Grant both via `gcloud projects add-iam-policy-binding` (see Step 2).

**Phoenix returns Intelligence Extractor output**
This is a pkl collision — both agents were deployed to the same staging bucket. Redeploy with separate buckets for each agent (`GOOGLE_CLOUD_STORAGE_BUCKET` for Phoenix, `IE_STAGING_BUCKET` for Intelligence Extractor).

**`429 Resource Exhausted` errors**
The agents include proactive rate limiting (`MIN_CALL_INTERVAL`) but Gemini 2.5 Pro has low default quotas on Vertex AI. Request a quota increase for `generate_content` in the Cloud Console under **IAM & Admin → Quotas**.
