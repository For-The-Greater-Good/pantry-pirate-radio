"""Tests for base reconciler utilities."""

import logging
from unittest.mock import MagicMock
import pytest

from app.reconciler.base import BaseReconciler


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    return MagicMock()


class TestBaseReconciler:
    """Tests for BaseReconciler class."""

    def test_initialization(self, mock_db_session):
        """Test BaseReconciler initialization."""
        reconciler = BaseReconciler(db=mock_db_session)

        assert reconciler.db == mock_db_session
        assert isinstance(reconciler.logger, logging.Logger)
        assert reconciler.logger.name == "app.reconciler.base"

    def test_context_manager_enter(self, mock_db_session):
        """Test BaseReconciler context manager enter."""
        reconciler = BaseReconciler(db=mock_db_session)

        # Test __enter__ method
        context_result = reconciler.__enter__()
        assert context_result is reconciler

    def test_context_manager_exit(self, mock_db_session):
        """Test BaseReconciler context manager exit."""
        reconciler = BaseReconciler(db=mock_db_session)

        # Test __exit__ method - should not raise any exceptions
        result = reconciler.__exit__(None, None, None)
        assert result is None

    def test_context_manager_exit_with_exception(self, mock_db_session):
        """Test BaseReconciler context manager exit with exception parameters."""
        reconciler = BaseReconciler(db=mock_db_session)

        # Test __exit__ method with exception parameters
        exception_type = ValueError
        exception_value = ValueError("Test exception")
        exception_traceback = None

        result = reconciler.__exit__(
            exception_type, exception_value, exception_traceback
        )
        assert result is None

    def test_full_context_manager_usage(self, mock_db_session):
        """Test BaseReconciler used as a full context manager."""
        # Test that it can be used with 'with' statement
        with BaseReconciler(db=mock_db_session) as reconciler:
            assert isinstance(reconciler, BaseReconciler)
            assert reconciler.db == mock_db_session

    def test_logger_configuration(self, mock_db_session):
        """Test that logger is properly configured."""
        reconciler = BaseReconciler(db=mock_db_session)

        # Test logger properties
        assert reconciler.logger.name == "app.reconciler.base"
        assert isinstance(reconciler.logger, logging.Logger)

        # Test that logger can be used for logging
        # This shouldn't raise any exceptions
        reconciler.logger.info("Test log message")
        reconciler.logger.debug("Test debug message")
        reconciler.logger.warning("Test warning message")

    def test_multiple_instances_independent(self, mock_db_session):
        """Test that multiple BaseReconciler instances are independent."""
        session1 = MagicMock()
        session2 = MagicMock()

        reconciler1 = BaseReconciler(db=session1)
        reconciler2 = BaseReconciler(db=session2)

        assert reconciler1.db is session1
        assert reconciler2.db is session2
        assert reconciler1.db is not reconciler2.db

        # Both should have the same logger (Python logging returns same instance for same name)
        assert reconciler1.logger.name == reconciler2.logger.name
        assert reconciler1.logger is reconciler2.logger  # This is expected behavior
