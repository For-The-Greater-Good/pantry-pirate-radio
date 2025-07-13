"""Tests for recorder service."""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from redis import Redis

from app.llm.queue.models import JobResult, JobStatus, LLMJob, LLMResponse


@pytest.fixture
def redis() -> Redis:
    """Create Redis connection."""
    redis = Redis.from_url(
        "redis://cache:6379",
        decode_responses=False,
    )
    # Verify Redis connection
    try:
        redis.ping()
    except Exception as e:
        pytest.fail(f"Redis connection failed: {e}")
    return redis


@pytest.fixture
def sample_job_result() -> dict[str, Any]:
    """Sample job result fixture."""
    llm_response = LLMResponse(
        text=json.dumps(
            {
                "organization": [
                    {"name": "Test Org", "description": "Test Description"}
                ],
                "service": [
                    {"name": "Test Service", "description": "Test Service Description"}
                ],
                "location": [
                    {
                        "name": "Test Location",
                        "description": "Test Location Description",
                        "latitude": 42.3675294,
                        "longitude": -71.186966,
                    }
                ],
            }
        ),
        model="test-model",
        usage={"total_tokens": 100},
        raw={},
    )

    job_result = JobResult(
        job_id=str(uuid.uuid4()),
        job=LLMJob(
            id="test-job",
            prompt="test prompt",
            provider_config={},
            format={},
            created_at=datetime.now(),
            metadata={"scraper_id": "test_scraper"},
        ),
        status=JobStatus.COMPLETED,
        result=llm_response,
    )

    return job_result.model_dump()


@pytest.fixture
def output_dir(tmp_path: Path) -> Path:
    """Create temporary output directory."""
    output = tmp_path / "outputs"
    output.mkdir()
    return output


@pytest.fixture
def archive_dir(tmp_path: Path) -> Path:
    """Create temporary archive directory."""
    archive = tmp_path / "archives"
    archive.mkdir()
    return archive


def test_record_result(
    redis: Redis,
    sample_job_result: dict[str, Any],
    output_dir: Path,
    archive_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test recording job result."""
    # Set environment variables
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("ARCHIVE_DIR", str(archive_dir))

    # Just test the function directly since RQ testing is complex
    from app.recorder.utils import record_result

    result = record_result(sample_job_result)

    # Check result
    assert result["status"] == "completed"
    assert result["error"] is None

    # Check output file was created
    output_file = output_dir / f"{sample_job_result['job_id']}.json"
    assert output_file.exists()
    assert output_file.is_file()

    # Verify file contents
    with open(output_file) as f:
        saved_data = json.load(f)
        assert saved_data["job_id"] == sample_job_result["job_id"]
        assert saved_data["status"] == sample_job_result["status"]


def test_error_handling(
    redis: Redis,
    output_dir: Path,
    archive_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test error handling."""
    # Set environment variables
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("ARCHIVE_DIR", str(archive_dir))

    # Test error handling with direct call
    from app.recorder.utils import record_result

    result = record_result({})  # Empty dict should fail validation

    # Check result
    assert result["status"] == "failed"
    assert result["error"] is not None

    # Check no file was created
    assert len(list(output_dir.iterdir())) == 0


def test_multiple_jobs(
    redis: Redis,
    sample_job_result: dict[str, Any],
    output_dir: Path,
    archive_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test processing multiple jobs."""
    # Set environment variables
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))
    monkeypatch.setenv("ARCHIVE_DIR", str(archive_dir))

    # Test multiple jobs with direct calls
    from app.recorder.utils import record_result

    results = []
    for i in range(3):
        # Modify data for each job
        data = sample_job_result.copy()
        data["job_id"] = str(uuid.uuid4())  # New ID for each job
        if data["result"]:
            result_data = json.loads(data["result"]["text"])
            result_data["organization"][0]["name"] = f"Test Org {i}"
            data["result"]["text"] = json.dumps(result_data)

        # Process job directly
        result = record_result(data)
        results.append(result)

    # Check results
    assert all(result["status"] == "completed" for result in results)
    assert all(result["error"] is None for result in results)

    # Check output files
    output_files = list(output_dir.iterdir())
    assert len(output_files) == 3
    assert all(f.suffix == ".json" for f in output_files)


def test_metrics_on_exception(
    output_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that metrics are properly updated when an exception occurs without job metadata."""
    # Set environment variables
    monkeypatch.setenv("OUTPUT_DIR", str(output_dir))

    from app.recorder.utils import record_result, RECORDER_JOBS

    # Get initial metric value
    initial_failure_count = RECORDER_JOBS.labels(
        scraper_id="unknown", status="failure"
    )._value._value

    # Test with data that will cause an exception during processing
    # but has enough structure to avoid the early validation error
    problematic_data = {
        "job_id": "test-job-123",
        # Missing job metadata, so scraper_id extraction will fall back to "unknown"
    }

    # Mock the file writing to fail after scraper_id extraction
    import builtins

    original_open = builtins.open

    def mock_open(*args, **kwargs):
        # Allow the first call (for checking file existence) but fail on write
        if "w" in str(args):
            raise PermissionError("Cannot write to file")
        return original_open(*args, **kwargs)

    monkeypatch.setattr("builtins.open", mock_open)

    result = record_result(problematic_data)

    # Check result indicates failure
    assert result["status"] == "failed"
    assert "Cannot write to file" in result["error"]

    # Check that metrics were incremented for unknown scraper_id
    final_failure_count = RECORDER_JOBS.labels(
        scraper_id="unknown", status="failure"
    )._value._value
    assert final_failure_count == initial_failure_count + 1
