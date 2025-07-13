"""Test configuration."""

import os
from collections.abc import Generator
from pathlib import Path
from typing import Any, List, TypeVar, cast

import pytest
from pytest import (
    Config,
    FixtureRequest,
    Item,
    Mark,
    MarkDecorator,
    Module,
)

from app.core.logging import configure_logging

# Load .env file for tests
try:
    from dotenv import load_dotenv

    # Load .env file from project root
    project_dir = Path(__file__).parent.parent
    env_file = project_dir / ".env"
    if env_file.exists():
        load_dotenv(env_file)
except ImportError:
    # dotenv not available, skip loading
    pass

fixture = pytest.fixture
mark = pytest.mark


@fixture(scope="session")
def project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


pytest_plugins: List[str] = [
    "tests.fixtures.db",
    "tests.fixtures.cache",
    "tests.fixtures.api",
    "tests.fixtures.websocket",
]


def get_worker_id() -> str:
    """Get the current worker ID for parallel test execution.

    Returns:
        str: Worker ID (e.g., 'gw0', 'gw1') or 'master' for single process
    """
    worker_id = os.environ.get("PYTEST_XDIST_WORKER", "")
    return worker_id if worker_id else "master"


_T = TypeVar("_T")


# type: ignore[misc]
@fixture(scope="session", name="worker_resources", autouse=True)
def worker_resources_fixture(request: FixtureRequest) -> Generator[None, None, None]:
    """Configure resources for each test worker.

    Handles resource isolation between parallel test workers:
    - Unique database schemas per worker
    - Isolated Redis namespaces
    - Separate log files

    Args:
        request: Pytest fixture request object

    Yields:
        None: Resource configuration context
    """
    worker_id = get_worker_id()

    # Set worker-specific environment variables
    os.environ["TEST_DB_SCHEMA"] = f"test_{worker_id}"
    os.environ["TEST_REDIS_PREFIX"] = f"test:{worker_id}:"
    os.environ["TEST_LOG_FILE"] = f"test_{worker_id}.log"
    os.environ["TESTING"] = "true"

    yield

    # Cleanup worker-specific resources if needed
    if worker_id != "master":
        # Additional cleanup could be added here
        pass


def pytest_configure(config: Config) -> None:
    """Configure pytest.

    Args:
        config: Pytest configuration object
    """
    # Configure logging for test environment
    configure_logging(testing=True)
    # Add test markers
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    config.addinivalue_line(
        "markers", "concurrent: mark test as safe for concurrent execution"
    )
    config.addinivalue_line(
        "markers", "serial: mark test as requiring serial execution"
    )

    # Configure xdist to respect serial tests
    plugin_manager: Any = getattr(config, "pluginmanager", None)
    if plugin_manager and getattr(plugin_manager, "has_plugin", lambda _: False)(
        "xdist"
    ):  # noqa: vulture
        config.option.dist = "loadscope"  # type: ignore[attr-defined]

    # These are configured in pyproject.toml
    # asyncio_mode = "auto"
    # asyncio_default_fixture_loop_scope = "function"


def pytest_collection_modifyitems(config: Config, items: List[Item]) -> None:
    """Modify test items before execution.

    Args:
        config: Pytest configuration object
        items: List of test items to be executed
    """
    plugin_manager: Any = getattr(config, "pluginmanager", None)
    if not plugin_manager or not getattr(
        plugin_manager, "has_plugin", lambda _: False
    )(  # noqa: vulture
        "xdist"
    ):
        return

    for item in items:
        # Mark tests with heavy resource usage as serial
        module: Module = cast(Module, getattr(item, "module", None))
        module_name: str = cast(str, getattr(module, "__name__", ""))
        if "test_integration" in module_name:
            serial_marker: MarkDecorator = mark.serial
            item.add_marker(serial_marker)
        # By default, assume tests are concurrent-safe
        if not any(
            cast(Mark, marker).name == "serial" for marker in item.iter_markers()
        ):
            concurrent_marker: MarkDecorator = mark.concurrent
            item.add_marker(concurrent_marker)
