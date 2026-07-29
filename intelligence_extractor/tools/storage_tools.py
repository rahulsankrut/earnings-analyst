"""GCS storage tools for saving extracted intelligence reports."""

import os
import json
import logging
from datetime import datetime, timezone

from google.cloud import storage

logger = logging.getLogger(__name__)

from company_profiles import load_profile

INTELLIGENCE_BUCKET = os.environ.get("INTELLIGENCE_BUCKET", "")
PROJECT_ID = os.environ.get("GOOGLE_CLOUD_PROJECT", "")

# Reports are namespaced by profile. Without this, pointing a second company at
# an existing INTELLIGENCE_BUCKET would silently overwrite — or serve — the
# first company's intelligence.
REPORT_PREFIX = f"reports/{load_profile().profile_name}"

INTELLIGENCE_REPORT_PATH = f"{REPORT_PREFIX}/intelligence_report.md"
ANALYST_REPORT_PATH = f"{REPORT_PREFIX}/analyst_report.md"
COMPETITOR_REPORT_PATH = f"{REPORT_PREFIX}/competitor_report.md"
METADATA_PATH = f"{REPORT_PREFIX}/metadata.json"


def save_intelligence_report(report: str, report_type: str) -> str:
    """Saves an extracted intelligence report to Cloud Storage.

    Call this after extraction is complete to persist the report
    to the GCS staging bucket for Phoenix to read.

    Args:
        report: The full report content in markdown. Must be the
                COMPLETE report — do not summarize or truncate.
        report_type: Either "intelligence", "analyst", or "competitor".

    Returns:
        str: Success confirmation with timestamp, or error message.
    """
    try:
        valid_types = ("intelligence", "analyst", "competitor")
        if report_type not in valid_types:
            return (
                f"Invalid report_type: {report_type}. "
                f"Must be one of: {', '.join(valid_types)}."
            )

        client = storage.Client(project=PROJECT_ID)
        bucket = client.bucket(INTELLIGENCE_BUCKET)

        path_map = {
            "intelligence": INTELLIGENCE_REPORT_PATH,
            "analyst": ANALYST_REPORT_PATH,
            "competitor": COMPETITOR_REPORT_PATH,
        }
        path = path_map[report_type]
        blob = bucket.blob(path)
        blob.upload_from_string(report, content_type="text/markdown")

        # Update metadata with extraction timestamp
        meta_blob = bucket.blob(METADATA_PATH)
        metadata = {}
        if meta_blob.exists():
            metadata = json.loads(meta_blob.download_as_text())

        now = datetime.now(timezone.utc).isoformat()
        metadata[f"{report_type}_extracted_at"] = now
        # Stamped so readers can detect a profile/bucket mismatch instead of
        # silently serving another company's intelligence.
        metadata["profile"] = load_profile().profile_name
        metadata["company_name"] = load_profile().company_name
        meta_blob.upload_from_string(
            json.dumps(metadata, indent=2),
            content_type="application/json",
        )

        logger.info(
            "Saved %s report to gs://%s/%s", report_type, INTELLIGENCE_BUCKET, path
        )
        return (
            f"Successfully saved {report_type} report to "
            f"gs://{INTELLIGENCE_BUCKET}/{path} at {now}."
        )
    except Exception as e:
        logger.error("Failed to save %s report to GCS: %s", report_type, e)
        return f"Error saving {report_type} report. Check server logs for details."
