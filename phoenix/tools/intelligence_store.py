"""Tools for reading pre-extracted intelligence reports from GCS.

Intelligence reports are generated offline by the extraction pipeline and
stored in the staging bucket. Phoenix reads these at session start for
instant briefing generation, avoiding expensive real-time searches.
"""

import os
import json
import logging
from datetime import datetime, timezone

from google.cloud import storage

from company_profiles import load_profile

logger = logging.getLogger(__name__)

INTELLIGENCE_BUCKET = os.environ.get("INTELLIGENCE_BUCKET", "")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

# Paths within the bucket
# Namespaced by profile — see intelligence_extractor/tools/storage_tools.py,
# which writes to these same paths. Keep the two in step.
REPORT_PREFIX = f"reports/{load_profile().profile_name}"

INTELLIGENCE_REPORT_PATH = f"{REPORT_PREFIX}/intelligence_report.md"
ANALYST_REPORT_PATH = f"{REPORT_PREFIX}/analyst_report.md"
COMPETITOR_REPORT_PATH = f"{REPORT_PREFIX}/competitor_report.md"
METADATA_PATH = f"{REPORT_PREFIX}/metadata.json"

# Reports older than this are flagged to the model, which is instructed to
# surface the warning before advising. Earnings prep on last quarter's
# intelligence is a correctness problem, not a cosmetic one.
STALE_AFTER_DAYS = 45


def _get_storage_client():
    """Get a GCS storage client."""
    return storage.Client(project=PROJECT_ID)


def _report_age_days(extracted_at: str) -> "float | None":
    """Age of a report in days, or None if the timestamp is unparseable."""
    try:
        stamped = datetime.fromisoformat(extracted_at)
    except (ValueError, TypeError):
        return None
    if stamped.tzinfo is None:
        stamped = stamped.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - stamped).total_seconds() / 86400


def _provenance_banner(metadata: dict, metadata_key: str, report_label: str) -> str:
    """Builds the header prepended to every report the model reads.

    Carries three things the model must not have to infer: which company the
    data is about, how old it is, and whether either looks wrong.
    """
    profile = load_profile()
    extracted_at = metadata.get(metadata_key, "unknown")
    stamped_profile = metadata.get("profile")
    stamped_company = metadata.get("company_name", "unknown")

    lines = [
        f"[{report_label} | company: {stamped_company} | extracted: {extracted_at}]"
    ]

    # A mismatch means the bucket holds another company's extraction. Say so
    # loudly rather than letting the model brief on the wrong company.
    if stamped_profile and stamped_profile != profile.profile_name:
        lines.append(
            f"[!! PROFILE MISMATCH — this report was extracted for "
            f"'{stamped_profile}' but the active profile is "
            f"'{profile.profile_name}'. The data below is about a DIFFERENT "
            f"COMPANY. Tell the user immediately and do not brief from it.]"
        )

    age = _report_age_days(extracted_at)
    if age is not None and age > STALE_AFTER_DAYS:
        lines.append(
            f"[!! STALE — extracted {int(age)} days ago. Warn the user that "
            f"this predates the current quarter before advising.]"
        )

    return "\n".join(lines)


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

        meta_blob = bucket.blob(METADATA_PATH)
        if meta_blob.exists():
            metadata = json.loads(meta_blob.download_as_text())
            content = (
                _provenance_banner(metadata, metadata_key, report_label)
                + "\n\n"
                + content
            )

        return content
    except Exception as e:
        logger.error("Failed to read %s from GCS: %s", report_label, e)
        return f"Error reading {report_label}. Check server logs for details."


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

    Contains competitive dynamics for every competitor in the active
    company profile, analyst questions asked of them, competitive
    landmines, and sector themes — all pre-computed from the competitor
    Vertex AI Search data store.

    Returns:
        str: The full competitor report in markdown, or an error message
             if the report hasn't been generated yet.
    """
    return _read_report(
        COMPETITOR_REPORT_PATH,
        "Competitor report",
        "competitor_extracted_at",
    )
