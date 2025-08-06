"""Tests for container startup script functionality."""

import os
import subprocess
from pathlib import Path
from unittest.mock import Mock, patch

import pytest


@pytest.fixture
def startup_script():
    """Get path to container_startup.sh script."""
    # Try multiple possible locations (local dev vs CI environment)
    possible_paths = [
        Path(__file__).parent.parent.parent
        / "scripts"
        / "container_startup.sh",  # Local dev
        Path("/app/scripts/container_startup.sh"),  # CI environment (test stage)
        Path("/usr/local/bin/container_startup.sh"),  # CI environment (worker stage)
        Path.cwd() / "scripts" / "container_startup.sh",  # Alternative
    ]

    for script_path in possible_paths:
        if script_path.exists():
            return str(script_path)

    # If none found, show all attempted paths in error
    paths_tried = [str(p) for p in possible_paths]
    assert False, f"Script not found. Tried paths: {paths_tried}"


def test_should_validate_worker_count_as_positive_integer(startup_script):
    """Test script validates WORKER_COUNT is a positive integer."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    # Check for regex validation
    assert '[[ "$WORKER_COUNT" =~ ^[0-9]+$ ]]' in script_content
    assert '[ "$WORKER_COUNT" -ge 1 ]' in script_content
    assert '[ "$WORKER_COUNT" -le 20 ]' in script_content


def test_should_handle_invalid_worker_count_gracefully(startup_script):
    """Test script handles invalid WORKER_COUNT values gracefully."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    # Check for error message and fallback
    assert "Invalid WORKER_COUNT" in script_content
    assert "Defaulting to single worker mode" in script_content


def test_should_set_default_worker_count_to_one(startup_script):
    """Test script defaults WORKER_COUNT to 1."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert "WORKER_COUNT=${WORKER_COUNT:-1}" in script_content


def test_should_check_claude_cli_availability(startup_script):
    """Test script checks for Claude CLI availability."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert "command -v claude" in script_content
    assert "Claude CLI not found" in script_content


def test_should_check_claude_authentication_status(startup_script):
    """Test script checks Claude authentication status."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert "python -m app.claude_auth_manager status" in script_content
    assert "Claude authentication required" in script_content


def test_should_provide_authentication_instructions(startup_script):
    """Test script provides clear authentication instructions."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert (
        "docker compose exec worker python -m app.claude_auth_manager setup"
        in script_content
    )
    assert "Jobs will be safely queued and retried" in script_content


def test_should_start_health_server_when_enabled(startup_script):
    """Test script starts health server when CLAUDE_HEALTH_SERVER=true."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert 'if [ "$CLAUDE_HEALTH_SERVER" = "true" ]' in script_content
    assert "python -m app.claude_health_server 8080" in script_content


def test_should_exec_multi_worker_script_for_multiple_workers(startup_script):
    """Test script executes multi_worker.sh for multiple workers."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert "exec /app/scripts/multi_worker.sh" in script_content


def test_should_exec_single_worker_for_default_case(startup_script):
    """Test script executes single worker for default case."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert 'exec "$@"' in script_content


def test_should_use_set_minus_e_for_error_handling(startup_script):
    """Test script uses 'set -e' for proper error handling."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    assert "set -e" in script_content
    assert "set +e" in script_content  # For auth check


def test_should_have_executable_permissions(startup_script):
    """Test script file has executable permissions."""
    assert os.access(startup_script, os.X_OK)


def test_should_start_with_proper_shebang(startup_script):
    """Test script starts with proper bash shebang."""
    with open(startup_script, "r") as f:
        first_line = f.readline().strip()

    assert first_line == "#!/bin/bash"


def test_script_syntax_is_valid(startup_script):
    """Test script has valid bash syntax."""
    # Use bash -n to check syntax without executing
    result = subprocess.run(
        ["bash", "-n", startup_script], capture_output=True, text=True
    )

    assert result.returncode == 0, f"Script syntax error: {result.stderr}"


def test_should_provide_helpful_command_reference(startup_script):
    """Test script provides helpful command reference."""
    with open(startup_script, "r") as f:
        script_content = f.read()

    # Check for command examples
    assert "python -m app.claude_auth_manager status" in script_content
    assert "python -m app.claude_auth_manager setup" in script_content
    assert "python -m app.claude_auth_manager test" in script_content
    assert "python -m app.claude_auth_manager config" in script_content
