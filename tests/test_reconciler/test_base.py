"""Tests for the base reconciler class."""

from unittest.mock import MagicMock

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session

from app.reconciler.base import BaseReconciler


@pytest.fixture
def mock_db(mocker: MockerFixture) -> MagicMock:
    """Create a mock database session."""
    db = MagicMock(spec=Session)
    db.commit.return_value = None

    # Mock database result
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result

    return db


def test_base_reconciler_init(mock_db: MagicMock) -> None:
    """Test BaseReconciler initialization."""
    reconciler = BaseReconciler(mock_db)
    assert reconciler.db == mock_db
    assert reconciler.logger is not None


def test_base_reconciler_context_manager(mock_db: MagicMock) -> None:
    """Test BaseReconciler as context manager."""
    with BaseReconciler(mock_db) as reconciler:
        assert reconciler.db == mock_db


def test_base_reconciler_context_manager_with_error(mock_db: MagicMock) -> None:
    """Test BaseReconciler context manager handles errors."""
    with pytest.raises(ValueError):
        with BaseReconciler(mock_db):
            raise ValueError("Test error")
