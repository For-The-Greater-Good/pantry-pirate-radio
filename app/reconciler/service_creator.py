"""Service creation utilities for the reconciler."""

import uuid
import time
import secrets
import json
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.reconciler.base import BaseReconciler
from app.reconciler.merge_strategy import MergeStrategy
from app.reconciler.version_tracker import VersionTracker


class ServiceCreator(BaseReconciler):
    """Utilities for creating service-related records."""

    def create_service(
        self,
        name: str,
        description: str,
        organization_id: uuid.UUID | None,
        metadata: dict[str, Any],
        confidence_score: int | None = None,
        validation_status: str | None = None,
        validation_notes: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Create new service.

        Args:
            name: Service name
            description: Service description
            organization_id: Optional ID of organization providing service
            metadata: Additional metadata

        Returns:
            Service ID
        """
        service_id = uuid.uuid4()
        query = text(
            """
            INSERT INTO service (
                id,
                name,
                description,
                organization_id,
                status,
                confidence_score,
                validation_status,
                validation_notes
            ) VALUES (
                :id,
                :name,
                :description,
                :organization_id,
                'active',
                :confidence_score,
                :validation_status,
                :validation_notes
            )
            """
        )

        self.db.execute(
            query,
            {
                "id": str(service_id),
                "name": name,
                "description": description,
                "organization_id": str(organization_id) if organization_id else None,
                "confidence_score": confidence_score,
                "validation_status": validation_status,
                "validation_notes": (
                    json.dumps(validation_notes) if validation_notes else None
                ),
            },
        )
        self.db.commit()

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            str(service_id),
            "service",
            {
                "name": name,
                "description": description,
                "organization_id": str(organization_id) if organization_id else None,
                "status": "active",
                **metadata,
            },
            "reconciler",
            commit=True,
        )

        # Already returns UUID for backward compatibility
        return service_id

    def create_service_source(
        self,
        service_id: str,
        scraper_id: str,
        name: str,
        description: str,
        organization_id: str | None,
        metadata: dict[str, Any],
    ) -> str:
        """Create new source-specific service record.

        Args:
            service_id: Canonical service ID
            scraper_id: ID of the scraper that found this service
            name: Service name
            description: Service description
            organization_id: Optional ID of organization providing service
            metadata: Additional metadata

        Returns:
            Source service ID
        """
        source_id = str(uuid.uuid4())
        query = text(
            """
            INSERT INTO service_source (
                id,
                service_id,
                scraper_id,
                name,
                description,
                organization_id,
                status
            ) VALUES (
                :id,
                :service_id,
                :scraper_id,
                :name,
                :description,
                :organization_id,
                'active'
            )
            ON CONFLICT (service_id, scraper_id) DO UPDATE SET
                name = :name,
                description = :description,
                organization_id = :organization_id,
                status = 'active',
                updated_at = NOW()
            RETURNING id
            """
        )

        result = self.db.execute(
            query,
            {
                "id": source_id,
                "service_id": service_id,
                "scraper_id": scraper_id,
                "name": name,
                "description": description,
                "organization_id": organization_id,
            },
        )
        row = result.first()
        if row:
            source_id = row[0]
        self.db.commit()

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            source_id,
            "service_source",
            {
                "service_id": service_id,
                "scraper_id": scraper_id,
                "name": name,
                "description": description,
                "organization_id": organization_id,
                "status": "active",
                **metadata,
            },
            "reconciler",
            source_id=source_id,
            commit=True,
        )

        return source_id

    def _retry_with_backoff(self, operation, max_attempts: int = 3) -> Any:
        """Execute operation with exponential backoff retry on constraint violations.

        Args:
            operation: Callable that performs the database operation
            max_attempts: Maximum number of retry attempts

        Returns:
            Result of the operation

        Raises:
            IntegrityError: If all retry attempts fail
        """
        base_delay = 0.1  # 100ms base delay
        backoff_multiplier = 2.0

        for attempt in range(max_attempts):
            try:
                return operation()
            except IntegrityError as e:
                if attempt == max_attempts - 1:
                    # Log constraint violation for monitoring
                    self._log_constraint_violation(
                        "service", "INSERT", {"error": str(e), "attempt": attempt + 1}
                    )
                    raise

                # Calculate delay with jitter to avoid thundering herd
                delay = base_delay * (backoff_multiplier**attempt)
                jitter = secrets.SystemRandom().uniform(0.1, 0.3) * delay
                time.sleep(delay + jitter)

                self.logger.warning(
                    f"Constraint violation on attempt {attempt + 1}, retrying in {delay + jitter:.3f}s",
                    extra={"error": str(e), "attempt": attempt + 1},
                )

        # This should never be reached, but satisfy type checker
        raise RuntimeError("Unexpected end of retry loop")

    def _log_constraint_violation(
        self, table_name: str, operation: str, data: dict[str, Any]
    ) -> None:
        """Log constraint violation for monitoring and debugging."""
        try:
            log_query = text(
                """
                INSERT INTO reconciler_constraint_violations
                (constraint_name, table_name, operation, conflicting_data)
                VALUES (:constraint_name, :table_name, :operation, :conflicting_data)
            """
            )
            self.db.execute(
                log_query,
                {
                    "constraint_name": data.get("error", "unknown"),
                    "table_name": table_name,
                    "operation": operation,
                    "conflicting_data": json.dumps(data),
                },
            )
            self.db.commit()
        except Exception as e:
            # Don't let logging failures break the main operation
            self.logger.error(f"Failed to log constraint violation: {e}")

    def process_service(
        self,
        name: str,
        description: str,
        organization_id: uuid.UUID | None,
        metadata: dict[str, Any],
        confidence_score: int | None = None,
        validation_status: str | None = None,
        validation_notes: dict[str, Any] | None = None,
    ) -> tuple[uuid.UUID, bool]:
        """Process a service by finding a match or creating a new one.

        This method implements race-condition-safe reconciliation logic for services.
        It uses INSERT...ON CONFLICT to atomically handle service creation based on
        name and organization combination.

        Args:
            name: Service name
            description: Service description
            organization_id: Optional ID of organization providing service
            metadata: Additional metadata including scraper_id

        Returns:
            Tuple of (service_id, is_new) where is_new indicates if a new service was created
        """
        scraper_id = metadata.get("scraper_id", "unknown")

        def _create_or_find_service():
            # Use INSERT...ON CONFLICT to atomically create or find service
            service_id = uuid.uuid4()

            query = text(
                """
                INSERT INTO service (
                    id, name, description, organization_id, status,
                    confidence_score, validation_status, validation_notes
                ) VALUES (
                    :id, :name, :description, :organization_id, 'active',
                    :confidence_score, :validation_status, :validation_notes
                )
                ON CONFLICT (name, organization_id) DO UPDATE SET
                    description = COALESCE(EXCLUDED.description, service.description),
                    status = 'active',
                    confidence_score = COALESCE(EXCLUDED.confidence_score, service.confidence_score),
                    validation_status = COALESCE(EXCLUDED.validation_status, service.validation_status),
                    validation_notes = COALESCE(EXCLUDED.validation_notes, service.validation_notes)
                RETURNING id, (xmax = 0) AS is_new
            """
            )

            result = self.db.execute(
                query,
                {
                    "id": str(service_id),
                    "name": name,
                    "description": description,
                    "organization_id": (
                        str(organization_id) if organization_id else None
                    ),
                    "confidence_score": confidence_score,
                    "validation_status": validation_status,
                    "validation_notes": (
                        json.dumps(validation_notes) if validation_notes else None
                    ),
                },
            )

            row = result.first()
            if not row:
                raise RuntimeError("INSERT...ON CONFLICT failed to return a row")

            svc_uuid = uuid.UUID(row[0])
            is_new = row[1]

            return svc_uuid, is_new

        # Execute with retry logic
        service_id, is_new = self._retry_with_backoff(_create_or_find_service)
        # Always create or update source record (this also has ON CONFLICT)
        self.create_service_source(
            str(service_id),
            scraper_id,
            name,
            description,
            str(organization_id) if organization_id else None,
            metadata,
        )

        # Create version record for new canonical service
        if is_new:
            version_tracker = VersionTracker(self.db)
            version_tracker.create_version(
                str(service_id),
                "service",
                {
                    "name": name,
                    "description": description,
                    "organization_id": (
                        str(organization_id) if organization_id else None
                    ),
                    "status": "active",
                    **metadata,
                },
                "reconciler",
                commit=True,
            )
        else:
            # Merge source records to update canonical record
            merge_strategy = MergeStrategy(self.db)
            merge_strategy.merge_service(str(service_id))

        return service_id, is_new

    def create_service_at_location(
        self,
        service_id: uuid.UUID,
        location_id: uuid.UUID,
        description: str | None,
        metadata: dict[str, Any],
    ) -> uuid.UUID:
        """Create new service at location.

        Args:
            service_id: ID of the service
            location_id: ID of the location
            description: Optional description specific to this location
            metadata: Additional metadata

        Returns:
            Service at location ID
        """
        sal_id = uuid.uuid4()
        query = text(
            """
            INSERT INTO service_at_location (
                id,
                service_id,
                location_id,
                description
            ) VALUES (
                :id,
                :service_id,
                :location_id,
                :description
            )
            """
        )

        self.db.execute(
            query,
            {
                "id": str(sal_id),
                "service_id": str(service_id),
                "location_id": str(location_id),
                "description": description,
            },
        )
        self.db.commit()

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            str(sal_id),
            "service_at_location",
            {
                "service_id": str(service_id),
                "location_id": str(location_id),
                "description": description,
                **metadata,
            },
            "reconciler",
            commit=True,
        )

        return sal_id

    def create_phone(
        self,
        number: str,
        phone_type: str,
        metadata: dict[str, Any],
        organization_id: uuid.UUID | None = None,
        service_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        contact_id: uuid.UUID | None = None,
        service_at_location_id: uuid.UUID | None = None,
        extension: int | None = None,
        description: str | None = None,
        transaction: Session | None = None,
    ) -> uuid.UUID:
        """Create new phone number.

        Args:
            number: Phone number
            phone_type: Type of phone service
            metadata: Additional metadata
            organization_id: Organization ID if applicable
            service_id: Service ID if applicable
            location_id: Location ID if applicable
            contact_id: Contact ID if applicable
            service_at_location_id: Service at location ID if applicable
            extension: Phone extension
            description: Additional description
            transaction: Optional transaction to use

        Returns:
            Phone ID
        """
        # Skip creation if no valid phone number provided
        if not number or number.strip() == "":
            self.logger.debug(
                "No phone number provided, skipping phone record creation"
            )
            return None  # Don't create invalid phone records

        # Clean the phone number
        number = number.strip()

        # Basic validation - skip if obviously invalid
        if number.upper() in ["UNKNOWN", "INVALID", "N/A", "NA", "NONE"]:
            self.logger.warning(
                f"Invalid phone placeholder '{number}', skipping creation"
            )
            return None

        # Check if it has at least some digits (allow for formatted numbers)
        if not any(char.isdigit() for char in number):
            self.logger.warning(f"Phone number '{number}' contains no digits, skipping")
            return None

        phone_id = uuid.uuid4()
        query = text(
            """
        INSERT INTO phone (
            id,
            number,
            type,
            organization_id,
            service_id,
            location_id,
            contact_id,
            service_at_location_id,
            extension,
            description
        ) VALUES (
            :id,
            :number,
            :type,
            :organization_id,
            :service_id,
            :location_id,
            :contact_id,
            :service_at_location_id,
            :extension,
            :description
        )
        """
        )

        db = transaction or self.db
        db.execute(
            query,
            {
                "id": str(phone_id),
                "number": number,
                "type": phone_type or "voice",  # Default to "voice" if type is empty
                "organization_id": str(organization_id) if organization_id else None,
                "service_id": str(service_id) if service_id else None,
                "location_id": str(location_id) if location_id else None,
                "contact_id": str(contact_id) if contact_id else None,
                "service_at_location_id": (
                    str(service_at_location_id) if service_at_location_id else None
                ),
                "extension": extension,
                "description": description,
            },
        )

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            str(phone_id),
            "phone",
            {
                "number": number,
                "type": phone_type
                or "voice",  # Ensure type is never NULL in version tracking too
                "organization_id": str(organization_id) if organization_id else None,
                "service_id": str(service_id) if service_id else None,
                "location_id": str(location_id) if location_id else None,
                "contact_id": str(contact_id) if contact_id else None,
                "service_at_location_id": (
                    str(service_at_location_id) if service_at_location_id else None
                ),
                "extension": extension,
                "description": description,
                **metadata,
            },
            "reconciler",
            commit=not transaction,
        )

        return phone_id

    def create_language(
        self,
        metadata: dict[str, Any],
        name: str | None = None,
        code: str | None = None,
        note: str | None = None,
        service_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        phone_id: uuid.UUID | None = None,
    ) -> uuid.UUID:
        """Create new language.

        Args:
            metadata: Additional metadata
            name: Language name
            code: ISO language code
            note: Additional notes
            service_id: Service ID if applicable
            location_id: Location ID if applicable
            phone_id: Phone ID if applicable

        Returns:
            Language ID
        """
        language_id = uuid.uuid4()
        query = text(
            """
        INSERT INTO language (
            id,
            name,
            code,
            note,
            service_id,
            location_id,
            phone_id
        ) VALUES (
            :id,
            :name,
            :code,
            :note,
            :service_id,
            :location_id,
            :phone_id
        )
        """
        )

        self.db.execute(
            query,
            {
                "id": str(language_id),
                "name": name,
                "code": code,
                "note": note,
                "service_id": str(service_id) if service_id else None,
                "location_id": str(location_id) if location_id else None,
                "phone_id": str(phone_id) if phone_id else None,
            },
        )

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            str(language_id),
            "language",
            {
                "name": name,
                "code": code,
                "note": note,
                "service_id": str(service_id) if service_id else None,
                "location_id": str(location_id) if location_id else None,
                "phone_id": str(phone_id) if phone_id else None,
                **metadata,
            },
            "reconciler",
            commit=False,
        )

        self.db.commit()

        return language_id

    def create_schedule(
        self,
        freq: str,
        wkst: str,
        opens_at: str,
        closes_at: str,
        metadata: dict[str, Any],
        service_id: uuid.UUID | None = None,
        location_id: uuid.UUID | None = None,
        service_at_location_id: uuid.UUID | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        dtstart: str | None = None,
        until: str | None = None,
        count: str | None = None,
        interval: int | None = None,
        byday: str | None = None,
        description: str | None = None,
    ) -> uuid.UUID:
        """Create new schedule.

        Args:
            freq: Frequency(WEEKLY/MONTHLY)
            wkst: Week start day
            opens_at: Opening time
            closes_at: Closing time
            metadata: Additional metadata
            service_id: Service ID if applicable
            location_id: Location ID if applicable
            service_at_location_id: Service at location ID if applicable
            valid_from: Start date of validity
            valid_to: End date of validity
            dtstart: First event date
            until: Last event date
            count: Number of occurrences
            interval: Frequency interval
            byday: Days of week
            description: Additional description

        Returns:
            Schedule ID
        """
        schedule_id = uuid.uuid4()
        query = text(
            """
        INSERT INTO schedule (
            id,
            freq,
            wkst,
            opens_at,
            closes_at,
            service_id,
            location_id,
            service_at_location_id,
            valid_from,
            valid_to,
            dtstart,
            until,
            count,
            interval,
            byday,
            description
        ) VALUES (
            :id,
            :freq,
            :wkst,
            :opens_at,
            :closes_at,
            :service_id,
            :location_id,
            :service_at_location_id,
            :valid_from,
            :valid_to,
            :dtstart,
            :until,
            :count,
            :interval,
            :byday,
            :description
        )
        """
        )

        # Convert time strings to time objects (handle None values)
        opens_at_time = (
            datetime.strptime(opens_at, "%H:%M").time() if opens_at else None
        )
        closes_at_time = (
            datetime.strptime(closes_at, "%H:%M").time() if closes_at else None
        )

        self.db.execute(
            query,
            {
                "id": str(schedule_id),
                "freq": freq,
                "wkst": wkst,
                "opens_at": opens_at_time,
                "closes_at": closes_at_time,
                "service_id": str(service_id) if service_id else None,
                "location_id": str(location_id) if location_id else None,
                "service_at_location_id": (
                    str(service_at_location_id) if service_at_location_id else None
                ),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "dtstart": dtstart,
                "until": until,
                "count": count,
                "interval": interval,
                "byday": byday,
                "description": description,
            },
        )

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            str(schedule_id),
            "schedule",
            {
                "freq": freq,
                "wkst": wkst,
                "opens_at": opens_at,
                "closes_at": closes_at,
                "service_id": str(service_id) if service_id else None,
                "location_id": str(location_id) if location_id else None,
                "service_at_location_id": (
                    str(service_at_location_id) if service_at_location_id else None
                ),
                "valid_from": valid_from,
                "valid_to": valid_to,
                "dtstart": dtstart,
                "until": until,
                "count": count,
                "interval": interval,
                "byday": byday,
                "description": description,
                **metadata,
            },
            "reconciler",
            commit=False,
        )

        self.db.commit()

        return schedule_id

    def delete_schedules_for_service_at_location(
        self, service_at_location_id: uuid.UUID
    ) -> int:
        """Delete all schedules for a specific service_at_location.

        Args:
            service_at_location_id: Service at location ID

        Returns:
            Number of schedules deleted
        """
        query = text(
            """
            DELETE FROM schedule
            WHERE service_at_location_id = :service_at_location_id
            """
        )

        result = self.db.execute(
            query,
            {"service_at_location_id": str(service_at_location_id)},
        )

        self.db.commit()
        deleted_count = result.rowcount

        if deleted_count > 0:
            self.logger.info(
                f"Deleted {deleted_count} existing schedules for service_at_location {service_at_location_id}"
            )

        return deleted_count

    def delete_schedules_for_service(self, service_id: uuid.UUID) -> int:
        """Delete all schedules for a specific service.

        Args:
            service_id: Service ID

        Returns:
            Number of schedules deleted
        """
        query = text(
            """
            DELETE FROM schedule
            WHERE service_id = :service_id
            """
        )

        result = self.db.execute(
            query,
            {"service_id": str(service_id)},
        )

        self.db.commit()
        deleted_count = result.rowcount

        if deleted_count > 0:
            self.logger.info(
                f"Deleted {deleted_count} existing schedules for service {service_id}"
            )

        return deleted_count

    def delete_schedules_for_location(self, location_id: uuid.UUID) -> int:
        """Delete all schedules for a specific location.

        Args:
            location_id: Location ID

        Returns:
            Number of schedules deleted
        """
        query = text(
            """
            DELETE FROM schedule
            WHERE location_id = :location_id
            """
        )

        result = self.db.execute(
            query,
            {"location_id": str(location_id)},
        )

        self.db.commit()
        deleted_count = result.rowcount

        if deleted_count > 0:
            self.logger.info(
                f"Deleted {deleted_count} existing schedules for location {location_id}"
            )

        return deleted_count
