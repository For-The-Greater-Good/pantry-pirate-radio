"""Unit tests for bouy script functions.

These tests are designed to run inside the Docker test container
and test the bouy script functionality without requiring actual
Docker Compose operations.
"""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Skip all tests in this file when running in Docker
pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)


class TestBouyFunctions:
    """Test individual functions from the bouy script."""

    @pytest.fixture
    def bouy_functions_path(self):
        """Get the correct path to bouy functions file."""

        if Path("/app/bouy-functions.sh").exists():
            return "/app/bouy-functions.sh"
        else:
            return "./bouy-functions.sh"

    @pytest.fixture
    def setup_env(self):
        """Set up environment for testing."""
        return {
            "PROGRAMMATIC_MODE": "1",
            "JSON_OUTPUT": "1",
            "COMPOSE_CMD": "echo docker compose",  # Mock for testing
            "PATH": os.environ.get("PATH", ""),
        }

    def test_output_function_json_mode(self, setup_env, bouy_functions_path):
        """Test the output function in JSON mode."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=1
                JSON_OUTPUT=1
                QUIET=0
                NO_COLOR=0
                COMPOSE_CMD="docker compose"
                COMPOSE_FILES=""

                # Source the functions
                source {bouy_functions_path}

                # Call the function
                output "info" "Test message"
            """,
            ],
            capture_output=True,
            text=True,
            env=setup_env,
        )

        assert result.returncode == 0
        output = json.loads(result.stdout.strip())
        assert output["level"] == "info"
        assert output["message"] == "Test message"
        assert "timestamp" in output

    def test_output_function_text_mode(self, bouy_functions_path):
        """Test the output function in text mode."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=0
                JSON_OUTPUT=0
                QUIET=0
                NO_COLOR=0
                COMPOSE_CMD="docker compose"
                COMPOSE_FILES=""

                # Source the functions
                source {bouy_functions_path}

                # Call the function
                output "success" "Test success"
            """,
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # In text mode, output goes to stderr
        assert "Test success" in result.stderr
        assert "[SUCCESS]" in result.stderr or "✓" in result.stderr

    def test_parse_mode_function(self, setup_env, bouy_functions_path):
        """Test parse_mode function sets correct compose files."""
        test_cases = [
            ("--dev", "docker-compose.dev.yml"),
            ("--prod", "docker-compose.prod.yml"),
            ("--test", "docker-compose.test.yml"),
            ("--with-init", "docker-compose.with-init.yml"),
        ]

        for mode, expected_file in test_cases:
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
                    # Initialize required variables
                    PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                    JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                    QUIET=${{QUIET:-0}}
                    NO_COLOR=${{NO_COLOR:-0}}
                    COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                    COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                    # Source the functions
                    source {bouy_functions_path}
                    COMPOSE_FILES="-f docker-compose.yml"
                    parse_mode {mode}
                    echo "$COMPOSE_FILES"
                """,
                ],
                capture_output=True,
                text=True,
                env=setup_env,
            )

            assert result.returncode == 0
            assert expected_file in result.stdout

    def test_check_docker_function(self, setup_env, bouy_functions_path):
        """Test check_docker function."""
        # Test with docker available
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                QUIET=${{QUIET:-0}}
                NO_COLOR=${{NO_COLOR:-0}}
                COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                # Source the functions
                source {bouy_functions_path}
                PROGRAMMATIC_MODE=1
                # Mock which command to return success
                which() {{ return 0; }}
                export -f which
                # Mock docker version command
                docker() {{
                    if [ "$1" = "version" ]; then
                        echo "Docker version 20.10.0"
                        return 0
                    fi
                }}
                export -f docker
                check_docker
                echo $?
            """,
            ],
            capture_output=True,
            text=True,
            env=setup_env,
        )

        assert result.returncode == 0
        assert "0" in result.stdout

    def test_check_service_status_function(self, setup_env, bouy_functions_path):
        """Test check_service_status function."""
        # Create a mock docker compose ps output
        mock_ps_output = '[{"Name":"app","State":"running","Status":"Up 2 hours"}]'

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(
                f"""#!/bin/bash
if [[ "$*" == *"ps --format json app"* ]]; then
    echo '{mock_ps_output}'
    exit 0
fi
exit 1
"""
            )
            mock_compose = f.name

        os.chmod(mock_compose, 0o755)  # noqa: S103

        try:
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
                    # Initialize required variables
                    PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                    JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                    QUIET=${{QUIET:-0}}
                    NO_COLOR=${{NO_COLOR:-0}}
                    COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                    COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                    # Source the functions
                    source {bouy_functions_path}
                    COMPOSE_CMD="{mock_compose}"
                    COMPOSE_FILES=""
                    check_service_status "app"
                    echo $?
                """,
                ],
                capture_output=True,
                text=True,
                env=setup_env,
            )

            assert result.returncode == 0
            assert "0" in result.stdout.strip().split("\n")[-1]
        finally:
            os.unlink(mock_compose)

    def test_validate_scraper_name(self, setup_env, bouy_functions_path):
        """Test scraper name validation."""
        valid_names = ["nyc_efap", "food_bank_2024", "pantry_finder_v3"]
        invalid_names = ["../etc/passwd", "scraper;rm -rf /", "scraper$(echo bad)"]

        for name in valid_names:
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
                    # Initialize required variables
                    PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                    JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                    QUIET=${{QUIET:-0}}
                    NO_COLOR=${{NO_COLOR:-0}}
                    COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                    COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                    # Source the functions
                    source {bouy_functions_path}
                    validate_scraper_name '{name}'
                    echo $?
                """,
                ],
                capture_output=True,
                text=True,
                env=setup_env,
            )
            assert "0" in result.stdout.strip()

        for name in invalid_names:
            result = subprocess.run(
                [
                    "bash",
                    "-c",
                    f"""
                    # Initialize required variables
                    PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                    JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                    QUIET=${{QUIET:-0}}
                    NO_COLOR=${{NO_COLOR:-0}}
                    COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                    COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                    # Source the functions
                    source {bouy_functions_path}
                    validate_scraper_name '{name}'
                    echo $?
                """,
                ],
                capture_output=True,
                text=True,
                env=setup_env,
            )
            assert "1" in result.stdout.strip()

    def test_prompt_with_default_function(self, setup_env, bouy_functions_path):
        """Test prompt_with_default function."""
        # Test with user input
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Set up environment
                set -e
                export PROGRAMMATIC_MODE=0
                export VERBOSE=${{VERBOSE:-0}}
                export QUIET=${{QUIET:-0}}
                export JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                export NO_COLOR=${{NO_COLOR:-1}}

                # Source the functions
                source {bouy_functions_path}

                # Create a wrapper function that returns the value
                test_prompt() {{
                    prompt_with_default "$1" "$2" "$3"
                    eval "echo \\$$3"
                }}

                # Test with user input
                result1=$(echo "test_value" | test_prompt "Enter value" "default" "TEST_VAR")
                echo "RESULT1=$result1"

                # Test with empty input (should use default)
                result2=$(echo "" | test_prompt "Enter value" "default_value" "TEST_VAR2")
                echo "RESULT2=$result2"
                """,
            ],
            capture_output=True,
            text=True,
            env=setup_env,
        )
        assert result.returncode == 0
        assert "RESULT1=test_value" in result.stdout
        assert "RESULT2=default_value" in result.stdout


class TestBouyDependencyChecks:
    """Test dependency checking functions."""

    @pytest.fixture
    def bouy_functions_path(self):
        """Get the correct path to bouy functions file."""

        if Path("/app/bouy-functions.sh").exists():
            return "/app/bouy-functions.sh"
        else:
            return "./bouy-functions.sh"

    @pytest.fixture
    def mock_compose_script(self, tmp_path):
        """Create a mock docker compose script."""
        script = tmp_path / "mock-compose.sh"
        script.write_text(
            """#!/bin/bash
case "$*" in
    *"ps --format json db"*)
        echo '[{"State": "running"}]'
        exit 0
        ;;
    *"exec -T db pg_isready"*)
        echo "accepting connections"
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
    *"exec -T worker test -d"*)
        exit 0
        ;;
    *"exec -T worker test -f"*"content_store.db"*)
        exit 0
        ;;
    *)
        echo "Unhandled: $*" >&2
        exit 1
        ;;
esac
"""
        )
        script.chmod(0o755)
        return str(script)

    def test_check_database_connectivity(
        self, mock_compose_script, bouy_functions_path
    ):
        """Test database connectivity check."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                QUIET=${{QUIET:-0}}
                NO_COLOR=${{NO_COLOR:-0}}
                COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                # Source the functions
                source {bouy_functions_path}
                COMPOSE_CMD="{mock_compose_script}"
                COMPOSE_FILES=""
                PROGRAMMATIC_MODE=1
                check_database_connectivity
                echo $?
            """,
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "0" in result.stdout.strip().split("\n")[-1]

    def test_check_database_schema(self, mock_compose_script, bouy_functions_path):
        """Test database schema check."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                QUIET=${{QUIET:-0}}
                NO_COLOR=${{NO_COLOR:-0}}
                COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                # Source the functions
                source {bouy_functions_path}
                COMPOSE_CMD="{mock_compose_script}"
                COMPOSE_FILES=""
                PROGRAMMATIC_MODE=1
                check_database_schema
                echo $?
            """,
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "0" in result.stdout.strip().split("\n")[-1]

    def test_check_redis_connectivity(self, mock_compose_script, bouy_functions_path):
        """Test Redis connectivity check."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                QUIET=${{QUIET:-0}}
                NO_COLOR=${{NO_COLOR:-0}}
                COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                # Source the functions
                source {bouy_functions_path}
                COMPOSE_CMD="{mock_compose_script}"
                COMPOSE_FILES=""
                PROGRAMMATIC_MODE=1
                check_redis_connectivity
                echo $?
            """,
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "0" in result.stdout.strip().split("\n")[-1]

    def test_check_content_store(self, mock_compose_script, bouy_functions_path):
        """Test content store check."""
        result = subprocess.run(
            [
                "bash",
                "-c",
                f"""
                # Initialize required variables
                PROGRAMMATIC_MODE=${{PROGRAMMATIC_MODE:-0}}
                JSON_OUTPUT=${{JSON_OUTPUT:-0}}
                QUIET=${{QUIET:-0}}
                NO_COLOR=${{NO_COLOR:-0}}
                COMPOSE_CMD="${{COMPOSE_CMD:-docker compose}}"
                COMPOSE_FILES="${{COMPOSE_FILES:-}}"

                # Source the functions
                source {bouy_functions_path}
                COMPOSE_CMD="{mock_compose_script}"
                COMPOSE_FILES=""
                PROGRAMMATIC_MODE=1
                check_content_store
                echo $?
            """,
            ],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        assert "0" in result.stdout.strip().split("\n")[-1]
