"""Test bouy script functionality using Docker-in-Docker approach.

These tests verify bouy commands work correctly by mocking the docker compose
responses. They run inside the test container as part of the regular test suite.
"""

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Skip all tests in this file when running in Docker
pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)


class TestBouyInDocker:
    """Test bouy script commands with proper Docker mocking."""

    @pytest.fixture
    def bouy_path(self):
        """Get the path to the bouy script."""
        # When running in Docker test container, bouy should be in the project root
        if Path("/app/bouy").exists():
            return "/app/bouy"
        else:
            return "./bouy"

    @pytest.fixture
    def mock_docker_responses(self, tmp_path):
        """Create a directory with mock response files."""
        responses_dir = tmp_path / "mock_responses"
        responses_dir.mkdir()

        # Create response files for different commands
        (responses_dir / "ps_json_all.json").write_text(
            json.dumps(
                [
                    {
                        "Name": "app",
                        "State": "running",
                        "Status": "Up 2 hours",
                        "Health": "healthy",
                    },
                    {"Name": "db", "State": "running", "Status": "Up 2 hours"},
                    {"Name": "cache", "State": "running", "Status": "Up 2 hours"},
                    {"Name": "worker", "State": "running", "Status": "Up 1 hour"},
                ]
            )
        )

        (responses_dir / "ps_json_app.json").write_text(
            json.dumps(
                [
                    {
                        "Name": "app",
                        "State": "running",
                        "Status": "Up 2 hours",
                        "Health": "healthy",
                    }
                ]
            )
        )

        (responses_dir / "scraper_list.txt").write_text(
            """Available scrapers:
  - nyc_efap_programs
  - food_bank_nyc
  - hunter_college_nyc_food_pantries
  - nj_snap_screener
  - usda_food_access_research_atlas"""
        )

        return responses_dir

    @pytest.fixture
    def mock_compose_wrapper(self, tmp_path, mock_docker_responses):
        """Create a wrapper script that mocks docker compose behavior."""
        wrapper = tmp_path / "docker-compose-mock"
        # Create the wrapper script content
        # Using environment variable instead of direct string interpolation for safety
        # Set environment variable for the mock script
        os.environ["MOCK_RESPONSES_DIR"] = str(mock_docker_responses)

        # Create full script using a single string literal to avoid concatenation warning
        wrapper.write_text(
            """#!/bin/bash
# Mock docker compose wrapper for testing

RESPONSES_DIR="${MOCK_RESPONSES_DIR}"

case "$*" in
    *"ps --format json"*)
        if [[ "$*" == *"app"* ]]; then
            cat "$RESPONSES_DIR/ps_json_app.json"
        else
            cat "$RESPONSES_DIR/ps_json_all.json"
        fi
        exit 0
        ;;
    *"ps"*)
        echo "NAME    STATUS    PORTS"
        echo "app     Up        8000->8000/tcp"
        echo "db      Up        5432/tcp"
        echo "cache   Up        6379/tcp"
        exit 0
        ;;
    *"exec -T db pg_isready"*)
        echo "localhost:5432 - accepting connections"
        exit 0
        ;;
    *"exec -T cache redis-cli ping"*)
        echo "PONG"
        exit 0
        ;;
    *"exec -T db psql"*"SELECT 1 FROM record_version"*)
        echo " ?column?"
        echo "----------"
        echo "        1"
        echo "(1 row)"
        exit 0
        ;;
    *"exec -T scraper python -m app.scraper --list"*)
        cat "$RESPONSES_DIR/scraper_list.txt"
        exit 0
        ;;
    *"up -d"*)
        echo "✔ Container pantry-pirate-radio-db-1 Started"
        echo "✔ Container pantry-pirate-radio-cache-1 Started"
        echo "✔ Container pantry-pirate-radio-app-1 Started"
        exit 0
        ;;
    *"down"*)
        echo "✔ Container pantry-pirate-radio-app-1 Stopped"
        echo "✔ Container pantry-pirate-radio-db-1 Stopped"
        echo "✔ Container pantry-pirate-radio-cache-1 Stopped"
        exit 0
        ;;
    *)
        echo "Unhandled mock command: $*" >&2
        exit 1
        ;;
esac
"""
        )
        wrapper.chmod(0o755)
        return str(wrapper)

    def test_bouy_help(self, bouy_path):
        """Test bouy help command."""
        # This should work without any mocking
        result = subprocess.run([bouy_path, "--help"], capture_output=True, text=True)

        assert result.returncode == 0
        assert "Bouy v1.0.0 - Docker Fleet Management" in result.stdout
        assert "Commands:" in result.stdout

    def test_bouy_version(self, bouy_path):
        """Test bouy version command."""
        result = subprocess.run(
            [bouy_path, "--version"], capture_output=True, text=True
        )

        assert result.returncode == 0
        assert "Bouy v" in result.stdout

    @pytest.mark.skipif(
        not Path("/app/bouy").exists(), reason="Bouy script not found in container"
    )
    def test_bouy_status_json(self, bouy_path, mock_compose_wrapper):
        """Test bouy status command with JSON output."""
        env = os.environ.copy()
        env["COMPOSE_CMD"] = mock_compose_wrapper

        result = subprocess.run(
            [bouy_path, "--json", "status"], capture_output=True, text=True, env=env
        )

        assert result.returncode == 0

        # Parse JSON output lines
        json_lines = [
            line for line in result.stdout.strip().split("\n") if line.startswith("{")
        ]
        assert len(json_lines) > 0

        # Verify we got valid JSON
        for line in json_lines:
            data = json.loads(line)
            assert "timestamp" in data
            assert "level" in data
            assert "message" in data

    @pytest.mark.skipif(
        not Path("/app/bouy").exists(), reason="Bouy script not found in container"
    )
    def test_bouy_up_programmatic(self, bouy_path, mock_compose_wrapper):
        """Test bouy up command in programmatic mode."""
        env = os.environ.copy()
        env["COMPOSE_CMD"] = mock_compose_wrapper

        result = subprocess.run(
            [bouy_path, "--programmatic", "up"], capture_output=True, text=True, env=env
        )

        assert result.returncode == 0
        assert "Starting services" in result.stdout
        assert "Services started successfully" in result.stdout

    @pytest.mark.skipif(
        not Path("/app/bouy").exists(), reason="Bouy script not found in container"
    )
    def test_bouy_scraper_list(self, bouy_path, mock_compose_wrapper):
        """Test bouy scraper list command."""
        env = os.environ.copy()
        env["COMPOSE_CMD"] = mock_compose_wrapper

        result = subprocess.run(
            [bouy_path, "--programmatic", "scraper", "list"],
            capture_output=True,
            text=True,
            env=env,
        )

        assert result.returncode == 0
        assert "nyc_efap_programs" in result.stdout
        assert "food_bank_nyc" in result.stdout

    def test_bouy_command_validation(self, bouy_path):
        """Test bouy validates commands properly."""
        # Test invalid command
        result = subprocess.run(
            [bouy_path, "--programmatic", "invalid-command"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 1
        # When given an invalid command, bouy shows the help message
        assert "Usage: bouy" in result.stdout

    @pytest.mark.skipif(
        not Path("/app/bouy").exists(), reason="Bouy script not found in container"
    )
    def test_bouy_dependency_checks(self, bouy_path, mock_compose_wrapper, tmp_path):
        """Test bouy dependency checking functions."""
        # Create a mock wrapper that simulates missing dependencies
        failing_wrapper = tmp_path / "failing-compose"
        failing_wrapper.write_text(
            """#!/bin/bash
case "$*" in
    *"exec -T db pg_isready"*)
        echo "psql: could not connect to server" >&2
        exit 1
        ;;
    *)
        exit 1
        ;;
esac
"""
        )
        failing_wrapper.chmod(0o755)

        env = os.environ.copy()
        env["COMPOSE_CMD"] = str(failing_wrapper)

        # Try to run reconciler which requires database
        result = subprocess.run(
            [bouy_path, "--programmatic", "reconciler"],
            capture_output=True,
            text=True,
            env=env,
        )

        # Should fail due to database not being available
        assert result.returncode != 0
        assert "database" in result.stdout.lower()


class TestBouyScriptIntegrity:
    """Test the bouy script itself for common issues."""

    def test_bouy_script_exists(self):
        """Verify bouy script exists in the expected location."""
        bouy_paths = [
            Path("/app/bouy"),  # In Docker container
            Path("./bouy"),  # Local development
        ]

        found = False
        for path in bouy_paths:
            if path.exists():
                found = True
                break

        assert found, f"Bouy script not found in any of: {bouy_paths}"

    def test_bouy_script_executable(self):
        """Verify bouy script is executable."""
        bouy_path = Path("/app/bouy") if Path("/app/bouy").exists() else Path("./bouy")

        if bouy_path.exists():
            assert os.access(bouy_path, os.X_OK), "Bouy script is not executable"

    def test_bouy_script_shebang(self):
        """Verify bouy script has proper shebang."""
        bouy_path = Path("/app/bouy") if Path("/app/bouy").exists() else Path("./bouy")

        if bouy_path.exists():
            first_line = bouy_path.read_text().split("\n")[0]
            assert first_line == "#!/bin/bash", f"Invalid shebang: {first_line}"
