"""Service creation utilities for the reconciler."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

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
            status
        ) VALUES (
            :id,
            :name,
            :description,
            :organization_id,
            'active'
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

    def process_service(
        self,
        name: str,
        description: str,
        organization_id: uuid.UUID | None,
        metadata: dict[str, Any],
    ) -> tuple[uuid.UUID, bool]:
        """Process a service by finding a match or creating a new one.

        This method implements the core reconciliation logic for services.
        It first tries to find a matching service by name and organization.
        If a match is found, it creates or updates a source-specific record
        and merges all source records to update the canonical record.
        If no match is found, it creates a new canonical record and source record.

        Args:
            name: Service name
            description: Service description
            organization_id: Optional ID of organization providing service
            metadata: Additional metadata including scraper_id

        Returns:
            Tuple of (service_id, is_new) where is_new indicates if a new service was created
        """
        # Ensure scraper_id is present
        scraper_id = metadata.get("scraper_id", "unknown")

        # Try to find a matching service by name and organization
        query = text(
            """
        SELECT id FROM service
        WHERE name=:name
        AND (organization_id=:organization_id OR (organization_id IS NULL AND :organization_id IS NULL))
        LIMIT 1
        """
        )
        result = self.db.execute(
            query,
            {
                "name": name,
                "organization_id": str(organization_id) if organization_id else None,
            },
        )
        row = result.first()

        if row:
            # Match found - create or update source record
            service_id = uuid.UUID(row[0])
            self.create_service_source(
                str(service_id),
                scraper_id,
                name,
                description,
                str(organization_id) if organization_id else None,
                metadata,
            )

            # Merge source records to update canonical record
            merge_strategy = MergeStrategy(self.db)
            merge_strategy.merge_service(str(service_id))

            return service_id, False
        else:
            # No match found - create new canonical and source records
            service_id = self.create_service(
                name, description, organization_id, metadata
            )

            # Create source record
            self.create_service_source(
                str(service_id),
                scraper_id,
                name,
                description,
                str(organization_id) if organization_id else None,
                metadata,
            )

            return service_id, True

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
        # Ensure number is never NULL - use a placeholder if empty
        if not number:
            number = (
                "UNKNOWN"  # Use a placeholder that's clearly not a real phone number
            )
            self.logger.warning("Empty phone number provided, using placeholder")

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

        # Convert time strings to time objects
        opens_at_time = datetime.strptime(opens_at, "%H:%M").time()
        closes_at_time = datetime.strptime(closes_at, "%H:%M").time()

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
