"""Tests for QueueBackend protocol and implementations.

This module tests the queue backend abstraction that enables swapping
between Redis/RQ (development/local) and AWS SQS (production) backends.
"""

import os
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
import redis

from app.llm.providers.base import BaseLLMProvider
from app.llm.providers.types import LLMResponse
from app.llm.queue.job import LLMJob
from app.llm.queue.types import JobResult, JobStatus

pytest_plugins = ["tests.fixtures.cache"]


@pytest.fixture
def sample_llm_job() -> LLMJob:
    """Create a sample LLM job for testing."""
    return LLMJob(
        id=str(uuid4()),
        prompt="Test prompt for backend testing",
        format={"type": "object", "properties": {"text": {"type": "string"}}},
        provider_config={"temperature": 0.7},
        metadata={"scraper_id": "test_scraper"},
        created_at=datetime.now(UTC),
    )


@pytest.fixture
def mock_provider() -> BaseLLMProvider:
    """Create a mock LLM provider."""
    from app.llm.providers.test_mock import MockProvider

    return MockProvider(model_name="test-model")


class TestQueueBackendProtocol:
    """Tests verifying QueueBackend protocol definition."""

    def test_protocol_is_runtime_checkable(self):
        """QueueBackend protocol should be runtime checkable."""
        from app.llm.queue.backend import QueueBackend

        assert hasattr(QueueBackend, "__protocol_attrs__") or isinstance(
            QueueBackend, type
        )

    def test_protocol_requires_enqueue_method(self):
        """QueueBackend should require enqueue method."""
        from app.llm.queue.backend import QueueBackend

        # Verify enqueue is defined in protocol
        assert hasattr(QueueBackend, "enqueue")

    def test_protocol_requires_get_status_method(self):
        """QueueBackend should require get_status method."""
        from app.llm.queue.backend import QueueBackend

        assert hasattr(QueueBackend, "get_status")

    def test_protocol_requires_setup_method(self):
        """QueueBackend should require setup method for initialization."""
        from app.llm.queue.backend import QueueBackend

        assert hasattr(QueueBackend, "setup")

    def test_protocol_requires_queue_name_property(self):
        """QueueBackend should have queue_name property."""
        from app.llm.queue.backend import QueueBackend

        assert hasattr(QueueBackend, "queue_name")


class TestRedisQueueBackend:
    """Tests for RedisQueueBackend implementation."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Reset any singleton state between tests."""
        yield

    def test_implements_queue_backend_protocol(self, redis_client: redis.Redis):
        """RedisQueueBackend should implement QueueBackend protocol."""
        from app.llm.queue.backend import QueueBackend, RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="test")

        # Runtime protocol check
        assert isinstance(backend, QueueBackend)

    def test_init_with_redis_client(self, redis_client: redis.Redis):
        """Should initialize with Redis client."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")

        assert backend.redis_client == redis_client
        assert backend.queue_name == "llm"

    def test_init_with_custom_ttl_settings(self, redis_client: redis.Redis):
        """Should accept custom TTL settings."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(
            redis_client=redis_client,
            queue_name="llm",
            result_ttl=3600,
            failure_ttl=7200,
        )

        assert backend.result_ttl == 3600
        assert backend.failure_ttl == 7200

    def test_init_with_max_retries(self, redis_client: redis.Redis):
        """Should accept max_retries setting."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(
            redis_client=redis_client,
            queue_name="llm",
            max_retries=5,
        )

        assert backend.max_retries == 5

    def test_setup_verifies_redis_connection(self, redis_client: redis.Redis):
        """setup() should verify Redis connection is working."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")

        # Should not raise
        backend.setup()

    def test_setup_raises_on_connection_failure(self):
        """setup() should raise if Redis connection fails."""
        from app.llm.queue.backend import RedisQueueBackend

        # Create a mock redis client that fails ping
        mock_redis = MagicMock(spec=redis.Redis)
        mock_redis.ping.side_effect = redis.ConnectionError("Connection refused")

        backend = RedisQueueBackend(redis_client=mock_redis, queue_name="llm")

        with pytest.raises(ConnectionError):
            backend.setup()

    def test_enqueue_returns_job_id(
        self,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """enqueue() should return the job ID."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)

        assert job_id == sample_llm_job.id

    def test_enqueue_stores_job_metadata(
        self,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """enqueue() should store job metadata in RQ job."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)

        # Fetch RQ job and verify metadata
        rq_job = backend.queue.fetch_job(job_id)
        assert rq_job is not None
        assert "job" in rq_job.meta
        assert rq_job.meta["job"]["id"] == sample_llm_job.id
        assert rq_job.meta["job"]["prompt"] == sample_llm_job.prompt

    def test_enqueue_uses_configured_ttl(
        self,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """enqueue() should use configured result_ttl and failure_ttl."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(
            redis_client=redis_client,
            queue_name="llm",
            result_ttl=1800,
            failure_ttl=3600,
        )
        backend.setup()

        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)

        rq_job = backend.queue.fetch_job(job_id)
        assert rq_job is not None
        assert rq_job.result_ttl == 1800
        assert rq_job.failure_ttl == 3600

    def test_get_status_returns_none_for_nonexistent_job(
        self, redis_client: redis.Redis
    ):
        """get_status() should return None for non-existent job."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        status = backend.get_status("nonexistent-job-id")

        assert status is None

    def test_get_status_returns_queued_for_new_job(
        self,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """get_status() should return QUEUED for newly enqueued job."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)
        status = backend.get_status(job_id)

        assert status is not None
        assert status.status == JobStatus.QUEUED
        assert status.job_id == job_id

    def test_get_status_returns_job_result_model(
        self,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """get_status() should return JobResult model."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)
        status = backend.get_status(job_id)

        assert isinstance(status, JobResult)
        assert status.job is not None
        assert status.job.prompt == sample_llm_job.prompt

    def test_multiple_queues_independent(self, redis_client: redis.Redis):
        """Different queue names should be independent."""
        from app.llm.queue.backend import RedisQueueBackend

        backend_llm = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend_validator = RedisQueueBackend(
            redis_client=redis_client, queue_name="validator"
        )

        backend_llm.setup()
        backend_validator.setup()

        assert backend_llm.queue_name == "llm"
        assert backend_validator.queue_name == "validator"
        assert backend_llm.queue.name != backend_validator.queue.name


class TestQueueBackendFactory:
    """Tests for queue backend factory function."""

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

    def test_get_queue_backend_returns_backend(self):
        """get_queue_backend() should return a QueueBackend instance."""
        from app.llm.queue.backend import QueueBackend, get_queue_backend

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.Redis.from_url") as mock_redis:
                mock_redis.return_value = MagicMock(spec=redis.Redis)
                mock_redis.return_value.ping.return_value = True

                backend = get_queue_backend()

                assert isinstance(backend, QueueBackend)

    def test_get_queue_backend_defaults_to_redis(self):
        """get_queue_backend() should default to RedisQueueBackend."""
        from app.llm.queue.backend import RedisQueueBackend, get_queue_backend

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.Redis.from_url") as mock_redis:
                mock_redis.return_value = MagicMock(spec=redis.Redis)
                mock_redis.return_value.ping.return_value = True

                backend = get_queue_backend()

                assert isinstance(backend, RedisQueueBackend)

    def test_get_queue_backend_uses_redis_url_from_env(self):
        """get_queue_backend() should use REDIS_URL from environment."""
        from app.llm.queue.backend import get_queue_backend

        with patch.dict(
            os.environ, {"REDIS_URL": "redis://custom-redis:6380/1"}, clear=False
        ):
            with patch("redis.Redis.from_url") as mock_redis:
                mock_redis.return_value = MagicMock(spec=redis.Redis)
                mock_redis.return_value.ping.return_value = True

                get_queue_backend()

                mock_redis.assert_called_once()
                call_args = mock_redis.call_args
                assert "redis://custom-redis:6380/1" in str(call_args)

    def test_get_queue_backend_caches_instance(self):
        """get_queue_backend() should cache and return same instance."""
        from app.llm.queue.backend import get_queue_backend

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.Redis.from_url") as mock_redis:
                mock_redis.return_value = MagicMock(spec=redis.Redis)
                mock_redis.return_value.ping.return_value = True

                backend1 = get_queue_backend()
                backend2 = get_queue_backend()

                assert backend1 is backend2

    def test_get_queue_backend_sqs_backend_type(self):
        """get_queue_backend() should create SQS backend when configured."""
        from app.llm.queue.backend import get_queue_backend
        from app.llm.queue.backend_sqs import SQSQueueBackend

        with patch.dict(
            os.environ,
            {
                "QUEUE_BACKEND": "sqs",
                "SQS_QUEUE_URL": "https://sqs.us-east-1.amazonaws.com/123/test-queue",
                "SQS_JOBS_TABLE": "test-jobs-table",
                "AWS_DEFAULT_REGION": "us-east-1",
            },
            clear=True,
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
                assert isinstance(backend, SQSQueueBackend)

    def test_get_queue_backend_invalid_type_raises(self):
        """get_queue_backend() should raise for unknown backend type."""
        from app.llm.queue.backend import get_queue_backend

        with patch.dict(os.environ, {"QUEUE_BACKEND": "unknown"}, clear=True):
            with pytest.raises(ValueError) as exc_info:
                get_queue_backend()

            assert "Unknown QUEUE_BACKEND" in str(exc_info.value)

    def test_reset_queue_backend_clears_singleton(self):
        """reset_queue_backend() should clear cached instance."""
        from app.llm.queue.backend import get_queue_backend, reset_queue_backend

        with patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379/0"}):
            with patch("redis.Redis.from_url") as mock_redis:
                mock_redis.return_value = MagicMock(spec=redis.Redis)
                mock_redis.return_value.ping.return_value = True

                backend1 = get_queue_backend()
                reset_queue_backend()
                backend2 = get_queue_backend()

                # After reset, should be a new instance
                assert backend1 is not backend2


class TestQueueBackendIntegration:
    """Integration tests for queue backend with real Redis."""

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

    def test_enqueue_and_get_status_roundtrip(
        self,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """Full roundtrip: enqueue job and retrieve status."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        # Enqueue
        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)

        # Get status
        status = backend.get_status(job_id)

        assert status is not None
        assert status.job_id == job_id
        assert status.status == JobStatus.QUEUED
        assert status.job is not None
        assert status.job.id == sample_llm_job.id
        assert status.job.prompt == sample_llm_job.prompt
        assert status.job.metadata == sample_llm_job.metadata

    def test_multiple_jobs_enqueued_independently(
        self,
        redis_client: redis.Redis,
        mock_provider: BaseLLMProvider,
    ):
        """Multiple jobs should be enqueued and tracked independently."""
        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        # Create multiple jobs
        jobs = [
            LLMJob(
                id=str(uuid4()),
                prompt=f"Test prompt {i}",
                format={"type": "object"},
                provider_config={},
                metadata={"index": i},
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Enqueue all
        job_ids = [backend.enqueue(job, provider=mock_provider) for job in jobs]

        # Verify each can be retrieved
        for i, job_id in enumerate(job_ids):
            status = backend.get_status(job_id)
            assert status is not None
            assert status.job_id == job_id
            assert status.job is not None
            assert status.job.metadata["index"] == i

    @patch("app.llm.queue.processor.process_llm_job")
    def test_job_processing_updates_status(
        self,
        mock_processor,
        redis_client: redis.Redis,
        sample_llm_job: LLMJob,
        mock_provider: BaseLLMProvider,
    ):
        """Job status should update after processing."""
        from rq import SimpleWorker

        from app.llm.queue.backend import RedisQueueBackend

        backend = RedisQueueBackend(redis_client=redis_client, queue_name="llm")
        backend.setup()

        # Clear queue for isolation
        backend.queue.empty()

        # Mock processor to return success
        mock_response = LLMResponse(
            text="Test response",
            model="test-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        )
        mock_processor.return_value = mock_response

        # Enqueue job
        job_id = backend.enqueue(sample_llm_job, provider=mock_provider)

        # Process with worker
        worker = SimpleWorker([backend.queue], connection=redis_client)
        worker.work(burst=True)

        # Status should be completed
        status = backend.get_status(job_id)
        assert status is not None
        assert status.status == JobStatus.COMPLETED
        assert status.result is not None
