"""Tests for recorder S3 persistence."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def sample_job_data() -> dict[str, Any]:
    """Minimal job result data for testing."""
    return {
        "job_id": "test-job-abc123",
        "job": {
            "created_at": "2026-03-11T12:00:00+00:00",
            "metadata": {"scraper_id": "nyc_efap_programs"},
        },
        "result": {"text": "{}"},
        "status": "completed",
    }


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output = tmp_path / "outputs"
    output.mkdir()
    return output


class TestRecorderS3Write:
    """Tests for S3 write path in record_result."""

    def test_writes_to_s3_when_env_var_set(
        self,
        sample_job_data: dict[str, Any],
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When RECORDER_S3_BUCKET is set, write to S3 instead of local filesystem."""
        monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
        monkeypatch.setenv("RECORDER_S3_BUCKET", "my-test-bucket")

        mock_s3 = MagicMock()

        with patch("boto3.client", return_value=mock_s3):
            from app.recorder.utils import record_result

            result = record_result(sample_job_data)

        assert result["status"] == "completed"
        assert result["output_file"].startswith("s3://my-test-bucket/recorder/")
        assert "nyc_efap_programs" in result["output_file"]
        assert "test-job-abc123.json" in result["output_file"]

        mock_s3.put_object.assert_called_once()
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "my-test-bucket"
        assert call_kwargs["Key"].startswith("recorder/daily/2026-03-11/scrapers/")
        assert call_kwargs["ContentType"] == "application/json"

        body = call_kwargs["Body"].decode("utf-8")
        parsed = json.loads(body)
        assert parsed["job_id"] == "test-job-abc123"

    def test_s3_key_structure(
        self,
        sample_job_data: dict[str, Any],
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """S3 key follows recorder/daily/YYYY-MM-DD/scrapers/{scraper_id}/{job_id}.json."""
        monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
        monkeypatch.setenv("RECORDER_S3_BUCKET", "test-bucket")

        mock_s3 = MagicMock()

        with patch("boto3.client", return_value=mock_s3):
            from app.recorder.utils import record_result

            record_result(sample_job_data)

        expected_key = (
            "recorder/daily/2026-03-11/scrapers/"
            "nyc_efap_programs/test-job-abc123.json"
        )
        call_kwargs = mock_s3.put_object.call_args[1]
        assert call_kwargs["Key"] == expected_key

    def test_no_local_files_created_when_s3(
        self,
        sample_job_data: dict[str, Any],
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """S3 path should not create local directories, symlinks, or summary files."""
        monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
        monkeypatch.setenv("RECORDER_S3_BUCKET", "test-bucket")

        mock_s3 = MagicMock()

        with patch("boto3.client", return_value=mock_s3):
            from app.recorder.utils import record_result

            record_result(sample_job_data)

        # No local files should be created
        assert list(output_dir.iterdir()) == []


class TestRecorderLocalFallback:
    """Tests for local filesystem fallback when RECORDER_S3_BUCKET is not set."""

    def test_writes_locally_when_no_s3_env(
        self,
        sample_job_data: dict[str, Any],
        output_dir: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Without RECORDER_S3_BUCKET, write to local filesystem as before."""
        monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
        monkeypatch.delenv("RECORDER_S3_BUCKET", raising=False)

        from app.recorder.utils import record_result

        result = record_result(sample_job_data)

        assert result["status"] == "completed"
        assert not result["output_file"].startswith("s3://")

        # Local file should exist
        output_file = Path(result["output_file"])
        assert output_file.exists()

        # Summary and symlink should exist
        date_str = datetime.fromisoformat(
            sample_job_data["job"]["created_at"]
        ).strftime("%Y-%m-%d")
        assert (output_dir / "daily" / date_str / "summary.json").exists()
        assert (output_dir / "latest").is_symlink()


class TestRecorderS3Retry:
    """Tests for @with_aws_retry on _write_to_s3."""

    def test_transient_error_is_retried(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Transient S3 errors (Throttling) should be retried."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "Throttling", "Message": "Rate exceeded"}}
        throttle_error = ClientError(error_response, "PutObject")

        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = [throttle_error, None]

        with patch("app.content_store.retry.time.sleep"):
            with patch("boto3.client", return_value=mock_s3):
                from app.recorder.utils import _write_to_s3

                result = _write_to_s3("test-bucket", "test-key", '{"data": 1}')

        assert result == "s3://test-bucket/test-key"
        assert mock_s3.put_object.call_count == 2

    def test_permanent_error_not_retried(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Permanent S3 errors (AccessDenied) should not be retried."""
        from botocore.exceptions import ClientError

        error_response = {"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}
        access_denied = ClientError(error_response, "PutObject")

        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = access_denied

        with patch("app.content_store.retry.time.sleep"):
            with patch("boto3.client", return_value=mock_s3):
                from app.recorder.utils import _write_to_s3

                with pytest.raises(ClientError) as exc_info:
                    _write_to_s3("test-bucket", "test-key", '{"data": 1}')

        assert exc_info.value.response["Error"]["Code"] == "AccessDenied"
        assert mock_s3.put_object.call_count == 1
