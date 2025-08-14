"""Shared fixtures for validator tests."""

from typing import Generator
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from redis import Redis
from sqlalchemy.orm import Session

from tests.fixtures.types.config import get_test_settings

settings = get_test_settings()


@pytest.fixture
def mock_redis():
    """Mock Redis connection for testing."""
    mock = MagicMock(spec=Redis)
    mock.ping.return_value = True
    return mock


@pytest.fixture
def sample_hsds_job():
    """Create a sample HSDSJob for testing."""
    from app.llm.queue.models import JobResult, JobStatus, LLMJob
    from app.llm.providers.types import LLMResponse
    
    # Create LLM job
    llm_job = LLMJob(
        id="test-llm-job-123",
        prompt="Extract organization data",
        format={"type": "hsds"},
        provider_config={},
        metadata={"content_hash": "abc123", "source": "test_scraper"},
        created_at=datetime.now(),
    )
    
    # Create LLM response with HSDS data
    llm_response = LLMResponse(
        text='{"organization": {"name": "Test Food Bank", "description": "A test food bank"}}',
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )
    
    # Create job result
    return JobResult(
        job_id=llm_job.id,
        job=llm_job,
        status=JobStatus.COMPLETED,
        result=llm_response,
        error=None,
        completed_at=datetime.now(),
        processing_time=1.5,
    )


@pytest.fixture
def mock_validator_queue():
    """Mock validator queue."""
    with patch("app.validator.queues.validator_queue") as mock:
        mock.enqueue_call = MagicMock()
        mock.fetch_job = MagicMock()
        yield mock


@pytest.fixture
def mock_reconciler_queue():
    """Mock reconciler queue."""
    with patch("app.validator.queues.reconciler_queue") as mock:
        mock.enqueue_call = MagicMock()
        yield mock


@pytest.fixture
def validator_config():
    """Validator service configuration."""
    return {
        "enabled": True,
        "queue_name": "validator",
        "redis_ttl": 3600,
        "log_data_flow": True,
    }


@pytest.fixture
def disabled_validator_config():
    """Disabled validator service configuration."""
    return {
        "enabled": False,
        "queue_name": "validator",
        "redis_ttl": 3600,
        "log_data_flow": False,
    }


# Import the sync db_session fixture from the main fixtures
from tests.fixtures.db import db_session_sync as db_session