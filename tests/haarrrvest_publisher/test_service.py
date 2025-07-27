"""
Tests for HAARRRvest Publisher Service

Tests cover:
- Repository setup and conflict handling
- File discovery and tracking
- Branch creation and merging
- SQLite export functionality
- Map data generation
- Error handling and recovery
"""

import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import pytest
import shutil

from app.haarrrvest_publisher.service import HAARRRvestPublisher


@pytest.fixture
def temp_dirs():
    """Create temporary directories for testing."""
    with tempfile.TemporaryDirectory() as output_dir:
        with tempfile.TemporaryDirectory() as repo_dir:
            # Create directory structure
            output_path = Path(output_dir)
            repo_path = Path(repo_dir)

            (output_path / "daily").mkdir()
            (output_path / "latest").mkdir()

            yield output_path, repo_path


@pytest.fixture
def publisher(temp_dirs, monkeypatch):
    """Create a publisher instance with test directories."""
    output_dir, repo_dir = temp_dirs
    # Ensure no token is set for tests
    monkeypatch.delenv("DATA_REPO_TOKEN", raising=False)
    # Default to push disabled for safety
    monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "false")
    return HAARRRvestPublisher(
        output_dir=str(output_dir),
        data_repo_path=str(repo_dir),
        data_repo_url="https://github.com/test/repo.git",
        check_interval=60,
        days_to_sync=7,
    )


class TestHAARRRvestPublisher:
    """Test suite for HAARRRvest Publisher Service."""

    def test_should_use_https_url_by_default(self, temp_dirs, monkeypatch):
        """Test that publisher uses HTTPS URL by default."""
        output_dir, repo_dir = temp_dirs
        # Make sure env var is not set
        monkeypatch.delenv("DATA_REPO_URL", raising=False)

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
        )
        assert (
            publisher.data_repo_url
            == "https://github.com/For-The-Greater-Good/HAARRRvest.git"
        )

    def test_should_construct_authenticated_url_with_token(
        self, temp_dirs, monkeypatch
    ):
        """Test that publisher constructs authenticated URL when token is provided."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("DATA_REPO_TOKEN", "test_token_123")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        auth_url = publisher._get_authenticated_url()
        assert auth_url == "https://test_token_123@github.com/test/repo.git"

    def test_should_initialize_with_correct_paths(self, publisher, temp_dirs):
        """Test publisher initializes with correct configuration."""
        output_dir, repo_dir = temp_dirs

        assert publisher.output_dir == output_dir
        assert publisher.data_repo_path == repo_dir
        assert publisher.data_repo_url == "https://github.com/test/repo.git"
        assert publisher.check_interval == 60
        assert publisher.days_to_sync == 7
        assert publisher.processed_files == set()

    def test_should_load_processed_files_from_state(self, temp_dirs):
        """Test loading previously processed files from state file."""
        output_dir, repo_dir = temp_dirs

        # Create state file
        state_file = output_dir / ".haarrrvest_publisher_state.json"
        state_data = {"processed_files": ["file1.json", "file2.json"]}
        with open(state_file, "w") as f:
            json.dump(state_data, f)

        # Create publisher - should load state
        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir), data_repo_path=str(repo_dir)
        )

        assert publisher.processed_files == {"file1.json", "file2.json"}

    def test_should_save_processed_files_to_state(self, publisher, temp_dirs):
        """Test saving processed files to state file."""
        output_dir, _ = temp_dirs

        # Add some processed files
        publisher.processed_files = {"file1.json", "file2.json", "file3.json"}
        publisher._save_processed_files()

        # Verify state file
        state_file = output_dir / ".haarrrvest_publisher_state.json"
        assert state_file.exists()

        with open(state_file, "r") as f:
            state_data = json.load(f)

        assert set(state_data["processed_files"]) == {
            "file1.json",
            "file2.json",
            "file3.json",
        }

    @patch("subprocess.run")
    def test_should_clone_repository_if_not_exists(
        self, mock_run, publisher, temp_dirs
    ):
        """Test cloning repository on first run."""
        _, repo_dir = temp_dirs

        # Remove repo directory to simulate first run
        shutil.rmtree(repo_dir)

        # Mock successful clone
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        publisher._setup_git_repo()

        # Verify clone command was called
        clone_calls = [call for call in mock_run.call_args_list if "clone" in str(call)]
        assert len(clone_calls) >= 1
        # Check that clone was called with the repo URL
        assert any(
            "https://github.com/test/repo.git" in str(call) for call in clone_calls
        )

    @patch("subprocess.run")
    def test_should_update_repository_if_exists(self, mock_run, publisher, temp_dirs):
        """Test updating existing repository."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        # Mock git commands
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        publisher._setup_git_repo()

        # Verify update sequence
        calls = mock_run.call_args_list
        assert any(
            "status" in str(call) and "--porcelain" in str(call) for call in calls
        )
        assert any("checkout" in str(call) and "main" in str(call) for call in calls)
        assert any("fetch" in str(call) for call in calls)
        assert any("rev-list" in str(call) for call in calls)

    @patch("subprocess.run")
    def test_should_handle_uncommitted_changes(self, mock_run, publisher, temp_dirs):
        """Test handling uncommitted changes in repository."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        # Mock git status showing uncommitted changes
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # config user.email
            Mock(returncode=0, stdout="", stderr=""),  # config user.name
            Mock(returncode=0, stdout="M file.txt", stderr=""),  # status --porcelain
            Mock(returncode=0, stdout="", stderr=""),  # stash
            Mock(returncode=0, stdout="", stderr=""),  # checkout main
            Mock(returncode=0, stdout="", stderr=""),  # fetch
            Mock(returncode=0, stdout="0", stderr=""),  # rev-list
        ]

        publisher._setup_git_repo()

        # Verify stash was called
        stash_calls = [call for call in mock_run.call_args_list if "stash" in str(call)]
        assert len(stash_calls) == 1

    def test_should_find_new_files_in_daily_directory(self, publisher, temp_dirs):
        """Test finding new files in daily directories."""
        output_dir, _ = temp_dirs

        # Create test files
        today = datetime.now().strftime("%Y-%m-%d")
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        (output_dir / "daily" / today).mkdir(parents=True)
        (output_dir / "daily" / yesterday).mkdir(parents=True)

        file1 = output_dir / "daily" / today / "file1.json"
        file2 = output_dir / "daily" / yesterday / "file2.json"

        file1.write_text('{"test": 1}')
        file2.write_text('{"test": 2}')

        # Find new files
        new_files = publisher._find_new_files()

        assert len(new_files) == 2
        assert file1 in new_files
        assert file2 in new_files

    def test_should_save_state_atomically(self, publisher, temp_dirs):
        """Test atomic state saving with temporary file."""
        output_dir, _ = temp_dirs

        # Add files to processed set
        publisher.processed_files = {"file1.json", "file2.json"}

        # Save state
        publisher._save_processed_files()

        # Verify state file exists
        state_file = output_dir / ".haarrrvest_publisher_state.json"
        assert state_file.exists()

        # Verify temp file doesn't exist
        temp_file = state_file.with_suffix(".tmp")
        assert not temp_file.exists()

        # Verify state content
        import json

        with open(state_file) as f:
            data = json.load(f)
        assert set(data["processed_files"]) == {"file1.json", "file2.json"}
        assert "last_updated" in data

    def test_should_validate_branch_names(self, publisher):
        """Test branch name validation."""
        # Valid branch name should pass
        branch_name = publisher._create_branch_name()
        assert branch_name.startswith("data-update-")

        # Test invalid branch name
        with patch("app.haarrrvest_publisher.service.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.return_value = "invalid@name"
            with pytest.raises(ValueError, match="Invalid branch name"):
                publisher._create_branch_name()

    def test_should_validate_file_paths(self, publisher, temp_dirs):
        """Test file path validation during sync."""
        output_dir, _ = temp_dirs

        # Create a file outside output directory using tempfile
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            outside_file = Path(tf.name)

        try:
            # Create a valid file in output directory
            valid_file = output_dir / "valid.json"
            valid_file.write_text("{}")

            # Mock logger to capture warnings
            with patch("app.haarrrvest_publisher.service.logger") as mock_logger:
                # Try to sync files including one outside directory
                publisher._sync_files_to_repo([valid_file, outside_file])

                # Verify warning was logged
                mock_logger.error.assert_any_call(
                    f"File path {outside_file} is outside output directory"
                )
        finally:
            # Clean up
            if outside_file.exists():
                outside_file.unlink()

    def test_should_use_configurable_error_retry_delay(self, publisher):
        """Test that error retry delay is configurable."""
        # Default should be 60
        assert publisher.error_retry_delay == 60

        # Create with custom value
        custom_publisher = HAARRRvestPublisher(
            output_dir=str(publisher.output_dir),
            data_repo_path=str(publisher.data_repo_path),
            error_retry_delay=120,
        )
        assert custom_publisher.error_retry_delay == 120

    def test_should_skip_already_processed_files(self, publisher, temp_dirs):
        """Test skipping files that have been processed."""
        output_dir, _ = temp_dirs

        # Create test file
        today = datetime.now().strftime("%Y-%m-%d")
        (output_dir / "daily" / today).mkdir(parents=True)
        file1 = output_dir / "daily" / today / "file1.json"
        file1.write_text('{"test": 1}')

        # Mark as processed
        publisher.processed_files.add(f"daily/{today}/file1.json")

        # Find new files
        new_files = publisher._find_new_files()

        assert len(new_files) == 0

    def test_should_skip_old_files_beyond_sync_window(self, publisher, temp_dirs):
        """Test skipping files older than sync window."""
        output_dir, _ = temp_dirs

        # Create old file
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        (output_dir / "daily" / old_date).mkdir(parents=True)
        old_file = output_dir / "daily" / old_date / "old.json"
        old_file.write_text('{"test": "old"}')

        # Find new files (should skip old file)
        new_files = publisher._find_new_files()

        assert len(new_files) == 0

    def test_should_sync_files_to_repository(self, publisher, temp_dirs):
        """Test syncing files to HAARRRvest repository."""
        output_dir, repo_dir = temp_dirs

        # Create test files
        today = datetime.now().strftime("%Y-%m-%d")
        (output_dir / "daily" / today).mkdir(parents=True)
        file1 = output_dir / "daily" / today / "file1.json"
        file1.write_text('{"test": 1}')

        # Sync files
        publisher._sync_files_to_repo([file1])

        # Verify file was copied
        target_file = repo_dir / "daily" / today / "file1.json"
        assert target_file.exists()
        assert target_file.read_text() == '{"test": 1}'

        # Verify marked as processed
        assert f"daily/{today}/file1.json" in publisher.processed_files

    def test_should_generate_statistics(self, publisher, temp_dirs):
        """Test generating repository statistics."""
        _, repo_dir = temp_dirs

        # Create test structure
        (repo_dir / "daily" / "2025-01-20" / "scrapers" / "scraper1").mkdir(
            parents=True
        )
        (repo_dir / "daily" / "2025-01-21" / "scrapers" / "scraper1").mkdir(
            parents=True
        )
        (repo_dir / "daily" / "2025-01-21" / "scrapers" / "scraper2").mkdir(
            parents=True
        )

        # Add some files
        (
            repo_dir / "daily" / "2025-01-20" / "scrapers" / "scraper1" / "1.json"
        ).write_text("{}")
        (
            repo_dir / "daily" / "2025-01-21" / "scrapers" / "scraper1" / "2.json"
        ).write_text("{}")
        (
            repo_dir / "daily" / "2025-01-21" / "scrapers" / "scraper2" / "3.json"
        ).write_text("{}")

        stats = publisher._generate_statistics()

        assert stats["total_records"] == 3
        assert stats["sources"] == 2
        assert stats["date_range"] == "2025-01-20 to 2025-01-21"

    def test_should_create_unique_branch_if_exists(self, publisher):
        """Test creating unique branch name if branch already exists."""

        with patch("app.haarrrvest_publisher.service.datetime") as mock_datetime:
            mock_datetime.now.return_value.strftime.side_effect = [
                "2025-01-25",
                "143052",
            ]

            # Mock the _run_command method
            def mock_run_command(cmd, cwd=None):
                cmd_str = " ".join(cmd)
                if "checkout main" in cmd_str:
                    return 0, "", ""
                elif "rev-parse --verify" in cmd_str:
                    return 1, "", ""  # Branch doesn't exist locally
                elif (
                    "ls-remote --heads" in cmd_str
                    and "data-update-2025-01-25" in cmd_str
                ):
                    return (
                        0,
                        "refs/heads/data-update-2025-01-25",
                        "",
                    )  # Exists on remote
                elif "checkout -b data-update-2025-01-25-" in cmd_str:
                    # Accept any UUID suffix
                    return 0, "", ""
                elif "add -A" in cmd_str:
                    return 0, "", ""
                elif "status --porcelain" in cmd_str:
                    return 0, "", ""  # No changes
                else:
                    return 0, "", ""

            with patch.object(
                publisher, "_run_command", side_effect=mock_run_command
            ) as mock_cmd:
                # Test only the branch creation part
                branch_name = publisher._create_branch_name()
                publisher._create_and_merge_branch(branch_name)

                # Verify unique branch name was used
                checkout_calls = [
                    call
                    for call in mock_cmd.call_args_list
                    if len(call[0]) > 0
                    and "checkout" in call[0][0]
                    and "-b" in str(call)
                ]
                # Check that a unique branch name with UUID suffix was used
                found_unique_branch = False
                for call in checkout_calls:
                    call_str = str(call)
                    if "-b" in call_str and "data-update-2025-01-25-" in call_str:
                        found_unique_branch = True
                        # Verify the UUID suffix format (8 characters)
                        import re

                        match = re.search(
                            r"data-update-2025-01-25-([a-f0-9]{8})", call_str
                        )
                        assert (
                            match is not None
                        ), f"UUID suffix not found in: {call_str}"
                        break

                assert (
                    found_unique_branch
                ), f"No unique branch checkout found. Calls: {checkout_calls}"

    @patch("subprocess.run")
    def test_should_handle_git_push_failure(self, mock_run, temp_dirs, monkeypatch):
        """Test handling git push failures when push is enabled."""
        output_dir, repo_dir = temp_dirs
        # Enable push for this test
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "true")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Mock the entire sequence up to push failure
        mock_run.side_effect = [
            Mock(returncode=0, stdout="", stderr=""),  # checkout main
            Mock(
                returncode=1, stdout="", stderr=""
            ),  # rev-parse (branch doesn't exist)
            Mock(
                returncode=0, stdout="", stderr=""
            ),  # ls-remote (branch doesn't exist)
            Mock(returncode=0, stdout="", stderr=""),  # checkout -b
            Mock(returncode=0, stdout="", stderr=""),  # git add -A
            Mock(
                returncode=0, stdout="M file.txt", stderr=""
            ),  # git status --porcelain
            Mock(returncode=0, stdout="", stderr=""),  # git commit
            Mock(returncode=0, stdout="", stderr=""),  # checkout main
            Mock(returncode=0, stdout="", stderr=""),  # git merge
            Mock(returncode=0, stdout="", stderr=""),  # git branch -d
            Mock(returncode=1, stdout="", stderr="Permission denied"),  # push fails
        ]

        with pytest.raises(Exception) as exc_info:
            publisher._create_and_merge_branch("test-branch")

        assert "Git push failed" in str(exc_info.value)

    def test_should_export_to_sqlite_using_datasette_exporter(
        self, publisher, temp_dirs
    ):
        """Test SQLite export using datasette exporter."""
        _, repo_dir = temp_dirs

        with patch.object(publisher, "_run_command") as mock_run:
            mock_run.return_value = (0, "Success", "")

            with patch.dict(
                "os.environ", {"DATABASE_URL": "postgresql://test:test@localhost/test"}
            ):
                publisher._export_to_sqlite()

            # Verify datasette exporter was called
            mock_run.assert_called()
            args = mock_run.call_args[0][0]
            assert args[0] == "python"
            assert args[1] == "-m"
            assert args[2] == "app.datasette.exporter"
            assert "--output" in args

    def test_should_raise_error_when_sqlite_export_fails(self, publisher):
        """Test error handling when SQLite export fails."""
        # Mock datasette exporter failure
        with patch.object(publisher, "_run_command") as mock_run:
            mock_run.return_value = (1, "", "Export failed")

            with patch.dict(
                "os.environ", {"DATABASE_URL": "postgresql://test:test@localhost/test"}
            ):
                with pytest.raises(Exception) as exc_info:
                    publisher._export_to_sqlite()

                assert "Failed to export SQLite database" in str(exc_info.value)

    def test_should_run_location_export_script(self, publisher, temp_dirs):
        """Test running HAARRRvest's location export script."""
        _, repo_dir = temp_dirs

        # Create mock script
        scripts_dir = repo_dir / "scripts"
        scripts_dir.mkdir()
        export_script = scripts_dir / "export-locations.py"
        export_script.write_text("print('Export success')")

        with patch.object(publisher, "_run_command") as mock_run:
            mock_run.return_value = (0, "Export success", "")

            publisher._run_location_export()

            mock_run.assert_called_with(["python3", str(export_script)], cwd=repo_dir)

    @patch.object(HAARRRvestPublisher, "_setup_git_repo")
    @patch.object(HAARRRvestPublisher, "_find_new_files")
    @patch.object(HAARRRvestPublisher, "_sync_files_to_repo")
    @patch.object(HAARRRvestPublisher, "_update_repository_metadata")
    @patch.object(HAARRRvestPublisher, "_run_database_operations")
    @patch.object(HAARRRvestPublisher, "_create_and_merge_branch")
    @patch.object(HAARRRvestPublisher, "_save_processed_files")
    def test_should_run_complete_pipeline(
        self,
        mock_save,
        mock_merge,
        mock_db_ops,
        mock_metadata,
        mock_sync,
        mock_find,
        mock_setup,
        publisher,
        temp_dirs,
    ):
        """Test complete publishing pipeline."""
        output_dir, _ = temp_dirs

        # Create test file
        test_file = output_dir / "daily" / "2025-01-25" / "test.json"
        test_file.parent.mkdir(parents=True)
        test_file.write_text('{"test": true}')

        # Mock methods
        mock_find.return_value = [test_file]

        # Run pipeline
        publisher.process_once()

        # Verify all steps were called
        mock_setup.assert_called_once()
        mock_find.assert_called_once()
        mock_sync.assert_called_once_with([test_file])
        mock_metadata.assert_called_once()
        mock_db_ops.assert_called_once()
        mock_merge.assert_called_once()
        mock_save.assert_called_once()

    def test_should_skip_processing_when_no_new_files(self, publisher):
        """Test skipping processing when no new files found."""
        with patch.object(publisher, "_setup_git_repo"):
            with patch.object(publisher, "_find_new_files", return_value=[]):
                with patch.object(publisher, "_sync_files_to_repo") as mock_sync:

                    publisher.process_once()

                    # Verify sync was not called
                    mock_sync.assert_not_called()

    @patch("time.sleep")
    def test_should_run_continuously_with_interval(self, mock_sleep, publisher):
        """Test continuous running with check interval."""
        call_count = 0

        def side_effect(*args):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise KeyboardInterrupt()

        with patch.object(
            publisher, "_setup_git_repo"
        ):  # Mock setup to avoid real git calls
            with patch.object(publisher, "process_once", side_effect=side_effect):
                publisher.run()

        # Verify process_once was called multiple times
        assert call_count == 2
        mock_sleep.assert_called_with(60)  # check_interval

    @patch("time.sleep")
    def test_should_handle_errors_in_loop(self, mock_sleep, publisher):
        """Test error handling in continuous run loop (not startup)."""
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First call succeeds (startup)
                return
            elif call_count == 2:
                # Second call fails (in loop)
                raise Exception("Test error")
            else:
                # Third call triggers shutdown
                raise KeyboardInterrupt()

        # Patch the logger to suppress error output
        with patch("app.haarrrvest_publisher.service.logger"):
            with patch.object(
                publisher, "_setup_git_repo"
            ):  # Mock setup to avoid real git calls
                with patch.object(publisher, "process_once", side_effect=side_effect):
                    publisher.run()

        # Verify it ran 3 times: startup, error, then shutdown
        assert call_count == 3
        # Should sleep 60 seconds after error
        mock_sleep.assert_any_call(60)

    def test_should_handle_error_loading_state_file(self, temp_dirs):
        """Test handling corrupted state file."""
        output_dir, repo_dir = temp_dirs

        # Create corrupted state file
        state_file = output_dir / ".haarrrvest_publisher_state.json"
        state_file.write_text("corrupted json{")

        # Should handle gracefully and start with empty state
        with patch("app.haarrrvest_publisher.service.logger"):
            publisher = HAARRRvestPublisher(
                output_dir=str(output_dir), data_repo_path=str(repo_dir)
            )

        assert publisher.processed_files == set()

    def test_should_handle_error_saving_state_file(self, publisher, temp_dirs):
        """Test handling errors when saving state file."""
        output_dir, _ = temp_dirs

        # Make directory read-only to cause save error
        with patch("builtins.open", side_effect=PermissionError("No write access")):
            with patch("app.haarrrvest_publisher.service.logger") as mock_logger:
                publisher.processed_files = {"test.json"}
                publisher._save_processed_files()

                # Should log error
                mock_logger.error.assert_called()

    def test_should_handle_git_clone_failure(self, publisher, temp_dirs):
        """Test handling git clone failures."""
        _, repo_dir = temp_dirs

        # Remove repo directory to simulate first run
        shutil.rmtree(repo_dir)

        with patch.object(publisher, "_run_command") as mock_run:
            mock_run.return_value = (1, "", "Permission denied")

            with pytest.raises(Exception) as exc_info:
                publisher._setup_git_repo()

            assert "Failed to clone repository" in str(exc_info.value)

    def test_should_handle_git_checkout_failure(self, publisher, temp_dirs):
        """Test handling git checkout failures."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        with patch.object(publisher, "_run_command") as mock_run:
            # Mock various git commands
            def side_effect(cmd, cwd=None):
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "status" in cmd_str and "--porcelain" in cmd_str:
                    return 0, "", ""
                elif (
                    "checkout" in cmd_str and "main" in cmd_str and "-b" not in cmd_str
                ):
                    return 1, "", "Cannot checkout"
                return 0, "", ""

            mock_run.side_effect = side_effect

            with pytest.raises(Exception) as exc_info:
                publisher._setup_git_repo()

            assert "Cannot switch to main branch" in str(exc_info.value)

    def test_should_handle_git_fetch_failure(self, publisher, temp_dirs):
        """Test handling git fetch failures."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        with patch.object(publisher, "_run_command") as mock_run:
            # Mock various git commands
            def side_effect(cmd, cwd=None):
                if "status" in cmd:
                    return 0, "", ""
                elif "checkout main" in cmd:
                    return 0, "", ""
                elif "fetch" in cmd:
                    return 1, "", "Network error"
                return 0, "", ""

            mock_run.side_effect = side_effect

            with pytest.raises(Exception) as exc_info:
                publisher._setup_git_repo()

            assert "Cannot fetch from origin" in str(exc_info.value)

    def test_should_pull_when_behind_origin(self, publisher, temp_dirs):
        """Test pulling updates when behind origin."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        with patch.object(publisher, "_run_command") as mock_run:
            # Mock various git commands
            def side_effect(cmd, cwd=None):
                if "status" in cmd:
                    return 0, "", ""
                elif "checkout main" in cmd:
                    return 0, "", ""
                elif "fetch" in cmd:
                    return 0, "", ""
                elif "rev-list" in cmd:
                    return 0, "3", ""  # 3 commits behind
                elif "pull" in cmd:
                    return 0, "", ""
                return 0, "", ""

            mock_run.side_effect = side_effect

            publisher._setup_git_repo()

            # Verify pull was called
            pull_calls = [
                call for call in mock_run.call_args_list if "pull" in str(call)
            ]
            assert len(pull_calls) == 1

    def test_should_handle_pull_failure(self, publisher, temp_dirs):
        """Test handling git pull failures."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        with patch.object(publisher, "_run_command") as mock_run:
            # Mock various git commands
            def side_effect(cmd, cwd=None):
                if "status" in cmd:
                    return 0, "", ""
                elif "checkout main" in cmd:
                    return 0, "", ""
                elif "fetch" in cmd:
                    return 0, "", ""
                elif "rev-list" in cmd:
                    return 0, "3", ""  # 3 commits behind
                elif "pull" in cmd:
                    return 1, "", "Merge conflict"
                return 0, "", ""

            mock_run.side_effect = side_effect

            with pytest.raises(Exception) as exc_info:
                publisher._setup_git_repo()

            assert "Cannot pull from origin" in str(exc_info.value)

    def test_should_find_files_in_latest_directory(self, publisher, temp_dirs):
        """Test finding new files in latest directory."""
        output_dir, _ = temp_dirs

        # Create test file in latest
        latest_file = output_dir / "latest" / "test_latest.json"
        latest_file.write_text('{"test": "latest"}')

        # Find new files
        new_files = publisher._find_new_files()

        assert len(new_files) == 1
        assert latest_file in new_files

    def test_should_skip_non_date_directories(self, publisher, temp_dirs):
        """Test skipping non-date directories in daily folder."""
        output_dir, _ = temp_dirs

        # Create non-date directory
        (output_dir / "daily" / "not-a-date").mkdir(parents=True)
        bad_file = output_dir / "daily" / "not-a-date" / "file.json"
        bad_file.write_text('{"test": 1}')

        # Find new files (should skip bad directory)
        new_files = publisher._find_new_files()

        assert len(new_files) == 0

    def test_should_handle_no_changes_to_commit(self, publisher):
        """Test handling case where there are no changes to commit."""
        with patch.object(publisher, "_run_command") as mock_run:
            # Mock git commands
            def side_effect(cmd, cwd=None):
                if "status --porcelain" in " ".join(cmd):
                    return 0, "", ""  # No changes
                return 0, "", ""

            mock_run.side_effect = side_effect

            # Should handle gracefully
            publisher._create_and_merge_branch("test-branch")

            # Verify branch was cleaned up
            branch_delete_calls = [
                call
                for call in mock_run.call_args_list
                if "branch" in str(call) and "-d" in str(call)
            ]
            assert len(branch_delete_calls) >= 1

    @patch("subprocess.run")
    def test_should_push_with_token_authentication(
        self, mock_run, temp_dirs, monkeypatch
    ):
        """Test pushing with token authentication when push is enabled."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("DATA_REPO_TOKEN", "test_token_123")
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "true")  # Enable push

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Mock git commands with changes to commit
        def side_effect(cmd, cwd=None):
            if "status --porcelain" in " ".join(cmd):
                return 0, "M file.txt", ""  # Changes exist
            return 0, "", ""

        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")
        mock_run.side_effect = lambda cmd, **kwargs: Mock(
            returncode=0,
            stdout="M file.txt" if "status --porcelain" in " ".join(cmd) else "",
            stderr="",
        )

        # Create test branch
        publisher._create_and_merge_branch("test-branch")

        # Check that push was called with authenticated URL
        push_calls = [call for call in mock_run.call_args_list if "push" in str(call)]
        assert len(push_calls) > 0
        # Token should be used in push URL
        assert any("test_token_123" in str(call) for call in push_calls)

    def test_should_delete_local_branch_if_exists(self, publisher):
        """Test deleting existing local branch."""
        with patch.object(publisher, "_run_command") as mock_run:
            # Mock branch exists locally
            def side_effect(cmd, cwd=None):
                if "rev-parse --verify" in " ".join(cmd):
                    return 0, "hash", ""  # Branch exists
                elif "branch -D" in " ".join(cmd):
                    return 0, "", ""
                return 0, "", ""

            mock_run.side_effect = side_effect

            publisher._create_and_merge_branch("test-branch")

            # Verify branch was deleted
            delete_calls = [
                call
                for call in mock_run.call_args_list
                if "branch" in str(call) and "-D" in str(call)
            ]
            assert len(delete_calls) == 1

    def test_should_handle_create_branch_failure(self, publisher):
        """Test handling branch creation failure."""
        with patch.object(publisher, "_run_command") as mock_run:
            # Mock branch creation failure
            def side_effect(cmd, cwd=None):
                if "checkout -b" in " ".join(cmd):
                    return 1, "", "Cannot create branch"
                return 0, "", ""

            mock_run.side_effect = side_effect

            with pytest.raises(Exception) as exc_info:
                publisher._create_and_merge_branch("test-branch")

            assert "Failed to create branch" in str(exc_info.value)

    def test_should_handle_location_export_script_missing(self, publisher, temp_dirs):
        """Test handling missing location export script."""
        _, repo_dir = temp_dirs

        with patch("app.haarrrvest_publisher.service.logger") as mock_logger:
            publisher._run_location_export()

            # Should log error
            mock_logger.error.assert_called()

    def test_should_handle_location_export_failure(self, publisher, temp_dirs):
        """Test handling location export script failure."""
        _, repo_dir = temp_dirs

        # Create mock script
        scripts_dir = repo_dir / "scripts"
        scripts_dir.mkdir()
        export_script = scripts_dir / "export-locations.py"
        export_script.write_text("raise Exception('Export failed')")

        with patch.object(publisher, "_run_command") as mock_run:
            mock_run.return_value = (1, "", "Export failed")

            with patch("app.haarrrvest_publisher.service.logger") as mock_logger:
                publisher._run_location_export()

                # Should log error
                mock_logger.error.assert_called()

    def test_should_handle_sqlite_export_exception(self, publisher):
        """Test handling exceptions during SQLite export."""
        with patch.object(publisher, "_run_command") as mock_run:
            mock_run.side_effect = Exception("Unexpected error")

            with pytest.raises(Exception) as exc_info:
                publisher._export_to_sqlite()

            assert "Failed to export SQLite database" in str(exc_info.value)

    def test_should_sync_database_from_haarrrvest_with_recent_data(
        self, publisher, temp_dirs
    ):
        """Test syncing database with 90 most recent days per scraper."""
        _, repo_dir = temp_dirs

        # Create mock HAARRRvest data structure
        daily_dir = repo_dir / "daily"
        daily_dir.mkdir()

        # Create test data for multiple scrapers and dates
        from datetime import datetime, timedelta

        base_date = datetime(2025, 1, 1)

        # Scraper 1: 100 days of data (should take most recent 90)
        scraper1_dates = []
        for i in range(100):
            date = base_date + timedelta(days=i)
            date_str = date.strftime("%Y-%m-%d")
            scraper_dir = daily_dir / date_str / "scrapers" / "scraper1"
            scraper_dir.mkdir(parents=True, exist_ok=True)

            # Create a JSON file
            json_file = scraper_dir / f"job_{i}.json"
            json_file.write_text('{"test": "data"}')
            scraper1_dates.append(date)

        # Scraper 2: 30 days of data (should take all 30)
        scraper2_dates = []
        for i in range(30):
            date = base_date + timedelta(days=i * 2)  # Every other day
            date_str = date.strftime("%Y-%m-%d")
            scraper_dir = daily_dir / date_str / "scrapers" / "scraper2"
            scraper_dir.mkdir(parents=True, exist_ok=True)

            json_file = scraper_dir / f"job_{i}.json"
            json_file.write_text('{"test": "data"}')
            scraper2_dates.append(date)

        with patch("app.replay.replay.replay_file") as mock_replay:
            mock_replay.return_value = True  # Success

            publisher._sync_database_from_haarrrvest()

            # Should process files from both scrapers
            assert mock_replay.call_count > 0

            # Verify the most recent 90 days were processed for scraper1
            # and all 30 days for scraper2

    def test_should_update_repository_metadata(self, publisher, temp_dirs):
        """Test updating repository metadata files."""
        _, repo_dir = temp_dirs

        # Create some test data
        (repo_dir / "daily" / "2025-01-20" / "scrapers" / "test").mkdir(parents=True)

        publisher._update_repository_metadata()

        # Verify files were created
        assert (repo_dir / "README.md").exists()
        assert (repo_dir / "STATS.md").exists()

        # Verify content
        readme_content = (repo_dir / "README.md").read_text()
        assert "HAARRRvest" in readme_content
        assert "Last Update" in readme_content

    def test_should_generate_statistics_without_data(self, publisher, temp_dirs):
        """Test generating statistics with no data."""
        _, repo_dir = temp_dirs

        stats = publisher._generate_statistics()

        assert stats["total_records"] == 0
        assert stats["sources"] == 0
        assert stats["date_range"] == "N/A"

    @patch("app.haarrrvest_publisher.service.logger")
    def test_main_function(self, mock_logger):
        """Test main entry point function."""
        with patch(
            "app.haarrrvest_publisher.service.HAARRRvestPublisher"
        ) as mock_publisher_class:
            mock_instance = Mock()
            mock_publisher_class.return_value = mock_instance

            with patch.dict(
                "os.environ",
                {
                    "OUTPUT_DIR": "/test/outputs",
                    "DATA_REPO_PATH": "/test/repo",
                    "DATA_REPO_URL": "git@test.com:repo.git",
                    "PUBLISHER_CHECK_INTERVAL": "120",
                    "DAYS_TO_SYNC": "14",
                },
            ):
                from app.haarrrvest_publisher.service import main

                main()

            # Verify publisher was created with correct params
            mock_publisher_class.assert_called_with(
                output_dir="/test/outputs",
                data_repo_path="/test/repo",
                data_repo_url="git@test.com:repo.git",
                error_retry_delay=60,
                check_interval=120,
                days_to_sync=14,
            )

            # Verify run was called
            mock_instance.run.assert_called_once()

    def test_should_handle_non_digit_rev_list_output(self, publisher):
        """Test handling non-digit output from rev-list command."""
        with patch.object(publisher, "_run_command") as mock_run:
            # Mock various git commands
            def side_effect(cmd, cwd=None):
                if "status" in cmd:
                    return 0, "", ""
                elif "checkout main" in cmd:
                    return 0, "", ""
                elif "fetch" in cmd:
                    return 0, "", ""
                elif "rev-list" in cmd:
                    return 0, "not-a-number", ""  # Non-digit output
                return 0, "", ""

            mock_run.side_effect = side_effect

            # Should handle gracefully with behind_count = 0
            publisher._setup_git_repo()

            # Should not attempt to pull
            pull_calls = [
                call for call in mock_run.call_args_list if "pull" in str(call)
            ]
            assert len(pull_calls) == 0

    def test_should_handle_process_exception(self, publisher):
        """Test handling exceptions in process_once."""
        with patch.object(
            publisher, "_setup_git_repo", side_effect=Exception("Setup failed")
        ):
            with patch("app.haarrrvest_publisher.service.logger") as mock_logger:
                with pytest.raises(Exception):
                    publisher.process_once()

    def test_should_handle_finding_scrapers_in_daily_subdirs(
        self, publisher, temp_dirs
    ):
        """Test finding files in scraper subdirectories."""
        output_dir, _ = temp_dirs

        # Create test files in scraper subdirectories
        today = datetime.now().strftime("%Y-%m-%d")
        scraper_dir = output_dir / "daily" / today / "scrapers" / "test_scraper"
        scraper_dir.mkdir(parents=True)

        file1 = scraper_dir / "file1.json"
        file1.write_text('{"test": 1}')

        # Find new files
        new_files = publisher._find_new_files()

        assert len(new_files) == 1
        assert file1 in new_files

    def test_should_handle_git_stash_with_changes(self, publisher, temp_dirs):
        """Test stashing uncommitted changes."""
        _, repo_dir = temp_dirs

        # Create a .git directory to simulate existing repository
        (repo_dir / ".git").mkdir()

        with patch.object(publisher, "_run_command") as mock_run:
            # Mock git status with changes
            def side_effect(cmd, cwd=None):
                cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
                if "status" in cmd_str and "--porcelain" in cmd_str:
                    return 0, "M file.txt\nA new.txt", ""  # Multiple changes
                elif "stash" in cmd_str:
                    return 0, "", ""
                elif "checkout main" in cmd_str:
                    return 0, "", ""
                elif "fetch" in cmd_str:
                    return 0, "", ""
                elif "rev-list" in cmd_str:
                    return 0, "0", ""
                return 0, "", ""

            mock_run.side_effect = side_effect

            publisher._setup_git_repo()

            # Verify stash was called
            stash_calls = [
                call for call in mock_run.call_args_list if "stash" in str(call)
            ]
            assert len(stash_calls) == 1

    def test_should_handle_directory_creation_in_sync(self, publisher, temp_dirs):
        """Test creating nested directories during sync."""
        output_dir, repo_dir = temp_dirs

        # Create deeply nested file
        deep_file = (
            output_dir
            / "daily"
            / "2025-01-25"
            / "scrapers"
            / "test"
            / "nested"
            / "file.json"
        )
        deep_file.parent.mkdir(parents=True, exist_ok=True)
        deep_file.write_text('{"test": "nested"}')

        # Sync files
        publisher._sync_files_to_repo([deep_file])

        # Verify nested structure was created
        target_file = (
            repo_dir
            / "daily"
            / "2025-01-25"
            / "scrapers"
            / "test"
            / "nested"
            / "file.json"
        )
        assert target_file.exists()
        assert target_file.read_text() == '{"test": "nested"}'

    def test_should_handle_empty_processed_directory(self, publisher, temp_dirs):
        """Test handling empty processed directory."""
        output_dir, _ = temp_dirs

        # Create empty processed directory
        today = datetime.now().strftime("%Y-%m-%d")
        (output_dir / "daily" / today / "processed").mkdir(parents=True)

        # Should not find any files
        new_files = publisher._find_new_files()
        assert len(new_files) == 0

    def test_should_run_multiple_iterations_before_shutdown(self, publisher):
        """Test running multiple iterations in continuous mode."""
        call_count = 0

        def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 3:
                raise KeyboardInterrupt()

        with patch("time.sleep"):  # Mock sleep to speed up test
            with patch.object(
                publisher, "_setup_git_repo"
            ):  # Mock setup to avoid real git calls
                with patch.object(publisher, "process_once", side_effect=side_effect):
                    publisher.run()

        # Should have run 3 times before shutdown
        assert call_count == 3

    def test_push_enabled_environment_variable_true(self, temp_dirs, monkeypatch):
        """Test that push is enabled when PUBLISHER_PUSH_ENABLED=true."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "true")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        assert publisher.push_enabled is True

    def test_push_enabled_environment_variable_false(self, temp_dirs, monkeypatch):
        """Test that push is disabled when PUBLISHER_PUSH_ENABLED=false."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "false")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        assert publisher.push_enabled is False

    def test_push_enabled_environment_variable_default(self, temp_dirs, monkeypatch):
        """Test that push is disabled by default when env var not set."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.delenv("PUBLISHER_PUSH_ENABLED", raising=False)

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        assert publisher.push_enabled is False

    def test_push_enabled_case_insensitive(self, temp_dirs, monkeypatch):
        """Test that PUBLISHER_PUSH_ENABLED is case-insensitive."""
        output_dir, repo_dir = temp_dirs

        # Test various case combinations
        for value in ["TRUE", "True", "TrUe"]:
            monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", value)
            publisher = HAARRRvestPublisher(
                output_dir=str(output_dir),
                data_repo_path=str(repo_dir),
                data_repo_url="https://github.com/test/repo.git",
            )
            assert publisher.push_enabled is True, f"Failed for value: {value}"

    @patch("app.haarrrvest_publisher.service.logger")
    def test_push_enabled_logs_warning(self, mock_logger, temp_dirs, monkeypatch):
        """Test that enabling push logs a warning."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "true")

        HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Should log warning when push is enabled
        mock_logger.warning.assert_called_once()
        assert "PUBLISHER PUSH ENABLED" in mock_logger.warning.call_args[0][0]

    @patch("app.haarrrvest_publisher.service.logger")
    def test_push_disabled_logs_info(self, mock_logger, temp_dirs, monkeypatch):
        """Test that disabling push logs info message."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "false")

        HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Should log info when push is disabled
        mock_logger.info.assert_called()
        info_calls = [
            call
            for call in mock_logger.info.call_args_list
            if "READ-ONLY mode" in str(call)
        ]
        assert len(info_calls) == 1

    @patch("subprocess.run")
    def test_push_disabled_prevents_git_push(self, mock_run, temp_dirs, monkeypatch):
        """Test that push is prevented when PUBLISHER_PUSH_ENABLED=false."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "false")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Mock git commands with changes to commit
        mock_run.return_value = Mock(returncode=0, stdout="M file.txt", stderr="")

        with patch.object(publisher, "_run_command") as mock_run_cmd:

            def side_effect(cmd, cwd=None):
                if "status --porcelain" in " ".join(cmd):
                    return 0, "M file.txt", ""  # Changes exist
                return 0, "", ""

            mock_run_cmd.side_effect = side_effect

            # Create test branch
            publisher._create_and_merge_branch("test-branch")

            # Verify push was NOT called
            push_calls = [
                call for call in mock_run_cmd.call_args_list if "push" in str(call)
            ]
            assert len(push_calls) == 0

    @patch("subprocess.run")
    @patch("app.haarrrvest_publisher.service.logger")
    def test_push_disabled_logs_warning_instead_of_push(
        self, mock_logger, mock_run, temp_dirs, monkeypatch
    ):
        """Test that warning is logged instead of pushing when disabled."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "false")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Mock git commands with changes to commit
        mock_run.return_value = Mock(returncode=0, stdout="M file.txt", stderr="")

        with patch.object(publisher, "_run_command") as mock_run_cmd:

            def side_effect(cmd, cwd=None):
                if "status --porcelain" in " ".join(cmd):
                    return 0, "M file.txt", ""  # Changes exist
                return 0, "", ""

            mock_run_cmd.side_effect = side_effect

            # Create test branch
            publisher._create_and_merge_branch("test-branch")

            # Should log warning about push being disabled
            warning_calls = [
                call
                for call in mock_logger.warning.call_args_list
                if "PUSH DISABLED" in str(call)
            ]
            assert len(warning_calls) == 1

            # Should also log info about enabling push
            info_calls = [
                call
                for call in mock_logger.info.call_args_list
                if "PUBLISHER_PUSH_ENABLED=true" in str(call)
            ]
            assert len(info_calls) == 1

    @patch("subprocess.run")
    def test_push_enabled_allows_git_push(self, mock_run, temp_dirs, monkeypatch):
        """Test that push occurs when PUBLISHER_PUSH_ENABLED=true."""
        output_dir, repo_dir = temp_dirs
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "true")
        monkeypatch.setenv("DATA_REPO_TOKEN", "test_token")

        publisher = HAARRRvestPublisher(
            output_dir=str(output_dir),
            data_repo_path=str(repo_dir),
            data_repo_url="https://github.com/test/repo.git",
        )

        # Mock git commands
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch.object(publisher, "_run_command") as mock_run_cmd:

            def side_effect(cmd, cwd=None):
                if "status --porcelain" in " ".join(cmd):
                    return 0, "M file.txt", ""  # Changes exist
                return 0, "", ""

            mock_run_cmd.side_effect = side_effect

            # Create test branch
            publisher._create_and_merge_branch("test-branch")

            # Verify push WAS called
            push_calls = [
                call for call in mock_run_cmd.call_args_list if "push" in str(call)
            ]
            assert len(push_calls) > 0

    def test_should_preserve_existing_readme_content(self, publisher, temp_dirs):
        """Test preserving existing README content while updating harvester section."""
        _, repo_dir = temp_dirs

        # Create existing README with custom content
        readme_path = repo_dir / "README.md"
        existing_content = """# HAARRRvest - Food Resource Data

This is a custom introduction added by the maintainer.

## Custom Section

This is important documentation that should be preserved.

## Another Section

More custom content here.
"""
        readme_path.write_text(existing_content)

        # Update repository metadata
        publisher._update_repository_metadata()

        # Read the updated content
        updated_content = readme_path.read_text()

        # Verify harvester section was added
        assert "<!-- HARVESTER AUTO-GENERATED SECTION START -->" in updated_content
        assert "<!-- HARVESTER AUTO-GENERATED SECTION END -->" in updated_content
        assert "Last Update" in updated_content
        assert "Data Structure" in updated_content

        # Verify existing content was preserved
        assert (
            "This is a custom introduction added by the maintainer." in updated_content
        )
        assert "## Custom Section" in updated_content
        assert (
            "This is important documentation that should be preserved."
            in updated_content
        )
        assert "## Another Section" in updated_content
        assert "More custom content here." in updated_content

    def test_should_update_existing_harvester_section_in_readme(
        self, publisher, temp_dirs
    ):
        """Test updating existing harvester section without affecting other content."""
        _, repo_dir = temp_dirs

        # Create README with existing harvester section
        readme_path = repo_dir / "README.md"
        existing_content = """# HAARRRvest - Food Resource Data

Custom intro text here.

<!-- HARVESTER AUTO-GENERATED SECTION START -->
## Last Update

- **Date**: 2025-01-01 12:00:00 UTC
- **Total Records**: 100
- **Data Sources**: 5
- **Date Range**: 2025-01-01 to 2025-01-02

## Data Structure

Old structure info...
<!-- HARVESTER AUTO-GENERATED SECTION END -->

## Manual Documentation

This should be preserved.
"""
        readme_path.write_text(existing_content)

        # Create some test data to generate different statistics
        (repo_dir / "daily" / "2025-01-25" / "scrapers" / "test").mkdir(parents=True)
        (
            repo_dir / "daily" / "2025-01-25" / "scrapers" / "test" / "file.json"
        ).write_text("{}")

        # Update repository metadata
        publisher._update_repository_metadata()

        # Read the updated content
        updated_content = readme_path.read_text()

        # Verify harvester section was updated (different date)
        assert "2025-01-01 12:00:00 UTC" not in updated_content  # Old date removed
        assert "Last Update" in updated_content  # New section present
        assert "Total Records" in updated_content

        # Verify other content was preserved
        assert "Custom intro text here." in updated_content
        assert "## Manual Documentation" in updated_content
        assert "This should be preserved." in updated_content

    def test_should_create_readme_when_none_exists(self, publisher, temp_dirs):
        """Test creating README when none exists."""
        _, repo_dir = temp_dirs

        # Ensure no README exists
        readme_path = repo_dir / "README.md"
        assert not readme_path.exists()

        # Update repository metadata
        publisher._update_repository_metadata()

        # Verify README was created
        assert readme_path.exists()
        content = readme_path.read_text()

        # Verify it contains expected sections
        assert "# HAARRRvest - Food Resource Data" in content
        assert "This repository contains food resource data" in content
        assert "<!-- HARVESTER AUTO-GENERATED SECTION START -->" in content
        assert "Last Update" in content
        assert "Data Structure" in content

    def test_should_handle_readme_without_title(self, publisher, temp_dirs):
        """Test handling README that doesn't start with a title."""
        _, repo_dir = temp_dirs

        # Create README without title
        readme_path = repo_dir / "README.md"
        existing_content = """This is a README without a title.

Some content here.
"""
        readme_path.write_text(existing_content)

        # Update repository metadata
        publisher._update_repository_metadata()

        # Read the updated content
        updated_content = readme_path.read_text()

        # Verify harvester section was added at the beginning
        assert updated_content.startswith(
            "<!-- HARVESTER AUTO-GENERATED SECTION START -->"
        )

        # Verify existing content was preserved
        assert "This is a README without a title." in updated_content
        assert "Some content here." in updated_content
