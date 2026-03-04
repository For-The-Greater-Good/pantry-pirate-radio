"""Tests for SQSQueueBackend implementation.

This module tests the AWS SQS-based queue backend for production deployment.
SQS is used for message delivery, DynamoDB for job status tracking.
"""

import json
import os
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from app.llm.providers.base import BaseLLMProvider
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobStatus


@pytest.fixture
def sample_llm_job() -> LLMJob:
    """Create a sample LLM job for testing."""
    return LLMJob(
        id=str(uuid4()),
        prompt="Test prompt for SQS backend testing",
        format={"type": "object", "properties": {"text": {"type": "string"}}},
        provider_config={"temperature": 0.7},
        metadata={"scraper_id": "test_scraper", "content_hash": "abc123"},
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_provider() -> BaseLLMProvider:
    """Create a mock LLM provider."""
    from app.llm.providers.test_mock import MockProvider

    return MockProvider(model_name="test-model")


@pytest.fixture
def mock_sqs_client():
    """Create a mock SQS client."""
    client = MagicMock()
    client.send_message.return_value = {
        "MessageId": "msg-123",
        "MD5OfMessageBody": "abc",
    }
    client.get_queue_attributes.return_value = {
        "Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:123456789:test-queue"}
    }
    return client


@pytest.fixture
def mock_dynamodb_client():
    """Create a mock DynamoDB client."""
    client = MagicMock()
    client.describe_table.return_value = {"Table": {"TableName": "test-jobs"}}
    return client


class TestSQSQueueBackendProtocol:
    """Tests verifying SQSQueueBackend implements QueueBackend protocol."""

    def test_implements_queue_backend_protocol(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """SQSQueueBackend should implement QueueBackend protocol."""
        from app.llm.queue.backend import QueueBackend
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
            dynamodb_table="test-jobs",
        )

        # Inject mocks
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client

        assert isinstance(backend, QueueBackend)

    def test_has_queue_name_property(self, mock_sqs_client, mock_dynamodb_client):
        """SQSQueueBackend should have queue_name property."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
            dynamodb_table="test-jobs",
        )

        assert hasattr(backend, "queue_name")
        assert backend.queue_name == "test-queue"

    def test_has_setup_method(self):
        """SQSQueueBackend should have setup method."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
            dynamodb_table="test-jobs",
        )

        assert hasattr(backend, "setup")
        assert callable(backend.setup)

    def test_has_enqueue_method(self):
        """SQSQueueBackend should have enqueue method."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
            dynamodb_table="test-jobs",
        )

        assert hasattr(backend, "enqueue")
        assert callable(backend.enqueue)

    def test_has_get_status_method(self):
        """SQSQueueBackend should have get_status method."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/test-queue",
            dynamodb_table="test-jobs",
        )

        assert hasattr(backend, "get_status")
        assert callable(backend.get_status)


class TestSQSQueueBackendInit:
    """Tests for SQSQueueBackend initialization."""

    def test_init_with_queue_url(self):
        """Should initialize with SQS queue URL."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        queue_url = "https://sqs.us-east-1.amazonaws.com/123456789/my-queue"
        backend = SQSQueueBackend(
            queue_url=queue_url,
            dynamodb_table="jobs-table",
        )

        assert backend.queue_url == queue_url

    def test_init_with_dynamodb_table(self):
        """Should initialize with DynamoDB table name."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="my-jobs-table",
        )

        assert backend.dynamodb_table == "my-jobs-table"

    def test_init_with_region(self):
        """Should accept optional region parameter."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-west-2.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
            region_name="us-west-2",
        )

        assert backend.region_name == "us-west-2"

    def test_init_with_visibility_timeout(self):
        """Should accept visibility timeout parameter."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
            visibility_timeout=300,
        )

        assert backend.visibility_timeout == 300

    def test_init_extracts_queue_name_from_url(self):
        """Should extract queue name from URL."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/my-llm-queue",
            dynamodb_table="jobs-table",
        )

        assert backend.queue_name == "my-llm-queue"

    def test_init_defaults(self):
        """Should have sensible defaults."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )

        # Default visibility timeout should be reasonable for LLM processing
        assert backend.visibility_timeout >= 60  # At least 1 minute
        assert backend.region_name is None  # Uses default credential chain


class TestSQSQueueBackendSetup:
    """Tests for SQSQueueBackend setup method."""

    def test_setup_verifies_sqs_queue_exists(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """setup() should verify SQS queue exists."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client

        backend.setup()

        mock_sqs_client.get_queue_attributes.assert_called_once()

    def test_setup_verifies_dynamodb_table_exists(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """setup() should verify DynamoDB table exists."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client

        backend.setup()

        mock_dynamodb_client.describe_table.assert_called_once_with(
            TableName="jobs-table"
        )

    def test_setup_raises_on_sqs_not_found(self, mock_dynamodb_client):
        """setup() should raise if SQS queue doesn't exist."""
        from botocore.exceptions import ClientError

        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs = MagicMock()
        mock_sqs.get_queue_attributes.side_effect = ClientError(
            {"Error": {"Code": "AWS.SimpleQueueService.NonExistentQueue"}},
            "GetQueueAttributes",
        )

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/nonexistent",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs
        backend._dynamodb_client = mock_dynamodb_client

        with pytest.raises(ConnectionError) as exc_info:
            backend.setup()

        assert "SQS queue" in str(exc_info.value)

    def test_setup_raises_on_dynamodb_not_found(self, mock_sqs_client):
        """setup() should raise if DynamoDB table doesn't exist."""
        from botocore.exceptions import ClientError

        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_dynamodb = MagicMock()
        mock_dynamodb.describe_table.side_effect = ClientError(
            {"Error": {"Code": "ResourceNotFoundException"}}, "DescribeTable"
        )

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="nonexistent-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb

        with pytest.raises(ConnectionError) as exc_info:
            backend.setup()

        assert "DynamoDB table" in str(exc_info.value)


class TestSQSQueueBackendEnqueue:
    """Tests for SQSQueueBackend enqueue method."""

    def test_enqueue_returns_job_id(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
        mock_provider,
    ):
        """enqueue() should return the job ID."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)

        assert job_id == sample_llm_job.id

    def test_enqueue_sends_message_to_sqs(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
        mock_provider,
    ):
        """enqueue() should send message to SQS."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.enqueue(sample_llm_job, provider=mock_provider)

        mock_sqs_client.send_message.assert_called_once()
        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        assert (
            call_kwargs["QueueUrl"] == "https://sqs.us-east-1.amazonaws.com/123/queue"
        )

    def test_enqueue_message_contains_job_data(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
        mock_provider,
    ):
        """enqueue() message should contain job data."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.enqueue(sample_llm_job, provider=mock_provider)

        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        message_body = json.loads(call_kwargs["MessageBody"])
        assert message_body["job_id"] == sample_llm_job.id
        assert message_body["job"]["prompt"] == sample_llm_job.prompt

    def test_enqueue_creates_dynamodb_record(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
        mock_provider,
    ):
        """enqueue() should create job record in DynamoDB."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.enqueue(sample_llm_job, provider=mock_provider)

        mock_dynamodb_client.put_item.assert_called_once()
        call_kwargs = mock_dynamodb_client.put_item.call_args.kwargs
        assert call_kwargs["TableName"] == "jobs-table"
        assert call_kwargs["Item"]["job_id"]["S"] == sample_llm_job.id
        assert call_kwargs["Item"]["status"]["S"] == "queued"

    def test_enqueue_uses_job_id_as_deduplication_id(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
        mock_provider,
    ):
        """enqueue() should use job ID for SQS deduplication (FIFO queues)."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue.fifo",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.enqueue(sample_llm_job, provider=mock_provider)

        call_kwargs = mock_sqs_client.send_message.call_args.kwargs
        # FIFO queues need MessageDeduplicationId
        assert "MessageDeduplicationId" in call_kwargs
        assert call_kwargs["MessageDeduplicationId"] == sample_llm_job.id


class TestSQSQueueBackendGetStatus:
    """Tests for SQSQueueBackend get_status method."""

    def test_get_status_returns_none_for_nonexistent_job(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """get_status() should return None for non-existent job."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_dynamodb_client.get_item.return_value = {}  # No Item key

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        status = backend.get_status("nonexistent-job-id")

        assert status is None

    def test_get_status_returns_queued_for_new_job(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """get_status() should return QUEUED status for new job."""
        from app.llm.queue.backend_sqs import SQSQueueBackend
        from app.llm.queue.types import JobResult

        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "job_id": {"S": sample_llm_job.id},
                "status": {"S": "queued"},
                "job_data": {"S": sample_llm_job.model_dump_json()},
                "created_at": {"S": datetime.now(UTC).isoformat()},
            }
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        status = backend.get_status(sample_llm_job.id)

        assert status is not None
        assert isinstance(status, JobResult)
        assert status.status == JobStatus.QUEUED
        assert status.job_id == sample_llm_job.id

    def test_get_status_returns_processing_status(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """get_status() should return PROCESSING status."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "job_id": {"S": sample_llm_job.id},
                "status": {"S": "processing"},
                "job_data": {"S": sample_llm_job.model_dump_json()},
                "created_at": {"S": datetime.now(UTC).isoformat()},
                "started_at": {"S": datetime.now(UTC).isoformat()},
            }
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        status = backend.get_status(sample_llm_job.id)

        assert status is not None
        assert status.status == JobStatus.PROCESSING

    def test_get_status_returns_completed_with_result(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """get_status() should return COMPLETED status with result."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        result_data = {
            "text": "Test response",
            "model": "test-model",
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }

        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "job_id": {"S": sample_llm_job.id},
                "status": {"S": "completed"},
                "job_data": {"S": sample_llm_job.model_dump_json()},
                "result_data": {"S": json.dumps(result_data)},
                "created_at": {"S": datetime.now(UTC).isoformat()},
                "completed_at": {"S": datetime.now(UTC).isoformat()},
            }
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        status = backend.get_status(sample_llm_job.id)

        assert status is not None
        assert status.status == JobStatus.COMPLETED
        assert status.result is not None

    def test_get_status_returns_failed_with_error(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """get_status() should return FAILED status with error."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_dynamodb_client.get_item.return_value = {
            "Item": {
                "job_id": {"S": sample_llm_job.id},
                "status": {"S": "failed"},
                "job_data": {"S": sample_llm_job.model_dump_json()},
                "error": {"S": "LLM processing failed: timeout"},
                "created_at": {"S": datetime.now(UTC).isoformat()},
                "completed_at": {"S": datetime.now(UTC).isoformat()},
            }
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        status = backend.get_status(sample_llm_job.id)

        assert status is not None
        assert status.status == JobStatus.FAILED
        assert status.error == "LLM processing failed: timeout"


class TestSQSQueueBackendStatusUpdate:
    """Tests for SQSQueueBackend status update methods."""

    def test_update_status_to_processing(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """Should be able to update job status to processing."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.update_status(sample_llm_job.id, JobStatus.PROCESSING)

        mock_dynamodb_client.update_item.assert_called_once()
        call_kwargs = mock_dynamodb_client.update_item.call_args.kwargs
        assert call_kwargs["TableName"] == "jobs-table"
        assert ":status" in str(call_kwargs["ExpressionAttributeValues"])

    def test_update_status_to_completed_with_result(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """Should be able to update job status to completed with result."""
        from app.llm.queue.backend_sqs import SQSQueueBackend
        from app.llm.providers.types import LLMResponse

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        result = LLMResponse(
            text="Test response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )

        backend.update_status(sample_llm_job.id, JobStatus.COMPLETED, result=result)

        mock_dynamodb_client.update_item.assert_called_once()

    def test_update_status_to_failed_with_error(
        self,
        mock_sqs_client,
        mock_dynamodb_client,
        sample_llm_job,
    ):
        """Should be able to update job status to failed with error."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.update_status(
            sample_llm_job.id,
            JobStatus.FAILED,
            error="Processing timeout",
        )

        mock_dynamodb_client.update_item.assert_called_once()


class TestSQSQueueBackendFactory:
    """Tests for SQS backend factory integration."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset singleton between tests."""
        import app.llm.queue.backend as backend_module

        if hasattr(backend_module, "_queue_backend_instance"):
            backend_module._queue_backend_instance = None
        if hasattr(backend_module, "_queue_backend_initialized"):
            backend_module._queue_backend_initialized = False
        yield
        if hasattr(backend_module, "_queue_backend_instance"):
            backend_module._queue_backend_instance = None
        if hasattr(backend_module, "_queue_backend_initialized"):
            backend_module._queue_backend_initialized = False

    def test_factory_creates_sqs_backend_when_configured(self):
        """get_queue_backend() should create SQS backend when QUEUE_BACKEND=sqs."""
        from app.llm.queue.backend import get_queue_backend
        from app.llm.queue.backend_sqs import SQSQueueBackend

        with patch.dict(
            os.environ,
            {
                "QUEUE_BACKEND": "sqs",
                "SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/queue",
                "SQS_JOBS_TABLE": "jobs-table",
            },
            clear=False,
        ):
            with patch("boto3.client") as mock_boto:
                mock_sqs = MagicMock()
                mock_dynamodb = MagicMock()
                mock_sqs.get_queue_attributes.return_value = {
                    "Attributes": {"QueueArn": "arn:aws:sqs:us-east-1:123:queue"}
                }
                mock_dynamodb.describe_table.return_value = {"Table": {}}

                def client_factory(service, **kwargs):
                    if service == "sqs":
                        return mock_sqs
                    elif service == "dynamodb":
                        return mock_dynamodb
                    raise ValueError(f"Unknown service: {service}")

                mock_boto.side_effect = client_factory

                backend = get_queue_backend()

                assert isinstance(backend, SQSQueueBackend)

    def test_factory_uses_env_vars_for_sqs_config(self):
        """Factory should read SQS config from environment variables."""
        from app.llm.queue.backend import get_queue_backend

        queue_url = "https://sqs.us-west-2.amazonaws.com/999/my-queue"
        table_name = "my-jobs-table"

        with patch.dict(
            os.environ,
            {
                "QUEUE_BACKEND": "sqs",
                "SQS_QUEUE_URL": queue_url,
                "SQS_JOBS_TABLE": table_name,
                "AWS_DEFAULT_REGION": "us-west-2",
            },
            clear=False,
        ):
            with patch("boto3.client") as mock_boto:
                mock_sqs = MagicMock()
                mock_dynamodb = MagicMock()
                mock_sqs.get_queue_attributes.return_value = {"Attributes": {}}
                mock_dynamodb.describe_table.return_value = {"Table": {}}

                def client_factory(service, **kwargs):
                    if service == "sqs":
                        return mock_sqs
                    elif service == "dynamodb":
                        return mock_dynamodb
                    raise ValueError(f"Unknown service: {service}")

                mock_boto.side_effect = client_factory

                backend = get_queue_backend()

                assert backend.queue_url == queue_url
                assert backend.dynamodb_table == table_name

    def test_factory_raises_if_sqs_url_missing(self):
        """Factory should raise ValueError if SQS_QUEUE_URL not set."""
        from app.llm.queue.backend import get_queue_backend

        with patch.dict(
            os.environ,
            {
                "QUEUE_BACKEND": "sqs",
                # SQS_QUEUE_URL intentionally missing
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                get_queue_backend()

            assert "SQS_QUEUE_URL" in str(exc_info.value)

    def test_factory_raises_if_jobs_table_missing(self):
        """Factory should raise ValueError if SQS_JOBS_TABLE not set."""
        from app.llm.queue.backend import get_queue_backend

        with patch.dict(
            os.environ,
            {
                "QUEUE_BACKEND": "sqs",
                "SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/queue",
                # SQS_JOBS_TABLE intentionally missing
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                get_queue_backend()

            assert "SQS_JOBS_TABLE" in str(exc_info.value)


class TestSQSQueueBackendReceiveMessages:
    """Tests for SQSQueueBackend receive_messages method."""

    def test_receive_messages_returns_empty_list_when_no_messages(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should return empty list when queue is empty."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {}  # No Messages key

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        assert messages == []

    def test_receive_messages_parses_valid_message(
        self, mock_sqs_client, mock_dynamodb_client, sample_llm_job
    ):
        """receive_messages() should parse valid SQS message correctly."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        message_body = {
            "job_id": sample_llm_job.id,
            "job": sample_llm_job.model_dump(mode="json"),
            "enqueued_at": datetime.now(UTC).isoformat(),
        }

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-123",
                    "ReceiptHandle": "receipt-abc",
                    "Body": json.dumps(message_body),
                }
            ]
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        assert len(messages) == 1
        assert messages[0]["job_id"] == sample_llm_job.id
        assert messages[0]["message_id"] == "msg-123"
        assert messages[0]["receipt_handle"] == "receipt-abc"

    def test_receive_messages_handles_malformed_json(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should delete and skip malformed JSON messages."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-bad",
                    "ReceiptHandle": "receipt-bad",
                    "Body": "not valid json {{{",
                }
            ]
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        # Should return empty since malformed message was skipped
        assert messages == []
        # Should have attempted to delete the malformed message
        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-bad",
        )

    def test_receive_messages_handles_missing_job_data(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should delete and skip messages with missing job data."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {
            "Messages": [
                {
                    "MessageId": "msg-incomplete",
                    "ReceiptHandle": "receipt-incomplete",
                    "Body": json.dumps({"job_id": "123"}),  # Missing 'job' key
                }
            ]
        }

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        messages = backend.receive_messages()

        # Should return empty since incomplete message was skipped
        assert messages == []
        # Should have attempted to delete the incomplete message
        mock_sqs_client.delete_message.assert_called_once()

    def test_receive_messages_respects_max_messages(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """receive_messages() should respect max_messages parameter."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.receive_message.return_value = {"Messages": []}

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.receive_messages(max_messages=5, wait_time_seconds=10)

        call_kwargs = mock_sqs_client.receive_message.call_args.kwargs
        assert call_kwargs["MaxNumberOfMessages"] == 5
        assert call_kwargs["WaitTimeSeconds"] == 10


class TestSQSQueueBackendDeleteMessage:
    """Tests for SQSQueueBackend delete_message method."""

    def test_delete_message_calls_sqs(self, mock_sqs_client, mock_dynamodb_client):
        """delete_message() should call SQS delete_message."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.delete_message("receipt-handle-123")

        mock_sqs_client.delete_message.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-handle-123",
        )

    def test_delete_message_raises_on_invalid_receipt(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """delete_message() should raise on invalid receipt handle."""
        from botocore.exceptions import ClientError

        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.delete_message.side_effect = ClientError(
            {"Error": {"Code": "ReceiptHandleIsInvalid"}}, "DeleteMessage"
        )

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        with pytest.raises(ClientError):
            backend.delete_message("invalid-receipt")


class TestSQSQueueBackendChangeVisibility:
    """Tests for SQSQueueBackend change_visibility method."""

    def test_change_visibility_calls_sqs(self, mock_sqs_client, mock_dynamodb_client):
        """change_visibility() should call SQS change_message_visibility."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.change_visibility("receipt-handle-123", 300)

        mock_sqs_client.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-handle-123",
            VisibilityTimeout=300,
        )

    def test_change_visibility_raises_on_invalid_receipt(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """change_visibility() should raise on invalid receipt handle."""
        from botocore.exceptions import ClientError

        from app.llm.queue.backend_sqs import SQSQueueBackend

        mock_sqs_client.change_message_visibility.side_effect = ClientError(
            {"Error": {"Code": "ReceiptHandleIsInvalid"}}, "ChangeMessageVisibility"
        )

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        with pytest.raises(ClientError):
            backend.change_visibility("invalid-receipt", 300)

    def test_change_visibility_with_zero_timeout(
        self, mock_sqs_client, mock_dynamodb_client
    ):
        """change_visibility() with timeout=0 should make message immediately visible."""
        from app.llm.queue.backend_sqs import SQSQueueBackend

        backend = SQSQueueBackend(
            queue_url="https://sqs.us-east-1.amazonaws.com/123/queue",
            dynamodb_table="jobs-table",
        )
        backend._sqs_client = mock_sqs_client
        backend._dynamodb_client = mock_dynamodb_client
        backend._initialized = True

        backend.change_visibility("receipt-handle-123", 0)

        mock_sqs_client.change_message_visibility.assert_called_once_with(
            QueueUrl="https://sqs.us-east-1.amazonaws.com/123/queue",
            ReceiptHandle="receipt-handle-123",
            VisibilityTimeout=0,
        )
