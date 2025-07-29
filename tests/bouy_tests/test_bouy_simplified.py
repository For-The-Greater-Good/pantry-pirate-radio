"""Simplified unit tests for bouy script functions."""

import json
import os
import subprocess
from pathlib import Path

import pytest

# Skip all tests in this file when running in Docker
pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)


# Template for setting up bouy function tests
BOUY_TEST_TEMPLATE = """
# Initialize required variables
PROGRAMMATIC_MODE={programmatic_mode}
JSON_OUTPUT={json_output}
QUIET={quiet}
NO_COLOR={no_color}
VERBOSE={verbose}
COMPOSE_CMD="{compose_cmd}"
COMPOSE_FILES="{compose_files}"

# Source the functions
source {bouy_functions_path}

# Run the test
{test_code}
"""


class TestBouyFunctions:
    """Test individual functions from the bouy script."""

    @pytest.fixture
    def bouy_functions_path(self):
        """Get the correct path to bouy functions file."""
        if Path("/app/bouy-functions.sh").exists():
            return "/app/bouy-functions.sh"
        else:
            return "./bouy-functions.sh"

    def run_bouy_test(self, bouy_functions_path, test_code, env=None, **kwargs):
        """Helper to run a bouy function test."""
        # Set defaults
        params = {
            "programmatic_mode": kwargs.get("programmatic_mode", 0),
            "json_output": kwargs.get("json_output", 0),
            "quiet": kwargs.get("quiet", 0),
            "no_color": kwargs.get("no_color", 0),
            "verbose": kwargs.get("verbose", 0),
            "compose_cmd": kwargs.get("compose_cmd", "docker compose"),
            "compose_files": kwargs.get("compose_files", ""),
            "bouy_functions_path": bouy_functions_path,
            "test_code": test_code,
        }

        script = BOUY_TEST_TEMPLATE.format(**params)

        result = subprocess.run(
            ["bash", "-c", script], capture_output=True, text=True, env=env or {}
        )
        return result

    def test_output_function_json_mode(self, bouy_functions_path):
        """Test the output function in JSON mode."""
        result = self.run_bouy_test(
            bouy_functions_path,
            'output "info" "Test message"',
            programmatic_mode=1,
            json_output=1,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output["level"] == "info"
        assert output["message"] == "Test message"
        assert "timestamp" in output

    def test_output_function_text_mode(self, bouy_functions_path):
        """Test the output function in text mode."""
        result = self.run_bouy_test(
            bouy_functions_path,
            'output "success" "Test success"',
            programmatic_mode=0,
            json_output=0,
        )

        assert result.returncode == 0
        # In text mode, output goes to stderr
        assert "Test success" in result.stderr
        assert "[SUCCESS]" in result.stderr or "✓" in result.stderr

    def test_parse_mode_dev(self, bouy_functions_path):
        """Test parse_mode function for dev mode."""
        test_code = """
COMPOSE_FILES="-f docker-compose.yml"
parse_mode --dev
echo "$COMPOSE_FILES"
"""
        result = self.run_bouy_test(bouy_functions_path, test_code)

        assert result.returncode == 0
        assert "docker-compose.dev.yml" in result.stdout

    def test_parse_mode_prod(self, bouy_functions_path):
        """Test parse_mode function for prod mode."""
        test_code = """
COMPOSE_FILES="-f docker-compose.yml"
parse_mode --prod
echo "$COMPOSE_FILES"
"""
        result = self.run_bouy_test(bouy_functions_path, test_code)

        assert result.returncode == 0
        assert "docker-compose.prod.yml" in result.stdout

    def test_validate_scraper_name_valid(self, bouy_functions_path):
        """Test scraper name validation with valid names."""
        valid_names = ["nyc_efap", "food_bank_2024", "pantry_finder_v3"]

        for name in valid_names:
            test_code = f'validate_scraper_name "{name}" && echo "0" || echo "1"'
            result = self.run_bouy_test(bouy_functions_path, test_code)
            assert result.returncode == 0
            assert "0" in result.stdout.strip()

    def test_validate_scraper_name_invalid(self, bouy_functions_path):
        """Test scraper name validation with invalid names."""
        invalid_names = ["../etc/passwd", "scraper;rm -rf /", "scraper`echo bad`"]

        for name in invalid_names:
            # Escape the name properly for bash
            escaped_name = (
                name.replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
            )
            test_code = f'validate_scraper_name "{escaped_name}" && echo "VALID" || echo "INVALID"'
            result = self.run_bouy_test(bouy_functions_path, test_code)
            assert (
                result.returncode == 0
            ), f"Failed to run test for {name}: {result.stderr}"
            assert (
                "INVALID" in result.stdout
            ), f"Expected INVALID for {name}, got: {result.stdout}"

    def test_check_docker_mocked(self, bouy_functions_path):
        """Test check_docker function with mocking."""
        test_code = """
# Mock which and docker commands
which() { return 0; }
docker() {
    if [ "$1" = "version" ]; then
        echo "Docker version 20.10.0"
        return 0
    fi
}
export -f which
export -f docker

PROGRAMMATIC_MODE=1
check_docker && echo "0" || echo "1"
"""
        result = self.run_bouy_test(bouy_functions_path, test_code, programmatic_mode=1)
        assert result.returncode == 0
        assert "0" in result.stdout


class TestBouyDependencyChecks:
    """Test dependency checking functions with mocking."""

    @pytest.fixture
    def bouy_functions_path(self):
        """Get the correct path to bouy functions file."""
        if Path("/app/bouy-functions.sh").exists():
            return "/app/bouy-functions.sh"
        else:
            return "./bouy-functions.sh"

    def run_bouy_test(
        self, bouy_functions_path, test_code, compose_cmd="docker compose", **kwargs
    ):
        """Helper to run a bouy function test."""
        params = {
            "programmatic_mode": 1,  # Use programmatic mode for cleaner output
            "json_output": 0,
            "quiet": 0,
            "no_color": 0,
            "verbose": 0,
            "compose_cmd": compose_cmd,
            "compose_files": "",
            "bouy_functions_path": bouy_functions_path,
            "test_code": test_code,
        }
        params.update(kwargs)

        script = BOUY_TEST_TEMPLATE.format(**params)

        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        return result

    def test_check_database_connectivity_success(self, bouy_functions_path, tmp_path):
        """Test database connectivity check with success."""
        # Create mock compose script
        mock_script = tmp_path / "mock-compose.sh"
        mock_script.write_text(
            """#!/bin/bash
if [[ "$*" == *"exec -T db pg_isready"* ]]; then
    echo "accepting connections"
    exit 0
fi
exit 1
"""
        )
        mock_script.chmod(0o755)

        test_code = 'check_database_connectivity && echo "0" || echo "1"'
        result = self.run_bouy_test(
            bouy_functions_path, test_code, compose_cmd=str(mock_script)
        )

        assert result.returncode == 0
        assert "0" in result.stdout

    def test_check_redis_connectivity_success(self, bouy_functions_path, tmp_path):
        """Test Redis connectivity check with success."""
        # Create mock compose script
        mock_script = tmp_path / "mock-compose.sh"
        mock_script.write_text(
            """#!/bin/bash
if [[ "$*" == *"exec -T cache redis-cli ping"* ]]; then
    echo "PONG"
    exit 0
fi
exit 1
"""
        )
        mock_script.chmod(0o755)

        test_code = 'check_redis_connectivity && echo "0" || echo "1"'
        result = self.run_bouy_test(
            bouy_functions_path, test_code, compose_cmd=str(mock_script)
        )

        assert result.returncode == 0
        assert "0" in result.stdout

    def test_check_database_schema_success(self, bouy_functions_path, tmp_path):
        """Test database schema check with success."""
        # Create mock compose script
        mock_script = tmp_path / "mock-compose.sh"
        mock_script.write_text(
            """#!/bin/bash
if [[ "$*" == *"SELECT 1 FROM record_version"* ]]; then
    echo "1"
    exit 0
fi
exit 1
"""
        )
        mock_script.chmod(0o755)

        test_code = 'check_database_schema && echo "0" || echo "1"'
        result = self.run_bouy_test(
            bouy_functions_path, test_code, compose_cmd=str(mock_script)
        )

        assert result.returncode == 0
        assert "0" in result.stdout
