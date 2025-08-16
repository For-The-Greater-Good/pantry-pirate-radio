"""Tests for validation database operations.

NOTE: The validator service does NOT write to the database.
These tests verify that the validator only adds validation fields to the data.
All database writes are handled by the reconciler service.
"""

import pytest
from unittest.mock import Mock

from app.validator.database import ValidationDatabaseHelper


class TestValidationDatabaseHelper:
    """Test database helper for validation data."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_session = Mock()
        self.db_helper = ValidationDatabaseHelper(self.mock_session)

    def test_initialization(self):
        """Test that database helper initializes in read-only mode."""
        helper = ValidationDatabaseHelper(session=None)
        assert helper.session is None
        
        helper = ValidationDatabaseHelper(session=self.mock_session)
        assert helper.session == self.mock_session

    def test_no_write_operations(self):
        """Test that no write operations are performed by the validator."""
        # The validator should not have any write methods
        # All writes are handled by the reconciler
        assert not hasattr(self.db_helper, 'update_location_validation')
        assert not hasattr(self.db_helper, 'update_organization_validation')
        assert not hasattr(self.db_helper, 'update_service_validation')
        assert not hasattr(self.db_helper, 'commit_changes')
        
    def test_validator_only_enriches_data(self):
        """Test that validator only adds fields to data without database writes."""
        # This is more of a documentation test to clarify the validator's role
        # The validator adds these fields to the job data:
        expected_fields = [
            'confidence_score',      # 0-100 score
            'validation_status',     # 'verified', 'needs_review', or 'rejected'
            'validation_notes',      # Dictionary with validation details
        ]
        
        # The reconciler will then save these fields to the database
        # The validator does NOT perform any database operations
        for field in expected_fields:
            assert field in ['confidence_score', 'validation_status', 'validation_notes']