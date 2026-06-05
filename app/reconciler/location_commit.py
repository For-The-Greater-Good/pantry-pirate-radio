"""Per-location commit logic for the reconciler.

Extracted from job_processor.py per Constitution Principle IX (file size limits).
Owns the cohesive responsibility of committing a single (already HSDS-shaped)
location dict to the database: preprocessing (validation-data extraction,
coordinate/address normalization), match resolution (submarine direct-id vs.
coordinate matching), and the two terminal commit branches —
``_commit_matched_location`` (update an existing canonical row) and
``_commit_new_location`` (create a new one). Those two methods are the single,
clean sites where downstream work (e.g. a federation-log ``Update`` hook)
attaches.

The handler is constructed once per job with the job-scoped collaborators and
context, then ``process_location`` is called per location. This is a pure
extraction of behavior previously inline in ``JobProcessor.process_job_result``;
logic, ordering, transaction boundaries, and side effects are unchanged.
"""

import logging
import re
import uuid
from typing import Any, Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.llm.queue.models import JobResult
from app.reconciler.location_creator import LocationCreator
from app.reconciler.location_match import LocationPreprocessor
from app.reconciler.merge_strategy import MergeStrategy
from app.reconciler.service_creator import ServiceCreator
from app.reconciler.submarine_location_handler import SubmarineLocationHandler
from app.reconciler.version_tracker import VersionTracker

# Stdlib logger matching the original job_processor module logger, so log
# message format and capture (e.g. pytest caplog) behavior is unchanged.
logger = logging.getLogger("app.reconciler.job_processor")

# Phone-shaped patterns for last-resort extraction from narrative text. Kept
# verbatim from the original inline blocks in job_processor.py.
_PHONE_PATTERNS = [
    r"\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}",
    r"\d{3}[-.\s]\d{3}[-.\s]\d{4}",
    r"\d{10}",
    r"1[-.\s]?\d{3}[-.\s]?\d{3}[-.\s]?\d{4}",
    r"1[-.\s]?8\d{2}[-.\s]?[A-Z]{3}[-.\s]?[A-Z]{4}",
]


class LocationCommitHandler:
    """Commits a single location (matched-update or new-create) to the DB.

    Built once per job with the job-scoped collaborators/context; call
    ``process_location`` once per location in the job's HSDS data.
    """

    def __init__(
        self,
        db: Session,
        *,
        validation_data: dict[str, Any] | None,
        job_result: JobResult,
        location_creator: LocationCreator,
        service_creator: ServiceCreator,
        location_ids: dict[str, uuid.UUID],
        location_key_fn: Callable[[dict], str],
        transform_schedule_fn: Callable[[dict], dict | None],
    ) -> None:
        self.db = db
        self.validation_data = validation_data
        self.job_result = job_result
        self.location_creator = location_creator
        self.service_creator = service_creator
        self.location_ids = location_ids
        self.location_key_fn = location_key_fn
        self.transform_schedule_fn = transform_schedule_fn
        self.metadata = job_result.job.metadata
        # Preprocessing + coordinate-match resolution lives in a sibling module
        # (Principle IX); this handler keeps both terminal commit branches.
        self.preprocessor = LocationPreprocessor(
            db,
            validation_data=validation_data,
            location_creator=location_creator,
        )

    def process_location(
        self,
        location: dict[str, Any],
        org_id: uuid.UUID | None,
    ) -> uuid.UUID | None:
        """Preprocess, match, and commit a single location.

        ``location`` is mutated in place (coordinate/address normalization) so
        the post-mutation dict remains the one stored in ``data["location"]``
        and keyed by ``location_key_fn`` downstream. For a newly created
        location this also records the new id in ``location_ids``. Returns the
        committed location id, or ``None`` if skipped (rejected by validator, no
        coordinates, or unresolved submarine target).
        """
        validation = self.preprocessor.extract_validation(location)
        loc_validation_status = validation[1]

        # Skip locations marked as rejected by validator.
        if loc_validation_status == "rejected":
            logger.warning(
                f"Location '{location.get('name')}' rejected: "
                f"confidence={validation[0]}, notes={validation[2]}"
            )
            return None

        self.preprocessor.normalize_coordinates(location)
        self.preprocessor.normalize_address(location)

        # Resolve location match — submarine uses direct ID, standard path uses
        # coordinate matching.
        submarine_handler = SubmarineLocationHandler(self.db)
        is_submarine = submarine_handler.is_submarine_job(self.metadata)

        if is_submarine:
            match_id = submarine_handler.resolve_target_location(self.metadata)
            if match_id is None:
                return None
        # Trust the validator's coordinates - no geocoding needed here. The
        # validator has already enriched and validated coordinates.
        elif (
            "latitude" in location
            and "longitude" in location
            and location["latitude"] is not None
            and location["longitude"] is not None
        ):
            match_id = self.preprocessor.find_coordinate_match(location, org_id)
        else:
            # No coordinates from validator - this location should have been
            # rejected.
            location_name = location.get("name", "Unknown")
            logger.warning(
                f"Skipping location '{location_name}' - no coordinates after "
                f"validation"
            )
            return None

        if match_id:
            return self._commit_matched_location(
                match_id,
                location,
                org_id,
                submarine_handler,
                is_submarine,
                loc_confidence_score=validation[0],
            )

        return self._commit_new_location(location, org_id, validation)

    def _commit_matched_location(
        self,
        match_id: str,
        location: dict[str, Any],
        org_id: uuid.UUID | None,
        submarine_handler: SubmarineLocationHandler,
        is_submarine: bool,
        *,
        loc_confidence_score: Any,
    ) -> uuid.UUID:
        """Commit an update against an existing (matched) canonical location.

        One of the two terminal commit sites for a federation-log ``Update``
        hook. Behavior unchanged from the original inline ``if match_id:`` branch.
        """
        # Tier-distribution increments (tier1/tier2/tier3/none) live inside
        # find_matching_location_with_lock; this caller no longer double-counts.
        location_id = uuid.UUID(match_id)

        self._keep_existing_name_over_city(location, location_id)

        if is_submarine:
            # Submarine: dynamic UPDATE — only set fields actually extracted.
            update_description = submarine_handler.update_location(
                location_id, location, org_id
            )
            submarine_handler.persist_schedules(
                location_id,
                location,
                self.metadata,
                self.service_creator,
                self.transform_schedule_fn,
            )
            # Persist submarine phones (the standard phone block runs only on
            # location create, so the update path would otherwise discard them).
            submarine_handler.persist_phones(
                location_id, location, self.metadata, self.service_creator
            )
        else:
            update_description = self._standard_matched_update(
                location, location_id, org_id
            )

        # For version tracking, use update_description if set, otherwise fall
        # back to location description.
        version_description = (
            update_description
            or location.get("description")
            or f"Food service location: {location['name']}"
        )

        VersionTracker(self.db).create_version(
            str(location_id),
            "location",
            {
                "name": location["name"],
                "description": version_description,
                "latitude": float(location["latitude"]),
                "longitude": float(location["longitude"]),
                "organization_id": str(org_id) if org_id else None,
                **self.metadata,
            },
            "reconciler",
            commit=True,
        )

        # Create/update location_source entry so every scraper that finds a
        # location is recorded.
        self.location_creator.create_location_source(
            str(location_id),
            self.metadata.get("scraper_id", "unknown"),
            location["name"],
            version_description,
            float(location["latitude"]),
            float(location["longitude"]),
            self.metadata,
            source_type=self.metadata.get("source_type", "scraper"),
        )

        # REC-4: route the canonical content + corroboration write through the
        # field-level MergeStrategy.merge_location (majority name, longest
        # description, most-recent coordinates + idempotent corroboration bonus,
        # owner-protected). MUST run after create_location_source so this scraper
        # is present for both the field merge and the distinct-scraper count.
        # Submarine jobs are enrichment, not confirmation (constitution v1.5.1)
        # — excluded. The per-job validator score (not the already-bonused
        # canonical score) keeps corroboration idempotent across reprocesses.
        # Wrapped so a merge failure can't abort the job (Principle XI); the
        # scrape is already in location_source and the next pass re-merges.
        if not is_submarine:
            try:
                MergeStrategy(self.db).merge_location(
                    str(location_id), loc_confidence_score
                )
            except Exception as e:
                logger.warning(
                    "merge_location_failed",
                    extra={
                        "location_id": str(location_id),
                        "per_job_score": loc_confidence_score,
                        "error": str(e),
                    },
                )

        return location_id

    def _keep_existing_name_over_city(
        self, location: dict[str, Any], location_id: uuid.UUID
    ) -> None:
        """If the incoming name equals the city, keep the DB's existing name
        (common LLM issue), mutating ``location`` in place."""
        if not location.get("address"):
            return
        first_addr = (
            location["address"][0]
            if isinstance(location["address"], list)
            else location["address"]
        )
        city = first_addr.get("city", "")
        if location["name"] == city and city:
            query = text("SELECT name FROM location WHERE id = :id")
            row = self.db.execute(query, {"id": str(location_id)}).first()
            if row and row[0] and row[0] != city:
                logger.info(
                    f"Keeping existing location name '{row[0]}' instead of "
                    f"city name '{city}'"
                )
                location["name"] = row[0]

    def _standard_matched_update(
        self,
        location: dict[str, Any],
        location_id: uuid.UUID,
        org_id: uuid.UUID | None,
    ) -> str | None:
        """Standard-path matched update: compute the source/version description
        and FILL a missing organization link.

        REC-4: the canonical content write (name/description/coordinates) is
        delegated to MergeStrategy.merge_location (field-level merge across ALL
        sources), not last-write-wins. Returns the description used for the
        source/version records.
        """
        update_description = location.get("description")
        if update_description is None or update_description == "":
            update_description = f"Food service location: {location['name']}"
            logger.warning(
                f"Missing description for location update {location['name']}, "
                f"using generated description"
            )

        # Organization: fill-only. REC-4/SUB-1 class fix — binding
        # organization_id=NULL on an org-less re-scrape WIPED an existing link.
        # Set the org only when the canonical row has none (enrichment); never
        # overwrite, clear, or touch an owner-curated row.
        if org_id:
            self.db.execute(
                text(
                    """
                    UPDATE location
                    SET organization_id = :organization_id
                    WHERE id = :id
                        AND organization_id IS NULL
                        AND (verified_by IS NULL
                             OR verified_by NOT IN
                                ('admin', 'source', 'claimed'))
                    """
                ),
                {"id": str(location_id), "organization_id": str(org_id)},
            )
            self.db.commit()

        return update_description

    def _commit_new_location(
        self,
        location: dict[str, Any],
        org_id: uuid.UUID | None,
        validation: tuple[Any, Any, Any, Any],
    ) -> uuid.UUID:
        """Create a new canonical location and its child records.

        The second of the two terminal commit sites for a federation-log
        ``Update`` hook. Behavior unchanged from the original inline ``else:``
        (create-new) branch.
        """
        # Ensure location has a name.
        if "name" not in location or not location.get("name"):
            location["name"] = f"Location {len(self.location_ids) + 1}"
            logger.warning(
                f"Missing name for location, using default: {location['name']}"
            )

        self._fix_city_only_name(location)

        # Ensure description is never null.
        loc_description = location.get("description")
        if loc_description is None or loc_description == "":
            loc_description = f"Food service location: {location['name']}"
            logger.warning(
                f"Missing description for location {location['name']}, "
                f"using generated description"
            )

        location_id = uuid.UUID(
            self.location_creator.create_location(
                location["name"],
                loc_description,
                float(location["latitude"]),
                float(location["longitude"]),
                self.metadata,
                str(org_id) if org_id else None,
                confidence_score=validation[0],
                validation_status=validation[1],
                validation_notes=validation[2],
                geocoding_source=validation[3],
            )
        )

        self._create_new_location_addresses(location, location_id)
        self._extract_narrative_phones(location, location_id)
        self._create_new_location_phones(location, location_id)
        self._create_new_location_accessibility(location, location_id)

        # Store UUID in location_ids dictionary.
        self.location_ids[self.location_key_fn(location)] = location_id

        # Submarine enrichment is handled by the weekly scanner (Step Functions
        # schedule), not per-location dispatch.
        return location_id

    def _fix_city_only_name(self, location: dict[str, Any]) -> None:
        """If a new location's name equals its city, try a better name from the
        description pattern (common LLM issue), mutating ``location``."""
        if not location.get("address"):
            return
        first_addr = (
            location["address"][0]
            if isinstance(location["address"], list)
            else location["address"]
        )
        city = first_addr.get("city", "")
        if location["name"] != city or not city:
            return

        better_name = None
        if location.get("description"):
            # Look for patterns like "Food service location: [Real Name]".
            match = re.search(
                r"Food service location:\s*(.+)", location.get("description", "")
            )
            if match:
                better_name = match.group(1).strip()

        if better_name and better_name != city:
            logger.info(
                f"Fixing location name from '{location['name']}' to "
                f"'{better_name}' (was using city name)"
            )
            location["name"] = better_name
        else:
            logger.warning(
                f"Location name '{location['name']}' matches city name, "
                f"may be incorrect"
            )

    def _create_new_location_addresses(
        self, location: dict[str, Any], location_id: uuid.UUID
    ) -> None:
        """Create address rows for a newly created location (none-exist guard)."""
        if not (location.get("address") and location_id):
            return
        location_id_str = str(location_id)

        # Check if addresses already exist for this location.
        result = self.db.execute(
            text("SELECT COUNT(*) FROM address WHERE location_id = :location_id"),
            {"location_id": location_id_str},
        )
        row = result.first()
        address_count = row[0] if row else 0
        if address_count != 0:
            return

        for address in location["address"]:
            # Ensure country defaults to US if not provided.
            country = address.get("country", "US")
            if not country or country == "":
                country = "US"
            # No geocoding here — the validator already enriched the data.
            self.location_creator.create_address(
                address_1=address.get("address_1", ""),
                city=address.get("city", ""),
                state_province=address.get("state_province", ""),
                postal_code=address.get("postal_code", ""),
                country=country,
                address_type=address.get("address_type") or "physical",
                location_id=location_id_str,
                metadata=self.metadata,
            )

    def _extract_narrative_phones(
        self, location: dict[str, Any], location_id: uuid.UUID | None
    ) -> None:
        """Last-resort phone extraction from narrative text, mutating location.

        Fires only when the LLM produced no nested phones[] AND a schema-kept
        text field (name, description, url) contains a phone-shaped string.
        """
        if not location_id or (
            location.get("phones") and len(location.get("phones", [])) != 0
        ):
            return

        extracted_phones: list[dict[str, Any]] = []
        search_text = ""
        for field in ("name", "description", "url"):
            if location.get(field):
                search_text += " " + str(location[field])

        if not search_text:
            return

        for pattern in _PHONE_PATTERNS:
            for match in re.findall(pattern, search_text):
                if match not in [p.get("number") for p in extracted_phones]:
                    extracted_phones.append(
                        {"number": match, "type": "voice", "languages": []}
                    )

        if extracted_phones:
            location["phones"] = extracted_phones
            logger.info(
                f"Extracted {len(extracted_phones)} phone numbers "
                f"for location '{location.get('name', 'Unknown')}' "
                "from narrative text"
            )

    def _create_new_location_phones(
        self, location: dict[str, Any], location_id: uuid.UUID | None
    ) -> None:
        """Create phones (with languages) for a newly created location."""
        if not (location.get("phones") and location_id):
            return
        for phone in location["phones"]:
            phone_id = self.service_creator.create_phone(
                number=phone.get("number", ""),
                phone_type=phone.get("type", ""),
                location_id=location_id,
                metadata=self.metadata,
                transaction=self.db,
            )
            if phone_id and phone.get("languages"):
                for language in phone["languages"]:
                    self.service_creator.create_language(
                        name=language.get("name", ""),
                        code=language.get("code", ""),
                        phone_id=phone_id,
                        metadata=self.metadata,
                    )

    def _create_new_location_accessibility(
        self, location: dict[str, Any], location_id: uuid.UUID | None
    ) -> None:
        """Create accessibility rows for a newly created location."""
        if not (
            "accessibility" in location and location_id and location["accessibility"]
        ):
            return
        location_id_str = str(location_id)
        for access in location["accessibility"]:
            self.location_creator.create_accessibility(
                location_id=location_id_str,
                description=access.get("description"),
                details=access.get("details"),
                url=access.get("url"),
                metadata=self.metadata,
            )
