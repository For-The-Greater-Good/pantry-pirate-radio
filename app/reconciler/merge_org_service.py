"""Organization + service + field-provenance merge for the reconciler.

Extracted from ``merge_strategy.py`` (Principle IX responsibility boundary,
federation P2 Slice 1) as a MIXIN so ``MergeStrategy`` keeps its single public API
(``MergeStrategy(db).merge_organization`` / ``.merge_service`` / ``.get_field_sources``)
with ZERO behaviour change: the methods are relocated verbatim and still resolve
``self.db``, ``self.logger`` (from ``BaseReconciler``) and ``self._row_to_dict``
(defined on ``MergeStrategy``) on the composed instance. Splitting this out keeps
both files under the 600-line limit while *location*-record merging stays in
``merge_strategy.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    import logging

    from sqlalchemy.orm import Session


class OrgServiceMergeMixin:
    """Organization, service, and field-provenance merge methods for MergeStrategy.

    Holds no state and defines no ``__init__``. The attributes/method below are
    provided by the composed ``MergeStrategy`` (``db``/``logger`` via
    ``BaseReconciler``; ``_row_to_dict`` on ``MergeStrategy``); declared here under
    ``TYPE_CHECKING`` only so the type checker sees them — at runtime they resolve
    via the MRO, never shadowing the real implementations.
    """

    if TYPE_CHECKING:
        db: Session
        logger: logging.Logger

        def _row_to_dict(self, row: Any, result: Any) -> dict[str, Any]: ...

    def merge_organization(self, organization_id: str) -> None:
        """Merge source-specific organization records into a canonical record.

        Args:
            organization_id: ID of the canonical organization
        """
        # Get all source records for this organization
        query = text(
            """
        SELECT
            id,
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
            created_at,
            updated_at
        FROM organization_source
        WHERE organization_id = :organization_id
        ORDER BY updated_at DESC
        """
        )

        result = self.db.execute(query, {"organization_id": organization_id})

        # Handle the result safely
        rows = result.fetchall()
        if not rows:
            self.logger.warning(
                f"No source records found for organization {organization_id}"
            )
            return

        try:
            # Use safer conversion method
            source_records = [self._row_to_dict(row, result) for row in rows]

            # Filter out any empty records (conversion failures)
            valid_records = [record for record in source_records if record]

            # If no valid records after conversion, fall back
            if not valid_records:
                self.logger.warning(
                    f"No valid source records after conversion for organization {organization_id}"
                )
                raise ValueError("No valid source records after conversion")

        except Exception as e:
            # Log the error and check the actual data structure
            self.logger.error(f"Error converting result to dict: {e}")
            self.logger.debug(f"First row type: {type(rows[0]) if rows else 'None'}")
            self.logger.debug(f"First row contents: {rows[0] if rows else 'None'}")
            self.logger.debug(
                f"Column names: {result.keys() if hasattr(result, 'keys') else 'Not available'}"
            )

            # If rows are UUIDs or strings, it might be that the organization_source table doesn't exist
            self.logger.warning(
                f"Falling back to default merge strategy for organization {organization_id}"
            )

            # Query the main organization table instead
            fallback_query = text(
                """
            SELECT
                id,
                name,
                description,
                website,
                email,
                year_incorporated,
                legal_status,
                tax_status,
                tax_id,
                uri
            FROM organization
            WHERE id = :organization_id
            """
            )

            fallback_result = self.db.execute(
                fallback_query, {"organization_id": organization_id}
            )
            fallback_row = fallback_result.first()

            if not fallback_row:
                self.logger.error(
                    f"Could not find organization with ID {organization_id}"
                )
                return

            # Use the organization record as is - no merging needed
            self.logger.info(
                f"Using existing organization record for {organization_id} without merging"
            )
            return

        # Apply merging strategy to create canonical record
        merged_data = self._merge_organization_data(valid_records)

        # Update canonical record — COALESCE preserves existing non-null
        # values when no source provides a replacement
        update_query = text(
            """
        UPDATE organization
        SET
            name = :name,
            description = :description,
            website = COALESCE(:website, website),
            email = COALESCE(:email, email),
            year_incorporated = COALESCE(:year_incorporated, year_incorporated),
            legal_status = COALESCE(:legal_status, legal_status),
            tax_status = COALESCE(:tax_status, tax_status),
            tax_id = COALESCE(:tax_id, tax_id),
            uri = COALESCE(:uri, uri)
        WHERE id = :id
        """
        )

        self.db.execute(
            update_query,
            {
                "id": organization_id,
                "name": merged_data["name"],
                "description": merged_data["description"],
                "website": merged_data["website"],
                "email": merged_data["email"],
                "year_incorporated": merged_data["year_incorporated"],
                "legal_status": merged_data["legal_status"],
                "tax_status": merged_data["tax_status"],
                "tax_id": merged_data["tax_id"],
                "uri": merged_data["uri"],
            },
        )
        self.db.commit()

        self.logger.info(
            f"Merged {len(valid_records)} source records for organization {organization_id}"
        )

    def _merge_organization_data(
        self, source_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Merge organization data from multiple source records.

        This implements the merging strategy for organization data.

        Args:
            source_records: List of source records to merge

        Returns:
            Merged organization data
        """
        # Start with the most recently updated record as the base
        merged = dict(source_records[0])

        # For name: Use the most common value (majority vote)
        name_counts: dict[str, int] = {}
        for record in source_records:
            name = record["name"]
            name_counts[name] = name_counts.get(name, 0) + 1

        # Find the name with the highest count
        merged["name"] = max(name_counts.items(), key=lambda x: x[1])[0]

        # For description: Use the longest non-empty description
        descriptions = [r["description"] for r in source_records if r["description"]]
        if descriptions:
            merged["description"] = max(descriptions, key=len)

        # For other fields: Use the first non-empty value
        for field in [
            "website",
            "email",
            "year_incorporated",
            "legal_status",
            "tax_status",
            "tax_id",
            "uri",
        ]:
            for record in source_records:
                if record[field]:
                    merged[field] = record[field]
                    break

        return merged

    def merge_service(self, service_id: str) -> None:
        """Merge source-specific service records into a canonical record.

        Args:
            service_id: ID of the canonical service
        """
        # Get all source records for this service
        query = text(
            """
        SELECT
            id,
            scraper_id,
            name,
            description,
            organization_id,
            status,
            created_at,
            updated_at
        FROM service_source
        WHERE service_id = :service_id
        ORDER BY updated_at DESC
        """
        )

        result = self.db.execute(query, {"service_id": service_id})

        # Handle the result safely
        rows = result.fetchall()
        if not rows:
            self.logger.warning(f"No source records found for service {service_id}")
            return

        try:
            # Use safer conversion method
            source_records = [self._row_to_dict(row, result) for row in rows]
        except Exception as e:
            # Log the error and check the actual data structure
            self.logger.error(f"Error converting result to dict: {e}")
            self.logger.debug(f"First row type: {type(rows[0]) if rows else 'None'}")
            self.logger.debug(f"First row contents: {rows[0] if rows else 'None'}")
            self.logger.debug(
                f"Column names: {result.keys() if hasattr(result, 'keys') else 'Not available'}"
            )

            # If rows are UUIDs or strings, it might be that the service_source table doesn't exist
            # In this case, we need to create a default merged record
            self.logger.warning(
                f"Falling back to default merge strategy for service {service_id}"
            )

            # Query the main service table instead
            fallback_query = text(
                """
            SELECT
                id,
                name,
                description,
                organization_id,
                status
            FROM service
            WHERE id = :service_id
            """
            )

            fallback_result = self.db.execute(
                fallback_query, {"service_id": service_id}
            )
            fallback_row = fallback_result.first()

            if not fallback_row:
                self.logger.error(f"Could not find service with ID {service_id}")
                return

            # Use the service record as is - no merging needed
            self.logger.info(
                f"Using existing service record for {service_id} without merging"
            )
            return

        # Apply merging strategy to create canonical record
        merged_data = self._merge_service_data(source_records)

        # Update canonical record
        update_query = text(
            """
        UPDATE service
        SET
            name = :name,
            description = :description,
            organization_id = :organization_id,
            status = :status
        WHERE id = :id
        """
        )

        self.db.execute(
            update_query,
            {
                "id": service_id,
                "name": merged_data["name"],
                "description": merged_data["description"],
                "organization_id": merged_data["organization_id"],
                "status": merged_data["status"],
            },
        )
        self.db.commit()

        self.logger.info(
            f"Merged {len(source_records)} source records for service {service_id}"
        )

    def _merge_service_data(
        self, source_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Merge service data from multiple source records.

        This implements the merging strategy for service data.

        Args:
            source_records: List of source records to merge

        Returns:
            Merged service data
        """
        # Start with the most recently updated record as the base
        merged = dict(source_records[0])

        # For name: Use the most common value (majority vote)
        name_counts: dict[str, int] = {}
        for record in source_records:
            name = record["name"]
            name_counts[name] = name_counts.get(name, 0) + 1

        # Find the name with the highest count
        merged["name"] = max(name_counts.items(), key=lambda x: x[1])[0]

        # For description: Use the longest non-empty description
        descriptions = [r["description"] for r in source_records if r["description"]]
        if descriptions:
            merged["description"] = max(descriptions, key=len)

        # For organization_id: Use the most common value
        org_counts: dict[str, int] = {}
        for record in source_records:
            org_id = record["organization_id"]
            if org_id:
                org_counts[org_id] = org_counts.get(org_id, 0) + 1

        if org_counts:
            merged["organization_id"] = max(org_counts.items(), key=lambda x: x[1])[0]

        # For status: Use the most recent value (already set from the most recent record)

        return merged

    def get_field_sources(self, record_type: str, record_id: str) -> dict[str, str]:
        """Get the source of each field in a canonical record.

        Args:
            record_type: Type of record (location, organization, service)
            record_id: ID of the canonical record

        Returns:
            Dictionary mapping field names to scraper IDs
        """
        if record_type == "location":
            query = text(
                """
            SELECT
                l.name as canonical_name,
                l.description as canonical_description,
                l.latitude as canonical_latitude,
                l.longitude as canonical_longitude,
                ls.scraper_id,
                ls.name as source_name,
                ls.description as source_description,
                ls.latitude as source_latitude,
                ls.longitude as source_longitude
            FROM location l
            JOIN location_source ls ON l.id = ls.location_id
            WHERE l.id = :record_id AND l.is_canonical = TRUE
            """
            )
        elif record_type == "organization":
            query = text(
                """
            SELECT
                o.name as canonical_name,
                o.description as canonical_description,
                o.website as canonical_website,
                o.email as canonical_email,
                os.scraper_id,
                os.name as source_name,
                os.description as source_description,
                os.website as source_website,
                os.email as source_email
            FROM organization o
            JOIN organization_source os ON o.id = os.organization_id
            WHERE o.id = :record_id
            """
            )
        elif record_type == "service":
            query = text(
                """
            SELECT
                s.name as canonical_name,
                s.description as canonical_description,
                s.organization_id as canonical_organization_id,
                s.status as canonical_status,
                ss.scraper_id,
                ss.name as source_name,
                ss.description as source_description,
                ss.organization_id as source_organization_id,
                ss.status as source_status
            FROM service s
            JOIN service_source ss ON s.id = ss.service_id
            WHERE s.id = :record_id
            """
            )
        else:
            raise ValueError(f"Unsupported record type: {record_type}")

        result = self.db.execute(query, {"record_id": record_id})
        rows = result.fetchall()

        if not rows:
            return {}

        # Map fields to their sources
        field_sources: dict[str, str] = {}

        # Get the canonical values from the first row
        canonical_values = {
            k: v for k, v in dict(rows[0]).items() if k.startswith("canonical_")
        }

        # For each field, find which source matches the canonical value
        for row in rows:
            row_dict = dict(row)
            scraper_id = row_dict["scraper_id"]

            for canonical_field, canonical_value in canonical_values.items():
                field_name = canonical_field.replace("canonical_", "")
                source_field = f"source_{field_name}"

                if row_dict[source_field] == canonical_value:
                    field_sources[field_name] = scraper_id

        return field_sources
