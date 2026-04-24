"""Tests for PortalIngestScraper — admin portal upload dispatch scraper."""

import json
from unittest.mock import MagicMock, patch

import pytest

from app.scraper.scrapers.portal_ingest_scraper import PortalIngestScraper


SAMPLE_PAYLOAD = {
    "rows": [
        {"name": "Pantry A", "address": "123 A St", "city": "Springfield"},
        {"name": "Pantry B", "address": "456 B St", "city": "Shelbyville"},
        {"name": "Pantry C", "address": "789 C St", "city": "Capital City"},
    ],
    "metadata": {
        "filename": "uploads.csv",
        "uploaded_by": "alice",
        "upload_id": "20260424-abcd1234",
    },
}


def test_scraper_init():
    """Scraper initializes with the canonical portal_ingest id."""
    scraper = PortalIngestScraper()
    assert scraper.scraper_id == "portal_ingest"


def test_scraper_accepts_custom_id():
    scraper = PortalIngestScraper(scraper_id="portal_ingest_test")
    assert scraper.scraper_id == "portal_ingest_test"


@pytest.mark.asyncio
async def test_scrape_submits_one_per_row(monkeypatch, tmp_path):
    """Each row becomes its own submit_to_queue call with raw JSON."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(SAMPLE_PAYLOAD))
    monkeypatch.setenv("UPLOAD_PAYLOAD_PATH", str(payload_path))
    monkeypatch.setenv("UPLOAD_ID", "20260424-abcd1234")

    scraper = PortalIngestScraper()
    submitted = []

    def capture(content: str) -> str:
        submitted.append(json.loads(content))
        return f"job-{len(submitted)}"

    with patch.object(scraper, "submit_to_queue", side_effect=capture):
        summary_str = await scraper.scrape()

    summary = json.loads(summary_str)
    assert summary["submitted"] == 3
    assert summary["total"] == 3
    assert summary["failed"] == 0
    assert summary["upload_id"] == "20260424-abcd1234"
    assert summary["source"] == "portal_ingest"

    assert len(submitted) == 3
    assert submitted[0]["name"] == "Pantry A"
    assert submitted[1]["name"] == "Pantry B"
    assert submitted[2]["name"] == "Pantry C"


@pytest.mark.asyncio
async def test_scrape_stamps_ingest_metadata_on_each_row(monkeypatch, tmp_path):
    """Every row carries upload_id + row_index + filename + uploaded_by."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(SAMPLE_PAYLOAD))
    monkeypatch.setenv("UPLOAD_PAYLOAD_PATH", str(payload_path))
    monkeypatch.setenv("UPLOAD_ID", "20260424-abcd1234")

    scraper = PortalIngestScraper()
    submitted = []

    def capture(content: str) -> str:
        submitted.append(json.loads(content))
        return "j"

    with patch.object(scraper, "submit_to_queue", side_effect=capture):
        await scraper.scrape()

    for idx, row in enumerate(submitted):
        assert row["_portal_ingest"]["upload_id"] == "20260424-abcd1234"
        assert row["_portal_ingest"]["row_index"] == idx
        assert row["_portal_ingest"]["filename"] == "uploads.csv"
        assert row["_portal_ingest"]["uploaded_by"] == "alice"


@pytest.mark.asyncio
async def test_scrape_empty_rows(monkeypatch, tmp_path):
    """Empty rows list yields a summary with zero submissions, no errors."""
    payload = {"rows": [], "metadata": {"filename": "empty.csv"}}
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(payload))
    monkeypatch.setenv("UPLOAD_PAYLOAD_PATH", str(payload_path))

    scraper = PortalIngestScraper()
    with patch.object(scraper, "submit_to_queue", return_value="j"):
        summary_str = await scraper.scrape()

    summary = json.loads(summary_str)
    assert summary["submitted"] == 0
    assert summary["total"] == 0
    assert summary["failed"] == 0


@pytest.mark.asyncio
async def test_scrape_row_failure_continues(monkeypatch, tmp_path):
    """A failure on one row does not abort subsequent rows."""
    payload_path = tmp_path / "payload.json"
    payload_path.write_text(json.dumps(SAMPLE_PAYLOAD))
    monkeypatch.setenv("UPLOAD_PAYLOAD_PATH", str(payload_path))

    scraper = PortalIngestScraper()

    calls = []

    def capture(content: str) -> str:
        calls.append(content)
        if len(calls) == 2:
            raise RuntimeError("queue full")
        return f"j{len(calls)}"

    with patch.object(scraper, "submit_to_queue", side_effect=capture):
        summary_str = await scraper.scrape()

    summary = json.loads(summary_str)
    assert summary["submitted"] == 2
    assert summary["failed"] == 1
    assert summary["total"] == 3
    assert len(calls) == 3  # all three rows attempted


@pytest.mark.asyncio
async def test_scrape_requires_env_var(monkeypatch):
    """Raise RuntimeError if neither S3 URI nor local path is set."""
    monkeypatch.delenv("UPLOAD_PAYLOAD_S3_URI", raising=False)
    monkeypatch.delenv("UPLOAD_PAYLOAD_PATH", raising=False)

    scraper = PortalIngestScraper()
    with pytest.raises(RuntimeError, match="UPLOAD_PAYLOAD_"):
        await scraper.scrape()


class TestLoadFromS3:
    """S3 payload loading uses boto3 and parses JSON correctly."""

    def test_load_from_s3_parses_payload(self, monkeypatch):
        monkeypatch.setenv(
            "UPLOAD_PAYLOAD_S3_URI", "s3://test-bucket/uploads/20260424-ab.json"
        )
        monkeypatch.delenv("UPLOAD_PAYLOAD_PATH", raising=False)

        mock_s3 = MagicMock()
        body = MagicMock()
        body.read.return_value = json.dumps(SAMPLE_PAYLOAD).encode("utf-8")
        mock_s3.get_object.return_value = {"Body": body}

        scraper = PortalIngestScraper()
        with patch("app.scraper.scrapers.portal_ingest_scraper.boto3") as mock_boto:
            mock_boto.client.return_value = mock_s3
            result = scraper._load_payload()

        assert result == SAMPLE_PAYLOAD
        mock_s3.get_object.assert_called_once_with(
            Bucket="test-bucket", Key="uploads/20260424-ab.json"
        )

    def test_load_from_s3_rejects_bad_uri(self, monkeypatch):
        monkeypatch.setenv("UPLOAD_PAYLOAD_S3_URI", "http://not-s3")
        scraper = PortalIngestScraper()
        with pytest.raises(ValueError, match="Invalid S3 URI"):
            scraper._load_payload()

    def test_load_from_s3_rejects_missing_key(self, monkeypatch):
        monkeypatch.setenv("UPLOAD_PAYLOAD_S3_URI", "s3://bucket-only")
        scraper = PortalIngestScraper()
        with pytest.raises(ValueError, match="Invalid S3 URI"):
            scraper._load_payload()

    def test_load_prefers_s3_over_local(self, monkeypatch, tmp_path):
        """S3 URI wins when both env vars are set."""
        local_path = tmp_path / "payload.json"
        local_path.write_text('{"rows":[],"metadata":{"filename":"local.csv"}}')
        monkeypatch.setenv("UPLOAD_PAYLOAD_PATH", str(local_path))
        monkeypatch.setenv("UPLOAD_PAYLOAD_S3_URI", "s3://bucket/key.json")

        mock_s3 = MagicMock()
        body = MagicMock()
        body.read.return_value = json.dumps(SAMPLE_PAYLOAD).encode("utf-8")
        mock_s3.get_object.return_value = {"Body": body}

        scraper = PortalIngestScraper()
        with patch("app.scraper.scrapers.portal_ingest_scraper.boto3") as mock_boto:
            mock_boto.client.return_value = mock_s3
            result = scraper._load_payload()

        assert result == SAMPLE_PAYLOAD  # not the local one
