import glob
import os
from dotenv import load_dotenv

# Load .env before importing agents — module-level code in tools reads env vars at import time
load_dotenv()

import vertexai
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp
from phoenix import PROFILE
from phoenix.agent import phoenix_agent
from intelligence_extractor.agent import root_agent as intelligence_extractor_agent


def _find_agent_wheel() -> str:
    """Locates the built agent wheel in dist/.

    The wheel filename embeds the package version, so hardcoding it means
    every version bump either breaks the deploy or, worse, silently ships a
    stale wheel that is still sitting in dist/. Pick the newest build and
    fail loudly when there is none.
    """
    wheels = sorted(
        glob.glob("dist/earnings_analyst-*-py3-none-any.whl"),
        key=os.path.getmtime,
        reverse=True,
    )
    if not wheels:
        raise FileNotFoundError(
            "No agent wheel found in dist/. Run `poetry build` before deploying."
        )
    if len(wheels) > 1:
        print(f"  ⚠️  Multiple wheels in dist/ — using newest: {wheels[0]}")

    _assert_wheel_is_current(wheels[0])
    return wheels[0]


def _assert_wheel_is_current(wheel: str) -> None:
    """Refuses to deploy a wheel older than the source it is built from.

    The agent is serialised with cloudpickle, which stores references by name
    and resolves them inside the container against the shipped wheel. So a
    stale wheel does not fail at build time — it fails minutes later as an
    opaque "failed to start and cannot serve traffic", and the real cause is
    buried in the container logs. This exact failure cost a full deploy cycle:
    the wheel predated a new class, and the container died with
    "module 'phoenix' has no attribute '_TimeoutGemini'".
    """
    wheel_mtime = os.path.getmtime(wheel)
    newer = []
    for package in ("phoenix", "intelligence_extractor", "company_profiles"):
        for root, _, files in os.walk(package):
            if "__pycache__" in root:
                continue
            for name in files:
                if not name.endswith((".py", ".json")):
                    continue
                path = os.path.join(root, name)
                if os.path.getmtime(path) > wheel_mtime:
                    newer.append(path)

    if newer:
        listed = "\n      ".join(sorted(newer)[:10])
        more = f"\n      ... and {len(newer) - 10} more" if len(newer) > 10 else ""
        raise RuntimeError(
            f"{wheel} is older than {len(newer)} source file(s):\n"
            f"      {listed}{more}\n"
            f"\n    Run `poetry build` first. Deploying now would ship stale "
            f"code and fail inside the container with an unrelated-looking "
            f"error."
        )


AGENT_WHL_FILE = _find_agent_wheel()

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
    # Without these the deployed agent queries the bare data stores, which
    # return titles and links but no extractive text or page numbers.
    "EARNINGS_SEARCH_ENGINE_ID",
    "COMPETITOR_SEARCH_ENGINE_ID",
    "DATA_STORE_LOCATION",
    "INTELLIGENCE_BUCKET",
    "PHOENIX_MODEL",
    "PHOENIX_FLASH_MODEL",
    # Without this the deployed agent falls back to the example profile.
    "COMPANY_PROFILE",
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
        labels["customer"] = PROFILE.customer_label
        engine.labels = labels
        lro = client.update_reasoning_engine(
            aiplatform_v1.UpdateReasoningEngineRequest(
                reasoning_engine=engine,
                update_mask=field_mask_pb2.FieldMask(paths=["labels"]),
            )
        )
        lro.result()
        print(f"  ✅ Label 'customer: {PROFILE.customer_label}' added")
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
