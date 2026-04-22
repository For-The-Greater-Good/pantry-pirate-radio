"""Tests for S3 upload module and exporter CLI args for AWS deployment.

Tests the S3 upload functionality extracted into app/datasette/s3_upload.py
and the new CLI arguments added to exporter.py for AWS pipeline usage.
"""

from unittest.mock import MagicMock, call, patch

import pytest


class TestUploadToS3:
    """Tests for the upload_to_s3 function."""

    @patch("app.datasette.s3_upload.boto3")
    def test_uploads_dated_copy(self, mock_boto3):
        """upload_to_s3 should upload a dated copy to S3."""
        from app.datasette.s3_upload import upload_to_s3

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch("app.datasette.s3_upload._today_str", return_value="2026-03-05"):
            upload_to_s3("/data/test.sqlite", "my-bucket")

        mock_client.upload_file.assert_any_call(
            "/data/test.sqlite",
            "my-bucket",
            "sqlite-exports/2026-03-05/test.sqlite",
        )

    @patch("app.datasette.s3_upload.boto3")
    def test_uploads_latest_copy(self, mock_boto3):
        """upload_to_s3 should upload a 'latest' copy to S3."""
        from app.datasette.s3_upload import upload_to_s3

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch("app.datasette.s3_upload._today_str", return_value="2026-03-05"):
            upload_to_s3("/data/test.sqlite", "my-bucket")

        mock_client.upload_file.assert_any_call(
            "/data/test.sqlite",
            "my-bucket",
            "sqlite-exports/latest/test.sqlite",
        )

    @patch("app.datasette.s3_upload.boto3")
    def test_custom_prefix(self, mock_boto3):
        """upload_to_s3 should respect custom S3 prefix."""
        from app.datasette.s3_upload import upload_to_s3

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch("app.datasette.s3_upload._today_str", return_value="2026-03-05"):
            upload_to_s3("/data/test.sqlite", "my-bucket", prefix="custom-prefix")

        mock_client.upload_file.assert_any_call(
            "/data/test.sqlite",
            "my-bucket",
            "custom-prefix/2026-03-05/test.sqlite",
        )
        mock_client.upload_file.assert_any_call(
            "/data/test.sqlite",
            "my-bucket",
            "custom-prefix/latest/test.sqlite",
        )

    @patch("app.datasette.s3_upload.boto3")
    def test_makes_exactly_two_uploads(self, mock_boto3):
        """upload_to_s3 should make exactly two uploads (dated + latest)."""
        from app.datasette.s3_upload import upload_to_s3

        mock_client = MagicMock()
        mock_boto3.client.return_value = mock_client

        with patch("app.datasette.s3_upload._today_str", return_value="2026-03-05"):
            upload_to_s3("/data/test.sqlite", "my-bucket")

        assert mock_client.upload_file.call_count == 2


class TestCloudFrontInvalidation:
    """Tests for the CloudFront invalidation triggered after /latest upload."""

    @patch.dict("os.environ", {"EXPORT_CLOUDFRONT_DISTRIBUTION_ID": "EABC123DEF"})
    @patch("app.datasette.s3_upload.boto3")
    def test_invalidates_after_upload(self, mock_boto3):
        """upload_to_s3 should invalidate CF after the latest/ copy is uploaded."""
        from app.datasette.s3_upload import upload_to_s3

        s3_client = MagicMock()
        cf_client = MagicMock()
        cf_client.create_invalidation.return_value = {
            "Invalidation": {"Id": "I-123ABC", "Status": "InProgress"}
        }
        mock_boto3.client.side_effect = lambda svc: {
            "s3": s3_client,
            "cloudfront": cf_client,
        }[svc]

        with patch("app.datasette.s3_upload._today_str", return_value="2026-04-22"):
            upload_to_s3("/data/test.sqlite", "my-bucket")

        cf_client.create_invalidation.assert_called_once()
        kwargs = cf_client.create_invalidation.call_args.kwargs
        assert kwargs["DistributionId"] == "EABC123DEF"
        paths = kwargs["InvalidationBatch"]["Paths"]["Items"]
        assert "/sqlite-exports/latest/test.sqlite" in paths
        assert "/sqlite-exports/latest/*" in paths

    @patch.dict("os.environ", {}, clear=True)
    @patch("app.datasette.s3_upload.boto3")
    def test_no_distribution_id_skips_invalidation(self, mock_boto3):
        """Missing EXPORT_CLOUDFRONT_DISTRIBUTION_ID env var → skip, don't raise."""
        from app.datasette.s3_upload import upload_to_s3

        s3_client = MagicMock()
        cf_client = MagicMock()
        mock_boto3.client.side_effect = lambda svc: {
            "s3": s3_client,
            "cloudfront": cf_client,
        }[svc]

        with patch("app.datasette.s3_upload._today_str", return_value="2026-04-22"):
            upload_to_s3("/data/test.sqlite", "my-bucket")

        cf_client.create_invalidation.assert_not_called()
        # S3 uploads still happen
        assert s3_client.upload_file.call_count == 2

    @patch.dict("os.environ", {"EXPORT_CLOUDFRONT_DISTRIBUTION_ID": "EABC123DEF"})
    @patch("app.datasette.s3_upload.boto3")
    def test_invalidation_failure_does_not_break_upload(self, mock_boto3, caplog):
        """CF errors are logged as warnings — publisher must not fail the run."""
        import logging

        from app.datasette.s3_upload import upload_to_s3

        s3_client = MagicMock()
        cf_client = MagicMock()
        cf_client.create_invalidation.side_effect = RuntimeError("AccessDenied")
        mock_boto3.client.side_effect = lambda svc: {
            "s3": s3_client,
            "cloudfront": cf_client,
        }[svc]

        with caplog.at_level(logging.WARNING):
            with patch("app.datasette.s3_upload._today_str", return_value="2026-04-22"):
                # Must not raise
                upload_to_s3("/data/test.sqlite", "my-bucket")

        # S3 uploads still succeeded
        assert s3_client.upload_file.call_count == 2
        # Failure surfaced in logs
        assert any(
            "cloudfront_invalidation_failed" in rec.message
            or "cloudfront_invalidation_failed" in str(rec.args)
            for rec in caplog.records
        )

    @patch.dict("os.environ", {"EXPORT_CLOUDFRONT_DISTRIBUTION_ID": "EABC123DEF"})
    @patch("app.datasette.s3_upload.boto3")
    def test_custom_prefix_paths(self, mock_boto3):
        """Custom prefix is reflected in invalidation paths."""
        from app.datasette.s3_upload import upload_to_s3

        s3_client = MagicMock()
        cf_client = MagicMock()
        cf_client.create_invalidation.return_value = {
            "Invalidation": {"Id": "I-456", "Status": "InProgress"}
        }
        mock_boto3.client.side_effect = lambda svc: {
            "s3": s3_client,
            "cloudfront": cf_client,
        }[svc]

        with patch("app.datasette.s3_upload._today_str", return_value="2026-04-22"):
            upload_to_s3("/data/test.sqlite", "my-bucket", prefix="custom-prefix")

        kwargs = cf_client.create_invalidation.call_args.kwargs
        paths = kwargs["InvalidationBatch"]["Paths"]["Items"]
        assert "/custom-prefix/latest/test.sqlite" in paths
        assert "/custom-prefix/latest/*" in paths


class TestBuildDatabaseUrlFromEnv:
    """Tests for building DATABASE_URL from component env vars."""

    @patch.dict(
        "os.environ",
        {
            "DATABASE_HOST": "my-proxy.rds.amazonaws.com",
            "DATABASE_NAME": "pantry_pirate_radio",
            "DATABASE_USER": "pantry_pirate",
            "DATABASE_PASSWORD": "secret123",
        },
    )
    def test_builds_url_from_env_vars(self):
        """build_database_url_from_env should construct URL from component vars."""
        from app.datasette.s3_upload import build_database_url_from_env

        url = build_database_url_from_env()
        assert url == (
            "postgresql://pantry_pirate:secret123@"
            "my-proxy.rds.amazonaws.com:5432/pantry_pirate_radio"
        )

    @patch.dict(
        "os.environ",
        {
            "DATABASE_HOST": "my-proxy.rds.amazonaws.com",
            "DATABASE_NAME": "pantry_pirate_radio",
            "DATABASE_USER": "pantry_pirate",
            "DATABASE_PASSWORD": "secret123",
            "DATABASE_PORT": "5433",
        },
    )
    def test_respects_custom_port(self):
        """build_database_url_from_env should use DATABASE_PORT if set."""
        from app.datasette.s3_upload import build_database_url_from_env

        url = build_database_url_from_env()
        assert "5433" in url

    @patch.dict("os.environ", {}, clear=True)
    def test_raises_on_missing_host(self):
        """build_database_url_from_env should raise if DATABASE_HOST is missing."""
        from app.datasette.s3_upload import build_database_url_from_env

        with pytest.raises(ValueError, match="DATABASE_HOST"):
            build_database_url_from_env()
