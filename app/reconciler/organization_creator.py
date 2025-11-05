"""Organization creation utilities for the reconciler."""

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


class OrganizationCreator(BaseReconciler):
    """Utilities for creating organization-related records."""

    def create_organization(
        self,
        name: str,
        description: str,
        metadata: dict[str, Any],
        website: str | None = None,
        email: str | None = None,
        year_incorporated: int | None = None,
        legal_status: str | None = None,
        tax_status: str | None = None,
        tax_id: str | None = None,
        uri: str | None = None,
        parent_organization_id: uuid.UUID | None = None,
        confidence_score: int | None = None,
        validation_status: str | None = None,
        validation_notes: dict[str, Any] | None = None,
    ) -> uuid.UUID:
        """Create new organization.

        Args:
            name: Organization name
            description: Organization description
            metadata: Additional metadata
            website: Organization website URL
            email: Organization email
            year_incorporated: Year organization was formed
            legal_status: Legal operating status
            tax_status: Tax status
            tax_id: Tax ID number
            uri: Persistent identifier
            parent_organization_id: Parent org ID if any

        Returns:
            Organization ID
        """
        org_id = uuid.uuid4()
        query = text(
            """
            INSERT INTO organization (
                id,
                name,
                normalized_name,
                description,
                website,
                email,
                year_incorporated,
                legal_status,
                tax_status,
                tax_id,
                uri,
                parent_organization_id,
                confidence_score,
                validation_status,
                validation_notes
            ) VALUES (
                :id,
                :name,
                normalize_organization_name(:name),
                :description,
                :website,
                :email,
                :year_incorporated,
                :legal_status,
                :tax_status,
                :tax_id,
                :uri,
                :parent_organization_id,
                :confidence_score,
                :validation_status,
                :validation_notes
            )
            """
        )

        self.db.execute(
            query,
            {
                "id": str(org_id),
                "name": name,
                "description": description,
                "website": website,
                "email": email,
                "year_incorporated": year_incorporated,
                "legal_status": legal_status,
                "tax_status": tax_status,
                "tax_id": tax_id,
                "uri": uri,
                "parent_organization_id": (
                    str(parent_organization_id) if parent_organization_id else None
                ),
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
            str(org_id),
            "organization",
            {
                "name": name,
                "description": description,
                "website": website,
                "email": email,
                "year_incorporated": year_incorporated,
                "legal_status": legal_status,
                "tax_status": tax_status,
                "tax_id": tax_id,
                "uri": uri,
                "parent_organization_id": (
                    str(parent_organization_id) if parent_organization_id else None
                ),
                **metadata,
            },
            "reconciler",
            commit=True,
        )

        # Return UUID for backward compatibility with tests
        return org_id  # Already a UUID object

    def create_organization_source(
        self,
        organization_id: str,
        scraper_id: str,
        name: str,
        description: str,
        metadata: dict[str, Any],
        website: str | None = None,
        email: str | None = None,
        year_incorporated: int | None = None,
        legal_status: str | None = None,
        tax_status: str | None = None,
        tax_id: str | None = None,
        uri: str | None = None,
        parent_organization_id: str | None = None,
    ) -> str:
        """Create new source-specific organization record.

        Args:
            organization_id: Canonical organization ID
            scraper_id: ID of the scraper that found this organization
            name: Organization name
            description: Organization description
            metadata: Additional metadata
            website: Organization website URL
            email: Organization email
            year_incorporated: Year organization was formed
            legal_status: Legal operating status
            tax_status: Tax status
            tax_id: Tax ID number
            uri: Persistent identifier
            parent_organization_id: Parent org ID if any

        Returns:
            Source organization ID
        """
        source_id = str(uuid.uuid4())
        query = text(
            """
            INSERT INTO organization_source (
                id,
                organization_id,
                scraper_id,
                name,
                description,
                website,
                email,
                year_incorporated,
                legal_status,
                tax_status,
                tax_id,
                uri,
                parent_organization_id
            ) VALUES (
                :id,
                :organization_id,
                :scraper_id,
                :name,
                :description,
                :website,
                :email,
                :year_incorporated,
                :legal_status,
                :tax_status,
                :tax_id,
                :uri,
                :parent_organization_id
            )
            ON CONFLICT (organization_id, scraper_id) DO UPDATE SET
                name = :name,
                description = :description,
                website = :website,
                email = :email,
                year_incorporated = :year_incorporated,
                legal_status = :legal_status,
                tax_status = :tax_status,
                tax_id = :tax_id,
                uri = :uri,
                parent_organization_id = :parent_organization_id,
                updated_at = NOW()
            RETURNING id
            """
        )

        result = self.db.execute(
            query,
            {
                "id": source_id,
                "organization_id": organization_id,
                "scraper_id": scraper_id,
                "name": name,
                "description": description,
                "website": website,
                "email": email,
                "year_incorporated": year_incorporated,
                "legal_status": legal_status,
                "tax_status": tax_status,
                "tax_id": tax_id,
                "uri": uri,
                "parent_organization_id": parent_organization_id,
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
            "organization_source",
            {
                "organization_id": organization_id,
                "scraper_id": scraper_id,
                "name": name,
                "description": description,
                "website": website,
                "email": email,
                "year_incorporated": year_incorporated,
                "legal_status": legal_status,
                "tax_status": tax_status,
                "tax_id": tax_id,
                "uri": uri,
                "parent_organization_id": parent_organization_id,
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
                # Rollback the failed transaction before retrying
                self.db.rollback()

                if attempt == max_attempts - 1:
                    # Log constraint violation for monitoring
                    self._log_constraint_violation(
                        "organization",
                        "INSERT",
                        {"error": str(e), "attempt": attempt + 1},
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

    def process_organization(
        self,
        name: str,
        description: str,
        metadata: dict[str, Any],
        website: str | None = None,
        email: str | None = None,
        year_incorporated: int | None = None,
        legal_status: str | None = None,
        tax_status: str | None = None,
        tax_id: str | None = None,
        uri: str | None = None,
        parent_organization_id: str | None = None,
        confidence_score: int | None = None,
        validation_status: str | None = None,
        validation_notes: dict[str, Any] | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
    ) -> tuple[uuid.UUID, bool]:
        """Process an organization by finding a match or creating a new one.

        This method implements proximity-based deduplication for organizations.
        Organizations with the same name can exist in different geographic locations
        (e.g., "Food Bank" in NYC and LA are separate entities).

        Args:
            name: Organization name
            description: Organization description
            metadata: Additional metadata including scraper_id
            website: Organization website URL
            email: Organization email
            year_incorporated: Year organization was formed
            legal_status: Legal operating status
            tax_status: Tax status
            tax_id: Tax ID number
            uri: Persistent identifier
            parent_organization_id: Parent org ID if any
            confidence_score: Confidence score from validation
            validation_status: Validation status
            validation_notes: Validation notes
            latitude: Latitude of organization's primary location (for proximity matching)
            longitude: Longitude of organization's primary location (for proximity matching)

        Returns:
            Tuple of (organization_id, is_new) where is_new indicates if a new organization was created
        """
        scraper_id = metadata.get("scraper_id", "unknown")

        # Proximity threshold for considering organizations as the same
        # 0.01 degrees is approximately 0.7 miles
        PROXIMITY_THRESHOLD = 0.01

        # If we have location data, check for proximity-based matches
        if latitude is not None and longitude is not None:
            proximity_check = text(
                """
                SELECT find_matching_organization(:name, :lat, :lon, :threshold)
                """
            )

            result = self.db.execute(
                proximity_check,
                {
                    "name": name,
                    "lat": latitude,
                    "lon": longitude,
                    "threshold": PROXIMITY_THRESHOLD,
                },
            )

            matched_org_id = result.scalar()
            if matched_org_id:
                # Found an organization with same name at this location
                self.logger.info(
                    f"Found existing organization '{name}' at location ({latitude}, {longitude})"
                )

                # Update the source record
                self.create_organization_source(
                    str(matched_org_id),
                    scraper_id,
                    name,
                    description,
                    metadata,
                    website=website,
                    email=email,
                    year_incorporated=year_incorporated,
                    legal_status=legal_status,
                    tax_status=tax_status,
                    tax_id=tax_id,
                    uri=uri,
                    parent_organization_id=parent_organization_id,
                )

                # Merge source records to update canonical record
                merge_strategy = MergeStrategy(self.db)
                merge_strategy.merge_organization(str(matched_org_id))

                return uuid.UUID(str(matched_org_id)), False

        def _create_or_find_organization():
            # No proximity match found or no location provided
            # Create new organization (allowing same names in different locations)
            org_id = uuid.uuid4()

            # Insert new organization without name conflict checking
            query = text(
                """
                INSERT INTO organization (
                    id, name, normalized_name, description, website, email, year_incorporated,
                    legal_status, tax_status, tax_id, uri, parent_organization_id,
                    confidence_score, validation_status, validation_notes
                ) VALUES (
                    :id, :name, normalize_organization_name(:name), :description, :website, :email, :year_incorporated,
                    :legal_status, :tax_status, :tax_id, :uri, :parent_organization_id,
                    :confidence_score, :validation_status, :validation_notes
                )
                RETURNING id, TRUE AS is_new
            """
            )

            result = self.db.execute(
                query,
                {
                    "id": str(org_id),
                    "name": name,
                    "description": description,
                    "website": website if website else None,
                    "email": email if email else None,
                    "year_incorporated": (
                        year_incorporated if year_incorporated else None
                    ),
                    "legal_status": legal_status if legal_status else None,
                    "tax_status": tax_status,
                    "tax_id": tax_id,
                    "uri": uri if uri else None,
                    "parent_organization_id": parent_organization_id,
                    "confidence_score": confidence_score,
                    "validation_status": validation_status,
                    "validation_notes": (
                        json.dumps(validation_notes) if validation_notes else None
                    ),
                },
            )

            row = result.first()
            if not row:
                raise RuntimeError("INSERT failed to return a row")

            org_uuid = uuid.UUID(row[0])
            is_new = row[1]

            self.logger.info(
                f"Created new organization '{name}' with ID {org_uuid}"
                + (
                    f" at location ({latitude}, {longitude})"
                    if latitude and longitude
                    else ""
                )
            )

            return org_uuid, is_new

        # Execute with retry logic
        organization_id, is_new = self._retry_with_backoff(_create_or_find_organization)
        # Always create or update source record (this also has ON CONFLICT)
        self.create_organization_source(
            str(organization_id),
            scraper_id,
            name,
            description,
            metadata,
            website=website,
            email=email,
            year_incorporated=year_incorporated,
            legal_status=legal_status,
            tax_status=tax_status,
            tax_id=tax_id,
            uri=uri,
            parent_organization_id=parent_organization_id,
        )

        # Create version record for canonical organization
        if is_new:
            version_tracker = VersionTracker(self.db)
            version_tracker.create_version(
                str(organization_id),
                "organization",
                {
                    "name": name,
                    "description": description,
                    "website": website,
                    "email": email,
                    "year_incorporated": year_incorporated,
                    "legal_status": legal_status,
                    "tax_status": tax_status,
                    "tax_id": tax_id,
                    "uri": uri,
                    "parent_organization_id": parent_organization_id,
                    **metadata,
                },
                "reconciler",
                commit=True,
            )

        # Merge source records to update canonical record (if not new)
        if not is_new:
            merge_strategy = MergeStrategy(self.db)
            merge_strategy.merge_organization(str(organization_id))

        return organization_id, is_new

    def create_organization_identifier(
        self, organization_id: uuid.UUID, identifier_type: str, identifier: str
    ) -> uuid.UUID:
        """Create new organization identifier.

        Args:
            organization_id: Organization ID
            identifier_type: Type of identifier
            identifier: Identifier value

        Returns:
            Organization identifier ID
        """
        identifier_id = uuid.uuid4()
        query = text(
            """
            INSERT INTO organization_identifier (
                id,
                organization_id,
                identifier_type,
                identifier
            ) VALUES (
                :id,
                :organization_id,
                :identifier_type,
                :identifier
            )
            """
        )

        self.db.execute(
            query,
            {
                "id": str(identifier_id),
                "organization_id": str(organization_id),
                "identifier_type": identifier_type,
                "identifier": identifier,
            },
        )
        self.db.commit()

        return identifier_id
