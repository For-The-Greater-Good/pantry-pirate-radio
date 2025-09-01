"""Scraper context for geocoding enrichment.

This module provides geographic context for scrapers to improve geocoding success rates.
Many scrapers operate in specific geographic areas, and we can use this knowledge
to enhance addresses that are missing state or city information.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

# Scraper-specific geographic defaults
# These are used to enhance addresses when geocoding
SCRAPER_DEFAULTS: Dict[str, Dict[str, Any]] = {
    # NYC-specific scrapers
    "nyc_efap_programs": {
        "state": "NY",
        "state_full": "New York",
        "city_default": "New York",
        "country": "US",
        "description": "NYC Emergency Food Assistance Program",
    },
    "food_bank_for_new_york_city_ny": {
        "state": "NY",
        "state_full": "New York",
        "city_default": "New York",
        "country": "US",
        "description": "Food Bank For New York City",
    },    
    # California scrapers
    "sfmarin_food_bank_ca": {
        "state": "CA",
        "state_full": "California",
        "city_default": "San Francisco",
        "country": "US",
        "description": "SF-Marin Food Bank",
    },
    "community_action_of_napa_valley_food_bank_ca": {
        "state": "CA",
        "state_full": "California",
        "city_default": "Napa",
        "country": "US",
        "description": "Community Action of Napa Valley Food Bank",
    },
    "second_harvest_of_silicon_valley_ca": {
        "state": "CA",
        "state_full": "California",
        "city_default": "San Jose",
        "country": "US",
        "description": "Second Harvest of Silicon Valley",
    },
    "food_bank_of_contra_costa_and_solano_ca": {
        "state": "CA",
        "state_full": "California",
        "city_default": "Fairfield",
        "country": "US",
        "description": "Food Bank of Contra Costa and Solano",
    },
    
    # Texas scrapers
    "north_texas_food_bank_tx": {
        "state": "TX",
        "state_full": "Texas",
        "city_default": "Dallas",
        "country": "US",
        "description": "North Texas Food Bank",
    },
    "houston_food_bank_tx": {
        "state": "TX",
        "state_full": "Texas",
        "city_default": "Houston",
        "country": "US",
        "description": "Houston Food Bank",
    },
    
    # Florida scrapers
    "feeding_the_gulf_coast_al": {
        "state": "FL",  # Also covers FL panhandle
        "state_full": "Florida",
        "city_default": None,  # Covers multiple states
        "country": "US",
        "description": "Feeding the Gulf Coast (AL, MS, FL)",
        "states_covered": ["AL", "MS", "FL"],
    },
    "feeding_tampa_bay_fl": {
        "state": "FL",
        "state_full": "Florida",
        "city_default": "Tampa",
        "country": "US",
        "description": "Feeding Tampa Bay",
    },
    
    # Ohio scrapers
    "toledo_northwestern_ohio_food_bank_oh": {
        "state": "OH",
        "state_full": "Ohio",
        "city_default": "Toledo",
        "country": "US",
        "description": "Toledo Northwestern Ohio Food Bank",
    },
    "akron_canton_regional_food_bank_oh": {
        "state": "OH",
        "state_full": "Ohio",
        "city_default": "Akron",
        "country": "US",
        "description": "Akron Canton Regional Food Bank",
    },
    
    # Pennsylvania scrapers
    "greater_pittsburgh_community_food_bank_pa": {
        "state": "PA",
        "state_full": "Pennsylvania",
        "city_default": "Pittsburgh",
        "country": "US",
        "description": "Greater Pittsburgh Community Food Bank",
    },
    "philabundance_pa": {
        "state": "PA",
        "state_full": "Pennsylvania",
        "city_default": "Philadelphia",
        "country": "US",
        "description": "Philabundance",
    },
    
    # North Carolina scrapers
    "second_harvest_food_bank_of_northwest_north_carolina_nc": {
        "state": "NC",
        "state_full": "North Carolina",
        "city_default": "Winston-Salem",
        "country": "US",
        "description": "Second Harvest Food Bank of Northwest North Carolina",
    },
    "food_bank_of_central_and_eastern_nc": {
        "state": "NC",
        "state_full": "North Carolina",
        "city_default": "Raleigh",
        "country": "US",
        "description": "Food Bank of Central & Eastern North Carolina",
    },
    
    # Washington scrapers
    "food_lifeline_wa": {
        "state": "WA",
        "state_full": "Washington",
        "city_default": "Seattle",
        "country": "US",
        "description": "Food Lifeline",
    },
    
    # Multi-state scrapers
    "freshtrak": {
        "state": None,  # Covers multiple states
        "state_full": None,
        "city_default": None,
        "country": "US",
        "description": "FreshTrak (multi-state)",
        "states_covered": ["OH", "FL", "NC", "SC"],  # Primary states
    },
    "the_food_pantries_org": {
        "state": None,  # National coverage
        "state_full": None,
        "city_default": None,
        "country": "US",
        "description": "The Food Pantries (national)",
    },
    "food_helpline_org": {
        "state": None,  # National coverage
        "state_full": None,
        "city_default": None,
        "country": "US",
        "description": "Food Helpline (national)",
    },
    "vivery_api": {
        "state": None,  # API covers multiple regions
        "state_full": None,
        "city_default": None,
        "country": "US",
        "description": "Vivery API",
    },
}


def get_scraper_context(scraper_id: str) -> Optional[Dict[str, Any]]:
    """Get geographic context for a scraper.
    
    Args:
        scraper_id: The scraper identifier
        
    Returns:
        Dictionary with geographic context or None if not found
    """
    return SCRAPER_DEFAULTS.get(scraper_id)


def enhance_address_with_context(
    address: Dict[str, Any], 
    scraper_id: Optional[str] = None
) -> Dict[str, Any]:
    """Enhance an address with scraper context.
    
    This function adds missing geographic information based on the scraper's
    known operating area. This significantly improves geocoding success rates
    for scrapers that operate in specific regions.
    
    Args:
        address: Address dictionary with keys like address_1, city, state_province, postal_code
        scraper_id: Optional scraper identifier for context
        
    Returns:
        Enhanced address dictionary with added context
    """
    if not scraper_id:
        return address
        
    context = get_scraper_context(scraper_id)
    if not context:
        return address
    
    enhanced = address.copy()
    
    # Add state if missing
    if not enhanced.get("state_province") and context.get("state"):
        enhanced["state_province"] = context["state"]
        logger.debug(
            f"Added state '{context['state']}' to address from scraper context: {scraper_id}"
        )
    
    # Only add city if it's specifically provided in the address
    # Don't use city defaults as they can be incorrect
    # Removed city default logic per user feedback
    
    # Add country if missing
    if not enhanced.get("country") and context.get("country"):
        enhanced["country"] = context["country"]
    
    return enhanced


def format_address_for_geocoding(
    address: Dict[str, Any],
    scraper_id: Optional[str] = None
) -> str:
    """Format an address for geocoding with scraper context.
    
    This function creates an optimally formatted address string for geocoding,
    using scraper context to fill in missing information.
    
    Args:
        address: Address dictionary
        scraper_id: Optional scraper identifier for context
        
    Returns:
        Formatted address string optimized for geocoding
    """
    # First enhance the address with context
    enhanced = enhance_address_with_context(address, scraper_id)
    
    # Build address components
    parts = []
    
    # Street address
    if enhanced.get("address_1"):
        parts.append(enhanced["address_1"])
    
    # City
    if enhanced.get("city"):
        parts.append(enhanced["city"])
    
    # State and postal code (no comma between them)
    state_zip = []
    if enhanced.get("state_province"):
        state_zip.append(enhanced["state_province"])
    if enhanced.get("postal_code"):
        state_zip.append(enhanced["postal_code"])
    
    if state_zip:
        parts.append(" ".join(state_zip))
    
    # Join with commas
    formatted = ", ".join(parts)
    
    # Log if we enhanced the address
    if scraper_id and formatted != ", ".join(filter(None, [
        address.get("address_1"),
        address.get("city"),
        " ".join(filter(None, [address.get("state_province"), address.get("postal_code")]))
    ])):
        logger.debug(
            f"Enhanced address for geocoding using {scraper_id} context: {formatted}"
        )
    
    return formatted


def get_scraper_state_list(scraper_id: str) -> list[str]:
    """Get list of states a scraper covers.
    
    Args:
        scraper_id: The scraper identifier
        
    Returns:
        List of state codes the scraper covers
    """
    context = get_scraper_context(scraper_id)
    if not context:
        return []
    
    # Check for explicit states_covered list
    if context.get("states_covered"):
        return context["states_covered"]
    
    # Return single state if defined
    if context.get("state"):
        return [context["state"]]
    
    return []


def is_address_in_scraper_region(
    latitude: float,
    longitude: float,
    scraper_id: str
) -> bool:
    """Check if coordinates are in the scraper's operating region.
    
    This can be used to validate if geocoded coordinates make sense
    for a given scraper's operating area.
    
    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        scraper_id: The scraper identifier
        
    Returns:
        True if coordinates are in expected region, False otherwise
    """
    states = get_scraper_state_list(scraper_id)
    if not states:
        # No specific region defined, accept all US coordinates
        return True
    
    # This would need the geocoding validator to check state bounds
    # For now, return True to avoid false rejections
    # TODO: Implement proper state boundary checking
    return True