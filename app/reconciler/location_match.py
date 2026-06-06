"""Location preprocessing and match resolution for the reconciler.

Extracted from ``location_commit.py`` per Constitution Principle IX (file size
limits), this module owns the *pre-commit* responsibility: taking a raw
(already HSDS-shaped) location dict and getting it ready to commit —

* resolving confidence/validation metadata (``extract_validation``),
* hoisting nested coordinates onto the location (``normalize_coordinates``),
* normalizing address fields into the ``address`` array (``normalize_address``),
* and resolving the coordinate-based canonical match (``find_coordinate_match``).

Keeping this preprocessing/matching concern here lets ``location_commit.py`` stay
focused on the two terminal commit branches (matched-update / new-create), which
remain together as the single clean site for a future federation-log ``Update``
hook. This is a pure extraction of behavior previously inline in
``LocationCommitHandler``; logic, ordering, mutation semantics, and log messages
are unchanged. ``location`` is mutated in place by ``normalize_coordinates`` and
``normalize_address`` exactly as before.
"""

import logging
import uuid
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import settings
from app.reconciler.location_creator import LocationCreator

# Match the original job_processor module logger so log message format and
# capture (e.g. pytest caplog) behavior is unchanged.
logger = logging.getLogger("app.reconciler.job_processor")


class LocationPreprocessor:
    """Preprocesses a raw location and resolves its coordinate-based match.

    Built once per job with the job-scoped collaborators/context (mirroring
    ``LocationCommitHandler``); the methods are pure transformations of the
    passed-in ``location`` dict plus DB lookups via the shared collaborators.
    """

    def __init__(
        self,
        db: Session,
        *,
        validation_data: dict[str, Any] | None,
        location_creator: LocationCreator,
    ) -> None:
        self.db = db
        self.validation_data = validation_data
        self.location_creator = location_creator

    def find_coordinate_match(
        self, location: dict[str, Any], org_id: uuid.UUID | None
    ) -> str | None:
        """Coordinate-based match resolution (standard, non-submarine path).

        Pulls address_1 + 5-digit ZIP from the first address for Tier 3's
        fuzzy-address gate (Tier 3 caps at ~200m, degrades to name-only when
        address fields are absent — so None is safe). Name and org_id let the
        matcher widen to a same-name/same-org search when scraper coords drift
        past the strict ~11m tolerance.
        """
        addr_payload = (
            location["address"][0]
            if isinstance(location.get("address"), list) and location["address"]
            else location.get("address") or {}
        )
        match_addr_1 = (
            addr_payload.get("address_1") if isinstance(addr_payload, dict) else None
        )
        match_postal = (
            addr_payload.get("postal_code") if isinstance(addr_payload, dict) else None
        )
        match_zip5 = match_postal[:5] if match_postal else None
        return self.location_creator.find_matching_location(
            float(location["latitude"]),
            float(location["longitude"]),
            name=location.get("name"),
            organization_id=str(org_id) if org_id else None,
            address_1=match_addr_1,
            zip5=match_zip5,
        )

    def extract_validation(self, location: dict[str, Any]) -> tuple[Any, Any, Any, Any]:
        """Resolve (confidence, status, notes, geocoding_source), preferring
        values on the location (from the validator), else the separate
        ``validation_data`` block matched by name or coordinates."""
        loc_confidence_score = location.get("confidence_score")
        loc_validation_status = location.get("validation_status")
        loc_validation_notes = location.get("validation_notes")
        loc_geocoding_source = location.get("geocoding_source")

        if loc_confidence_score is not None:
            logger.info(
                f"Location '{location.get('name')}' has confidence score: "
                f"{loc_confidence_score}, status: {loc_validation_status}"
            )
        elif self.validation_data and "location" in self.validation_data:
            for val_loc in self.validation_data["location"]:
                # Match by name and coordinates if available
                if val_loc.get("name") == location.get("name") or (
                    location.get("latitude")
                    and location.get("longitude")
                    and abs(
                        float(val_loc.get("latitude", 0))
                        - float(location.get("latitude", 0))
                    )
                    < settings.RECONCILER_LOCATION_TOLERANCE
                    and abs(
                        float(val_loc.get("longitude", 0))
                        - float(location.get("longitude", 0))
                    )
                    < settings.RECONCILER_LOCATION_TOLERANCE
                ):
                    loc_confidence_score = val_loc.get("confidence_score")
                    loc_validation_status = val_loc.get("validation_status")
                    loc_validation_notes = val_loc.get("validation_notes")
                    loc_geocoding_source = val_loc.get("geocoding_source")
                    if loc_confidence_score:
                        logger.info(
                            f"Location '{location.get('name')}' has confidence "
                            f"score: {loc_confidence_score}, "
                            f"status: {loc_validation_status}"
                        )
                    break

        return (
            loc_confidence_score,
            loc_validation_status,
            loc_validation_notes,
            loc_geocoding_source,
        )

    def normalize_coordinates(self, location: dict[str, Any]) -> None:
        """Hoist nested coordinates onto the location, mutating in place."""
        # Check if coordinates are directly on location (from array format)
        if "coordinates" in location and isinstance(location["coordinates"], dict):
            coords = location["coordinates"]
            if "latitude" in coords and "longitude" in coords:
                location["latitude"] = coords["latitude"]
                location["longitude"] = coords["longitude"]
                del location["coordinates"]
                logger.debug(
                    f"Extracted coordinates from location object for "
                    f"'{location.get('name', 'Unknown')}'"
                )
        # Also check if coordinates are nested in addresses structure
        elif (
            "addresses" in location
            and isinstance(location.get("addresses"), list)
            and len(location["addresses"]) > 0
        ):
            first_address = location["addresses"][0]
            if "coordinates" in first_address and isinstance(
                first_address["coordinates"], dict
            ):
                coords = first_address["coordinates"]
                if "latitude" in coords and "longitude" in coords:
                    location["latitude"] = coords["latitude"]
                    location["longitude"] = coords["longitude"]
                    logger.debug(
                        f"Extracted coordinates from nested address structure "
                        f"for location '{location.get('name', 'Unknown')}'"
                    )

    def normalize_address(self, location: dict[str, Any]) -> None:
        """Normalize address into the ``address`` array, mutating in place."""
        # Handle address fields directly on location (from array format)
        if "address_1" in location or "city" in location:
            if "address" not in location:
                location["address"] = [
                    {
                        "address_1": location.pop("address_1", ""),
                        "city": location.pop("city", ""),
                        "state_province": location.pop("state_province", ""),
                        "postal_code": location.pop("postal_code", ""),
                        "country": location.pop("country", "US"),
                        "address_type": "physical",
                    }
                ]
                logger.debug(
                    f"Created address array from direct fields for location "
                    f"'{location.get('name', 'Unknown')}'"
                )
        # Rename addresses to address (fixed from CSV typo)
        elif "addresses" in location and "address" not in location:
            location["address"] = location.pop("addresses")
            # Remove coordinates from address entries since we've extracted them
            for addr in location.get("address", []):
                if "coordinates" in addr:
                    del addr["coordinates"]
