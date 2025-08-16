"""Database operations for validation data.

NOTE: The validator service does NOT write to the database directly.
All database writes are handled by the reconciler service.

The validator only:
1. Adds confidence_score, validation_status, and validation_notes to the job data
2. Passes the enriched data to the reconciler queue
3. The reconciler then writes everything to the database

This module is kept minimal for any read-only operations if needed.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ValidationDatabaseHelper:
    """Helper class for validation-related database operations.
    
    This class is kept for backward compatibility but should NOT
    perform any database writes. The reconciler handles all database persistence.
    """

    def __init__(self, session=None):
        """Initialize with optional database session.
        
        Args:
            session: SQLAlchemy database session (not used for writes)
        """
        self.session = session
        logger.debug("ValidationDatabaseHelper initialized (read-only mode)")

    # Note: All write methods have been removed as the validator
    # should not write to the database. The reconciler handles persistence.