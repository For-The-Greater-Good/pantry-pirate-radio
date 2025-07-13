"""Tests for logging configuration."""

import json
from typing import Any, Dict

import pytest
import structlog
from structlog.stdlib import BoundLogger
from structlog.testing import LogCapture
from structlog.types import BindableLogger

from app.core.logging import (
    add_request_metadata,
    configure_logging,
    get_logger,
    get_request_logger,
)


@pytest.fixture
def log_output() -> LogCapture:
    """Fixture to capture log output."""
    return LogCapture()


@pytest.fixture(autouse=True)
def setup_logging(log_output: LogCapture) -> None:
    """Configure logging for tests."""
    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="%Y-%m-%d %H:%M:%S.%f"),
            log_output,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )


def test_configure_logging() -> None:
    """Test logging configuration."""
    configure_logging()
    logger = structlog.get_logger()
    assert isinstance(logger, BoundLogger | BindableLogger)

    # Test that JSON renderer is configured
    logger.info("test_message", test_key="test_value")
    # Get the last processor (should be JSONRenderer)
    processors = structlog.get_config()["processors"]
    assert any(
        p.__class__.__name__ == "JSONRenderer" for p in processors
    ), "JSONRenderer not configured"


def test_get_logger() -> None:
    """Test get_logger returns a configured logger."""
    logger = get_logger()
    assert isinstance(logger, BoundLogger | BindableLogger)

    # Test logging with the returned logger
    logger.info("test_message", test_key="test_value")


def test_get_request_logger() -> None:
    """Test get_request_logger binds request ID."""
    request_id = "test-request-id"
    logger = get_request_logger(request_id)
    assert isinstance(logger, BoundLogger | BindableLogger)

    # Test that request_id is bound
    logger.info("test_message")
    assert logger._context.get("request_id") == request_id


def test_add_request_metadata(log_output: LogCapture) -> None:
    """Test request metadata processor."""
    # Configure logging with our test processor
    processor = add_request_metadata()
    structlog.configure(
        processors=[processor, log_output],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    # Get a logger and log a message
    logger = structlog.get_logger()
    logger.info("test_message", test_key="test_value")

    # Verify the log output
    assert len(log_output.entries) > 0
    log_entry = log_output.entries[-1]
    assert isinstance(log_entry, dict)
    assert "test_key" in log_entry
    assert log_entry["test_key"] == "test_value"


def test_json_logging() -> None:
    """Test that logs are properly formatted as JSON."""
    configure_logging()
    logger = get_logger()

    # Create a test message with various data types
    test_data = {
        "string": "test",
        "number": 123,
        "boolean": True,
        "null": None,
        "list": [1, 2, 3],
        "nested": {"key": "value"},
    }

    # Log the test message
    logger.info("test_message", **test_data)

    # Since we're using JSONRenderer, the output should be JSON serializable
    try:
        # Get the last processor (JSONRenderer)
        processors = structlog.get_config()["processors"]
        json_renderer = next(
            p for p in processors if p.__class__.__name__ == "JSONRenderer"
        )

        # Create a test event dict
        event_dict: Dict[str, Any] = {
            "event": "test_message",
            **test_data,
        }

        # Process through JSONRenderer
        result = json_renderer(None, None, event_dict)

        # Verify it's valid JSON
        parsed = json.loads(result)

        # Verify all our test data is present
        assert parsed["event"] == "test_message"
        assert parsed["string"] == "test"
        assert parsed["number"] == 123
        assert parsed["boolean"] is True
        assert parsed["null"] is None
        assert parsed["list"] == [1, 2, 3]
        assert parsed["nested"] == {"key": "value"}

    except (json.JSONDecodeError, AssertionError) as e:
        pytest.fail(f"Failed to validate JSON logging: {str(e)}")
