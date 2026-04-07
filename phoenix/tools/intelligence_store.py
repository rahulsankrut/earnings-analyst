"""Tools for reading pre-extracted intelligence reports from GCS.

Intelligence reports are generated offline by the extraction pipeline and
stored in the staging bucket. Phoenix reads these at session start for
instant briefing generation, avoiding expensive real-time searches.
"""

import os
import json
import logging

from google.cloud import storage

logger = logging.getLogger(__name__)

INTELLIGENCE_BUCKET = os.environ["INTELLIGENCE_BUCKET"]
PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

# Paths within the bucket
INTELLIGENCE_REPORT_PATH = "reports/intelligence_report.md"
ANALYST_REPORT_PATH = "reports/analyst_report.md"
COMPETITOR_REPORT_PATH = "reports/competitor_report.md"
METADATA_PATH = "reports/metadata.json"


def _get_storage_client():
    """Get a GCS storage client."""
    return storage.Client(project=PROJECT_ID)


def _read_report(blob_path: str, report_label: str, metadata_key: str) -> str:
    """Internal helper to read a report from GCS with metadata."""
    try:
        client = _get_storage_client()
        bucket = client.bucket(INTELLIGENCE_BUCKET)
        blob = bucket.blob(blob_path)

        if not blob.exists():
            return (
                f"No pre-extracted {report_label} found. "
                "Run the extraction pipeline first: "
                "adk run intelligence_extractor"
            )

        content = blob.download_as_text()

        # Read metadata to show freshness
        meta_blob = bucket.blob(METADATA_PATH)
        if meta_blob.exists():
            metadata = json.loads(meta_blob.download_as_text())
            extracted_at = metadata.get(metadata_key, "unknown")
            content = (
                f"[{report_label} extracted: {extracted_at}]\n\n"
                + content
            )

        return content
    except Exception as e:
        logger.error(f"Failed to read {report_label} from GCS: {e}")
        return f"Error reading {report_label}: {e}"


def read_intelligence_report() -> str:
    """Reads the pre-extracted company intelligence report from Cloud Storage.

    Contains historical financial trends, guidance credibility analysis,
    narrative risk map, and a high-risk question bank — all pre-computed
    from the Vertex AI Search data stores.

    Returns:
        str: The full intelligence report in markdown, or an error message
             if the report hasn't been generated yet.
    """
    return _read_report(
        INTELLIGENCE_REPORT_PATH,
        "Intelligence report",
        "intelligence_extracted_at",
    )


def read_analyst_report() -> str:
    """Reads the pre-extracted analyst intelligence report from Cloud Storage.

    Contains deep behavioral profiles of every sell-side analyst covering
    the company — their questioning patterns, escalation behaviors, core
    obsessions, and predicted focus areas. Pre-computed from earnings call
    transcript analysis.

    Returns:
        str: The full analyst report in markdown, or an error message
             if the report hasn't been generated yet.
    """
    return _read_report(
        ANALYST_REPORT_PATH,
        "Analyst report",
        "analyst_extracted_at",
    )


def read_competitor_report() -> str:
    """Reads the pre-extracted competitor intelligence report from Cloud Storage.

    Contains Carrier Global competitive dynamics, analyst questions asked
    of competitors, competitive landmines, and sector themes — all
    pre-computed from the competitor Vertex AI Search data store.

    Returns:
        str: The full competitor report in markdown, or an error message
             if the report hasn't been generated yet.
    """
    return _read_report(
        COMPETITOR_REPORT_PATH,
        "Competitor report",
        "competitor_extracted_at",
    )
