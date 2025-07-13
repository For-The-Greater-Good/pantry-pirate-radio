"""Location creation utilities for the reconciler."""

import uuid
import time
import secrets
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.reconciler.base import BaseReconciler
from app.reconciler.merge_strategy import MergeStrategy
from app.reconciler.version_tracker import VersionTracker


class LocationCreator(BaseReconciler):
    """Utilities for creating location-related records."""

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
                    self._log_constraint_violation("location", "INSERT", {
                        "error": str(e),
                        "attempt": attempt + 1
                    })
                    raise
                
                # Calculate delay with jitter to avoid thundering herd
                delay = base_delay * (backoff_multiplier ** attempt)
                jitter = secrets.SystemRandom().uniform(0.1, 0.3) * delay
                time.sleep(delay + jitter)
                
                self.logger.warning(
                    f"Constraint violation on attempt {attempt + 1}, retrying in {delay + jitter:.3f}s",
                    extra={"error": str(e), "attempt": attempt + 1}
                )
        
        # This should never be reached, but satisfy type checker
        raise RuntimeError("Unexpected end of retry loop")

    def _log_constraint_violation(self, table_name: str, operation: str, data: dict[str, Any]) -> None:
        """Log constraint violation for monitoring and debugging."""
        try:
            log_query = text("""
                INSERT INTO reconciler_constraint_violations 
                (constraint_name, table_name, operation, conflicting_data)
                VALUES (:constraint_name, :table_name, :operation, :conflicting_data)
            """)
            self.db.execute(log_query, {
                "constraint_name": data.get("error", "unknown"),
                "table_name": table_name,
                "operation": operation,
                "conflicting_data": json.dumps(data)
            })
            self.db.commit()
        except Exception as e:
            # Don't let logging failures break the main operation
            self.logger.error(f"Failed to log constraint violation: {e}")

    def find_matching_location(
        self, latitude: float, longitude: float, tolerance: float = 0.0001
    ) -> str | None:
        """Find matching location by coordinates (backward compatibility wrapper).

        Args:
            latitude: Location latitude
            longitude: Location longitude
            tolerance: Coordinate matching tolerance (4 decimal places = ~11m)

        Returns:
            ID of matching location if found, None otherwise
        """
        return self.find_matching_location_with_lock(latitude, longitude, tolerance)

    def find_matching_location_with_lock(
        self, latitude: float, longitude: float, tolerance: float = 0.0001
    ) -> str | None:
        """Find matching location by coordinates using advisory locks for consistency.

        Args:
            latitude: Location latitude
            longitude: Location longitude
            tolerance: Coordinate matching tolerance (4 decimal places = ~11m)

        Returns:
            ID of matching location if found, None otherwise
        """
        # Acquire advisory lock for coordinate area to prevent concurrent modifications
        lock_query = text("SELECT acquire_location_lock(:lat, :lon)")
        lock_result = self.db.execute(lock_query, {"lat": latitude, "lon": longitude})
        lock_id = lock_result.scalar()
        
        try:
            # Use the database function for consistent coordinate matching
            query = text("""
                SELECT id
                FROM location
                WHERE location_coordinates_match(:lat1, :lon1, latitude, longitude, :tolerance)
                AND is_canonical = TRUE
                ORDER BY ABS(latitude - :lat1) + ABS(longitude - :lon1)
                LIMIT 1
                FOR UPDATE SKIP LOCKED
            """)

            result = self.db.execute(query, {
                "lat1": latitude,
                "lon1": longitude,
                "tolerance": tolerance
            })
            row = result.first()
            return row[0] if row else None
            
        finally:
            # Always release the advisory lock
            release_query = text("SELECT release_location_lock(:lock_id)")
            self.db.execute(release_query, {"lock_id": lock_id})
            self.db.commit()

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

        This method implements race-condition-safe reconciliation logic for locations.
        It uses coordinate-based matching with advisory locks to prevent concurrent
        workers from creating duplicate locations at the same coordinates.

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
        scraper_id = metadata.get("scraper_id", "unknown")
        tolerance = 0.0001  # ~11m tolerance for coordinate matching
        
        def _create_or_find_location():
            # Acquire advisory lock for this coordinate area
            lock_query = text("SELECT acquire_location_lock(:lat, :lon)")
            lock_result = self.db.execute(lock_query, {"lat": latitude, "lon": longitude})
            lock_id = lock_result.scalar()
            
            try:
                # First, check if a location exists at these coordinates
                match_query = text("""
                    SELECT id
                    FROM location
                    WHERE location_coordinates_match(:lat1, :lon1, latitude, longitude, :tolerance)
                    AND is_canonical = TRUE
                    ORDER BY ABS(latitude - :lat1) + ABS(longitude - :lon1)
                    LIMIT 1
                    FOR UPDATE
                """)
                
                result = self.db.execute(match_query, {
                    "lat1": latitude,
                    "lon1": longitude,
                    "tolerance": tolerance
                })
                row = result.first()
                
                if row:
                    # Found existing location
                    return row[0], False
                
                # No existing location found, create new one
                location_id = str(uuid.uuid4())
                
                insert_query = text("""
                    INSERT INTO location (
                        id, name, description, latitude, longitude,
                        organization_id, location_type, is_canonical
                    ) VALUES (
                        :id, :name, :description, :latitude, :longitude,
                        :organization_id, 'physical', TRUE
                    )
                    RETURNING id
                """)
                
                insert_result = self.db.execute(insert_query, {
                    "id": location_id,
                    "name": name,
                    "description": description,
                    "latitude": latitude,
                    "longitude": longitude,
                    "organization_id": organization_id,
                })
                
                new_row = insert_result.first()
                if not new_row:
                    raise RuntimeError("Failed to create location")
                    
                return new_row[0], True
                
            finally:
                # Always release the advisory lock
                release_query = text("SELECT release_location_lock(:lock_id)")
                self.db.execute(release_query, {"lock_id": lock_id})
                self.db.commit()

        # Execute with retry logic
        location_id, is_new = self._retry_with_backoff(_create_or_find_location)
        
        # Always create or update source record (this has ON CONFLICT)
        self.create_location_source(
            location_id,
            scraper_id,
            name,
            description,
            latitude,
            longitude,
            metadata,
        )

        # Create version record for new canonical location
        if is_new:
            version_tracker = VersionTracker(self.db)
            version_tracker.create_version(
                location_id,
                "location",
                {
                    "name": name,
                    "description": description,
                    "latitude": latitude,
                    "longitude": longitude,
                    "organization_id": organization_id,
                    **metadata,
                },
                "reconciler",
                commit=True,
            )
        else:
            # Update organization_id if provided and different
            if organization_id:
                update_query = text("""
                    UPDATE location
                    SET organization_id = :organization_id
                    WHERE id = :id AND (organization_id IS NULL OR organization_id != :organization_id)
                """)
                self.db.execute(update_query, {
                    "id": location_id, 
                    "organization_id": organization_id
                })
                self.db.commit()

            # Merge source records to update canonical record
            merge_strategy = MergeStrategy(self.db)
            merge_strategy.merge_location(location_id)

        return location_id, is_new

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
