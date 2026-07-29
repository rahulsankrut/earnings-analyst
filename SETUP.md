# Setting up on a new machine

End-to-end setup for the Alphabet configuration: local tooling, the GCP
resources the agents read from, running the pipeline, deploying, and
registering with Gemini Enterprise.

If the GCP resources already exist in your project, skip Part 2 and just fill
in `.env` with the existing IDs from Part 3.

> Several steps here look optional and are not. Each one marked **Gotcha** cost
> real debugging time — they fail late, quietly, or with an error that names
> the wrong thing.

---

## Part 1 — Local tooling

```bash
# Python 3.10+ and Poetry
python3 --version
pipx install poetry          # or: pip install poetry

git clone https://github.com/rahulsankrut/earnings-analyst.git
cd earnings-analyst
git checkout v2              # the generic, multi-company line

poetry install --with dev
```

Google Cloud CLI and credentials:

```bash
gcloud auth login
gcloud auth application-default login    # ADC — the libraries use this, not the gcloud token
gcloud config set project YOUR_PROJECT_ID
```

**Gotcha — two separate credentials.** `gcloud auth login` and
`gcloud auth application-default login` are different. The Python clients use
ADC. A stale gcloud token makes `gcloud` commands fail while Python keeps
working, and vice versa. If `gcloud` fails but scripts work, re-run
`gcloud auth login`; if scripts fail with auth errors, re-run the ADC one.

Optional, for Gemini Enterprise registration in Part 7:

```bash
uv tool install "google-agents-cli~=1.2.1"
```

Verify:

```bash
poetry run pytest tests/unit -q          # expect: 81 passed
COMPANY_PROFILE=alphabet poetry run python local_test.py
```

Both run offline — no credentials, no cost.

---

## Part 2 — GCP resources

Only needed when standing up a **new** project or a new company.

### 2.1 Enable APIs

```bash
gcloud services enable \
  aiplatform.googleapis.com \
  discoveryengine.googleapis.com \
  storage.googleapis.com \
  --project YOUR_PROJECT_ID
```

### 2.2 Buckets

Three, with distinct jobs:

| Bucket | Purpose |
|---|---|
| `<project>-<company>-documents` | Source PDFs, ingested into the data stores |
| `<intelligence-bucket>` | Extracted reports Phoenix reads (`INTELLIGENCE_BUCKET`) |
| `<project>-agents-staging`, `<project>-ie-staging` | Agent Engine deploy staging — **must be two separate buckets**, one per agent, or the second deploy overwrites the first's pickle |

```bash
gcloud storage buckets create gs://YOUR_PROJECT-alphabet-documents --location=US
```

### 2.3 Upload source documents

Two corpora, separate prefixes: the company's own filings, and the
competitors'. They go to different data stores.

```
reports/
  alphabet/     -> Google 10-K, 10-Q, earnings call transcripts
  competitor/   -> Microsoft and Amazon 10-K, 10-Q
```

```bash
gcloud storage cp "reports/alphabet/*.pdf"   gs://YOUR_PROJECT-alphabet-documents/alphabet/
gcloud storage cp "reports/competitor/*.pdf" gs://YOUR_PROJECT-alphabet-documents/competitor/
```

**Include earnings-call transcripts, not just filings.** The analyst profiler
mines transcripts for who asks what — filings alone yield nothing. In the
Alphabet run the competitor corpus had no transcripts, and the competitor
report's "What Analysts Are Asking" section correctly came back with
"No direct analyst questions or Q&A transcripts were found."

### 2.4 Data stores and search engines

Two data stores (company, competitors), each behind its own **Enterprise**
search engine.

**Gotcha — the engine is not optional.** Extractive answers and segments, and
the page numbers the citation format depends on, are Enterprise-edition
features enabled at the *engine* level. Query a bare data store and the API
returns document titles and links but no text: search comes back
"No relevant information found" while the documents are indexed perfectly.
Measured difference on the same store: **63 characters vs 25,855**.

```bash
python3 - <<'PY'
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine

PROJECT = "YOUR_PROJECT_ID"
PARENT = f"projects/{PROJECT}/locations/global/collections/default_collection"
opts = ClientOptions(api_endpoint="discoveryengine.googleapis.com")

ds_client = discoveryengine.DataStoreServiceClient(client_options=opts)
for ds_id, name in [
    ("alphabet-earnings-docs", "Alphabet Historical Earnings Documents"),
    ("alphabet-competitor-docs", "Alphabet Competitor Documents"),
]:
    op = ds_client.create_data_store(
        parent=PARENT,
        data_store_id=ds_id,
        data_store=discoveryengine.DataStore(
            display_name=name,
            industry_vertical=discoveryengine.IndustryVertical.GENERIC,
            solution_types=[discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH],
            content_config=discoveryengine.DataStore.ContentConfig.CONTENT_REQUIRED,
        ),
    )
    op.result(timeout=300)
    print("created data store", ds_id)

eng_client = discoveryengine.EngineServiceClient(client_options=opts)
for eng_id, name, ds_id in [
    ("alphabet-earnings-engine", "Alphabet Earnings Search", "alphabet-earnings-docs"),
    ("alphabet-competitor-engine", "Alphabet Competitor Search", "alphabet-competitor-docs"),
]:
    op = eng_client.create_engine(
        parent=PARENT,
        engine_id=eng_id,
        engine=discoveryengine.Engine(
            display_name=name,
            solution_type=discoveryengine.SolutionType.SOLUTION_TYPE_SEARCH,
            data_store_ids=[ds_id],
            search_engine_config=discoveryengine.Engine.SearchEngineConfig(
                search_tier=discoveryengine.SearchTier.SEARCH_TIER_ENTERPRISE,
                search_add_ons=[discoveryengine.SearchAddOn.SEARCH_ADD_ON_LLM],
            ),
        ),
    )
    op.result(timeout=600)
    print("created engine", eng_id)
PY
```

### 2.5 Ingest the documents

```bash
python3 - <<'PY'
from google.api_core.client_options import ClientOptions
from google.cloud import discoveryengine

PROJECT, BUCKET = "YOUR_PROJECT_ID", "YOUR_PROJECT-alphabet-documents"
client = discoveryengine.DocumentServiceClient(
    client_options=ClientOptions(api_endpoint="discoveryengine.googleapis.com"))

for ds_id, prefix in [("alphabet-earnings-docs", "alphabet"),
                      ("alphabet-competitor-docs", "competitor")]:
    parent = (f"projects/{PROJECT}/locations/global/collections/default_collection"
              f"/dataStores/{ds_id}/branches/default_branch")
    op = client.import_documents(request=discoveryengine.ImportDocumentsRequest(
        parent=parent,
        gcs_source=discoveryengine.GcsSource(
            input_uris=[f"gs://{BUCKET}/{prefix}/*.pdf"], data_schema="content"),
        reconciliation_mode=discoveryengine.ImportDocumentsRequest
            .ReconciliationMode.INCREMENTAL,
    ))
    print("import started:", ds_id, op.operation.name.split("/")[-1])
PY
```

Ingestion runs server-side and takes roughly 5–10 minutes. Poll with
`list_documents` until each store reports the expected count before extracting.

### 2.6 Service account IAM

The deployed agents run as `AGENT_SERVICE_ACCOUNT`, **not** as your ADC. A
local success proves nothing about the deployed identity. Required:

| Role | Why |
|---|---|
| `roles/discoveryengine.viewer` | Query both data stores |
| `roles/storage.objectAdmin` | Extractor writes reports; Phoenix reads them |
| `roles/aiplatform.user` | Model calls |

---

## Part 3 — Configure `.env`

```bash
cp .env.example .env
```

Fill in. The non-obvious ones:

| Variable | Notes |
|---|---|
| `COMPANY_PROFILE` | Profile name in `company_profiles/data/` (e.g. `alphabet`). Namespaces reports under `reports/<profile>/` |
| `EARNINGS_SEARCH_ENGINE_ID` | The **engine**, not the data store — see 2.4 |
| `COMPETITOR_SEARCH_ENGINE_ID` | Same |
| `MODEL_LOCATION` | `global`. See below |
| `GOOGLE_CLOUD_LOCATION` | `us-central1` — where the *agents* deploy |
| `GOOGLE_CLOUD_STORAGE_BUCKET` / `IE_STAGING_BUCKET` | Must differ |

**Gotcha — `MODEL_LOCATION` is not `GOOGLE_CLOUD_LOCATION`.**
`gemini-3.5-flash` and `gemini-3.6-flash` serve **only from the global
endpoint**. They appear in `us-central1`'s `models.list()`, but an actual
`generate_content` call there returns `404 NOT_FOUND`. Listing a model is not
the same as being able to call it. Model traffic goes to `global`; the agents
still deploy to `us-central1`. To check a model before switching:

```bash
poetry run python -c "
from dotenv import load_dotenv; load_dotenv()
from google import genai
c = genai.Client(vertexai=True, location='global')
print(c.models.generate_content(model='gemini-3.6-flash', contents='Say OK').text)"
```

---

## Part 4 — Run the extraction pipeline

Populates the three reports Phoenix reads. Run before any coaching session,
and after adding documents.

```bash
poetry run adk run intelligence_extractor
```

Roughly 11 minutes for Alphabet (121 searches: 26 company + 35 analyst + 60
competitor). Search count scales with the profile — each competitor adds 22
queries plus one per declared segment.

Confirm all three landed:

```bash
gcloud storage ls -l gs://YOUR_INTELLIGENCE_BUCKET/reports/alphabet/
```

Expect `intelligence_report.md`, `analyst_report.md`, `competitor_report.md`,
and `metadata.json`. Check the timestamps in `metadata.json` are from this run
— a stage can complete without its report updating, which is why the
`after_agent_callback` safety net in `intelligence_extractor/agent.py` exists.

---

## Part 5 — Run Phoenix locally

```bash
poetry run adk web .        # browser UI, select "phoenix"
poetry run adk run phoenix  # terminal
```

Say "Hello" — it should list its coaching modules. Ask for one by name and it
transfers to that module.

---

## Part 6 — Deploy

```bash
poetry build                       # ALWAYS build first
poetry run python deployment/deploy.py
```

**Gotcha — rebuild the wheel after every code change.** The agent is
serialised with cloudpickle, which stores references by name and resolves them
inside the container against the shipped wheel. A stale wheel does not fail at
build or upload time: it fails minutes later as
`failed to start and cannot serve traffic`, with the real cause
(`module 'phoenix' has no attribute '_TimeoutGemini'`) buried in container
logs. `deploy.py` now refuses to deploy a wheel older than its source, but
building first avoids the round trip.

Deployment takes 5–10 minutes per agent. When it fails, the useful logs are:

```bash
gcloud logging read \
  'resource.type="aiplatform.googleapis.com/ReasoningEngine"
   AND resource.labels.reasoning_engine_id="YOUR_ENGINE_ID"' \
  --project YOUR_PROJECT_ID --limit 50 --freshness 1h
```

### Verify the deployed IAM

A local pass says nothing about the deployed service account. Probe the live
agent:

```bash
poetry run python - <<'PY'
import os, vertexai
from dotenv import load_dotenv; load_dotenv()
from vertexai import agent_engines
vertexai.init(project=os.environ["GOOGLE_CLOUD_PROJECT"],
              location=os.environ["GOOGLE_CLOUD_LOCATION"])
a = agent_engines.get("projects/.../reasoningEngines/YOUR_PHOENIX_ID")
for q in ["Call read_intelligence_report and reply with only the company name.",
          "Use search_historical_documents for 'cloud revenue'; reply with only the first document title."]:
    out = "".join(p.get("text","") for e in a.stream_query(message=q, user_id="probe")
                  for p in (e.get("content") or {}).get("parts", []) or [])
    print(("FAIL " if any(m in out for m in ("Error", "Permission", "No relevant")) else "OK   "), out[:120])
PY
```

**Do not probe the Intelligence Extractor this way.** Its orchestrator's only
instruction is to transfer into the full pipeline, so any message triggers all
121 searches and overwrites the live reports. Verify its IAM from the bucket
policy instead.

---

## Part 7 — Register with Gemini Enterprise

```bash
agents-cli publish gemini-enterprise --list      # find the app resource name

agents-cli publish gemini-enterprise \
  --registration-type adk \
  --agent-runtime-id projects/.../reasoningEngines/YOUR_PHOENIX_ID \
  --gemini-enterprise-app-id projects/.../engines/YOUR_APP_ID \
  --display-name "Phoenix C-Suite Earnings Prep" \
  --description "..." \
  --tool-description "..." \
  --deployment-target agent_runtime
```

`--registration-type adk` is required in programmatic mode (`a2a` is for
agents fronted by an agent card).

**The `cid` in a Gemini Enterprise console URL is not the engine ID.** A URL
like `.../home/cid/454ba24c-...` carries a console-side identifier that the
Discovery Engine API does not expose — it matches no engine and no assistant.
Use `--list` to get the real `projects/.../engines/...` resource name.

Consider whether to register the extractor at all: anyone invoking it from the
Gemini Enterprise UI triggers the full pipeline and overwrites the reports.

---

## Onboarding a different company

No code changes needed:

1. `cp company_profiles/data/example.json company_profiles/data/acme.json`
2. Fill in `company_name`, `sector`, `competitors[].name`, and — most
   importantly — each competitor's `segments`, their own reporting-segment
   names as they appear in filings. These become targeted searches and drive
   extraction quality. They cannot be guessed from a company name.
3. Create data stores and engines for the new corpora (Part 2), ingest
4. Set `COMPANY_PROFILE=acme`, plus the new store and engine IDs
5. Re-run extraction — reports land under `reports/acme/`, leaving other
   companies untouched

Reports are namespaced by profile and stamped with the profile that produced
them. Phoenix refuses to brief from a report whose profile does not match the
active one, rather than silently presenting another company's intelligence.

---

## Troubleshooting

| Symptom | Cause |
|---|---|
| Search returns "No relevant information found" but documents are indexed | Querying the data store instead of an Enterprise engine — set `*_SEARCH_ENGINE_ID` (2.4) |
| `404 NOT_FOUND` on a model that `models.list()` shows | Model is global-only; set `MODEL_LOCATION=global` |
| Deploy fails "failed to start and cannot serve traffic" | Stale wheel — `poetry build`, then read container logs for the real error |
| Phoenix reports no intelligence | Extraction never ran, or `COMPANY_PROFILE` does not match the `reports/<profile>/` prefix |
| A `PROFILE MISMATCH` banner in output | The bucket holds another company's extraction — re-run extraction for this profile |
| Extraction stalls with no output, 0% CPU | A model call hung; `_TimeoutGemini` bounds this at 10 minutes. Older revisions had no timeout and hung indefinitely |
| `429 RESOURCE_EXHAUSTED` kills a run | Should retry automatically (6 attempts, exponential backoff). If it still fails, raise `MIN_CALL_INTERVAL` in `callbacks.py` |
