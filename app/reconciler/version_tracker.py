"""Version tracking utilities for the reconciler."""

import json
from typing import Any

from sqlalchemy import text

from app.reconciler.base import BaseReconciler
from app.reconciler.metrics import RECORD_VERSIONS


class VersionTracker(BaseReconciler):
    """Utilities for tracking record versions."""

    def create_version(
        self,
        record_id: Any,  # Can be UUID or str
        record_type: str,
        data: dict[str, Any],
        created_by: str,
        source_id: str | None = None,
        commit: bool = True,
    ) -> None:
        """Create new version of a record.

        Args:
            record_id: ID of record being versioned
            record_type: Type of record(organization, service, location)
            data: Complete record data
            created_by: What created this version
            source_id: Optional ID of the source record
            commit: Whether to commit the transaction(default True)
        """
        # Insert new version with auto-incrementing version number
        query = text(
            """
        WITH next_version AS (
            SELECT COALESCE(MAX(version_num), 0) + 1 as version_num
            FROM record_version
            WHERE record_id=:record_id
            AND record_type=:record_type
        )
        INSERT INTO record_version (
            record_id,
            record_type,
            version_num,
            data,
            created_by,
            source_id
        )
        SELECT :record_id,
            :record_type,
            version_num,
            :data,
            :created_by,
            :source_id
        FROM next_version
        """
        )

        self.db.execute(
            query,
            {
                "record_id": record_id,
                "record_type": record_type,
                "data": json.dumps(data),
                "created_by": created_by,
                "source_id": source_id,
            },
        )
        if commit:
            self.db.commit()

        # Update metrics
        RECORD_VERSIONS.labels(record_type=record_type).inc()
