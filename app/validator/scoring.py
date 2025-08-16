"""Confidence scoring for validated location data."""

import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """Calculate confidence scores for location data after validation."""

    def __init__(self, config: Dict[str, Any] = None):
        """Initialize the confidence scorer.
        
        Args:
            config: Optional configuration dictionary
        """
        from app.core.config import settings
        
        self.config = config or {}
        self.rejection_threshold = self.config.get(
            "rejection_threshold",
            getattr(settings, "VALIDATION_REJECTION_THRESHOLD", 10)
        )

    def calculate_score(
        self, location: Dict[str, Any], validation_results: Dict[str, Any]
    ) -> int:
        """Calculate confidence score based on validation results.
        
        This method assumes geocoding enrichment has already been performed.
        Missing coordinates after enrichment results in immediate rejection (score 0).
        
        Args:
            location: Location data dictionary
            validation_results: Results from validation rules
            
        Returns:
            Confidence score from 0-100
        """
        # CRITICAL FAILURES - Return immediately
        
        # No coordinates after enrichment = automatic rejection
        if not validation_results.get("has_coordinates", False):
            logger.debug(f"Location {location.get('name', 'unknown')}: No coordinates after enrichment, score=0")
            return 0
            
        # 0,0 or near-zero coordinates = automatic rejection
        if validation_results.get("is_zero_coordinates", False):
            logger.debug(f"Location {location.get('name', 'unknown')}: Zero/near-zero coordinates, score=0")
            return 0
            
        # Outside US bounds = almost reject (score 5)
        if not validation_results.get("within_us_bounds", False):
            logger.debug(f"Location {location.get('name', 'unknown')}: Outside US bounds, score=5")
            return 5
            
        # Test data detected = almost reject (score 5)
        if validation_results.get("is_test_data", False):
            logger.debug(f"Location {location.get('name', 'unknown')}: Test data detected, score=5")
            return 5
        
        # Start with perfect score and deduct for issues
        score = 100
        
        # MAJOR DEDUCTIONS
        
        # Placeholder address (-75 points)
        if validation_results.get("has_placeholder_address", False):
            score -= 75
            logger.debug(f"Location {location.get('name', 'unknown')}: Placeholder address detected, -75 points")
            
        # Wrong state (-20 points)
        if not validation_results.get("within_state_bounds", True):
            score -= 20
            logger.debug(f"Location {location.get('name', 'unknown')}: Outside claimed state bounds, -20 points")
            
        # GEOCODING QUALITY DEDUCTIONS
        
        geocoding_source = location.get("geocoding_source", "").lower()
        geocoding_confidence = validation_results.get("geocoding_confidence", "unknown")
        
        # Census geocoder is less reliable (-10 points)
        if geocoding_source == "census":
            score -= 10
            logger.debug(f"Location {location.get('name', 'unknown')}: Census geocoder used, -10 points")
            
        # Fallback geocoding (state centroid, etc.) (-15 points)
        if geocoding_source in ["state_centroid", "fallback"] or geocoding_confidence == "fallback":
            score -= 15
            logger.debug(f"Location {location.get('name', 'unknown')}: Fallback geocoding used, -15 points")
            
        # MINOR DEDUCTIONS
        
        # Missing postal code after enrichment (-5 points)
        if validation_results.get("missing_postal", False) or not location.get("postal_code"):
            score -= 5
            logger.debug(f"Location {location.get('name', 'unknown')}: Missing postal code, -5 points")
            
        # Missing city after enrichment (-10 points)
        if validation_results.get("missing_city", False) or not location.get("city"):
            score -= 10
            logger.debug(f"Location {location.get('name', 'unknown')}: Missing city, -10 points")
        
        # Clamp score to 0-100 range
        final_score = max(0, min(100, score))
        
        logger.info(
            f"Location {location.get('name', 'unknown')}: "
            f"Final confidence score={final_score} "
            f"(geocoding_source={geocoding_source})"
        )
        
        return final_score
    
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
            # No locations means we can't validate the organization
            return 0
            
        # Calculate average, weighted towards lower scores
        # (one bad location affects the whole organization)
        avg_score = sum(location_scores) / len(location_scores)
        min_score = min(location_scores)
        
        # If any location is rejected, heavily penalize the organization
        if min_score < self.rejection_threshold:
            org_score = min(avg_score, 50)  # Cap at 50 if any location is rejected
        else:
            org_score = avg_score
            
        return int(org_score)
    
    def score_service(
        self, service_data: Dict[str, Any], location_score: int
    ) -> int:
        """Calculate service-level confidence score.
        
        Service score inherits from its associated location.
        
        Args:
            service_data: Service data dictionary
            location_score: Confidence score of the service's location
            
        Returns:
            Service confidence score from 0-100
        """
        # Services inherit their location's confidence
        # with a small penalty if service data is incomplete
        score = location_score
        
        # Deduct for missing service details
        if not service_data.get("name"):
            score -= 5
        if not service_data.get("description"):
            score -= 5
            
        return max(0, min(100, score))