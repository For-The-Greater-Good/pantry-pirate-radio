"""Tests for the reconciler module."""

import pytest
from unittest.mock import MagicMock, patch
from app.reconciler.reconciler import Reconciler


class TestReconciler:
    """Test cases for Reconciler class."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock database session."""
        return MagicMock()

    def test_reconciler_initialization(self, mock_db):
        """Test reconciler initialization."""
        reconciler = Reconciler(mock_db)
        assert reconciler.db == mock_db

    def test_reconciler_str(self, mock_db):
        """Test reconciler string representation."""
        reconciler = Reconciler(mock_db)
        result = str(reconciler)
        assert "Reconciler" in result

    def test_reconciler_repr(self, mock_db):
        """Test reconciler repr."""
        reconciler = Reconciler(mock_db)
        result = repr(reconciler)
        assert "Reconciler" in result
