"""Merge strategy for reconciling source-specific records into canonical records."""

import logging
from typing import Any, Protocol

from sqlalchemy import text
from sqlalchemy.engine.row import Row
from sqlalchemy.orm import Session

from app.reconciler.base import BaseReconciler
from app.reconciler.drift_events import publish_drift_event
from app.reconciler.merge_org_service import OrgServiceMergeMixin
from app.validator.scoring import HUMAN_VERIFIED_SOURCES


# Define a Protocol to represent any SQLAlchemy result object with keys method
class HasKeys(Protocol):
    def keys(self) -> Any: ...


class MergeStrategy(OrgServiceMergeMixin, BaseReconciler):
    """Strategy for merging source-specific records into canonical records."""

    def __init__(self, db: Session) -> None:
        """Initialize merge strategy.

        Args:
            db: Database session
        """
        super().__init__(db)
        self.logger = logging.getLogger(__name__)

    def _fetch_existing_verification(self, location_id: str) -> dict[str, Any] | None:
        """Return the current verified_by value for a location, or None.

        Used by merge/update paths to skip canonical writes that would
        silently overwrite data curated by an authoritative human writer.
        """
        result = self.db.execute(
            text("SELECT verified_by FROM location WHERE id = :id"),
            {"id": location_id},
        ).first()
        if result is None:
            return None
        return {"verified_by": result[0]}

    def _fetch_canonical_for_drift(self, location_id: str) -> dict[str, Any] | None:
        """Fetch the current canonical fields we compare against for drift.

        Kept narrow: only the fields a scraper can realistically diverge
        on in a way a claimant would want to see (name, description).
        Coordinates drift every scrape due to geocoder noise — we skip
        those to avoid alarm fatigue.
        """
        result = self.db.execute(
            text(
                "SELECT name, description FROM location WHERE id = :id",
            ),
            {"id": location_id},
        ).first()
        if result is None:
            return None
        return {"name": result[0], "description": result[1]}

    def _emit_drift_events(
        self,
        *,
        location_id: str,
        merged: dict[str, Any],
        canonical: dict[str, Any],
        valid_records: list[dict[str, Any]],
    ) -> None:
        """Emit one drift event per field that diverges between the
        scraper-merged data and the canonical owner-curated data.

        The scraper name is inferred from the first source record with
        a populated scraper_id — good enough for the "which source
        disagreed" message without threading scraper metadata through
        the whole merge path.
        """
        scraper_name = "unknown"
        for r in valid_records:
            sid = r.get("scraper_id") or r.get("scraper_name")
            if sid:
                scraper_name = str(sid)
                break

        for field in ("name", "description"):
            merged_val = merged.get(field)
            canonical_val = canonical.get(field)
            # Treat "nothing vs nothing" and matching strings as no-drift.
            if (merged_val or "") == (canonical_val or ""):
                continue
            publish_drift_event(
                location_id=str(location_id),
                scraper_name=scraper_name,
                field_name=field,
                scraper_value="" if merged_val is None else str(merged_val),
                canonical_value=("" if canonical_val is None else str(canonical_val)),
            )

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
                self.logger.warning(
                    f"Result type: {type(result)}, has keys: {hasattr(result, 'keys')}"
                )
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

    def merge_location(
        self, location_id: str, current_confidence_score: int | None = None
    ) -> int | None:
        """Merge source-specific location records into a canonical record.

        Args:
            location_id: ID of the canonical location
            current_confidence_score: Current confidence score for source corroboration

        Returns:
            Updated confidence score if source bonus applied, None otherwise
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
        AND (source_type = 'scraper' OR source_type IS NULL)
        ORDER BY updated_at DESC
        """
        )

        result = self.db.execute(query, {"location_id": location_id})
        rows = result.fetchall()

        if not rows:
            self.logger.warning(f"No source records found for location {location_id}")
            return None

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
                return None

            # Use the location record as is - no merging needed
            self.logger.info(
                f"Using existing location record for {location_id} without merging"
            )
            return None

        # Apply merging strategy to create canonical record
        merged_data = self._merge_location_data(valid_records)

        # Source corroboration: count distinct sources and apply the bonus
        # (extracted to app/reconciler/corroboration.py — the seam P2 §12.1 widens
        # from distinct scraper_id to distinct ORIGIN DID).
        updated_score = None
        if current_confidence_score is not None:
            from app.reconciler.corroboration import apply_corroboration

            updated_score = apply_corroboration(current_confidence_score, valid_records)

        # Update canonical record.
        # When verified_by identifies an authoritative human writer
        # (admin/source/claimed), preserve every canonical field — name,
        # description, coordinates, score, status — from the existing row so
        # scraper merges never silently overwrite owner-curated data.
        # Scraper-origin changes still land in `location_source` for
        # provenance; the delta is surfaced to claim owners separately.
        # See app/validator/scoring.py:HUMAN_VERIFIED_SOURCES.
        existing = self._fetch_existing_verification(location_id)
        if existing and existing["verified_by"] in HUMAN_VERIFIED_SOURCES:
            self.logger.info(
                "merge_location_owner_protected",
                extra={
                    "location_id": location_id,
                    "verified_by": existing["verified_by"],
                    "scraper_count": len(valid_records),
                },
            )
            # Emit source-drift events for the fields the scraper merge
            # would have changed had protection not been in place. The
            # ppr-lighthouse owner dashboard reads these off SNS →
            # DriftEvents and renders a per-location callout.
            canonical = self._fetch_canonical_for_drift(location_id)
            if canonical:
                self._emit_drift_events(
                    location_id=str(location_id),
                    merged=merged_data,
                    canonical=canonical,
                    valid_records=valid_records,
                )
            # Only keep the is_canonical=TRUE housekeeping; skip content writes.
            self.db.execute(
                text("UPDATE location SET is_canonical = TRUE WHERE id = :id"),
                {"id": location_id},
            )
            self.db.commit()
            self.logger.info(
                f"Merged {len(valid_records)} source records for location "
                f"{location_id} (owner-protected — canonical untouched)"
            )
            return None

        update_query = text(
            """
        UPDATE location
        SET
            name = :name,
            description = :description,
            latitude = :latitude,
            longitude = :longitude,
            is_canonical = TRUE,
            confidence_score = COALESCE(:confidence_score, confidence_score),
            validation_status = CASE
                WHEN :confidence_score IS NOT NULL AND :confidence_score >= 80 THEN 'verified'
                WHEN :confidence_score IS NOT NULL AND :confidence_score >= 10 THEN 'needs_review'
                WHEN :confidence_score IS NOT NULL THEN 'rejected'
                ELSE validation_status
            END
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
                "confidence_score": updated_score,
            },
        )
        self.db.commit()

        self.logger.info(
            f"Merged {len(valid_records)} source records for location {location_id}"
        )

        return updated_score

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
