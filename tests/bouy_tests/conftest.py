"""
Isolated conftest for bouy tests.

This conftest ensures that no parent conftest files are loaded,
preventing any app dependencies from being imported.
"""

import sys
import os
from pathlib import Path
import pytest
import tempfile

def pytest_configure(config):
    """Configure pytest to skip loading parent conftest files."""
    # Prevent pytest from searching parent directories
    config.option.confcutdir = os.path.dirname(__file__)
    
    # Ensure we don't accidentally import app modules
    # by removing the project root from sys.path if it's there
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if project_root in sys.path:
        sys.path.remove(project_root)


@pytest.fixture
def bouy_path():
    """Get the correct path to bouy script."""
    # In CI, we're in the project root
    if Path("/app/bouy").exists():
        return "/app/bouy"
    elif Path("./bouy").exists():
        return "./bouy"
    else:
        # For tests running from bouy_tests directory
        project_root = Path(__file__).parent.parent.parent
        return str(project_root / "bouy")


@pytest.fixture
def failing_compose(tmp_path):
    """Create a mock docker compose that always fails."""
    mock_script = tmp_path / "mock-compose.sh"
    mock_script.write_text(
        """#!/bin/bash
echo "Error: Service not running" >&2
exit 1
"""
    )
    mock_script.chmod(0o755)
    return str(mock_script)


@pytest.fixture
def mock_compose(tmp_path):
    """Create a comprehensive mock docker compose executable."""
    mock_script = tmp_path / "mock-docker-compose"
    mock_script.write_text(
        """#!/bin/bash
# Mock docker compose for testing

case "$*" in
    *"ps --format json"*)
        # Return JSON format for all services
        if [[ "$*" == *"app"* ]]; then
            echo '[{"Name": "app", "State": "running", "Status": "Up 2 hours", "Health": "healthy"}]'
        elif [[ "$*" == *"db"* ]]; then
            echo '[{"Name": "db", "State": "running", "Status": "Up 2 hours"}]'
        elif [[ "$*" == *"cache"* ]]; then
            echo '[{"Name": "cache", "State": "running", "Status": "Up 2 hours"}]'
        elif [[ "$*" == *"worker"* ]]; then
            echo '[{"Name": "worker", "State": "running", "Status": "Up 1 hour"}]'
        else
            echo '[{"Name": "app", "State": "running"}, {"Name": "db", "State": "running"}]'
        fi
        exit 0
        ;;
    *"ps"*)
        # Text format
        echo "NAME    STATUS    PORTS"
        echo "app     Up        8000->8000/tcp"
        echo "db      Up        5432/tcp"
        echo "cache   Up        6379/tcp"
        exit 0
        ;;
    *"up -d"*)
        echo "Starting services..."
        echo "✔ Container db Started"
        echo "✔ Container cache Started"
        echo "✔ Container app Started"
        exit 0
        ;;
    *"down"*)
        echo "Stopping services..."
        echo "✔ Container app Stopped"
        echo "✔ Container db Stopped"
        exit 0
        ;;
    *"exec -T db pg_isready"*)
        echo "localhost:5432 - accepting connections"
        exit 0
        ;;
    *"exec -T db psql"*"SELECT 1 FROM record_version"*)
        echo "1"
        exit 0
        ;;
    *"exec -T db psql"*"test_pantry_pirate_radio"*)
        # Mock test database operations
        echo "CREATE DATABASE"
        exit 0
        ;;
    *"exec -T cache redis-cli ping"*)
        echo "PONG"
        exit 0
        ;;
    *"exec -T worker test -d /app/data/content_store"*)
        exit 0
        ;;
    *"exec -T worker test -f /app/data/content_store/content_store.db"*)
        exit 0
        ;;
    *"exec -T scraper python -m app.scraper --list"*)
        echo "Available scrapers:"
        echo "  - nyc_efap_programs"
        echo "  - food_bank_nyc"
        exit 0
        ;;
    *"exec -T scraper python -m app.scraper list"*)
        echo "Available scrapers:"
        echo "  - nyc_efap_programs"
        echo "  - food_bank_nyc"
        exit 0
        ;;
    *"exec -T scraper python -m app.scraper"*)
        echo "Running scraper..."
        exit 0
        ;;
    *"exec -T reconciler"*)
        echo "Running reconciler..."
        exit 0
        ;;
    *"exec -T app echo test"*)
        echo "test"
        exit 0
        ;;
    *"exec"*"app"*)
        # Service not running
        echo "service \\"app\\" is not running" >&2
        exit 1
        ;;
    *"logs"*)
        echo "2025-01-01 12:00:00 App started"
        echo "2025-01-01 12:00:01 Listening on port 8000"
        exit 0
        ;;
    *"build"*)
        echo "Building services..."
        exit 0
        ;;
    *)
        echo "Unhandled docker compose command: $*" >&2
        exit 1
        ;;
esac
"""
    )
    mock_script.chmod(0o755)
    return str(mock_script)


@pytest.fixture
def mock_compose_script(tmp_path):
    """Create a mock docker compose script for testing."""
    mock_script = tmp_path / "mock-compose.sh"
    mock_script.write_text(
        """#!/bin/bash
# Mock docker compose for dependency tests

case "$*" in
    *"exec -T db pg_isready"*)
        echo "localhost:5432 - accepting connections"
        exit 0
        ;;
    *"exec -T db psql"*"SELECT 1 FROM record_version"*)
        echo "1"
        exit 0
        ;;
    *"exec -T cache redis-cli ping"*)
        echo "PONG"
        exit 0
        ;;
    *"exec -T worker test -d /app/data/content_store"*)
        exit 0
        ;;
    *"exec -T worker test -f /app/data/content_store/content_store.db"*)
        exit 0
        ;;
    *)
        echo "Unknown command: $*" >&2
        exit 1
        ;;
esac
"""
    )
    mock_script.chmod(0o755)
    return str(mock_script)