"""Tests for SQS sender audit fixes (M3 error classification)."""

from unittest.mock import MagicMock, patch

import pytest

from app.pipeline.sqs_sender import _is_retryable


class TestM3ErrorClassification:
    """M3: _is_retryable should use proper isinstance checks."""

    def test_retries_on_connection_error(self):
        """ConnectionError should be retryable."""
        assert _is_retryable(ConnectionError("refused")) is True

    def test_retries_on_timeout_error(self):
        """TimeoutError should be retryable."""
        assert _is_retryable(TimeoutError("timed out")) is True

    def test_does_not_retry_value_error(self):
        """ValueError should not be retryable."""
        assert _is_retryable(ValueError("bad input")) is False

    def test_does_not_retry_runtime_error(self):
        """RuntimeError should not be retryable."""
        assert _is_retryable(RuntimeError("unexpected")) is False

    def test_retries_on_botocore_client_error_throttling(self):
        """ClientError with Throttling code should be retryable."""
        try:
            from botocore.exceptions import ClientError

            error = ClientError(
                error_response={
                    "Error": {"Code": "Throttling", "Message": "Rate exceeded"}
                },
                operation_name="SendMessage",
            )
            assert _is_retryable(error) is True
        except ImportError:
            pytest.skip("botocore not available")

    def test_does_not_retry_botocore_client_error_access_denied(self):
        """ClientError with AccessDenied code should NOT be retryable."""
        try:
            from botocore.exceptions import ClientError

            error = ClientError(
                error_response={"Error": {"Code": "AccessDenied", "Message": "Denied"}},
                operation_name="SendMessage",
            )
            assert _is_retryable(error) is False
        except ImportError:
            pytest.skip("botocore not available")

    def test_retries_on_botocore_service_unavailable(self):
        """ClientError with ServiceUnavailable code should be retryable."""
        try:
            from botocore.exceptions import ClientError

            error = ClientError(
                error_response={
                    "Error": {"Code": "ServiceUnavailable", "Message": "Unavailable"}
                },
                operation_name="SendMessage",
            )
            assert _is_retryable(error) is True
        except ImportError:
            pytest.skip("botocore not available")
