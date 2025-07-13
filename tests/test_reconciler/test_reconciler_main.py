"""Tests for reconciler service main entry point."""

from unittest.mock import MagicMock, patch

import pytest

from app.reconciler.__main__ import main


def test_main_success():
    """Test main function runs successfully."""
    with patch("app.reconciler.__main__.Redis") as mock_redis_class, patch(
        "app.reconciler.__main__.Connection"
    ) as mock_connection, patch(
        "app.reconciler.__main__.Worker"
    ) as mock_worker_class, patch(
        "app.reconciler.__main__.settings"
    ) as mock_settings:

        # Mock settings
        mock_settings.REDIS_URL = "redis://localhost:6379/0"

        # Mock Redis instance
        mock_redis_instance = MagicMock()
        mock_redis_class.from_url.return_value = mock_redis_instance

        # Mock worker instance
        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        # Mock connection context manager
        mock_connection_instance = MagicMock()
        mock_connection.return_value = mock_connection_instance

        main()

        # Verify Redis connection
        mock_redis_class.from_url.assert_called_once_with("redis://localhost:6379/0")

        # Verify connection context manager
        mock_connection.assert_called_once_with(mock_redis_instance)

        # Verify worker creation
        mock_worker_class.assert_called_once_with(
            ["reconciler"], default_worker_ttl=600
        )

        # Verify worker starts
        mock_worker_instance.work.assert_called_once_with(with_scheduler=True)


def test_main_with_connection_context():
    """Test main function properly uses connection context manager."""
    with patch("app.reconciler.__main__.Redis") as mock_redis_class, patch(
        "app.reconciler.__main__.Connection"
    ) as mock_connection, patch(
        "app.reconciler.__main__.Worker"
    ) as mock_worker_class, patch(
        "app.reconciler.__main__.settings"
    ) as mock_settings, patch(
        "app.reconciler.__main__.logger"
    ) as mock_logger:

        mock_settings.REDIS_URL = "redis://test:6379/1"

        mock_redis_instance = MagicMock()
        mock_redis_class.from_url.return_value = mock_redis_instance

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        # Mock connection as context manager
        mock_connection_cm = MagicMock()
        mock_connection.return_value = mock_connection_cm

        main()

        # Verify connection context manager is used
        mock_connection_cm.__enter__.assert_called_once()
        mock_connection_cm.__exit__.assert_called_once()

        # Verify logging
        mock_logger.info.assert_called_with("Starting reconciler worker...")


def test_main_worker_configuration():
    """Test worker is configured with correct parameters."""
    with patch("app.reconciler.__main__.Redis") as mock_redis_class, patch(
        "app.reconciler.__main__.Connection"
    ) as mock_connection, patch(
        "app.reconciler.__main__.Worker"
    ) as mock_worker_class, patch(
        "app.reconciler.__main__.settings"
    ) as mock_settings:

        mock_settings.REDIS_URL = "redis://localhost:6379/0"

        mock_redis_instance = MagicMock()
        mock_redis_class.from_url.return_value = mock_redis_instance

        mock_worker_instance = MagicMock()
        mock_worker_class.return_value = mock_worker_instance

        main()

        # Verify worker is created with correct queue and TTL
        mock_worker_class.assert_called_once_with(
            ["reconciler"], default_worker_ttl=600
        )

        # Verify worker starts with scheduler
        mock_worker_instance.work.assert_called_once_with(with_scheduler=True)
