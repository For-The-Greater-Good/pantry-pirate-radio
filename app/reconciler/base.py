"""Base reconciler utilities."""

import logging

from sqlalchemy.orm import Session

from app.core.config import settings


class BaseReconciler:
    """Base class for reconciler utilities."""

    def __init__(self, db: Session) -> None:
        """Initialize reconciler utils.

        Args:
            db: Database session
        """
        self.db = db
        self.logger = logging.getLogger(__name__)
        # Get location tolerance from settings
        self.location_tolerance = settings.RECONCILER_LOCATION_TOLERANCE

    def __enter__(self) -> "BaseReconciler":
        """Enter context."""
        return self

    def __exit__(
        self,
        _exc_type: type | None,
        _exc_val: Exception | None,
        _exc_tb: object | None,
    ) -> None:
        """Exit context."""
        pass
