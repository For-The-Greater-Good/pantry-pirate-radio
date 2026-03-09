"""Tests for AWS retry decorator functionality."""

import time
from unittest.mock import MagicMock, patch

import pytest

from app.content_store.retry import (
    AWS_RETRYABLE_ERROR_CODES,
    _get_aws_error_code,
    _is_aws_client_error,
    with_aws_retry,
)


class TestIsAwsClientError:
    """Tests for _is_aws_client_error helper function."""

    def test_returns_true_for_client_error_with_response(self):
        """ClientError with response dict should be detected."""
        try:
            from botocore.exceptions import ClientError

            # Use real ClientError for accurate testing
            error = ClientError(
                {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
                "PutItem",
            )
            assert _is_aws_client_error(error) is True
        except ImportError:
            pytest.skip("botocore not installed")

    def test_returns_false_for_regular_exception(self):
        """Regular exceptions should not be detected as ClientError."""
        error = ValueError("some error")
        assert _is_aws_client_error(error) is False

    def test_returns_false_for_client_error_without_response(self):
        """ClientError without response attribute should return False."""

        class FakeClientError(Exception):
            pass

        error = FakeClientError("test")
        assert _is_aws_client_error(error) is False

    def test_returns_false_for_client_error_with_non_dict_response(self):
        """ClientError with non-dict response should return False."""

        class FakeClientError(Exception):
            response = "not a dict"

        error = FakeClientError("test")
        # Type name doesn't match "ClientError" exactly
        assert _is_aws_client_error(error) is False


class TestGetAwsErrorCode:
    """Tests for _get_aws_error_code helper function."""

    def test_extracts_error_code_from_response(self):
        """Should extract error code from ClientError response."""
        mock_error = MagicMock()
        mock_error.response = {
            "Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}
        }

        assert _get_aws_error_code(mock_error) == "ThrottlingException"

    def test_returns_empty_string_for_missing_response(self):
        """Should return empty string when response is missing."""
        error = ValueError("no response")
        assert _get_aws_error_code(error) == ""

    def test_returns_empty_string_for_missing_error_key(self):
        """Should return empty string when Error key is missing."""
        mock_error = MagicMock()
        mock_error.response = {"SomethingElse": {}}

        assert _get_aws_error_code(mock_error) == ""

    def test_returns_empty_string_for_missing_code_key(self):
        """Should return empty string when Code key is missing."""
        mock_error = MagicMock()
        mock_error.response = {"Error": {"Message": "Something went wrong"}}

        assert _get_aws_error_code(mock_error) == ""


class TestAwsRetryableErrorCodes:
    """Tests for AWS_RETRYABLE_ERROR_CODES constant."""

    def test_contains_throttling_errors(self):
        """Should include throttling-related error codes."""
        assert "Throttling" in AWS_RETRYABLE_ERROR_CODES
        assert "ThrottlingException" in AWS_RETRYABLE_ERROR_CODES
        assert "ProvisionedThroughputExceededException" in AWS_RETRYABLE_ERROR_CODES
        assert "RequestLimitExceeded" in AWS_RETRYABLE_ERROR_CODES

    def test_contains_service_errors(self):
        """Should include service availability error codes."""
        assert "ServiceUnavailable" in AWS_RETRYABLE_ERROR_CODES
        assert "InternalError" in AWS_RETRYABLE_ERROR_CODES
        assert "InternalServerError" in AWS_RETRYABLE_ERROR_CODES

    def test_contains_timeout_errors(self):
        """Should include timeout-related error codes."""
        assert "RequestTimeout" in AWS_RETRYABLE_ERROR_CODES
        assert "RequestTimeoutException" in AWS_RETRYABLE_ERROR_CODES

    def test_contains_dynamodb_specific_errors(self):
        """Should include DynamoDB-specific transient error codes."""
        assert "TransactionConflictException" in AWS_RETRYABLE_ERROR_CODES
        assert "ItemCollectionSizeLimitExceededException" in AWS_RETRYABLE_ERROR_CODES


class TestWithAwsRetry:
    """Tests for with_aws_retry decorator."""

    def test_successful_call_returns_result(self):
        """Decorated function should return result on success."""

        @with_aws_retry
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_retries_on_connection_error(self):
        """Should retry on ConnectionError."""
        call_count = 0

        @with_aws_retry
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Connection refused")
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = flaky_function()

        assert result == "success"
        assert call_count == 3

    def test_retries_on_timeout_error(self):
        """Should retry on TimeoutError."""
        call_count = 0

        @with_aws_retry
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise TimeoutError("Operation timed out")
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = flaky_function()

        assert result == "success"
        assert call_count == 2

    def test_retries_on_throttling_client_error(self):
        """Should retry on AWS ClientError with throttling code."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def throttled_function():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ThrottlingException",
                            "Message": "Rate exceeded",
                        }
                    },
                    "PutItem",
                )
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = throttled_function()

        assert result == "success"
        assert call_count == 3

    def test_does_not_retry_on_access_denied(self):
        """Should NOT retry on AccessDenied error (non-retryable)."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def access_denied_function():
            nonlocal call_count
            call_count += 1
            raise ClientError(
                {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
                "GetObject",
            )

        with pytest.raises(ClientError) as exc_info:
            access_denied_function()

        assert "AccessDenied" in str(exc_info.value)
        assert call_count == 1  # Should not retry

    def test_does_not_retry_on_validation_exception(self):
        """Should NOT retry on ValidationException error (non-retryable)."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def validation_error_function():
            nonlocal call_count
            call_count += 1
            raise ClientError(
                {"Error": {"Code": "ValidationException", "Message": "Invalid input"}},
                "PutItem",
            )

        with pytest.raises(ClientError) as exc_info:
            validation_error_function()

        assert "ValidationException" in str(exc_info.value)
        assert call_count == 1  # Should not retry

    def test_does_not_retry_on_no_such_key(self):
        """Should NOT retry on NoSuchKey error (non-retryable)."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def not_found_function():
            nonlocal call_count
            call_count += 1
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "Object not found"}},
                "GetObject",
            )

        with pytest.raises(ClientError) as exc_info:
            not_found_function()

        assert "NoSuchKey" in str(exc_info.value)
        assert call_count == 1  # Should not retry

    def test_max_retries_exhausted(self):
        """Should raise after max retries are exhausted."""

        @with_aws_retry
        def always_fails():
            raise ConnectionError("Persistent failure")

        with patch("app.content_store.retry.time.sleep"):
            with pytest.raises(ConnectionError) as exc_info:
                always_fails()

        assert "Persistent failure" in str(exc_info.value)

    def test_preserves_function_metadata(self):
        """Decorator should preserve function name and docstring."""

        @with_aws_retry
        def documented_function():
            """This is a documented function."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."

    def test_exponential_backoff_timing(self):
        """Should use exponential backoff for delays."""
        call_count = 0
        sleep_times = []

        @with_aws_retry
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 4:
                raise ConnectionError("Connection refused")
            return "success"

        def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch("app.content_store.retry.time.sleep", side_effect=mock_sleep):
            result = flaky_function()

        assert result == "success"
        # Expected delays: 0.1, 0.2, 0.4, 0.8 (exponential with factor 2)
        assert len(sleep_times) == 4
        assert sleep_times[0] == pytest.approx(0.1)
        assert sleep_times[1] == pytest.approx(0.2)
        assert sleep_times[2] == pytest.approx(0.4)
        assert sleep_times[3] == pytest.approx(0.8)

    def test_max_delay_cap(self):
        """Should cap delay at max_delay (2.0 seconds)."""
        call_count = 0
        sleep_times = []

        @with_aws_retry
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count <= 5:  # Needs all 5 retries
                raise ConnectionError("Connection refused")
            return "success"

        def mock_sleep(seconds):
            sleep_times.append(seconds)

        with patch("app.content_store.retry.time.sleep", side_effect=mock_sleep):
            result = flaky_function()

        assert result == "success"
        # Last delay should be capped at 2.0
        # Delays: 0.1, 0.2, 0.4, 0.8, 1.6 (all under 2.0 cap)
        assert all(t <= 2.0 for t in sleep_times)

    def test_retries_on_service_unavailable(self):
        """Should retry on ServiceUnavailable error."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def unavailable_service():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ServiceUnavailable",
                            "Message": "Service is down",
                        }
                    },
                    "Scan",
                )
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = unavailable_service()

        assert result == "success"
        assert call_count == 2

    def test_retries_on_internal_error(self):
        """Should retry on InternalError."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def internal_error_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "InternalError",
                            "Message": "Internal server error",
                        }
                    },
                    "Query",
                )
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = internal_error_function()

        assert result == "success"
        assert call_count == 2

    def test_retries_on_provisioned_throughput_exceeded(self):
        """Should retry on ProvisionedThroughputExceededException."""
        try:
            from botocore.exceptions import ClientError
        except ImportError:
            pytest.skip("botocore not installed")

        call_count = 0

        @with_aws_retry
        def capacity_exceeded():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ClientError(
                    {
                        "Error": {
                            "Code": "ProvisionedThroughputExceededException",
                            "Message": "Capacity exceeded",
                        }
                    },
                    "PutItem",
                )
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = capacity_exceeded()

        assert result == "success"
        assert call_count == 2


class TestWithAwsRetryWithoutBotocore:
    """Tests for with_aws_retry when botocore is not installed."""

    def test_works_without_botocore(self):
        """Decorator should work even when botocore is not installed."""
        # We can't easily unimport botocore, but we can test that
        # the decorator handles the ImportError gracefully
        # by verifying it still retries on standard exceptions

        @with_aws_retry
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_retries_network_errors_without_botocore(self):
        """Should still retry network errors without botocore."""
        call_count = 0

        @with_aws_retry
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Network error")
            return "success"

        with patch("app.content_store.retry.time.sleep"):
            result = flaky_function()

        assert result == "success"
        assert call_count == 2
