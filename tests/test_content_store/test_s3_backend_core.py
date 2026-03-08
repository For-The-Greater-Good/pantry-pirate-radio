"""Tests for S3+DynamoDB content store backend - core operations.

Tests for import, initialization, properties, write/read content,
content_exists, write/read result, statistics, store size, and error handling.
"""

from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.content_store.backend import ContentStoreBackend


class TestS3ContentStoreBackendImport:
    """Tests for S3ContentStoreBackend import and instantiation."""

    def test_import_s3_backend(self):
        """S3ContentStoreBackend should be importable."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        assert S3ContentStoreBackend is not None

    def test_implements_protocol(self):
        """S3ContentStoreBackend should implement ContentStoreBackend protocol."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        # Create mock backend
        backend = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
            region_name="us-east-1",
        )
        assert isinstance(backend, ContentStoreBackend)


class TestS3ContentStoreBackendInit:
    """Tests for S3ContentStoreBackend initialization."""

    def test_init_with_required_params(self):
        """Should initialize with bucket and table names."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        backend = S3ContentStoreBackend(
            s3_bucket="my-bucket",
            dynamodb_table="my-table",
        )
        assert backend.s3_bucket == "my-bucket"
        assert backend.dynamodb_table == "my-table"

    def test_init_with_region(self):
        """Should accept region_name parameter."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        backend = S3ContentStoreBackend(
            s3_bucket="my-bucket",
            dynamodb_table="my-table",
            region_name="us-west-2",
        )
        assert backend.region_name == "us-west-2"

    def test_init_with_prefix(self):
        """Should accept s3_prefix parameter for object key prefixes."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        backend = S3ContentStoreBackend(
            s3_bucket="my-bucket",
            dynamodb_table="my-table",
            s3_prefix="content-store/",
        )
        assert backend.s3_prefix == "content-store/"


class TestS3ContentStoreBackendProperties:
    """Tests for S3ContentStoreBackend property implementations."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        return S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
            s3_prefix="content-store/",
        )

    def test_store_path_property(self, backend):
        """store_path should return S3 URI string (not Path, to avoid s3:// normalization)."""
        assert backend.store_path == "s3://test-bucket/content-store/"
        assert isinstance(backend.store_path, str)

    def test_content_store_path_property(self, backend):
        """content_store_path should return S3 URI string for content subdirectory."""
        assert (
            backend.content_store_path == "s3://test-bucket/content-store/content_store"
        )
        assert isinstance(backend.content_store_path, str)


class TestS3ContentStoreBackendInitialize:
    """Tests for S3ContentStoreBackend.initialize() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        return S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )

    def test_initialize_verifies_s3_bucket_exists(self, backend):
        """initialize() should verify S3 bucket exists."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with patch.object(
                backend, "_get_dynamodb_client", return_value=mock_dynamodb
            ):
                backend.initialize()

        mock_s3.head_bucket.assert_called_once_with(Bucket="test-bucket")

    def test_initialize_verifies_dynamodb_table_exists(self, backend):
        """initialize() should verify DynamoDB table exists."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with patch.object(
                backend, "_get_dynamodb_client", return_value=mock_dynamodb
            ):
                backend.initialize()

        mock_dynamodb.describe_table.assert_called_once_with(TableName="test-table")

    def test_initialize_is_idempotent(self, backend):
        """initialize() should be idempotent."""
        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with patch.object(
                backend, "_get_dynamodb_client", return_value=mock_dynamodb
            ):
                backend.initialize()
                backend.initialize()  # Second call should not fail


class TestS3ContentStoreBackendWriteContent:
    """Tests for S3ContentStoreBackend.write_content() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
            s3_prefix="store/",
        )
        b._initialized = True
        return b

    def test_write_content_uploads_to_s3(self, backend):
        """write_content() should upload data to S3."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58  # 64-char hash

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.write_content(content_hash, '{"test": "data"}')

        mock_s3.put_object.assert_called_once()
        call_args = mock_s3.put_object.call_args
        assert call_args.kwargs["Bucket"] == "test-bucket"
        assert "content/ab/" in call_args.kwargs["Key"]
        assert content_hash in call_args.kwargs["Key"]

    def test_write_content_returns_s3_path(self, backend):
        """write_content() should return S3 object key."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.write_content(content_hash, '{"test": "data"}')

        assert "s3://test-bucket/" in result
        assert content_hash in result

    def test_write_content_uses_hash_prefix_subdirectory(self, backend):
        """write_content() should use first 2 chars of hash as prefix."""
        mock_s3 = MagicMock()
        content_hash = "xy9876" + "0" * 58  # starts with "xy"

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            backend.write_content(content_hash, '{"test": "data"}')

        call_args = mock_s3.put_object.call_args
        assert "/content/xy/" in call_args.kwargs["Key"]


class TestS3ContentStoreBackendReadContent:
    """Tests for S3ContentStoreBackend.read_content() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_read_content_returns_stored_data(self, backend):
        """read_content() should return data from S3."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58
        mock_body = MagicMock()
        mock_body.read.return_value = b'{"test": "data"}'
        mock_s3.get_object.return_value = {"Body": mock_body}

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.read_content(content_hash)

        assert result == '{"test": "data"}'

    def test_read_content_returns_none_for_missing(self, backend):
        """read_content() should return None for non-existent content."""
        mock_s3 = MagicMock()
        content_hash = "nonexistent" + "0" * 54

        # Simulate S3 NoSuchKey error
        from botocore.exceptions import ClientError

        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.read_content(content_hash)

        assert result is None


class TestS3ContentStoreBackendContentExists:
    """Tests for S3ContentStoreBackend.content_exists() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_content_exists_returns_true_for_existing(self, backend):
        """content_exists() should return True for existing content."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.content_exists(content_hash)

        assert result is True
        mock_s3.head_object.assert_called_once()

    def test_content_exists_returns_false_for_missing(self, backend):
        """content_exists() should return False for non-existent content."""
        mock_s3 = MagicMock()
        content_hash = "nonexistent" + "0" * 54

        from botocore.exceptions import ClientError

        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not found"}},
            "HeadObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.content_exists(content_hash)

        assert result is False


class TestS3ContentStoreBackendWriteResult:
    """Tests for S3ContentStoreBackend.write_result() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_write_result_uploads_to_results_directory(self, backend):
        """write_result() should upload to results/ prefix in S3."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.write_result(content_hash, '{"processed": "data"}')

        call_args = mock_s3.put_object.call_args
        assert "/results/" in call_args.kwargs["Key"]

    def test_write_result_returns_s3_path(self, backend):
        """write_result() should return S3 path."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.write_result(content_hash, '{"processed": "data"}')

        assert "s3://test-bucket/" in result
        assert "/results/" in result


class TestS3ContentStoreBackendReadResult:
    """Tests for S3ContentStoreBackend.read_result() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_read_result_returns_stored_data(self, backend):
        """read_result() should return data from S3."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58
        mock_body = MagicMock()
        mock_body.read.return_value = b'{"processed": "data"}'
        mock_s3.get_object.return_value = {"Body": mock_body}

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.read_result(content_hash)

        assert result == '{"processed": "data"}'

    def test_read_result_returns_none_for_missing(self, backend):
        """read_result() should return None for non-existent result."""
        mock_s3 = MagicMock()
        content_hash = "nonexistent" + "0" * 54

        from botocore.exceptions import ClientError

        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "GetObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.read_result(content_hash)

        assert result is None


class TestS3ContentStoreBackendStatistics:
    """Tests for S3ContentStoreBackend.index_get_statistics() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_index_get_statistics_empty(self, backend):
        """index_get_statistics() should return zeros for empty store."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.scan.return_value = {"Items": [], "Count": 0}

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            stats = backend.index_get_statistics()

        assert stats["total_content"] == 0
        assert stats["processed_content"] == 0
        assert stats["pending_content"] == 0

    def test_index_get_statistics_counts_content(self, backend):
        """index_get_statistics() should count total and processed content."""
        mock_dynamodb = MagicMock()
        mock_dynamodb.scan.return_value = {
            "Items": [
                {"content_hash": {"S": "hash1"}, "result_path": {"S": "s3://..."}},
                {"content_hash": {"S": "hash2"}, "result_path": {"S": "s3://..."}},
                {"content_hash": {"S": "hash3"}},  # No result_path = pending
            ],
            "Count": 3,
        }

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            stats = backend.index_get_statistics()

        assert stats["total_content"] == 3
        assert stats["processed_content"] == 2
        assert stats["pending_content"] == 1


class TestS3ContentStoreBackendStoreSize:
    """Tests for S3ContentStoreBackend.get_store_size_bytes() method."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
            s3_prefix="store/",
        )
        b._initialized = True
        return b

    def test_get_store_size_bytes_sums_object_sizes(self, backend):
        """get_store_size_bytes() should sum sizes of all S3 objects."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {
            "Contents": [
                {"Key": "store/content/ab/hash1.json", "Size": 1000},
                {"Key": "store/content/cd/hash2.json", "Size": 2000},
                {"Key": "store/results/ab/hash1.json", "Size": 500},
            ],
            "IsTruncated": False,
        }

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            size = backend.get_store_size_bytes()

        assert size == 3500

    def test_get_store_size_bytes_handles_pagination(self, backend):
        """get_store_size_bytes() should handle paginated S3 listings."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.side_effect = [
            {
                "Contents": [{"Key": "obj1", "Size": 1000}],
                "IsTruncated": True,
                "NextContinuationToken": "token123",
            },
            {
                "Contents": [{"Key": "obj2", "Size": 2000}],
                "IsTruncated": False,
            },
        ]

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            size = backend.get_store_size_bytes()

        assert size == 3000
        assert mock_s3.list_objects_v2.call_count == 2

    def test_get_store_size_bytes_handles_empty_bucket(self, backend):
        """get_store_size_bytes() should return 0 for empty bucket."""
        mock_s3 = MagicMock()
        mock_s3.list_objects_v2.return_value = {"IsTruncated": False}  # No Contents key

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            size = backend.get_store_size_bytes()

        assert size == 0


class TestS3ContentStoreBackendErrorHandling:
    """Tests for S3ContentStoreBackend error handling."""

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_raises_clear_error_when_boto3_missing(self, backend):
        """Should raise ImportError with clear message when boto3 missing."""
        import sys

        with patch.dict(sys.modules, {"boto3": None}):
            with pytest.raises(ImportError, match="boto3 is required"):
                backend._get_s3_client()

    def test_handles_s3_access_denied(self, backend):
        """Should handle S3 AccessDenied errors gracefully."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        from botocore.exceptions import ClientError

        mock_s3.get_object.side_effect = ClientError(
            {"Error": {"Code": "AccessDenied", "Message": "Access denied"}},
            "GetObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with pytest.raises(ClientError):
                backend.read_content(content_hash)

    def test_handles_dynamodb_provisioned_throughput_exceeded(self, backend):
        """Should handle DynamoDB throughput errors."""
        mock_dynamodb = MagicMock()
        content_hash = "abc123" + "0" * 58

        from botocore.exceptions import ClientError

        mock_dynamodb.get_item.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ProvisionedThroughputExceededException",
                    "Message": "Throughput exceeded",
                }
            },
            "GetItem",
        )

        with patch.object(backend, "_get_dynamodb_client", return_value=mock_dynamodb):
            with pytest.raises(ClientError):
                backend.index_has_content(content_hash)


class TestS3ContentStoreBackendInitializeFailure:
    """Tests for T8: initialize() failure on missing bucket or table.

    The initialize() method lets ClientError propagate so @with_aws_retry can
    distinguish transient errors from permanent ones. Non-retryable errors
    (404, 403, ResourceNotFoundException) are re-raised as ClientError.
    """

    @pytest.fixture
    def backend(self):
        """Create S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        return S3ContentStoreBackend(
            s3_bucket="nonexistent-bucket",
            dynamodb_table="test-table",
        )

    def test_initialize_raises_on_missing_s3_bucket(self, backend):
        """initialize() should raise ClientError when S3 bucket doesn't exist."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()

        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadBucket",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with patch.object(
                backend, "_get_dynamodb_client", return_value=mock_dynamodb
            ):
                with pytest.raises(ClientError) as exc_info:
                    backend.initialize()

                assert exc_info.value.response["Error"]["Code"] == "404"

    def test_initialize_raises_on_access_denied_bucket(self, backend):
        """initialize() should raise ClientError when bucket access is denied."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        mock_dynamodb = MagicMock()

        mock_s3.head_bucket.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}},
            "HeadBucket",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with patch.object(
                backend, "_get_dynamodb_client", return_value=mock_dynamodb
            ):
                with pytest.raises(ClientError) as exc_info:
                    backend.initialize()

                assert exc_info.value.response["Error"]["Code"] == "403"

    def test_initialize_raises_on_missing_dynamodb_table(self):
        """initialize() should raise ClientError when DynamoDB table doesn't exist."""
        from botocore.exceptions import ClientError
        from app.content_store.backend_s3 import S3ContentStoreBackend

        backend = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="nonexistent-table",
        )

        mock_s3 = MagicMock()  # head_bucket succeeds
        mock_dynamodb = MagicMock()
        mock_dynamodb.describe_table.side_effect = ClientError(
            {
                "Error": {
                    "Code": "ResourceNotFoundException",
                    "Message": "Table not found",
                }
            },
            "DescribeTable",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with patch.object(
                backend, "_get_dynamodb_client", return_value=mock_dynamodb
            ):
                with pytest.raises(ClientError) as exc_info:
                    backend.initialize()

                assert (
                    exc_info.value.response["Error"]["Code"]
                    == "ResourceNotFoundException"
                )


class TestS3ContentStoreBackendContentExistsReRaise:
    """Tests for T9: content_exists() re-raises non-404 errors."""

    @pytest.fixture
    def backend(self):
        """Create initialized S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_content_exists_reraises_403_forbidden(self, backend):
        """content_exists() should re-raise 403 Forbidden instead of returning False."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "403", "Message": "Forbidden"}},
            "HeadObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with pytest.raises(ClientError) as exc_info:
                backend.content_exists(content_hash)

            assert exc_info.value.response["Error"]["Code"] == "403"

    def test_content_exists_reraises_500_internal_error(self, backend):
        """content_exists() should re-raise 500 InternalError."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Internal server error"}},
            "HeadObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with pytest.raises(ClientError) as exc_info:
                backend.content_exists(content_hash)

            assert exc_info.value.response["Error"]["Code"] == "InternalError"

    def test_content_exists_returns_false_for_nosuchkey(self, backend):
        """content_exists() should return False for NoSuchKey (not re-raise)."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        mock_s3.head_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not found"}},
            "HeadObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            result = backend.content_exists(content_hash)

        assert result is False


class TestS3ContentStoreBackendUploadFailure:
    """Tests for T11: S3 put_object failure propagation."""

    @pytest.fixture
    def backend(self):
        """Create initialized S3ContentStoreBackend for testing."""
        from app.content_store.backend_s3 import S3ContentStoreBackend

        b = S3ContentStoreBackend(
            s3_bucket="test-bucket",
            dynamodb_table="test-table",
        )
        b._initialized = True
        return b

    def test_write_content_propagates_put_object_failure(self, backend):
        """When S3 put_object fails, the error should propagate to the caller."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "S3 internal error"}},
            "PutObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with pytest.raises(ClientError) as exc_info:
                backend.write_content(content_hash, '{"test": "data"}')

            assert exc_info.value.response["Error"]["Code"] == "InternalError"

    def test_write_result_propagates_put_object_failure(self, backend):
        """When S3 put_object fails on write_result, the error should propagate."""
        from botocore.exceptions import ClientError

        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        mock_s3.put_object.side_effect = ClientError(
            {"Error": {"Code": "RequestTimeout", "Message": "Upload timed out"}},
            "PutObject",
        )

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with pytest.raises(ClientError) as exc_info:
                backend.write_result(content_hash, '{"processed": "data"}')

            assert exc_info.value.response["Error"]["Code"] == "RequestTimeout"

    def test_write_content_propagates_connection_error(self, backend):
        """When S3 connection fails during upload, error should propagate."""
        mock_s3 = MagicMock()
        content_hash = "abc123" + "0" * 58

        mock_s3.put_object.side_effect = ConnectionError("Network unreachable")

        with patch.object(backend, "_get_s3_client", return_value=mock_s3):
            with pytest.raises(ConnectionError, match="Network unreachable"):
                backend.write_content(content_hash, '{"test": "data"}')
