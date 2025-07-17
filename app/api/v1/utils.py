"""Utility functions for API endpoints."""

from typing import Any, Dict, Optional
from urllib.parse import urlencode

from fastapi import Request
from pydantic import HttpUrl


def create_pagination_links(
    request: Request,
    current_page: int,
    total_pages: int,
    per_page: int,
    extra_params: Optional[Dict[str, Any]] = None,
) -> Dict[str, Optional[str]]:
    """
    Create pagination links for API responses.

    Args:
        request: FastAPI request object
        current_page: Current page number
        total_pages: Total number of pages
        per_page: Items per page
        extra_params: Additional query parameters to include

    Returns:
        Dictionary containing pagination links
    """
    if extra_params is None:
        extra_params = {}

    # Remove None values from extra_params
    extra_params = {k: v for k, v in extra_params.items() if v is not None}

    # Base URL without query parameters
    base_url = str(request.url).split("?")[0]

    def create_link(page: int) -> str:
        """Create a pagination link for a specific page."""
        params = {"page": page, "per_page": per_page}
        params.update(extra_params)
        query_string = urlencode(params)
        return f"{base_url}?{query_string}"

    # Create links
    links = {
        "first": create_link(1),
        "last": create_link(total_pages),
        "next": create_link(current_page + 1) if current_page < total_pages else None,
        "prev": create_link(current_page - 1) if current_page > 1 else None,
    }

    return links


def calculate_pagination_metadata(
    total_items: int,
    current_page: int,
    per_page: int,
) -> Dict[str, int]:
    """
    Calculate pagination metadata.

    Args:
        total_items: Total number of items
        current_page: Current page number
        per_page: Items per page

    Returns:
        Dictionary containing pagination metadata
    """
    total_pages = max(1, (total_items + per_page - 1) // per_page)
    skip = (current_page - 1) * per_page

    return {
        "total_pages": total_pages,
        "skip": skip,
        "current_page": current_page,
        "per_page": per_page,
        "total_items": total_items,
    }


def validate_pagination_params(page: int, per_page: int) -> None:
    """
    Validate pagination parameters.

    Args:
        page: Page number
        per_page: Items per page

    Raises:
        ValueError: If parameters are invalid
    """
    if page < 1:
        raise ValueError("Page number must be greater than 0")
    if per_page < 1:
        raise ValueError("Items per page must be greater than 0")
    if per_page > 100:
        raise ValueError("Items per page cannot exceed 100")


def build_filter_dict(
    organization_id: Optional[str] = None,
    status: Optional[str] = None,
    location_type: Optional[str] = None,
    **kwargs,
) -> Dict[str, Any]:
    """
    Build a filter dictionary from optional parameters.

    Args:
        organization_id: Organization ID filter
        status: Status filter
        location_type: Location type filter
        **kwargs: Additional filters

    Returns:
        Dictionary of non-None filters
    """
    filters = {}

    if organization_id is not None:
        filters["organization_id"] = organization_id
    if status is not None:
        filters["status"] = status
    if location_type is not None:
        filters["location_type"] = location_type

    # Add additional filters
    for key, value in kwargs.items():
        if value is not None:
            filters[key] = value

    return filters


def format_distance(distance_meters: float) -> str:
    """
    Format distance in meters to human-readable string.

    Args:
        distance_meters: Distance in meters

    Returns:
        Formatted distance string
    """
    if distance_meters < 1000:
        return f"{distance_meters:.0f}m"
    elif distance_meters < 1609.34:  # Less than 1 mile
        return f"{distance_meters/1000:.1f}km"
    else:
        miles = distance_meters / 1609.34
        return f"{miles:.1f}mi"


def create_error_response(
    message: str,
    error_code: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create a standardized error response.

    Args:
        message: Error message
        error_code: Optional error code
        details: Optional additional details

    Returns:
        Standardized error response dictionary
    """
    response: Dict[str, Any] = {"error": message}

    if error_code:
        response["error_code"] = error_code

    if details:
        response["details"] = details

    return response


def extract_coordinates_from_query(
    latitude: Optional[float] = None,
    longitude: Optional[float] = None,
) -> Optional[tuple[float, float]]:
    """
    Extract and validate coordinates from query parameters.

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        Tuple of (latitude, longitude) or None if invalid
    """
    if latitude is None or longitude is None:
        return None

    # Validate coordinate ranges
    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90 degrees")
    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180 degrees")

    return (latitude, longitude)


def create_metadata_response(
    data_source: str = "Pantry Pirate Radio",
    coverage_area: str = "Continental United States",
    license: str = "CC BY-SA 4.0",
) -> Dict[str, Any]:
    """
    Create metadata response for API endpoints.

    Args:
        data_source: Source of the data
        coverage_area: Geographic coverage area
        license: Data license

    Returns:
        Metadata response dictionary
    """
    from datetime import datetime

    return {
        "last_updated": datetime.utcnow().isoformat() + "Z",
        "coverage_area": coverage_area,
        "data_source": data_source,
        "license": license,
    }
