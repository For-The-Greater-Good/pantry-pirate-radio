"""Scraper for food bank data uploaded via the Helm management UI.

Reads pre-parsed JSON rows from S3 (AWS) or the local filesystem.
Each row is submitted to the pipeline as raw content for LLM alignment.

This scraper is excluded from automated runs (--all, scouting-party).
It is triggered by the ppr-write-api ingest endpoint.
"""

import json
import os

import structlog

from app.scraper.utils import ScraperJob

log = structlog.get_logger()


class HelmPortalScraper(ScraperJob):
    """Scraper that ingests uploaded spreadsheet data from Helm."""

    def __init__(self, scraper_id: str = "helm_portal") -> None:
        super().__init__(scraper_id=scraper_id)

    async def run(self) -> None:
        """Read upload JSON and submit each row to the pipeline."""
        upload_path = os.environ.get("UPLOAD_PATH", "")
        if not upload_path:
            raise ValueError("UPLOAD_PATH environment variable is required")

        log.info("helm_portal_start", upload_path=upload_path)

        payload = self._read_payload(upload_path)
        rows = payload.get("rows", [])
        metadata = payload.get("metadata", {})
        filename = metadata.get("filename", "unknown")

        log.info(
            "helm_portal_loaded",
            filename=filename,
            row_count=len(rows),
        )

        submitted = 0
        for i, row in enumerate(rows):
            try:
                content = json.dumps(row, default=str)
                self.utils.queue_for_processing(
                    content,
                    metadata={
                        "source_type": "file_upload",
                        "filename": filename,
                        "row_number": i,
                    },
                )
                submitted += 1
            except Exception:
                log.warning(
                    "helm_portal_row_failed",
                    row_number=i,
                    exc_info=True,
                )

        log.info(
            "helm_portal_complete",
            submitted=submitted,
            total=len(rows),
            filename=filename,
        )

    async def scrape(self) -> str:
        """Not used — processing is handled in run()."""
        return ""

    @staticmethod
    def _read_payload(path: str) -> dict:
        """Read JSON payload from S3 or local filesystem."""
        if path.startswith("s3://"):
            return HelmPortalScraper._read_from_s3(path)
        with open(path) as f:
            return json.load(f)

    @staticmethod
    def _read_from_s3(uri: str) -> dict:
        """Read JSON from an S3 URI (s3://bucket/key)."""
        import boto3

        parts = uri.replace("s3://", "").split("/", 1)
        bucket = parts[0]
        key = parts[1] if len(parts) > 1 else ""

        s3 = boto3.client("s3")
        response = s3.get_object(Bucket=bucket, Key=key)
        body = response["Body"].read().decode("utf-8")
        return json.loads(body)
