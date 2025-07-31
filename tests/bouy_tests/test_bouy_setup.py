"""Tests for bouy setup command and related functions."""

import os
import subprocess
import tempfile
import shutil
from pathlib import Path
import pytest

# Skip all tests in this file when running in Docker
pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)


class TestBouySetup:
    """Test the bouy setup command functionality."""

    @pytest.fixture
    def test_env(self):
        """Set up test environment variables."""
        env = os.environ.copy()
        env["BOUY_TEST_MODE"] = "1"
        return env

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for testing."""
        temp_dir = tempfile.mkdtemp()
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)

    @pytest.fixture
    def bouy_path(self, temp_dir):
        """Get the path to the bouy script."""
        # Copy bouy script to temp directory
        original_bouy = Path(__file__).parent.parent.parent / "bouy"
        test_bouy = Path(temp_dir) / "bouy"
        shutil.copy(original_bouy, test_bouy)
        test_bouy.chmod(0o755)

        # Also copy .env.example
        original_env_example = Path(__file__).parent.parent.parent / ".env.example"
        test_env_example = Path(temp_dir) / ".env.example"
        shutil.copy(original_env_example, test_env_example)

        return str(test_bouy)

    def test_prompt_with_default_function(self, test_env):
        """Test the prompt_with_default function."""
        # Create a test script that uses prompt_with_default
        test_script = """
        #!/bin/bash
        source ./bouy-functions.sh

        # Simulate user input
        echo "test_value" | prompt_with_default "Enter value" "default" "TEST_VAR"
        echo "TEST_VAR=$TEST_VAR"

        # Test with empty input (should use default)
        echo "" | prompt_with_default "Enter value" "default_value" "TEST_VAR2"
        echo "TEST_VAR2=$TEST_VAR2"
        """

        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(test_script)
            f.flush()

            result = subprocess.run(
                ["bash", f.name], capture_output=True, text=True, env=test_env
            )

            assert "TEST_VAR=test_value" in result.stdout
            assert "TEST_VAR2=default_value" in result.stdout

    def test_setup_command_help(self, test_env, bouy_path, temp_dir):
        """Test that setup command is listed in help."""
        result = subprocess.run(
            [bouy_path, "--help"],
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        assert result.returncode == 0
        assert "setup" in result.stdout
        assert "Interactive setup wizard" in result.stdout

    def test_setup_command_creates_env_file(self, test_env, bouy_path, temp_dir):
        """Test setup command creates .env file with basic inputs."""
        # Simulate user inputs for setup wizard
        inputs = "\n".join(
            [
                "pirate",  # PostgreSQL password
                "1",  # OpenAI provider
                "test_api_key",  # OpenRouter API key
                "skip",  # GitHub token (skip)
            ]
        )

        result = subprocess.run(
            [bouy_path, "setup"],
            input=inputs,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        # Check that setup completed successfully
        assert result.returncode == 0
        assert ".env file created successfully!" in result.stdout

        # Check that .env file was created
        env_file = Path(temp_dir) / ".env"
        assert env_file.exists()

        # Read and verify .env content
        env_content = env_file.read_text()
        assert "POSTGRES_PASSWORD=pirate" in env_content
        assert "LLM_PROVIDER=openai" in env_content
        assert "OPENROUTER_API_KEY=test_api_key" in env_content
        assert "PUBLISHER_PUSH_ENABLED=false" in env_content

    def test_setup_command_with_claude_provider(self, test_env, bouy_path, temp_dir):
        """Test setup command with Claude provider selection."""
        # Simulate user inputs for Claude with CLI auth
        inputs = "\n".join(
            [
                "secure_password",  # PostgreSQL password
                "2",  # Claude provider
                "2",  # Claude CLI auth
                "skip",  # GitHub token (skip)
            ]
        )

        result = subprocess.run(
            [bouy_path, "setup"],
            input=inputs,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        assert result.returncode == 0

        # Read and verify .env content
        env_file = Path(temp_dir) / ".env"
        env_content = env_file.read_text()
        assert "POSTGRES_PASSWORD=secure_password" in env_content
        assert "LLM_PROVIDER=claude" in env_content
        assert "You'll need to run './bouy claude-auth' after setup" in result.stdout

    def test_setup_command_existing_env_no_overwrite(
        self, test_env, bouy_path, temp_dir
    ):
        """Test setup command with existing .env file (no overwrite)."""
        # Create existing .env file
        env_file = Path(temp_dir) / ".env"
        env_file.write_text("EXISTING=true\n")

        # Simulate user choosing not to overwrite
        inputs = "n\n"

        result = subprocess.run(
            [bouy_path, "setup"],
            input=inputs,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        assert result.returncode == 0
        assert "Setup cancelled. Existing .env file preserved." in result.stdout

        # Verify original file is unchanged
        assert env_file.read_text() == "EXISTING=true\n"

    def test_setup_command_existing_env_with_backup(
        self, test_env, bouy_path, temp_dir
    ):
        """Test setup command creates backup of existing .env file."""
        # Create existing .env file
        env_file = Path(temp_dir) / ".env"
        original_content = "EXISTING=true\nOLD_VALUE=123\n"
        env_file.write_text(original_content)

        # Simulate user choosing to overwrite
        inputs = "\n".join(
            [
                "y",  # Yes, overwrite
                "new_password",  # PostgreSQL password
                "1",  # OpenAI provider
                "new_api_key",  # OpenRouter API key
                "skip",  # GitHub token (skip)
            ]
        )

        result = subprocess.run(
            [bouy_path, "setup"],
            input=inputs,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        assert result.returncode == 0
        assert "Existing .env backed up" in result.stdout

        # Check that backup was created
        backup_files = list(Path(temp_dir).glob(".env.backup.*"))
        assert len(backup_files) == 1

        # Verify backup content
        assert backup_files[0].read_text() == original_content

        # Verify new .env was created
        new_content = env_file.read_text()
        assert "POSTGRES_PASSWORD=new_password" in new_content
        assert "EXISTING=true" not in new_content  # Old content replaced

    def test_setup_command_with_publisher_enabled(self, test_env, bouy_path, temp_dir):
        """Test setup command with HAARRRvest publisher enabled."""
        inputs = "\n".join(
            [
                "pirate",  # PostgreSQL password
                "1",  # OpenAI provider
                "test_api_key",  # OpenRouter API key
                "github_pat_123456",  # GitHub token (enable publisher)
            ]
        )

        result = subprocess.run(
            [bouy_path, "setup"],
            input=inputs,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        assert result.returncode == 0
        assert "Publisher will be enabled for pushing to HAARRRvest" in result.stdout

        # Verify .env content
        env_file = Path(temp_dir) / ".env"
        env_content = env_file.read_text()
        assert "PUBLISHER_PUSH_ENABLED=true" in env_content
        assert "DATA_REPO_TOKEN=github_pat_123456" in env_content

    def test_setup_command_special_characters_in_password(
        self, test_env, bouy_path, temp_dir
    ):
        """Test setup handles special characters in passwords correctly."""
        inputs = "\n".join(
            [
                "p@$$w0rd!with#special",  # PostgreSQL password with special chars
                "1",  # OpenAI provider
                "test_api_key",  # OpenRouter API key
                "skip",  # GitHub token (skip)
            ]
        )

        result = subprocess.run(
            [bouy_path, "setup"],
            input=inputs,
            capture_output=True,
            text=True,
            cwd=temp_dir,
            env=test_env,
        )

        assert result.returncode == 0

        # Verify password is properly escaped in .env
        env_file = Path(temp_dir) / ".env"
        env_content = env_file.read_text()
        assert "POSTGRES_PASSWORD=p@$$w0rd!with#special" in env_content
        # Check DATABASE_URL encoding
        assert "postgres:p@$$w0rd!with#special@db:5432" in env_content
