import os
from dotenv import load_dotenv

# Load .env before importing agents — module-level code in tools reads env vars at import time
load_dotenv()

import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
from phoenix.agent import phoenix_agent
from intelligence_extractor.agent import root_agent as intelligence_extractor_agent

AGENT_WHL_FILE = "dist/earnings_analyst-0.1-py3-none-any.whl"

REQUIREMENTS = [
    f"./{AGENT_WHL_FILE}",
    "google-adk>=1.0.0",
    "google-genai>=1.5.0",
    "google-cloud-discoveryengine>=0.13.0",
    "google-cloud-storage>=2.18.0",
    "google-cloud-aiplatform[adk,agent-engines]>=1.93.0",
    "pydantic==2.12.5",
    "cloudpickle==3.1.2",
]

# Custom app config forwarded to the deployed agent's runtime environment.
# GCP platform vars (GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, etc.) are
# reserved — Agent Engine sets them automatically and rejects them here.
RUNTIME_ENV_VARS = [
    "EARNINGS_DATA_STORE_ID",
    "COMPETITOR_DATA_STORE_ID",
    "DATA_STORE_LOCATION",
    "INTELLIGENCE_BUCKET",
    "PHOENIX_MODEL",
    "PHOENIX_FLASH_MODEL",
]

# These must also be in .env for local deployment to work, but are NOT
# forwarded to Agent Engine (it sets them automatically).
DEPLOY_REQUIRED_VARS = [
    "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
    "GOOGLE_CLOUD_STORAGE_BUCKET",
    "AGENT_SERVICE_ACCOUNT",
] + RUNTIME_ENV_VARS


def _build_env_vars() -> dict:
    """Build the runtime env dict from the loaded environment."""
    missing = [k for k in DEPLOY_REQUIRED_VARS if not os.environ.get(k)]
    if missing:
        raise EnvironmentError(
            f"Missing required .env variables: {', '.join(missing)}"
        )
    return {k: os.environ[k] for k in RUNTIME_ENV_VARS}


def _add_label(resource_name: str, location: str) -> None:
    try:
        from google.cloud import aiplatform_v1
        from google.api_core.client_options import ClientOptions
        from google.protobuf import field_mask_pb2

        client = aiplatform_v1.ReasoningEngineServiceClient(
            client_options=ClientOptions(
                api_endpoint=f"{location}-aiplatform.googleapis.com"
            )
        )
        engine = client.get_reasoning_engine(name=resource_name)
        labels = dict(engine.labels) if engine.labels else {}
        labels["customer"] = "trane"
        engine.labels = labels
        lro = client.update_reasoning_engine(
            aiplatform_v1.UpdateReasoningEngineRequest(
                reasoning_engine=engine,
                update_mask=field_mask_pb2.FieldMask(paths=["labels"]),
            )
        )
        lro.result()
        print("  ✅ Label 'customer: trane' added")
    except Exception as e:
        print(f"  ⚠️  Failed to add label: {e}")


def deploy_phoenix(env_vars: dict, bucket: str, location: str) -> None:
    print("\n--- Deploying Phoenix (C-Suite Earnings Prep) ---")
    vertexai.init(project=os.environ["GOOGLE_CLOUD_PROJECT"], location=location, staging_bucket=f"gs://{bucket}")
    adk_app = AdkApp(agent=phoenix_agent, enable_tracing=False)
    remote = agent_engines.create(
        adk_app,
        requirements=REQUIREMENTS,
        extra_packages=[f"./{AGENT_WHL_FILE}"],
        service_account=os.environ["AGENT_SERVICE_ACCOUNT"],
        display_name="Phoenix C-Suite Agent",
        description="C-Suite earnings call prep advisor — analyst intelligence, competitor benchmarking, interactive coaching.",
        env_vars=env_vars,
    )
    print(f"  ✅ Phoenix deployed: {remote.resource_name}")
    _add_label(remote.resource_name, location)


def deploy_intelligence_extractor(env_vars: dict, ie_bucket: str, location: str) -> None:
    print("\n--- Deploying Intelligence Extractor (Batch Pipeline) ---")
    # Uses a separate staging bucket so its pkl doesn't overwrite Phoenix's
    vertexai.init(project=os.environ["GOOGLE_CLOUD_PROJECT"], location=location, staging_bucket=f"gs://{ie_bucket}")
    adk_app = AdkApp(agent=intelligence_extractor_agent, enable_tracing=False)
    remote = agent_engines.create(
        adk_app,
        requirements=REQUIREMENTS,
        extra_packages=[f"./{AGENT_WHL_FILE}"],
        service_account=os.environ["AGENT_SERVICE_ACCOUNT"],
        display_name="Intelligence Extractor",
        description="Batch agent — extracts company financials, analyst profiles, and competitor intelligence from Vertex AI Search and saves to GCS.",
        env_vars=env_vars,
    )
    print(f"  ✅ Intelligence Extractor deployed: {remote.resource_name}")
    _add_label(remote.resource_name, location)


def main() -> None:
    load_dotenv()

    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT")
    location = os.environ.get("GOOGLE_CLOUD_LOCATION")
    bucket = os.environ.get("GOOGLE_CLOUD_STORAGE_BUCKET")

    print(f"PROJECT:  {project_id}")
    print(f"LOCATION: {location}")
    print(f"BUCKET:   {bucket}")

    if not all([project_id, location, bucket]):
        print("❌ Missing required .env variables: GOOGLE_CLOUD_PROJECT, GOOGLE_CLOUD_LOCATION, GOOGLE_CLOUD_STORAGE_BUCKET")
        return

    ie_bucket = os.environ.get("IE_STAGING_BUCKET")
    if not ie_bucket:
        print("❌ Missing required .env variable: IE_STAGING_BUCKET")
        return

    env_vars = _build_env_vars()

    deploy_phoenix(env_vars, bucket, location)
    deploy_intelligence_extractor(env_vars, ie_bucket, location)

    print("\n✅ All agents deployed.")


if __name__ == "__main__":
    main()
