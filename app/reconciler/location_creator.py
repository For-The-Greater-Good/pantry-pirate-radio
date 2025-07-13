"""Location creation utilities for the reconciler."""

import uuid
from typing import Any

from sqlalchemy import text

from app.reconciler.base import BaseReconciler
from app.reconciler.merge_strategy import MergeStrategy
from app.reconciler.version_tracker import VersionTracker


class LocationCreator(BaseReconciler):
    """Utilities for creating location-related records."""

    def find_matching_location(
        self, latitude: float, longitude: float, tolerance: float = 0.0001
    ) -> str | None:
        """Find matching location by coordinates.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            tolerance: Coordinate matching tolerance (4 decimal places = ~11m)

        Returns:
            ID of matching location if found, None otherwise
        """
        query = text(
            """
        SELECT id
        FROM location
        WHERE ABS(latitude - :latitude) < :tolerance
        AND ABS(longitude - :longitude) < :tolerance
        AND is_canonical = TRUE
        LIMIT 1
        """
        )

        result = self.db.execute(
            query,
            {"latitude": latitude, "longitude": longitude, "tolerance": tolerance},
        )
        row = result.first()
        if row:
            return row[0]
        return None

    def create_location(
        self,
        name: str,
        description: str,
        latitude: float,
        longitude: float,
        metadata: dict[str, Any],
        organization_id: str | None = None,
    ) -> str:
        """Create new canonical location.

        Args:
            name: Location name
            description: Location description
            latitude: Location latitude
            longitude: Location longitude
            metadata: Additional metadata
            organization_id: Optional ID of the parent organization

        Returns:
            Location ID
        """
        location_id = str(uuid.uuid4())
        query = text(
            """
        INSERT INTO location (
            id,
            name,
            description,
            latitude,
            longitude,
            organization_id,
            location_type,
            is_canonical
        ) VALUES (
            :id,
            :name,
            :description,
            :latitude,
            :longitude,
            :organization_id,
            'physical',
            TRUE
        )
        """
        )

        self.db.execute(
            query,
            {
                "id": location_id,
                "name": name,
                "description": description,
                "latitude": latitude,
                "longitude": longitude,
                "organization_id": organization_id,
            },
        )
        self.db.commit()

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            location_id,
            "location",
            {
                "name": name,
                "description": description,
                "latitude": latitude,
                "longitude": longitude,
                **metadata,
            },
            "reconciler",
            commit=False,
        )

        # Create source record
        self.create_location_source(
            location_id,
            metadata.get("scraper_id", "unknown"),
            name,
            description,
            latitude,
            longitude,
            metadata,
        )

        return location_id

    def create_location_source(
        self,
        location_id: str,
        scraper_id: str,
        name: str,
        description: str,
        latitude: float,
        longitude: float,
        metadata: dict[str, Any],
    ) -> str:
        """Create new source-specific location record.

        Args:
            location_id: Canonical location ID
            scraper_id: ID of the scraper that found this location
            name: Location name
            description: Location description
            latitude: Location latitude
            longitude: Location longitude
            metadata: Additional metadata

        Returns:
            Source location ID
        """
        source_id = str(uuid.uuid4())
        query = text(
            """
        INSERT INTO location_source (
            id,
            location_id,
            scraper_id,
            name,
            description,
            latitude,
            longitude,
            location_type
        ) VALUES (
            :id,
            :location_id,
            :scraper_id,
            :name,
            :description,
            :latitude,
            :longitude,
            'physical'
        )
        ON CONFLICT (location_id, scraper_id) DO UPDATE SET
            name = :name,
            description = :description,
            latitude = :latitude,
            longitude = :longitude,
            updated_at = NOW()
        RETURNING id
        """
        )

        result = self.db.execute(
            query,
            {
                "id": source_id,
                "location_id": location_id,
                "scraper_id": scraper_id,
                "name": name,
                "description": description,
                "latitude": latitude,
                "longitude": longitude,
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
            "location_source",
            {
                "location_id": location_id,
                "scraper_id": scraper_id,
                "name": name,
                "description": description,
                "latitude": latitude,
                "longitude": longitude,
                **metadata,
            },
            "reconciler",
            source_id=source_id,
            commit=True,
        )

        return source_id

    def process_location(
        self,
        name: str,
        description: str,
        latitude: float,
        longitude: float,
        metadata: dict[str, Any],
        organization_id: str | None = None,
    ) -> tuple[str, bool]:
        """Process a location by finding a match or creating a new one.

        This method implements the core reconciliation logic for locations.
        It first tries to find a matching location by coordinates.
        If a match is found, it creates or updates a source-specific record
        and merges all source records to update the canonical record.
        If no match is found, it creates a new canonical record and source record.

        Args:
            name: Location name
            description: Location description
            latitude: Location latitude
            longitude: Location longitude
            metadata: Additional metadata including scraper_id
            organization_id: Optional ID of the parent organization

        Returns:
            Tuple of (location_id, is_new) where is_new indicates if a new location was created
        """
        # Ensure scraper_id is present
        scraper_id = metadata.get("scraper_id", "unknown")

        # Try to find a matching location
        location_id = self.find_matching_location(latitude, longitude)

        if location_id:
            # Match found - create or update source record
            self.create_location_source(
                location_id,
                scraper_id,
                name,
                description,
                latitude,
                longitude,
                metadata,
            )

            # Update organization_id if provided
            if organization_id:
                query = text(
                    """
                UPDATE location
                SET organization_id = :organization_id
                WHERE id = :id
                """
                )
                self.db.execute(
                    query, {"id": location_id, "organization_id": organization_id}
                )
                self.db.commit()

            # Merge source records to update canonical record
            merge_strategy = MergeStrategy(self.db)
            merge_strategy.merge_location(location_id)

            return location_id, False
        else:
            # No match found - create new canonical and source records
            location_id = self.create_location(
                name, description, latitude, longitude, metadata, organization_id
            )

            return location_id, True

    def create_address(
        self,
        address_1: str,
        city: str,
        state_province: str,
        postal_code: str,
        country: str,
        address_type: str,
        metadata: dict[str, Any],
        location_id: str,
        attention: str | None = None,
        address_2: str | None = None,
        region: str | None = None,
    ) -> str:
        """Create new address.

        Args:
            address_1: First line of address
            city: City name
            state_province: State/province
            postal_code: Postal code
            country: Two-letter country code
            address_type: Type of address
            metadata: Additional metadata
            location_id: Location ID
            attention: Attention line
            address_2: Second line of address
            region: Region name

        Returns:
            Address ID
        """
        # Ensure postal_code is never null to satisfy NOT NULL constraint
        if postal_code is None or postal_code == "":
            # Use a placeholder for missing postal code
            postal_code = "UNKNOWN"
            self.logger.warning(
                f"Missing postal_code for address {address_1}, using placeholder"
            )

        address_id = str(uuid.uuid4())
        query = text(
            """
        INSERT INTO address (
            id,
            location_id,
            attention,
            address_1,
            address_2,
            city,
            region,
            state_province,
            postal_code,
            country,
            address_type
        ) VALUES (
            :id,
            :location_id,
            :attention,
            :address_1,
            :address_2,
            :city,
            :region,
            :state_province,
            :postal_code,
            :country,
            :address_type
        )
        """
        )

        self.db.execute(
            query,
            {
                "id": address_id,
                "location_id": location_id,
                "attention": attention,
                "address_1": address_1,
                "address_2": address_2,
                "city": city,
                "region": region,
                "state_province": state_province,
                "postal_code": postal_code,
                "country": country,
                "address_type": address_type,
            },
        )
        self.db.commit()

        # Update location name to match city
        query = text(
            """
        UPDATE location
        SET name=:name
        WHERE id=:id
        """
        )
        self.db.execute(query, {"id": location_id, "name": city})
        self.db.commit()

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            address_id,
            "address",
            {
                "location_id": location_id,
                "attention": attention,
                "address_1": address_1,
                "address_2": address_2,
                "city": city,
                "region": region,
                "state_province": state_province,
                "postal_code": postal_code,
                "country": country,
                "address_type": address_type,
                **metadata,
            },
            "reconciler",
            commit=True,
        )

        return address_id

    def create_accessibility(
        self,
        location_id: str,
        metadata: dict[str, Any],
        description: str | None = None,
        details: str | None = None,
        url: str | None = None,
    ) -> str:
        """Create new accessibility record.

        Args:
            location_id: Location ID
            metadata: Additional metadata
            description: Description of accessibility
            details: Additional details
            url: URL with more information

        Returns:
            Accessibility ID
        """
        accessibility_id = str(uuid.uuid4())
        query = text(
            """
        INSERT INTO accessibility (
            id,
            location_id,
            description,
            details,
            url
        ) VALUES (
            :id,
            :location_id,
            :description,
            :details,
            :url
        )
        """
        )

        self.db.execute(
            query,
            {
                "id": accessibility_id,
                "location_id": location_id,
                "description": description,
                "details": details,
                "url": url,
            },
        )
        self.db.commit()

        # Create version
        version_tracker = VersionTracker(self.db)
        version_tracker.create_version(
            accessibility_id,
            "accessibility",
            {
                "location_id": location_id,
                "description": description,
                "details": details,
                "url": url,
                **metadata,
            },
            "reconciler",
            commit=True,
        )

        return accessibility_id
