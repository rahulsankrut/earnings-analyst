"""Uploads PDF documents from the local reports/ directory to GCS.

Usage:
    python upload_to_gcs.py

Configure via .env:
    DOCUMENT_BUCKET  — target GCS bucket (required)
    SKIP_PATTERN     — filename substring to skip, e.g. "Q4 2025 10K" (optional)
"""

import os
import glob
from google.cloud import storage
from dotenv import load_dotenv


def main():
    load_dotenv()

    bucket_name = os.environ.get("DOCUMENT_BUCKET")
    if not bucket_name:
        print("❌ DOCUMENT_BUCKET not set in .env")
        return

    skip_pattern = os.environ.get("SKIP_PATTERN", "")

    client = storage.Client()
    bucket = client.bucket(bucket_name)

    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    files = glob.glob(os.path.join(reports_dir, "*.pdf"))

    if not files:
        print("No PDF files found in reports/")
        return

    for filepath in files:
        filename = os.path.basename(filepath)

        if skip_pattern and skip_pattern in filename:
            print(f"Skipping {filename}")
            continue

        blob = bucket.blob(filename)
        blob.upload_from_filename(filepath)
        print(f"Uploaded {filename} to gs://{bucket_name}/{filename}")


if __name__ == "__main__":
    main()
