"""Tests for scraper utilities."""

from pathlib import Path
from typing import Any, Iterator, Tuple, cast

import pytest
from redis import Redis
from rq import Queue
from rq.job import Job

from app.llm.providers.base import BaseLLMProvider
from app.llm.queue.job import LLMJob
from app.scraper.utils import ScraperJob, ScraperUtils

# Import redis_client fixture
pytest_plugins = ["tests.fixtures.cache"]


@pytest.fixture
def mock_redis_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Fixture to mock Redis URL in environment."""
    url = "redis://cache:6379/0"
    monkeypatch.setenv("REDIS_URL", url)
    yield url


@pytest.fixture
def mock_queue(redis_client: "Redis[Any]") -> Iterator[Queue]:
    """Create test queue."""
    queue = Queue("llm", connection=redis_client)  # Use same name as real queue
    # Clean up queue after test
    yield queue
    queue.empty()


@pytest.fixture
def mock_prompt_file(tmp_path: Path) -> Path:
    """Create mock prompt file."""
    prompt_dir = tmp_path / "app/llm/hsds_aligner/prompts"
    prompt_dir.mkdir(parents=True)
    prompt_file = prompt_dir / "food_pantry_mapper.prompt"
    prompt_file.write_text("Test system prompt")
    return prompt_file


def test_queue_job(
    mock_redis_url: str,
    mock_queue: Queue,
    mock_prompt_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test queueing content for processing."""
    # Mock prompt file path

    def mock_exists(self: Path) -> bool:
        return str(self).endswith("food_pantry_mapper.prompt")

    def mock_read_text(self: Path) -> str:
        return "Test system prompt"

    monkeypatch.setattr(Path, "exists", mock_exists)
    monkeypatch.setattr(Path, "read_text", mock_read_text)

    # Mock llm_queue to use test queue
    monkeypatch.setattr("app.llm.queue.queues.llm_queue", mock_queue)

    # Mock base path based on environment (container vs local)
    import os

    if os.path.exists("/app"):
        # Running in container
        base_path = "/app/app/scraper/utils.py"
    else:
        # Running locally
        base_path = "/workspace/app/scraper/utils.py"

    monkeypatch.setattr("app.scraper.utils.__file__", str(Path(base_path)))

    # Create test scraper
    scraper = ScraperJob(scraper_id="test_scraper")

    # Queue content
    job_id = scraper.submit_to_queue("Test content")
    assert job_id is not None

    # Verify job was queued
    job = mock_queue.fetch_job(job_id)
    assert job is not None
    assert isinstance(job, Job)

    # Type the job arguments
    args = cast(Tuple[LLMJob, BaseLLMProvider[Any, Any]], job.args)
    assert len(args) == 2  # job, provider
    assert isinstance(args[0], LLMJob)  # job
    assert "Test content" in args[0].prompt
    assert isinstance(args[1], BaseLLMProvider)  # provider


def test_missing_redis_url(
    mock_prompt_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling of missing Redis URL."""
    # Mock prompt file path

    def mock_exists(self: Path) -> bool:
        return str(self).endswith("food_pantry_mapper.prompt")

    def mock_read_text(self: Path) -> str:
        return "Test system prompt"

    monkeypatch.setattr(Path, "exists", mock_exists)
    monkeypatch.setattr(Path, "read_text", mock_read_text)

    # Mock base path to point to workspace
    monkeypatch.setattr(
        "app.scraper.utils.__file__", str(Path("/workspace/app/scraper/utils.py"))
    )

    # Remove REDIS_URL from environment
    monkeypatch.delenv("REDIS_URL", raising=False)

    # Verify error handling
    with pytest.raises(KeyError) as exc_info:
        ScraperUtils(scraper_id="test_scraper")
    assert "REDIS_URL" in str(exc_info.value)


def test_redis_connection_error(
    mock_redis_url: str,
    mock_prompt_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling of Redis connection errors."""
    # Mock prompt file path

    def mock_exists(self: Path) -> bool:
        return str(self).endswith("food_pantry_mapper.prompt")

    def mock_read_text(self: Path) -> str:
        return "Test system prompt"

    monkeypatch.setattr(Path, "exists", mock_exists)
    monkeypatch.setattr(Path, "read_text", mock_read_text)

    # Mock base path to point to workspace
    monkeypatch.setattr(
        "app.scraper.utils.__file__", str(Path("/workspace/app/scraper/utils.py"))
    )

    # Mock Redis to raise error
    def mock_from_url(*args: Any, **kwargs: Any) -> Any:
        raise ConnectionError("Failed to connect to Redis")

    monkeypatch.setattr(Redis, "from_url", mock_from_url)

    # Verify error handling
    with pytest.raises(ConnectionError) as exc_info:
        ScraperUtils(scraper_id="test_scraper")
    assert "Failed to connect to Redis" in str(exc_info.value)
