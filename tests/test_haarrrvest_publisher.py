import pytest
import os
import tempfile
import shutil
import subprocess
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock
import json
import signal

from app.haarrrvest_publisher.service import HAARRRvestPublisher


class TestHAARRRvestPublisher:
    """Test suite for HAARRRvest publisher service with SQL dump functionality."""

    @pytest.fixture
    def temp_dirs(self):
        """Create temporary directories for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            outputs_dir = temp_path / "outputs"
            outputs_dir.mkdir()
            (outputs_dir / "daily").mkdir()
            (outputs_dir / "latest").mkdir()

            repo_dir = temp_path / "HAARRRvest"
            repo_dir.mkdir()
            (repo_dir / ".git").mkdir()  # Simulate git repo

            yield {"base": temp_path, "outputs": outputs_dir, "repo": repo_dir}

    @pytest.fixture
    def mock_env(self, temp_dirs, monkeypatch):
        """Mock environment variables."""
        monkeypatch.setenv("OUTPUT_DIR", str(temp_dirs["outputs"]))
        monkeypatch.setenv("DATA_REPO_PATH", str(temp_dirs["repo"]))
        monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost:5432/test")
        monkeypatch.setenv("PUBLISHER_PUSH_ENABLED", "false")
        monkeypatch.setenv("SQL_DUMP_MIN_RECORDS", "100")
        monkeypatch.setenv("ALLOW_EMPTY_SQL_DUMP", "false")

    @pytest.fixture
    def publisher(self, mock_env, temp_dirs):
        """Create publisher instance."""
        _ = mock_env  # Fixture dependency, environment is already set
        publisher = HAARRRvestPublisher(
            output_dir=str(temp_dirs["outputs"]),
            data_repo_path=str(temp_dirs["repo"]),
        )
        return publisher

    def test_sql_dump_creation_success(self, publisher, temp_dirs):
        """Test successful SQL dump creation."""
        # Mock subprocess for pg_dump and psql
        with patch("subprocess.run") as mock_run:
            # Mock organization count check
            mock_run.side_effect = [
                # First call: organization count
                MagicMock(returncode=0, stdout="150\n"),
                # Second call: pg_dump
                MagicMock(returncode=0),
            ]

            publisher._export_to_sql_dump()

            # Verify calls
            assert mock_run.call_count == 2

            # Check organization count query
            count_call = mock_run.call_args_list[0]
            assert count_call[0][0][0] == "psql"  # First arg is command
            assert (
                "SELECT COUNT(*) FROM organization;" in count_call[0][0]
            )  # Query is in args list

            # Check pg_dump call
            dump_call = mock_run.call_args_list[1]
            assert dump_call[0][0][0] == "pg_dump"  # First arg is command
            assert "--no-owner" in dump_call[0][0]
            assert "--no-privileges" in dump_call[0][0]

    def test_sql_dump_ratchet_prevents_regression(self, publisher, temp_dirs):
        """Test that ratcheting threshold prevents regression in record count."""
        # Create ratchet file with high water mark
        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"
        sql_dumps_dir.mkdir()
        ratchet_file = sql_dumps_dir / ".record_count_ratchet"
        ratchet_data = {
            "max_record_count": 1000,
            "updated_at": "2025-01-01T00:00:00",
            "updated_by": "test",
        }
        ratchet_file.write_text(json.dumps(ratchet_data))

        with patch("subprocess.run") as mock_run:
            # Mock database with 800 records (below 90% of 1000)
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="800\n"),  # Count check
                # No pg_dump call should happen due to exception
            ]

            # Should not raise exception but should not create dump
            publisher._export_to_sql_dump()

            # Should only call subprocess once for count check, not for pg_dump
            assert mock_run.call_count == 1
            # Verify no SQL dump was created
            sql_dumps = list(sql_dumps_dir.glob("*.sql"))
            assert len(sql_dumps) == 0

    def test_sql_dump_safety_check_allows_override(
        self, publisher, temp_dirs, monkeypatch
    ):
        """Test that ALLOW_EMPTY_SQL_DUMP override works."""
        # Create existing dump
        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"
        sql_dumps_dir.mkdir()
        existing_dump = sql_dumps_dir / "pantry_pirate_radio_2025-01-01_00-00-00.sql"
        existing_dump.write_text("-- Previous dump")

        # Enable override
        monkeypatch.setenv("ALLOW_EMPTY_SQL_DUMP", "true")

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # Organization count
                MagicMock(returncode=0, stdout="5\n"),
                # pg_dump
                MagicMock(returncode=0),
            ]

            # Should not raise exception
            publisher._export_to_sql_dump()
            assert mock_run.call_count == 2

    def test_sql_dump_allows_first_dump_with_low_count(self, publisher, temp_dirs):
        """Test that first dump is allowed even with low record count."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # Organization count
                MagicMock(returncode=0, stdout="50\n"),
                # pg_dump
                MagicMock(returncode=0),
            ]

            # Should not raise exception for first dump
            publisher._export_to_sql_dump()
            assert mock_run.call_count == 2

    def test_sql_dump_updates_ratchet_on_growth(self, publisher, temp_dirs):
        """Test that ratchet updates when database grows."""
        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"
        sql_dumps_dir.mkdir()
        ratchet_file = sql_dumps_dir / ".record_count_ratchet"

        # Initial ratchet
        initial_data = {
            "max_record_count": 500,
            "updated_at": "2025-01-01T00:00:00",
            "updated_by": "test",
        }
        ratchet_file.write_text(json.dumps(initial_data))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # Organization count - higher than previous
                MagicMock(returncode=0, stdout="750\n"),
                # pg_dump
                MagicMock(returncode=0),
            ]

            publisher._export_to_sql_dump()

            # Check ratchet was updated
            updated_data = json.loads(ratchet_file.read_text())
            assert updated_data["max_record_count"] == 750
            assert updated_data["updated_by"] == "haarrrvest_publisher"

    def test_sql_dump_ratchet_with_custom_percentage(
        self, publisher, temp_dirs, monkeypatch
    ):
        """Test custom ratchet percentage threshold."""
        # Set custom threshold to 80%
        monkeypatch.setenv("SQL_DUMP_RATCHET_PERCENTAGE", "0.8")

        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"
        sql_dumps_dir.mkdir()
        ratchet_file = sql_dumps_dir / ".record_count_ratchet"
        ratchet_data = {
            "max_record_count": 1000,
            "updated_at": "2025-01-01T00:00:00",
            "updated_by": "test",
        }
        ratchet_file.write_text(json.dumps(ratchet_data))

        with patch("subprocess.run") as mock_run:
            # 850 records is above 80% threshold
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="850\n"),
                MagicMock(returncode=0),
            ]

            # Should succeed
            publisher._export_to_sql_dump()
            assert mock_run.call_count == 2

    def test_sql_dump_falls_back_to_minimum_without_ratchet(self, publisher, temp_dirs):
        """Test fallback to minimum threshold when no ratchet exists."""
        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"
        sql_dumps_dir.mkdir()

        # Create existing dump but no ratchet
        existing_dump = sql_dumps_dir / "pantry_pirate_radio_2025-01-01_00-00-00.sql"
        existing_dump.write_text("-- Previous dump")

        with patch("subprocess.run") as mock_run:
            # 50 records - below minimum
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="50\n"),  # Count check
                # No pg_dump should happen
            ]

            # Should not create dump due to minimum threshold
            publisher._export_to_sql_dump()

            # Should only call subprocess once for count check
            assert mock_run.call_count == 1
            # Verify no new SQL dump was created
            sql_dumps = list(sql_dumps_dir.glob("pantry_pirate_radio_*.sql"))
            assert len(sql_dumps) == 1  # Only the existing one

    def test_sql_dump_creates_symlink(self, publisher, temp_dirs):
        """Test that SQL dump creates latest.sql symlink."""
        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="150\n"),
                MagicMock(returncode=0),
            ]

            publisher._export_to_sql_dump()

            # Check symlink exists (now using compressed .gz extension)
            latest_link = sql_dumps_dir / "latest.sql.gz"
            assert latest_link.exists()
            assert latest_link.is_symlink()

    def test_sql_dump_rotation_keeps_24_hours(self, publisher, temp_dirs):
        """Test that SQL dump rotation keeps only last 3 hours of dumps."""
        sql_dumps_dir = temp_dirs["repo"] / "sql_dumps"
        sql_dumps_dir.mkdir()

        # Create old dumps (now using .sql.gz extension)
        old_dump1 = sql_dumps_dir / "pantry_pirate_radio_2025-01-27_00-00-00.sql.gz"
        old_dump1.write_text("old")
        old_dump1_time = datetime(2025, 1, 27, 0, 0).timestamp()  # 12 hours old
        os.utime(old_dump1, (old_dump1_time, old_dump1_time))

        recent_dump = sql_dumps_dir / "pantry_pirate_radio_2025-01-27_10-00-00.sql.gz"
        recent_dump.write_text("recent")
        recent_dump_time = datetime(2025, 1, 27, 10, 0).timestamp()  # 2 hours old
        os.utime(recent_dump, (recent_dump_time, recent_dump_time))

        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                MagicMock(returncode=0, stdout="150\n"),
                MagicMock(returncode=0),
            ]

            with patch("app.haarrrvest_publisher.service.datetime") as mock_datetime:
                mock_datetime.now.return_value = datetime(
                    2025, 1, 27, 12, 0
                )  # Current time: 12:00
                mock_datetime.strptime = datetime.strptime  # Keep strptime working
                publisher._export_to_sql_dump()

            # Old dump should be deleted
            assert not old_dump1.exists()
            # Recent dump should still exist
            assert recent_dump.exists()

    def test_graceful_shutdown_creates_final_dump(self, publisher):
        """Test that graceful shutdown creates a final SQL dump."""
        with patch.object(publisher, "_export_to_sql_dump") as mock_export:
            # Simulate shutdown signal
            publisher._shutdown_handler(signal.SIGTERM, None)

            # Should create final dump
            mock_export.assert_called_once()

    def test_run_pipeline_includes_sql_dump(self, publisher, temp_dirs):
        """Test that process_once includes SQL dump generation."""
        # Create a test file to process
        daily_dir = temp_dirs["outputs"] / "daily" / "2025-01-27"
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "data"}')

        # Mock the database operations
        with patch.object(publisher, "_export_to_sql_dump") as mock_export:
            with patch.object(publisher, "_export_to_sqlite"):
                # Call _run_database_operations which includes SQL dump
                publisher._run_database_operations()

                # SQL dump should be called
                mock_export.assert_called_once()

    def test_check_for_changes_always_true_for_sql_dumps(self, publisher):
        """Test that _check_for_changes always returns true to ensure SQL dumps."""
        # Even with no new files, should return true
        has_changes = publisher._check_for_changes()
        assert has_changes is True

    def test_sql_dump_handles_pg_dump_failure(self, publisher):
        """Test handling of pg_dump failure."""
        with patch("subprocess.run") as mock_run:
            mock_run.side_effect = [
                # Organization count succeeds
                MagicMock(returncode=0, stdout="150\n"),
                # pg_dump fails
                MagicMock(returncode=1, stderr="Connection failed"),
            ]

            # Should not raise exception, but log error via _safe_log
            with patch.object(publisher, "_safe_log") as mock_safe_log:
                publisher._export_to_sql_dump()
                # Check that error was logged
                error_calls = [
                    c for c in mock_safe_log.call_args_list if c[0][0] == "error"
                ]
                assert len(error_calls) > 0, "Expected error logs via _safe_log"

    def test_pipeline_continues_on_sql_dump_failure(self, publisher, temp_dirs):
        """Test that database operations continue even if SQL dump fails."""
        daily_dir = temp_dirs["outputs"] / "daily" / "2025-01-27"
        daily_dir.mkdir(parents=True)
        test_file = daily_dir / "test.json"
        test_file.write_text('{"test": "data"}')

        # Mock subprocess to fail for SQL dump
        with patch("subprocess.run") as mock_run:
            # First call for count check fails
            mock_run.side_effect = [
                MagicMock(returncode=1, stderr="Connection failed"),
            ]

            with patch.object(publisher, "_export_to_sqlite") as mock_sqlite:
                # Database operations should continue despite SQL dump failure
                publisher._run_database_operations()

                # SQLite export should still be called
                mock_sqlite.assert_called_once()
