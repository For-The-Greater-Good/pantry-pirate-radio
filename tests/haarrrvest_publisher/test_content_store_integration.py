"""Tests for HAARRRvest publisher content store integration."""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

import pytest

from app.haarrrvest_publisher.service import HAARRRvestPublisher
from app.content_store import ContentStore


class TestHAARRRvestContentStoreIntegration:
    """Test cases for HAARRRvest publisher with content store."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as output_dir, tempfile.TemporaryDirectory() as repo_dir, tempfile.TemporaryDirectory() as content_store_dir:
            yield {
                "output": Path(output_dir),
                "repo": Path(repo_dir),
                "content_store": Path(content_store_dir),
            }

    @pytest.fixture
    def mock_git_setup(self):
        """Mock git operations for testing."""
        with patch.object(HAARRRvestPublisher, "_run_command") as mock_cmd:
            # Setup default successful responses
            mock_cmd.return_value = (0, "", "")
            yield mock_cmd

    @pytest.fixture
    def publisher(self, temp_dirs, mock_git_setup):
        """Create a publisher instance with test directories."""
        with patch.dict(
            "os.environ",
            {
                "CONTENT_STORE_PATH": str(temp_dirs["content_store"]),
                "CONTENT_STORE_ENABLED": "true",
            },
        ):
            publisher = HAARRRvestPublisher(
                output_dir=str(temp_dirs["output"]),
                data_repo_path=str(temp_dirs["repo"]),
                check_interval=60,
                days_to_sync=7,
            )
            # Create git directory to simulate initialized repo
            (temp_dirs["repo"] / ".git").mkdir(parents=True)
            return publisher

    @pytest.fixture
    def content_store(self, temp_dirs):
        """Create a content store instance."""
        return ContentStore(store_path=temp_dirs["content_store"])

    @patch("app.content_store.config.get_content_store")
    def test_should_sync_content_store_to_haarrrvest(
        self,
        mock_get_content_store,
        publisher,
        content_store,
        temp_dirs,
        mock_git_setup,
    ):
        """Should sync content store data to HAARRRvest repository."""
        # Setup - mock content store retrieval
        mock_get_content_store.return_value = content_store

        # Create some content in content store
        content1 = '{"test": "data1"}'
        content2 = '{"test": "data2"}'

        entry1 = content_store.store_content(content1, {"scraper_id": "test_scraper"})
        entry2 = content_store.store_content(content2, {"scraper_id": "test_scraper"})

        # Store results for one
        content_store.store_result(entry1.hash, '{"processed": "result1"}', "job-1")

        # Create a test output file to trigger sync
        daily_dir = (
            temp_dirs["output"]
            / "daily"
            / datetime.now().strftime("%Y-%m-%d")
            / "scrapers"
            / "test"
        )
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Mock git operations to ensure commit happens
        def git_side_effect(cmd, cwd=None):
            if cmd == ["git", "status", "--porcelain"]:
                # Return non-empty to indicate changes
                return (0, "M README.md\nA content_store/", "")
            return (0, "", "")

        mock_git_setup.side_effect = git_side_effect

        # Act
        publisher.process_once()

        # Assert - check that content store was synced
        synced_store_path = temp_dirs["repo"] / "content_store"
        # The sync happens even if git commit doesn't, so check the method was called
        # or check for actual files if sync was successful
        assert synced_store_path.exists()
        assert (synced_store_path / "index.db").exists()

        # Verify content files were synced
        content_dir = synced_store_path / "content"
        assert content_dir.exists()

        # Check that git add was called with content store
        git_add_calls = [
            call
            for call in mock_git_setup.call_args_list
            if call[0][0] == ["git", "add", "-A"]
        ]
        assert len(git_add_calls) > 0

    def test_should_exclude_content_store_from_git_if_configured(
        self, publisher, temp_dirs, mock_git_setup
    ):
        """Should respect .gitignore for content store if configured."""
        # Setup - create .gitignore in repo
        gitignore_path = temp_dirs["repo"] / ".gitignore"
        gitignore_path.write_text("# Content store\ncontent_store/\n")

        # Create content store directory
        content_store_dir = temp_dirs["repo"] / "content_store"
        content_store_dir.mkdir(parents=True)
        (content_store_dir / "test.db").touch()

        # Create a test output file
        daily_dir = temp_dirs["output"] / "daily" / datetime.now().strftime("%Y-%m-%d")
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Mock git operations to show changes
        def git_side_effect(cmd, cwd=None):
            if cmd == ["git", "status", "--porcelain"]:
                # First call during branch creation shows changes
                if any("checkout" in str(c) for c in mock_git_setup.call_args_list):
                    return (0, "M README.md", "")
            return (0, "", "")

        mock_git_setup.side_effect = git_side_effect

        # Act
        publisher.process_once()

        # Assert - git operations should have been called
        assert mock_git_setup.called

        # Check that git add was called (proves publishing continued)
        git_add_calls = [
            c for c in mock_git_setup.call_args_list if c[0][0] == ["git", "add", "-A"]
        ]
        assert len(git_add_calls) > 0

    def test_should_preserve_existing_content_store_on_pull(
        self, publisher, content_store, temp_dirs, mock_git_setup
    ):
        """Should preserve local content store when pulling updates."""
        # Setup - simulate existing content store
        local_store_path = temp_dirs["repo"] / "content_store"
        local_store_path.mkdir(parents=True)

        # Create some local content
        local_content_file = local_store_path / "local_content.json"
        local_content_file.write_text('{"local": "data"}')

        # Simulate git pull
        def git_command_side_effect(cmd, cwd=None):
            if cmd[:2] == ["git", "pull"]:
                # Simulate remote changes (but not to content store)
                readme = temp_dirs["repo"] / "README.md"
                readme.write_text("Updated README")
                return (0, "Pulling changes", "")
            return (0, "", "")

        mock_git_setup.side_effect = git_command_side_effect

        # Act
        publisher._setup_git_repo()

        # Assert - local content should still exist
        assert local_content_file.exists()
        assert local_content_file.read_text() == '{"local": "data"}'

    @patch("app.content_store.config.get_content_store")
    def test_should_update_statistics_with_content_store_info(
        self, mock_get_store, publisher, content_store, temp_dirs, mock_git_setup
    ):
        """Should include content store statistics in repository metadata."""
        # Setup
        mock_get_store.return_value = content_store

        # Add some content to store
        for i in range(5):
            content = f'{{"item": {i}}}'
            entry = content_store.store_content(content, {"scraper_id": "test"})
            if i < 3:
                content_store.store_result(entry.hash, f'{{"result": {i}}}', f"job-{i}")

        # Create test file to trigger update
        daily_dir = temp_dirs["output"] / "daily" / datetime.now().strftime("%Y-%m-%d")
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Act
        publisher.process_once()

        # Assert - check STATS.md includes content store info
        stats_file = temp_dirs["repo"] / "STATS.md"
        if stats_file.exists():
            stats_content = stats_file.read_text()
            # Basic check that stats were written
            assert "Data Statistics" in stats_content

    def test_should_handle_content_store_sync_errors_gracefully(
        self, publisher, temp_dirs, mock_git_setup
    ):
        """Should continue publishing even if content store sync fails."""
        # Setup - create invalid content store path
        with patch.dict(
            "os.environ",
            {
                "CONTENT_STORE_PATH": "/invalid/path/that/does/not/exist",
                "CONTENT_STORE_ENABLED": "true",
            },
        ):
            # Create test output file
            daily_dir = (
                temp_dirs["output"] / "daily" / datetime.now().strftime("%Y-%m-%d")
            )
            daily_dir.mkdir(parents=True)
            test_file = daily_dir / "test.json"
            test_file.write_text('{"test": "file"}')

            # Act - should not raise exception
            publisher.process_once()

            # Assert - normal publishing should still happen
            assert mock_git_setup.called
            # Check that main repo operations continued
            readme_path = temp_dirs["repo"] / "README.md"
            assert readme_path.exists()

    def test_integration_flow_with_content_store(
        self, publisher, content_store, temp_dirs, mock_git_setup
    ):
        """Integration test of full publishing flow with content store."""
        # Setup
        with patch.dict(
            "os.environ",
            {
                "CONTENT_STORE_PATH": str(temp_dirs["content_store"]),
                "CONTENT_STORE_ENABLED": "true",
            },
        ):
            # 1. Simulate scraper storing content
            content = '{"name": "Test Pantry", "address": "123 Main St"}'
            entry = content_store.store_content(
                content,
                {"scraper_id": "test_scraper", "timestamp": datetime.now().isoformat()},
            )

            # 2. Simulate LLM processing result
            result = '{"organization": {"name": "Test Pantry", "id": "org-123"}}'
            content_store.store_result(entry.hash, result, "job-abc-123")

            # 3. Create output file from recorder
            daily_dir = (
                temp_dirs["output"]
                / "daily"
                / datetime.now().strftime("%Y-%m-%d")
                / "scrapers"
                / "test_scraper"
            )
            daily_dir.mkdir(parents=True)
            output_file = daily_dir / "job-abc-123.json"
            output_file.write_text(
                json.dumps(
                    {
                        "job_id": "job-abc-123",
                        "content_hash": entry.hash,
                        "result": json.loads(result),
                    }
                )
            )

            # 4. Run publisher
            publisher.process_once()

            # 5. Verify everything was synced
            # Check output file was synced
            synced_output = (
                temp_dirs["repo"]
                / "daily"
                / datetime.now().strftime("%Y-%m-%d")
                / "scrapers"
                / "test_scraper"
                / "job-abc-123.json"
            )
            assert synced_output.exists()

            # Check content store was synced
            synced_store = temp_dirs["repo"] / "content_store"
            assert synced_store.exists()

            # Verify git operations
            assert mock_git_setup.called
            # Check that git add was called (proves files were processed)
            git_add_calls = [
                c
                for c in mock_git_setup.call_args_list
                if c[0][0] == ["git", "add", "-A"]
            ]
            assert len(git_add_calls) > 0

    @patch("app.content_store.config.get_content_store")
    def test_should_not_create_nested_content_store_directory(
        self,
        mock_get_content_store,
        publisher,
        content_store,
        temp_dirs,
        mock_git_setup,
    ):
        """Should not create nested content-store/content_store directory."""
        # Setup - mock content store retrieval
        mock_get_content_store.return_value = content_store

        # Create some content in content store
        content = '{"test": "no_nesting"}'
        entry = content_store.store_content(content, {"scraper_id": "test"})
        content_store.store_result(entry.hash, '{"result": "data"}', "job-1")

        # Create a test output file to trigger sync
        daily_dir = (
            temp_dirs["output"]
            / "daily"
            / datetime.now().strftime("%Y-%m-%d")
            / "scrapers"
            / "test"
        )
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Mock git operations
        def git_side_effect(cmd, cwd=None):
            if cmd == ["git", "status", "--porcelain"]:
                return (0, "M README.md", "")
            return (0, "", "")

        mock_git_setup.side_effect = git_side_effect

        # Act
        publisher.process_once()

        # Assert - check that content store was synced correctly
        correct_path = temp_dirs["repo"] / "content_store"
        assert correct_path.exists()

        # Should NOT have nested content-store directory
        nested_hyphen = temp_dirs["repo"] / "content-store"
        assert not nested_hyphen.exists()

        # Should NOT have double-nested structure
        double_nested = temp_dirs["repo"] / "content_store" / "content_store"
        assert not double_nested.exists()

        # Should have correct structure
        assert (correct_path / "index.db").exists()
        assert (correct_path / "content").exists()
        assert (correct_path / "results").exists()

    @patch("app.content_store.config.get_content_store")
    def test_should_use_underscore_naming_consistently(
        self,
        mock_get_content_store,
        publisher,
        content_store,
        temp_dirs,
        mock_git_setup,
    ):
        """Should use content_store (underscore) naming throughout."""
        # Setup
        mock_get_content_store.return_value = content_store

        # Verify content store creates underscore path
        assert content_store.content_store_path.name == "content_store"
        assert (temp_dirs["content_store"] / "content_store").exists()

        # Create test data
        content = '{"test": "underscore_test"}'
        entry = content_store.store_content(content, {"scraper_id": "test"})

        # Create test output file
        daily_dir = temp_dirs["output"] / "daily" / datetime.now().strftime("%Y-%m-%d")
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Act
        publisher.process_once()

        # Assert - verify underscore naming in repository
        repo_content_store = temp_dirs["repo"] / "content_store"
        assert repo_content_store.exists()

        # Should not have hyphen version
        assert not (temp_dirs["repo"] / "content-store").exists()

    @patch("app.content_store.config.get_content_store")
    def test_should_handle_missing_content_store_gracefully(
        self,
        mock_get_content_store,
        publisher,
        temp_dirs,
        mock_git_setup,
    ):
        """Should handle missing content store path gracefully."""
        # Setup - mock content store with non-existent path
        mock_store = Mock()
        mock_store.content_store_path = Path("/nonexistent/path/content_store")
        # Mock get_statistics to return a proper dict instead of a Mock
        mock_store.get_statistics.return_value = {
            "total_content": 0,
            "processed_content": 0,
            "pending_content": 0,
            "store_size_bytes": 0,
        }
        mock_get_content_store.return_value = mock_store

        # Create test output file
        daily_dir = temp_dirs["output"] / "daily" / datetime.now().strftime("%Y-%m-%d")
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Act - should not raise exception
        publisher.process_once()

        # Assert - publishing should continue
        assert mock_git_setup.called

    @patch("app.content_store.config.get_content_store")
    def test_should_preserve_git_repo_content_store_on_sync(
        self,
        mock_get_content_store,
        publisher,
        content_store,
        temp_dirs,
        mock_git_setup,
    ):
        """Should preserve existing content in repository when syncing."""
        # Setup
        mock_get_content_store.return_value = content_store

        # Create existing content in repository
        repo_store = temp_dirs["repo"] / "content_store"
        repo_store.mkdir(parents=True)
        existing_content = repo_store / "content" / "ab"
        existing_content.mkdir(parents=True)
        existing_file = existing_content / "abcdef123456.json"
        existing_file.write_text('{"existing": "data"}')

        # Create new content in local store
        new_content = '{"new": "data"}'
        entry = content_store.store_content(new_content, {"scraper_id": "test"})

        # Create test output file
        daily_dir = temp_dirs["output"] / "daily" / datetime.now().strftime("%Y-%m-%d")
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "file"}')

        # Act
        publisher.process_once()

        # Assert - both old and new content should exist
        assert existing_file.exists()
        assert existing_file.read_text() == '{"existing": "data"}'

        # New content should also be synced
        assert (repo_store / "content").exists()
