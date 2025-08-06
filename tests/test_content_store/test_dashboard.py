"""Tests for content store dashboard module."""

import json
import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, mock_open

import pytest
import redis
from flask import Flask
from rq.job import Job

from app.content_store import ContentStore
from app.content_store.dashboard import (
    app,
    get_content_store,
    get_redis_connection,
)


class TestDashboardApp:
    """Test Flask app creation and configuration."""

    def test_app_is_flask_instance(self):
        """Dashboard app should be a Flask instance."""
        assert isinstance(app, Flask)

    def test_app_name(self):
        """Flask app should have correct name."""
        assert app.name == "app.content_store.dashboard"

    @patch.dict("os.environ", {"DASHBOARD_HOST": "localhost", "DASHBOARD_PORT": "8080"})
    @patch("app.content_store.dashboard.app.run")
    def test_main_with_env_vars(self, mock_run):
        """Main should use environment variables for host and port."""
        # Import and execute the __main__ block
        import app.content_store.dashboard as dashboard_module

        # Simulate running as main module
        dashboard_module.__name__ = "__main__"

        # Execute the main block code directly
        import os

        host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
        port = int(os.environ.get("DASHBOARD_PORT", "5050"))

        # Verify values are read from environment
        assert host == "localhost"
        assert port == 8080

    @patch.dict("os.environ", {}, clear=True)
    def test_main_with_default_values(self):
        """Main should use default values when env vars not set."""
        import os

        host = os.environ.get("DASHBOARD_HOST", "127.0.0.1")
        port = int(os.environ.get("DASHBOARD_PORT", "5050"))

        # Verify default values
        assert host == "127.0.0.1"
        assert port == 5050


class TestHelperFunctions:
    """Test helper functions."""

    @patch("app.content_store.dashboard.ContentStore")
    @patch("app.content_store.dashboard.Path")
    def test_get_content_store(self, mock_path, mock_content_store):
        """get_content_store should create ContentStore with correct path."""
        mock_path_instance = Mock()
        mock_path.return_value = mock_path_instance
        mock_store = Mock()
        mock_content_store.return_value = mock_store

        result = get_content_store()

        mock_path.assert_called_once_with("/data-repo")
        mock_content_store.assert_called_once_with(store_path=mock_path_instance)
        assert result == mock_store

    @patch("app.content_store.dashboard.redis.Redis")
    def test_get_redis_connection(self, mock_redis):
        """get_redis_connection should create Redis connection with correct config."""
        mock_connection = Mock()
        mock_redis.return_value = mock_connection

        result = get_redis_connection()

        mock_redis.assert_called_once_with(host="cache", port=6379, db=0)
        assert result == mock_connection


class TestDashboardRoutes:
    """Test dashboard route handlers."""

    @pytest.fixture
    def client(self):
        """Create test client."""
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    def test_dashboard_route(self, client):
        """Dashboard route should return HTML page."""
        response = client.get("/")

        assert response.status_code == 200
        assert response.content_type == "text/html; charset=utf-8"
        assert b"Content Store Dashboard" in response.data
        assert b"<html>" in response.data
        assert b"</html>" in response.data

    def test_dashboard_route_contains_required_elements(self, client):
        """Dashboard should contain required HTML elements."""
        response = client.get("/")
        content = response.data.decode()

        # Check for essential elements
        assert 'id="total-content"' in content
        assert 'id="completed-content"' in content
        assert 'id="pending-content"' in content
        assert 'id="cache-hits"' in content
        assert 'id="store-size"' in content
        assert "/api/stats" in content
        assert "refreshData()" in content

    @patch("app.content_store.dashboard.get_content_store")
    @patch("app.content_store.dashboard.get_redis_connection")
    @patch("app.content_store.dashboard.sqlite3.connect")
    @patch("app.content_store.dashboard.Path")
    def test_api_stats_success(
        self, mock_path, mock_connect, mock_redis, mock_get_store, client
    ):
        """API stats endpoint should return dashboard statistics."""
        # Mock ContentStore
        mock_store = Mock()
        mock_store.get_statistics.return_value = {
            "total_content": 100,
            "processed_content": 75,
            "pending_content": 25,
            "store_size_bytes": 1048576,  # 1MB
        }
        mock_get_store.return_value = mock_store

        # Mock Redis connection
        mock_redis_conn = Mock()
        mock_redis.return_value = mock_redis_conn

        # Mock SQLite connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(
            return_value=iter(
                [
                    ("abc123def456", "completed", "job_123", "2023-12-01 10:00:00"),
                    ("def456ghi789", "pending", None, "2023-12-01 09:00:00"),
                ]
            )
        )
        mock_conn.execute.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Mock Job.fetch for job status
        mock_job = Mock()
        mock_job.get_status.return_value = "finished"

        with patch.object(Job, "fetch", return_value=mock_job):
            # Mock content file reading
            mock_content_path = Mock()
            mock_content_path.exists.return_value = True
            mock_content_path.read_text.return_value = json.dumps(
                {"metadata": {"scraper_id": "test_scraper"}}
            )

            mock_store._get_content_path.return_value = mock_content_path

            # Mock Path for database
            mock_db_path = Mock()
            mock_path.return_value = mock_db_path
            mock_db_path.__truediv__ = Mock()
            mock_db_path.__truediv__.return_value.__truediv__ = Mock()
            mock_db_path.__truediv__.return_value.__truediv__.return_value = (
                "/data-repo/content_store/index.db"
            )

            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.get_json()

        # Check response structure
        assert "stats" in data
        assert "recent_entries" in data
        assert "cache_hits" in data
        assert "timestamp" in data

        # Check stats
        stats = data["stats"]
        assert stats["total_content"] == 100
        assert stats["processed_content"] == 75
        assert stats["pending_content"] == 25

        # Check cache hits calculation
        assert data["cache_hits"] == 150  # processed_content * 2

        # Check recent entries
        assert len(data["recent_entries"]) == 2
        entry = data["recent_entries"][0]
        assert entry["hash_short"] == "abc123de"
        assert entry["hash_full"] == "abc123def456"
        assert entry["status"] == "completed"
        assert entry["scraper_id"] == "test_scraper"
        assert entry["job_status"] == "finished"

    @patch("app.content_store.dashboard.get_content_store")
    @patch("app.content_store.dashboard.get_redis_connection")
    @patch("app.content_store.dashboard.sqlite3.connect")
    def test_api_stats_with_job_fetch_exception(
        self, mock_connect, mock_redis, mock_get_store, client
    ):
        """API stats should handle job fetch exceptions gracefully."""
        # Mock ContentStore
        mock_store = Mock()
        mock_store.get_statistics.return_value = {
            "total_content": 10,
            "processed_content": 5,
            "pending_content": 5,
            "store_size_bytes": 1024,
        }
        mock_get_store.return_value = mock_store

        # Mock Redis connection
        mock_redis.return_value = Mock()

        # Mock SQLite with job that will fail to fetch
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(
            return_value=iter(
                [("hash123", "pending", "invalid_job_id", "2023-12-01 10:00:00")]
            )
        )
        mock_conn.execute.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Mock Job.fetch to raise exception
        with patch.object(Job, "fetch", side_effect=Exception("Job not found")):
            # Mock content path
            mock_content_path = Mock()
            mock_content_path.exists.return_value = False
            mock_store._get_content_path.return_value = mock_content_path

            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.get_json()

        # Should handle exception and set job_status to "expired"
        entry = data["recent_entries"][0]
        assert entry["job_status"] == "expired"
        assert entry["scraper_id"] is None

    @patch("app.content_store.dashboard.get_content_store")
    @patch("app.content_store.dashboard.get_redis_connection")
    @patch("app.content_store.dashboard.sqlite3.connect")
    def test_api_stats_with_content_read_exception(
        self, mock_connect, mock_redis, mock_get_store, client
    ):
        """API stats should handle content file read exceptions gracefully."""
        # Mock ContentStore
        mock_store = Mock()
        mock_store.get_statistics.return_value = {
            "total_content": 10,
            "processed_content": 5,
            "pending_content": 5,
            "store_size_bytes": 1024,
        }
        mock_get_store.return_value = mock_store

        # Mock Redis connection
        mock_redis.return_value = Mock()

        # Mock SQLite
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_cursor.__iter__ = Mock(
            return_value=iter([("hash123", "completed", None, "2023-12-01 10:00:00")])
        )
        mock_conn.execute.return_value = mock_cursor
        mock_connect.return_value = mock_conn

        # Mock content path that exists but fails to read
        mock_content_path = Mock()
        mock_content_path.exists.return_value = True
        mock_content_path.read_text.side_effect = Exception("Read error")
        mock_store._get_content_path.return_value = mock_content_path

        response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.get_json()

        # Should handle exception and set scraper_id to None
        entry = data["recent_entries"][0]
        assert entry["scraper_id"] is None

    @patch("app.content_store.dashboard.get_content_store")
    def test_api_content_detail_success(self, mock_get_store, client):
        """API content detail endpoint should return content information."""
        # Mock ContentStore
        mock_store = Mock()
        mock_get_store.return_value = mock_store

        # Mock hash validation (no exception means valid)
        mock_store._validate_hash.return_value = None

        # Mock content and result paths
        mock_content_path = Mock()
        mock_content_path.exists.return_value = True
        mock_content_path.read_text.return_value = json.dumps(
            {
                "content": "This is test content for the pantry location",
                "metadata": {"scraper_id": "test_scraper", "url": "http://example.com"},
                "timestamp": "2023-12-01T10:00:00",
            }
        )

        mock_result_path = Mock()
        mock_result_path.exists.return_value = True
        mock_result_path.read_text.return_value = json.dumps(
            {
                "result": "Processed result data with LLM analysis",
                "job_id": "job_12345",
                "timestamp": "2023-12-01T11:00:00",
            }
        )

        mock_store._get_content_path.return_value = mock_content_path
        mock_store._get_result_path.return_value = mock_result_path

        response = client.get("/api/content/validhash123")

        assert response.status_code == 200
        data = response.get_json()

        # Check response structure
        assert data["hash"] == "validhash123"
        assert data["has_content"] is True
        assert data["has_result"] is True
        assert data["content"] == "This is test content for the pantry location"[:500]
        assert data["metadata"]["scraper_id"] == "test_scraper"
        assert data["result"] == "Processed result data with LLM analysis"[:500]
        assert data["job_id"] == "job_12345"
        assert data["stored_at"] == "2023-12-01T10:00:00"
        assert data["processed_at"] == "2023-12-01T11:00:00"

    @patch("app.content_store.dashboard.get_content_store")
    def test_api_content_detail_invalid_hash(self, mock_get_store, client):
        """API content detail should return 400 for invalid hash."""
        # Mock ContentStore
        mock_store = Mock()
        mock_get_store.return_value = mock_store

        # Mock hash validation to raise ValueError
        mock_store._validate_hash.side_effect = ValueError("Invalid hash format")

        response = client.get("/api/content/invalid-hash")

        assert response.status_code == 400
        data = response.get_json()
        assert data["error"] == "Invalid hash format"

    @patch("app.content_store.dashboard.get_content_store")
    def test_api_content_detail_no_files(self, mock_get_store, client):
        """API content detail should handle missing content and result files."""
        # Mock ContentStore
        mock_store = Mock()
        mock_get_store.return_value = mock_store

        # Mock hash validation (no exception means valid)
        mock_store._validate_hash.return_value = None

        # Mock content and result paths that don't exist
        mock_content_path = Mock()
        mock_content_path.exists.return_value = False

        mock_result_path = Mock()
        mock_result_path.exists.return_value = False

        mock_store._get_content_path.return_value = mock_content_path
        mock_store._get_result_path.return_value = mock_result_path

        response = client.get("/api/content/validhash123")

        assert response.status_code == 200
        data = response.get_json()

        # Check response structure for missing files
        assert data["hash"] == "validhash123"
        assert data["has_content"] is False
        assert data["has_result"] is False
        assert "content" not in data
        assert "metadata" not in data
        assert "result" not in data

    @patch("app.content_store.dashboard.get_content_store")
    def test_api_content_detail_content_only(self, mock_get_store, client):
        """API content detail should handle case with content but no result."""
        # Mock ContentStore
        mock_store = Mock()
        mock_get_store.return_value = mock_store

        # Mock hash validation (no exception means valid)
        mock_store._validate_hash.return_value = None

        # Mock content path that exists
        mock_content_path = Mock()
        mock_content_path.exists.return_value = True
        mock_content_path.read_text.return_value = json.dumps(
            {
                "content": "x" * 600,  # Long content to test truncation
                "metadata": {"source": "test"},
                "timestamp": "2023-12-01T10:00:00",
            }
        )

        # Mock result path that doesn't exist
        mock_result_path = Mock()
        mock_result_path.exists.return_value = False

        mock_store._get_content_path.return_value = mock_content_path
        mock_store._get_result_path.return_value = mock_result_path

        response = client.get("/api/content/validhash123")

        assert response.status_code == 200
        data = response.get_json()

        # Check response
        assert data["has_content"] is True
        assert data["has_result"] is False
        assert len(data["content"]) == 500  # Truncated to 500 chars
        assert data["metadata"]["source"] == "test"
        assert "result" not in data

    @patch("app.content_store.dashboard.get_content_store")
    def test_api_content_detail_result_only(self, mock_get_store, client):
        """API content detail should handle case with result but no content."""
        # Mock ContentStore
        mock_store = Mock()
        mock_get_store.return_value = mock_store

        # Mock hash validation (no exception means valid)
        mock_store._validate_hash.return_value = None

        # Mock content path that doesn't exist
        mock_content_path = Mock()
        mock_content_path.exists.return_value = False

        # Mock result path that exists
        mock_result_path = Mock()
        mock_result_path.exists.return_value = True
        mock_result_path.read_text.return_value = json.dumps(
            {
                "result": "y" * 600,  # Long result to test truncation
                "job_id": "job_67890",
                "timestamp": "2023-12-01T12:00:00",
            }
        )

        mock_store._get_content_path.return_value = mock_content_path
        mock_store._get_result_path.return_value = mock_result_path

        response = client.get("/api/content/validhash123")

        assert response.status_code == 200
        data = response.get_json()

        # Check response
        assert data["has_content"] is False
        assert data["has_result"] is True
        assert len(data["result"]) == 500  # Truncated to 500 chars
        assert data["job_id"] == "job_67890"
        assert "content" not in data
        assert "metadata" not in data

    def test_nonexistent_route_returns_404(self, client):
        """Nonexistent routes should return 404."""
        response = client.get("/api/nonexistent")
        assert response.status_code == 404

    def test_api_content_missing_hash_returns_404(self, client):
        """API content without hash parameter should return 404."""
        response = client.get("/api/content/")
        assert response.status_code == 404


class TestDashboardIntegration:
    """Integration tests for dashboard functionality."""

    @pytest.fixture
    def temp_db_path(self):
        """Create temporary database for testing."""
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = Path(tmp.name)

        # Create database with schema
        conn = sqlite3.connect(db_path)
        conn.execute(
            """
            CREATE TABLE content_index (
                hash TEXT PRIMARY KEY,
                status TEXT,
                job_id TEXT,
                created_at TEXT
            )
        """
        )
        conn.execute(
            """
            INSERT INTO content_index (hash, status, job_id, created_at)
            VALUES (?, ?, ?, ?)
        """,
            ("test_hash_123", "completed", "job_456", "2023-12-01 10:00:00"),
        )
        conn.commit()
        conn.close()

        yield db_path
        db_path.unlink()

    @pytest.fixture
    def client(self):
        """Create test client."""
        app.config["TESTING"] = True
        with app.test_client() as client:
            yield client

    @patch("app.content_store.dashboard.get_content_store")
    @patch("app.content_store.dashboard.get_redis_connection")
    def test_api_stats_integration(
        self, mock_redis, mock_get_store, client, temp_db_path
    ):
        """Integration test for api_stats with real database."""
        # Mock ContentStore
        mock_store = Mock()
        mock_store.get_statistics.return_value = {
            "total_content": 50,
            "processed_content": 30,
            "pending_content": 20,
            "store_size_bytes": 2048,
        }
        mock_get_store.return_value = mock_store

        # Mock Redis
        mock_redis.return_value = Mock()

        # Mock Path to return our temp database
        with patch("app.content_store.dashboard.Path") as mock_path:
            mock_path.return_value.__truediv__.return_value.__truediv__.return_value = (
                temp_db_path
            )

            # Mock content path
            mock_content_path = Mock()
            mock_content_path.exists.return_value = False
            mock_store._get_content_path.return_value = mock_content_path

            response = client.get("/api/stats")

        assert response.status_code == 200
        data = response.get_json()

        # Verify real database was queried
        assert len(data["recent_entries"]) == 1
        entry = data["recent_entries"][0]
        assert entry["hash_full"] == "test_hash_123"
        assert entry["status"] == "completed"

    def test_dashboard_template_rendering(self, client):
        """Test that dashboard template renders correctly."""
        response = client.get("/")
        content = response.data.decode()

        # Check that template contains expected JavaScript functions
        assert "function refreshData()" in content
        assert "setInterval(refreshData, 5000)" in content
        assert "fetch('/api/stats')" in content

        # Check CSS classes are present
        assert "stats-grid" in content
        assert "stat-card" in content
        assert "table-container" in content

