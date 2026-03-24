"""Confidence scoring for validated location data — build-up model.

Scraped data starts at a base score and earns points for quality signals.
Hard cap of 90 for scraped data; only human corrections (Tightbeam) reach 91-100.
"""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)

# Scoring constants
BASE_SCORE = 60
SCRAPED_DATA_CAP = 90


class ConfidenceScorer:
    """Calculate confidence scores for location data after validation.

    Uses a build-up model: scraped data starts at BASE_SCORE (60) and earns
    points for completeness, geocoding quality, and service-level richness.
    Penalties still apply for quality issues. Score capped at SCRAPED_DATA_CAP (90).
    """

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the confidence scorer.

        Args:
            config: Optional configuration dictionary
        """
        from app.core.config import settings

        self.config = config or {}
        self.rejection_threshold = self.config.get(
            "rejection_threshold",
            getattr(settings, "VALIDATION_REJECTION_THRESHOLD", 10),
        )

    def calculate_score(
        self, location: Dict[str, Any], validation_results: Dict[str, Any]
    ) -> int:
        """Calculate confidence score based on validation results.

        Uses a build-up model: start at base score (60) and add bonuses
        for data quality signals. Penalize for issues. Cap at 90.

        Args:
            location: Location data dictionary
            validation_results: Results from validation rules

        Returns:
            Confidence score from 0-90 (scraped data cap)
        """
        # CRITICAL FAILURES - Return immediately

        # No coordinates after enrichment = automatic rejection
        if not validation_results.get("has_coordinates", False):
            logger.debug(
                f"Location {location.get('name', 'unknown')}: "
                "No coordinates after enrichment, score=0"
            )
            return 0

        # 0,0 or near-zero coordinates = automatic rejection
        if validation_results.get("is_zero_coordinates", False):
            logger.debug(
                f"Location {location.get('name', 'unknown')}: "
                "Zero/near-zero coordinates, score=0"
            )
            return 0

        # Outside US bounds = almost reject (score 5)
        if not validation_results.get("within_us_bounds", False):
            logger.debug(
                f"Location {location.get('name', 'unknown')}: "
                "Outside US bounds, score=5"
            )
            return 5

        # Test data detected = almost reject (score 5)
        if validation_results.get("is_test_data", False):
            logger.debug(
                f"Location {location.get('name', 'unknown')}: "
                "Test data detected, score=5"
            )
            return 5

        # BUILD-UP MODEL: Start at base and earn points
        score = BASE_SCORE

        # COMPLETENESS BONUSES

        # Full address: street + city + state + postal code (+5)
        if self._has_full_address(location):
            score += 5

        # Meaningful description (+3)
        if self._has_meaningful_description(location):
            score += 3

        # GEOCODING QUALITY

        geocoding_source = location.get("geocoding_source", "").lower()
        geocoding_confidence = validation_results.get("geocoding_confidence", "unknown")

        # High-quality geocoder bonus (+5)
        if geocoding_source in (
            "arcgis",
            "google",
            "amazon-location",
            "amazon_location",
        ):
            score += 5
        # Census geocoder penalty (-5)
        elif geocoding_source == "census":
            score -= 5
        # Fallback geocoding penalty (-10)
        elif (
            geocoding_source in ("state_centroid", "fallback")
            or geocoding_confidence == "fallback"
        ):
            score -= 10

        # SERVICE-LEVEL RICHNESS (transient scoring annotations, NOT HSDS fields)

        if location.get("_has_phone"):
            score += 3
        if location.get("_has_schedule"):
            score += 3
        if location.get("_has_website"):
            score += 3

        # QUALITY PENALTIES

        # Placeholder address (-75)
        if validation_results.get("has_placeholder_address", False):
            score -= 75
            logger.debug(
                f"Location {location.get('name', 'unknown')}: "
                "Placeholder address detected, -75 points"
            )

        # Wrong state (-20)
        if not validation_results.get("within_state_bounds", True):
            score -= 20
            logger.debug(
                f"Location {location.get('name', 'unknown')}: "
                "Outside claimed state bounds, -20 points"
            )

        # Clamp to [0, SCRAPED_DATA_CAP]
        final_score = max(0, min(SCRAPED_DATA_CAP, score))

        logger.info(
            f"Location {location.get('name', 'unknown')}: "
            f"Final confidence score={final_score} "
            f"(geocoding_source={geocoding_source})"
        )

        return final_score

    def _has_full_address(self, location: Dict[str, Any]) -> bool:
        """Check if location has a complete address (all 4 components)."""
        address = location.get("address_1") or location.get("address") or ""
        city = location.get("city") or ""
        state = location.get("state_province") or location.get("state") or ""
        postal = location.get("postal_code") or ""
        return bool(address and city and state and postal)

    def _has_meaningful_description(self, location: Dict[str, Any]) -> bool:
        """Check if location has a meaningful description (>10 chars)."""
        description = location.get("description") or ""
        return len(description.strip()) > 10

    def apply_source_corroboration(self, base_score: int, source_count: int) -> int:
        """Apply source corroboration bonus based on number of distinct scrapers.

        Args:
            base_score: Current confidence score
            source_count: Number of distinct scrapers confirming this location

        Returns:
            Updated score with corroboration bonus, capped at SCRAPED_DATA_CAP
        """
        if source_count <= 1:
            return base_score

        # +5 for 2 sources, +10 for 3+ (capped)
        if source_count == 2:
            bonus = 5
        else:
            bonus = 10

        return min(base_score + bonus, SCRAPED_DATA_CAP)

    def get_validation_status(self, confidence_score: int) -> str:
        """Determine validation status based on confidence score.

        Args:
            confidence_score: Score from 0-100

        Returns:
            Validation status: 'verified', 'needs_review', or 'rejected'
        """
        if confidence_score >= 80:
            return "verified"
        elif confidence_score >= self.rejection_threshold:
            return "needs_review"
        else:
            return "rejected"

    def score_organization(
        self, org_data: Dict[str, Any], location_scores: list[int]
    ) -> int:
        """Calculate organization-level confidence score.

        Organization score is based on the average of its location scores.

        Args:
            org_data: Organization data dictionary
            location_scores: List of confidence scores for organization's locations

        Returns:
            Organization confidence score from 0-100
        """
        if not location_scores:
            return 0

        avg_score = sum(location_scores) / len(location_scores)
        min_score = min(location_scores)

        # If any location is rejected, heavily penalize the organization
        if min_score < self.rejection_threshold:
            org_score = min(avg_score, 50)
        else:
            org_score = avg_score

        return int(org_score)

    def score_service(self, service_data: Dict[str, Any], location_score: int) -> int:
        """Calculate service-level confidence score.

        Service score inherits from its associated location.

        Args:
            service_data: Service data dictionary
            location_score: Confidence score of the service's location

        Returns:
            Service confidence score from 0-100
        """
        score = location_score

        if not service_data.get("name"):
            score -= 5
        if not service_data.get("description"):
            score -= 5

        return max(0, min(100, score))
