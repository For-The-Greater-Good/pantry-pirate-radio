"""Organization creation utilities for the reconciler."""

import uuid
from typing import Any

from sqlalchemy import text

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
    ) -> tuple[uuid.UUID, bool]:
        """Process an organization by finding a match or creating a new one.

        This method implements the core reconciliation logic for organizations.
        It first tries to find a matching organization by name.
        If a match is found, it creates or updates a source-specific record
        and merges all source records to update the canonical record.
        If no match is found, it creates a new canonical record and source record.

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

        Returns:
            Tuple of (organization_id, is_new) where is_new indicates if a new organization was created
        """
        # Ensure scraper_id is present
        scraper_id = metadata.get("scraper_id", "unknown")

        # Try to find a matching organization by name
        query = text(
            """
        SELECT id FROM organization WHERE name=:name LIMIT 1
        """
        )
        result = self.db.execute(query, {"name": name})
        row = result.first()

        if row:
            # Match found - create or update source record
            organization_id = uuid.UUID(row[0])
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

            # Merge source records to update canonical record
            merge_strategy = MergeStrategy(self.db)
            merge_strategy.merge_organization(str(organization_id))

            return organization_id, False
        else:
            # No match found - create new canonical and source records
            organization_id = self.create_organization(
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
                parent_organization_id=(
                    uuid.UUID(parent_organization_id)
                    if parent_organization_id
                    else None
                ),
            )

            # Create source record
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

            return organization_id, True

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
