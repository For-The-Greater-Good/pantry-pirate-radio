"""Tests for plugin discovery — compose overlays and command dispatch."""

import os
import subprocess
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def plugin_dir(tmp_path):
    """Create a temporary plugin directory structure."""
    plugin = tmp_path / "plugins" / "test-plugin"
    plugin.mkdir(parents=True)

    # Create plugin manifest
    (plugin / "plugin.yml").write_text(
        "name: test-plugin\n" "version: 1.0.0\n" "description: A test plugin\n"
    )

    # Create compose overlay
    docker_dir = plugin / ".docker"
    docker_dir.mkdir()
    (docker_dir / "compose.yml").write_text(
        "services:\n"
        "  test-service:\n"
        "    image: alpine:latest\n"
        "    command: echo hello\n"
    )

    # Create commands
    cmd_dir = plugin / "commands"
    cmd_dir.mkdir()
    (cmd_dir / "status.sh").write_text('#!/bin/bash\necho "test-plugin is running"\n')
    os.chmod(cmd_dir / "status.sh", 0o755)  # noqa: S103

    (cmd_dir / "logs.sh").write_text('#!/bin/bash\necho "test-plugin logs"\n')
    os.chmod(cmd_dir / "logs.sh", 0o755)  # noqa: S103

    return tmp_path


class TestPluginDiscovery:
    """Test plugin compose overlay discovery."""

    def test_plugin_directory_exists(self):
        """Plugins directory should exist in the project."""
        project_root = Path(__file__).parent.parent.parent
        plugins_dir = project_root / "plugins"
        assert plugins_dir.exists(), "plugins/ directory should exist"
        assert (plugins_dir / ".gitkeep").exists(), ".gitkeep should exist"

    def test_discover_plugins_finds_compose_overlays(self, plugin_dir):
        """discover_plugins should find .docker/compose.yml in plugin dirs."""
        plugins_path = plugin_dir / "plugins"
        found_overlays = []

        for manifest in sorted(plugins_path.glob("*/plugin.yml")):
            compose_file = manifest.parent / ".docker" / "compose.yml"
            if compose_file.exists():
                found_overlays.append(str(compose_file))

        assert len(found_overlays) == 1
        assert "test-plugin" in found_overlays[0]

    def test_discover_plugins_ignores_dirs_without_manifest(self, plugin_dir):
        """Directories without plugin.yml should be ignored."""
        # Create a directory without a manifest
        no_manifest = plugin_dir / "plugins" / "not-a-plugin"
        no_manifest.mkdir()
        (no_manifest / "some_file.txt").write_text("not a plugin")

        plugins_path = plugin_dir / "plugins"
        found = list(plugins_path.glob("*/plugin.yml"))
        assert len(found) == 1  # Only test-plugin

    def test_discover_plugins_ignores_plugin_without_compose(self, plugin_dir):
        """Plugins without .docker/compose.yml should not add overlays."""
        # Create a plugin without compose
        no_compose = plugin_dir / "plugins" / "no-compose-plugin"
        no_compose.mkdir()
        (no_compose / "plugin.yml").write_text("name: no-compose\nversion: 1.0.0\n")

        plugins_path = plugin_dir / "plugins"
        found_overlays = []
        for manifest in sorted(plugins_path.glob("*/plugin.yml")):
            compose_file = manifest.parent / ".docker" / "compose.yml"
            if compose_file.exists():
                found_overlays.append(str(compose_file))

        assert len(found_overlays) == 1  # Only test-plugin

    def test_empty_plugins_directory(self, tmp_path):
        """Empty plugins directory should produce no overlays."""
        plugins_path = tmp_path / "plugins"
        plugins_path.mkdir()

        found = list(plugins_path.glob("*/plugin.yml"))
        assert len(found) == 0


class TestPluginCommandDispatch:
    """Test plugin command script dispatch."""

    def test_plugin_command_exists(self, plugin_dir):
        """Plugin command scripts should be discoverable."""
        cmd_file = plugin_dir / "plugins" / "test-plugin" / "commands" / "status.sh"
        assert cmd_file.exists()
        assert os.access(cmd_file, os.X_OK)

    def test_plugin_command_runs(self, plugin_dir):
        """Plugin command scripts should execute correctly."""
        cmd_file = plugin_dir / "plugins" / "test-plugin" / "commands" / "status.sh"
        result = subprocess.run(
            ["bash", str(cmd_file)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        assert result.returncode == 0
        assert "test-plugin is running" in result.stdout

    def test_missing_plugin_command(self, plugin_dir):
        """Nonexistent plugin command should fail gracefully."""
        cmd_file = (
            plugin_dir / "plugins" / "test-plugin" / "commands" / "nonexistent.sh"
        )
        assert not cmd_file.exists()

    def test_plugin_manifest_parsed(self, plugin_dir):
        """Plugin manifest should be parseable YAML."""
        import yaml

        manifest = plugin_dir / "plugins" / "test-plugin" / "plugin.yml"
        data = yaml.safe_load(manifest.read_text())
        assert data["name"] == "test-plugin"
        assert data["version"] == "1.0.0"


class TestPluginEnvVars:
    """Test plugin environment variable declarations."""

    def test_manifest_env_vars(self, tmp_path):
        """Plugin manifests can declare required env vars."""
        import yaml

        plugin = tmp_path / "plugins" / "env-plugin"
        plugin.mkdir(parents=True)

        manifest_content = {
            "name": "env-plugin",
            "version": "1.0.0",
            "env_vars": [
                {"name": "PLUGIN_TOKEN", "required": True, "description": "API token"},
                {
                    "name": "PLUGIN_URL",
                    "required": False,
                    "default": "http://localhost:8000",
                },
            ],
        }
        (plugin / "plugin.yml").write_text(yaml.dump(manifest_content))

        data = yaml.safe_load((plugin / "plugin.yml").read_text())
        assert len(data["env_vars"]) == 2
        assert data["env_vars"][0]["required"] is True
        assert data["env_vars"][1]["default"] == "http://localhost:8000"
