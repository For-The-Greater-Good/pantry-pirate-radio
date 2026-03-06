"""Tests for bouy deploy and scraper --aws commands.

These tests verify the deploy and scraper --aws command argument parsing,
help output, and error handling without requiring actual AWS credentials
or Docker.
"""

import os
import stat
import subprocess
from pathlib import Path

import pytest

# Skip all tests in this file when running in Docker
pytestmark = pytest.mark.skipif(
    os.path.exists("/.dockerenv") or os.environ.get("RUNNING_IN_DOCKER"),
    reason="Bouy tests cannot run inside Docker containers",
)


class TestBouyDeployHelp:
    """Test deploy command help and usage output."""

    @pytest.fixture
    def bouy_path(self):
        """Get the path to the bouy script."""
        if Path("/app/bouy").exists():
            return "/app/bouy"
        else:
            return "./bouy"

    def test_help_includes_deploy_command(self, bouy_path):
        """Help output should include deploy command."""
        result = subprocess.run([bouy_path, "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "deploy" in result.stdout

    def test_help_includes_deploy_options(self, bouy_path):
        """Help output should include deploy options."""
        result = subprocess.run([bouy_path, "--help"], capture_output=True, text=True)
        assert "--images-only" in result.stdout
        assert "--infra-only" in result.stdout
        assert "--diff" in result.stdout
        assert "--destroy" in result.stdout


class TestBouyDeployArgParsing:
    """Test deploy command argument parsing and validation."""

    @pytest.fixture
    def bouy_path(self):
        """Get the path to the bouy script."""
        if Path("/app/bouy").exists():
            return "/app/bouy"
        else:
            return "./bouy"

    @pytest.fixture
    def mock_aws_path(self, tmp_path):
        """Create a mock aws CLI that fails fast on sts calls."""
        mock_bin = tmp_path / "mock_bin"
        mock_bin.mkdir()
        mock_aws = mock_bin / "aws"
        mock_aws.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "sts" ]; then\n'
            '  echo "Unable to locate credentials" >&2\n'
            "  exit 255\n"
            "fi\n"
            'echo "mock-aws"\n'
        )
        mock_aws.chmod(mock_aws.stat().st_mode | stat.S_IEXEC)
        return str(mock_bin)

    def test_deploy_unknown_option_fails(self, bouy_path):
        """Deploy with unknown option should fail with helpful error."""
        result = subprocess.run(
            [bouy_path, "deploy", "dev", "--bad-option"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode != 0

    def test_deploy_requires_aws_cli(self, bouy_path, tmp_path):
        """Deploy should fail if aws CLI is not found."""
        env = os.environ.copy()
        # Create a minimal PATH that has basic utils but not aws
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        for cmd in ["dirname", "basename", "xargs", "sed", "grep", "cat", "id", "tput"]:
            src = f"/usr/bin/{cmd}"
            if os.path.exists(src):
                (fake_bin / cmd).symlink_to(src)
        env["PATH"] = str(fake_bin)

        result = subprocess.run(
            [bouy_path, "deploy", "dev"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "AWS CLI not found" in combined or "aws" in combined.lower()

    def test_deploy_default_env_is_dev(self, bouy_path, mock_aws_path):
        """Deploy without env argument should default to dev."""
        env = os.environ.copy()
        # Prepend mock aws to PATH so it's found first
        env["PATH"] = mock_aws_path + ":" + env.get("PATH", "")

        result = subprocess.run(
            [bouy_path, "deploy"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        # It will fail (mock aws returns credential error), but output should mention "dev"
        combined = result.stdout + result.stderr
        assert "dev" in combined

    def test_deploy_accepts_environment_argument(self, bouy_path, mock_aws_path):
        """Deploy should accept environment name as argument."""
        env = os.environ.copy()
        env["PATH"] = mock_aws_path + ":" + env.get("PATH", "")

        result = subprocess.run(
            [bouy_path, "deploy", "staging"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        combined = result.stdout + result.stderr
        assert "staging" in combined


class TestBouyScraperAwsHelp:
    """Test scraper --aws help and usage output."""

    @pytest.fixture
    def bouy_path(self):
        """Get the path to the bouy script."""
        if Path("/app/bouy").exists():
            return "/app/bouy"
        else:
            return "./bouy"

    def test_help_includes_scraper_aws(self, bouy_path):
        """Help output should include scraper --aws options."""
        result = subprocess.run([bouy_path, "--help"], capture_output=True, text=True)
        assert result.returncode == 0
        assert "--aws" in result.stdout

    def test_help_includes_scraper_aws_subcommands(self, bouy_path):
        """Help output should include scraper --aws subcommand options."""
        result = subprocess.run([bouy_path, "--help"], capture_output=True, text=True)
        assert "--status" in result.stdout
        assert "--logs" in result.stdout
        assert "Step Functions" in result.stdout


class TestBouyScraperAwsArgParsing:
    """Test scraper --aws command argument parsing and validation."""

    @pytest.fixture
    def bouy_path(self):
        """Get the path to the bouy script."""
        if Path("/app/bouy").exists():
            return "/app/bouy"
        else:
            return "./bouy"

    @pytest.fixture
    def mock_aws_path(self, tmp_path):
        """Create a mock aws CLI that fails on sts calls."""
        mock_bin = tmp_path / "mock_bin"
        mock_bin.mkdir()
        mock_aws = mock_bin / "aws"
        mock_aws.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "sts" ]; then\n'
            '  echo "Unable to locate credentials" >&2\n'
            "  exit 255\n"
            "fi\n"
            'echo "mock-aws"\n'
        )
        mock_aws.chmod(mock_aws.stat().st_mode | stat.S_IEXEC)
        return str(mock_bin)

    def test_scraper_aws_requires_aws_cli(self, bouy_path, tmp_path):
        """Scraper --aws should fail if aws CLI is not found."""
        env = os.environ.copy()
        fake_bin = tmp_path / "bin"
        fake_bin.mkdir()
        for cmd in ["dirname", "basename", "xargs", "sed", "grep", "cat", "id", "tput"]:
            src = f"/usr/bin/{cmd}"
            if os.path.exists(src):
                (fake_bin / cmd).symlink_to(src)
        env["PATH"] = str(fake_bin)

        result = subprocess.run(
            [bouy_path, "scraper", "--aws", "test_scraper"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "AWS CLI not found" in combined or "aws" in combined.lower()

    def test_scraper_aws_requires_credentials(self, bouy_path, mock_aws_path):
        """Scraper --aws should fail with mock aws that rejects credentials."""
        env = os.environ.copy()
        env["PATH"] = mock_aws_path + ":" + env.get("PATH", "")

        result = subprocess.run(
            [bouy_path, "scraper", "--aws", "test_scraper"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "credentials" in combined.lower()

    def test_scraper_aws_no_name_shows_usage(self, bouy_path, tmp_path):
        """Scraper --aws without a name should show usage and fail."""
        mock_bin = tmp_path / "mock_bin"
        mock_bin.mkdir()
        mock_aws = mock_bin / "aws"
        # Mock aws that passes sts but returns empty for stepfunctions
        mock_aws.write_text(
            "#!/bin/bash\n"
            'if [ "$1" = "sts" ]; then\n'
            '  echo \'{"Account": "123456789", "Arn": "arn:aws:iam::root"}\'\n'
            "  exit 0\n"
            "fi\n"
            'if [ "$1" = "configure" ]; then\n'
            '  echo "us-east-1"\n'
            "  exit 0\n"
            "fi\n"
            'if [ "$1" = "stepfunctions" ]; then\n'
            '  if [ "$2" = "list-state-machines" ]; then\n'
            '    echo "None"\n'
            "    exit 0\n"
            "  fi\n"
            "fi\n"
            'echo "mock-aws"\n'
        )
        mock_aws.chmod(mock_aws.stat().st_mode | stat.S_IEXEC)
        env = os.environ.copy()
        env["PATH"] = str(mock_bin) + ":" + env.get("PATH", "")

        result = subprocess.run(
            [bouy_path, "scraper", "--aws"],
            capture_output=True,
            text=True,
            env=env,
            timeout=10,
        )
        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "No scraper specified" in combined or "Usage" in combined
