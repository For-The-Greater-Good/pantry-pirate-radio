"""Merge strategy for reconciling source-specific records into canonical records."""

import logging
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.engine.row import Row
from sqlalchemy.orm import Session

from app.reconciler.base import BaseReconciler


# Define a Protocol to represent any SQLAlchemy result object with keys method
class HasKeys(Protocol):
    def keys(self) -> Any: ...


class MergeStrategy(BaseReconciler):
    """Strategy for merging source-specific records into canonical records."""

    def __init__(self, db: Session) -> None:
        """Initialize merge strategy.

        Args:
            db: Database session
        """
        super().__init__(db)
        self.logger = logging.getLogger(__name__)

    def _row_to_dict(self, row: Any, result: HasKeys) -> dict[str, Any]:
        """Convert a SQLAlchemy row to a dictionary regardless of result format.

        Args:
            row: SQLAlchemy result row
            result: SQLAlchemy result object with keys/column names

        Returns:
            Dictionary representation of the row
        """
        # Handle the case where row is a UUID string (36 chars with dashes)
        if isinstance(row, str):
            # Check if it looks like a UUID
            if len(row) == 36 and row.count("-") == 4:
                self.logger.warning(f"Row appears to be a UUID string: {row}")
                self.logger.warning(f"Result type: {type(result)}, has keys: {hasattr(result, 'keys')}")
                # This shouldn't happen in normal operation
                column_names = list(result.keys()) if hasattr(result, "keys") else []
                self.logger.warning(f"Column names from result: {column_names}")
                if len(column_names) == 1:
                    return {column_names[0]: row}
                else:
                    self.logger.error(
                        f"UUID string row with unexpected columns: {row}, columns: {column_names}"
                    )
                    return {}
            # Handle other string cases
            column_names = list(result.keys()) if hasattr(result, "keys") else []
            if len(column_names) == 1:
                return {column_names[0]: row}
            else:
                self.logger.error(
                    f"String value row with multiple columns: {row}, columns: {column_names}"
                )
                return {}

        # If the row is already a mapping or dict-like, use it directly
        if hasattr(row, "items") and callable(row.items):
            try:
                return dict(row)
            except (TypeError, ValueError) as e:
                self.logger.error(
                    f"Failed to convert row with items() to dict: {e}, row type: {type(row)}"
                )
                return {}

        # SQLAlchemy 1.4+ style with _mapping attribute (Row objects)
        if isinstance(row, Row):
            try:
                # Try using _mapping attribute first (SQLAlchemy 1.4+)
                if hasattr(row, "_mapping"):
                    return dict(row._mapping)
                # Try _asdict method
                elif hasattr(row, "_asdict") and callable(row._asdict):
                    return row._asdict()
                # Try direct iteration with column names
                else:
                    column_names = (
                        list(result.keys()) if hasattr(result, "keys") else []
                    )
                    return dict(zip(column_names, row, strict=False))
            except (TypeError, ValueError) as e:
                self.logger.error(f"Failed to convert Row to dict: {e}")
                # Try one more fallback - iterate over row with indices
                try:
                    column_names = (
                        list(result.keys()) if hasattr(result, "keys") else []
                    )
                    return {column_names[i]: row[i] for i in range(len(column_names))}
                except Exception as e2:
                    self.logger.error(f"Final fallback also failed: {e2}")
                    return {}

        # SQLAlchemy named tuple style with _asdict method
        elif hasattr(row, "_asdict") and callable(row._asdict):
            try:
                return dict(row._asdict())
            except (TypeError, ValueError) as e:
                self.logger.error(f"Failed to convert row with _asdict() to dict: {e}")
                return {}

        # Manual mapping using column names and values
        else:
            column_names = list(result.keys()) if hasattr(result, "keys") else []
            # Handle case where row might be a single value instead of tuple
            if not hasattr(row, "__iter__"):
                # Single value result - likely just the ID
                if len(column_names) == 1:
                    return {column_names[0]: row}
                else:
                    # This shouldn't happen but log it
                    self.logger.error(
                        f"Single non-iterable value with multiple columns: {row}, columns: {column_names}"
                    )
                    return {}

            try:
                return dict(zip(column_names, row, strict=False))
            except (TypeError, ValueError) as e:
                self.logger.error(
                    f"Failed to zip columns with row values: {e}, row: {row}, columns: {column_names}"
                )
                return {}

    def merge_location(self, location_id: str) -> None:
        """Merge source-specific location records into a canonical record.

        Args:
            location_id: ID of the canonical location
        """
        # Get all source records for this location
        query = text(
            """
        SELECT
            id,
            scraper_id,
            name,
            description,
            latitude,
            longitude,
            created_at,
            updated_at
        FROM location_source
        WHERE location_id = :location_id
        ORDER BY updated_at DESC
        """
        )

        result = self.db.execute(query, {"location_id": location_id})
        rows = result.fetchall()

        if not rows:
            self.logger.warning(f"No source records found for location {location_id}")
            return

        # Debug logging to understand what we're getting
        self.logger.debug(f"Query returned {len(rows)} rows for location {location_id}")
        if rows:
            self.logger.debug(f"First row type: {type(rows[0])}, value: {rows[0]}")

        try:
            # Use safer conversion method
            source_records = [self._row_to_dict(row, result) for row in rows]

            # Filter out any empty records (conversion failures)
            valid_records = [record for record in source_records if record]

            # If no valid records after conversion, fall back
            if not valid_records:
                self.logger.warning(
                    f"No valid source records after conversion for location {location_id}"
                )
                raise ValueError("No valid source records after conversion")

        except Exception as e:
            # Log error with more details
            self.logger.error(f"Error converting result to dict: {e}")
            self.logger.debug(f"First row type: {type(rows[0]) if rows else 'None'}")
            self.logger.debug(f"First row contents: {rows[0] if rows else 'None'}")
            self.logger.debug(
                f"Column names: {result.keys() if hasattr(result, 'keys') else 'Not available'}"
            )

            # Fallback to existing behavior
            self.logger.warning(
                f"Falling back to default merge strategy for location {location_id}"
            )

            # Query the main location table instead
            fallback_query = text(
                """
            SELECT
                id,
                name,
                description,
                latitude,
                longitude
            FROM location
            WHERE id = :location_id
            """
            )

            fallback_result = self.db.execute(
                fallback_query, {"location_id": location_id}
            )
            fallback_row = fallback_result.first()

            if not fallback_row:
                self.logger.error(f"Could not find location with ID {location_id}")
                return

            # Use the location record as is - no merging needed
            self.logger.info(
                f"Using existing location record for {location_id} without merging"
            )
            return

        # Apply merging strategy to create canonical record
        merged_data = self._merge_location_data(valid_records)

        # Update canonical record
        update_query = text(
            """
        UPDATE location
        SET
            name = :name,
            description = :description,
            latitude = :latitude,
            longitude = :longitude,
            is_canonical = TRUE
        WHERE id = :id
        """
        )

        self.db.execute(
            update_query,
            {
                "id": location_id,
                "name": merged_data["name"],
                "description": merged_data["description"],
                "latitude": merged_data["latitude"],
                "longitude": merged_data["longitude"],
            },
        )
        self.db.commit()

        self.logger.info(
            f"Merged {len(valid_records)} source records for location {location_id}"
        )

    def _merge_location_data(
        self, source_records: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Merge location data from multiple source records.

        This implements the merging strategy for location data.

        Args:
            source_records: List of source records to merge

        Returns:
            Merged location data
        """
        # Start with the most recently updated record as the base
        merged = dict(source_records[0])

        # For each field, apply the appropriate merging strategy
        # This is a simple implementation that could be enhanced with more sophisticated strategies

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

        # For coordinates: Use the most recent values
        # (already set from the most recent record)

        return merged

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

        # Update canonical record
        update_query = text(
            """
        UPDATE organization
        SET
            name = :name,
            description = :description,
            website = :website,
            email = :email,
            year_incorporated = :year_incorporated,
            legal_status = :legal_status,
            tax_status = :tax_status,
            tax_id = :tax_id,
            uri = :uri
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
