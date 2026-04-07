"""GCS storage tools for saving extracted intelligence reports."""

import os
import json
import logging
from datetime import datetime, timezone

from google.cloud import storage

logger = logging.getLogger(__name__)

INTELLIGENCE_BUCKET = os.environ["INTELLIGENCE_BUCKET"]
PROJECT_ID = os.environ["GOOGLE_CLOUD_PROJECT"]

INTELLIGENCE_REPORT_PATH = "reports/intelligence_report.md"
ANALYST_REPORT_PATH = "reports/analyst_report.md"
COMPETITOR_REPORT_PATH = "reports/competitor_report.md"
METADATA_PATH = "reports/metadata.json"


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
        logger.error(f"Failed to save {report_type} report to GCS: {e}")
        return f"Error saving report: {e}"
