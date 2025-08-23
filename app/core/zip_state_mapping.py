"""ZIP code to state mapping for validation and correction."""

from typing import Optional, Dict, Tuple

# ZIP code ranges by state (first 3 digits)
# Source: USPS ZIP code allocation
ZIP_RANGES_BY_STATE = {
    "AL": [(350, 369)],  # Alabama
    "AK": [(995, 999)],  # Alaska
    "AZ": [(850, 865)],  # Arizona
    "AR": [(716, 729), (755, 755)],  # Arkansas
    "CA": [(900, 961)],  # California
    "CO": [(800, 816)],  # Colorado
    "CT": [(60, 69)],  # Connecticut
    "DE": [(197, 199)],  # Delaware
    "DC": [(200, 205)],  # District of Columbia
    "FL": [(320, 349), (342, 342)],  # Florida
    "GA": [(300, 319), (398, 399)],  # Georgia
    "HI": [(967, 968)],  # Hawaii
    "ID": [(832, 838)],  # Idaho
    "IL": [(600, 629)],  # Illinois
    "IN": [(460, 479)],  # Indiana
    "IA": [(500, 528)],  # Iowa
    "KS": [(660, 679)],  # Kansas
    "KY": [(400, 427)],  # Kentucky
    "LA": [(700, 714)],  # Louisiana
    "ME": [(39, 49)],  # Maine
    "MD": [(206, 219)],  # Maryland
    "MA": [(10, 27), (55, 55)],  # Massachusetts
    "MI": [(480, 499)],  # Michigan
    "MN": [(550, 567)],  # Minnesota
    "MS": [(386, 397)],  # Mississippi
    "MO": [(630, 658)],  # Missouri
    "MT": [(590, 599)],  # Montana
    "NE": [(680, 693)],  # Nebraska
    "NV": [(889, 898)],  # Nevada
    "NH": [(30, 38)],  # New Hampshire
    "NJ": [(70, 89)],  # New Jersey
    "NM": [(870, 884)],  # New Mexico
    "NY": [(4, 5), (100, 149), (63, 63)],  # New York
    "NC": [(270, 289)],  # North Carolina
    "ND": [(580, 588)],  # North Dakota
    "OH": [(430, 459)],  # Ohio
    "OK": [(730, 749)],  # Oklahoma
    "OR": [(970, 979)],  # Oregon
    "PA": [(150, 196)],  # Pennsylvania
    "PR": [(6, 9)],  # Puerto Rico
    "RI": [(28, 29)],  # Rhode Island
    "SC": [(290, 299)],  # South Carolina
    "SD": [(570, 577)],  # South Dakota
    "TN": [(370, 385)],  # Tennessee
    "TX": [(750, 799), (885, 885)],  # Texas
    "UT": [(840, 847)],  # Utah
    "VT": [(50, 59)],  # Vermont
    "VA": [(220, 246), (201, 201)],  # Virginia
    "VI": [(8, 8)],  # Virgin Islands
    "WA": [(980, 994)],  # Washington
    "WV": [(247, 268)],  # West Virginia
    "WI": [(530, 549)],  # Wisconsin
    "WY": [(820, 831)],  # Wyoming
}

# Major cities to state mapping for validation
MAJOR_CITIES_TO_STATE = {
    # Wisconsin
    "milwaukee": "WI",
    "madison": "WI",
    "green bay": "WI",
    "kenosha": "WI",
    "racine": "WI",
    "appleton": "WI",
    "waukesha": "WI",
    "oshkosh": "WI",
    "eau claire": "WI",
    "janesville": "WI",
    # Colorado
    "denver": "CO",
    "colorado springs": "CO",
    "aurora": "CO",
    "fort collins": "CO",
    "lakewood": "CO",
    "thornton": "CO",
    "arvada": "CO",
    "westminster": "CO",
    "pueblo": "CO",
    "centennial": "CO",
    "boulder": "CO",
    # New York
    "new york": "NY",
    "new york city": "NY",
    "nyc": "NY",
    "manhattan": "NY",
    "brooklyn": "NY",
    "queens": "NY",
    "bronx": "NY",
    "staten island": "NY",
    "buffalo": "NY",
    "rochester": "NY",
    "yonkers": "NY",
    "syracuse": "NY",
    "albany": "NY",
    # Alabama
    "birmingham": "AL",
    "montgomery": "AL",
    "huntsville": "AL",
    "mobile": "AL",
    "tuscaloosa": "AL",
    "hoover": "AL",
    "dothan": "AL",
    "auburn": "AL",
    "decatur": "AL",
    # Note: madison is mapped to WI (more common)
    # California
    "los angeles": "CA",
    "san diego": "CA",
    "san jose": "CA",
    "san francisco": "CA",
    "fresno": "CA",
    "sacramento": "CA",
    "long beach": "CA",
    "oakland": "CA",
    "bakersfield": "CA",
    "anaheim": "CA",
    # Texas
    "houston": "TX",
    "san antonio": "TX",
    "dallas": "TX",
    "austin": "TX",
    "fort worth": "TX",
    "el paso": "TX",
    "arlington": "TX",
    "corpus christi": "TX",
    "plano": "TX",
    "laredo": "TX",
    # Add more cities as needed...
}


def get_state_from_zip(postal_code: Optional[str]) -> Optional[str]:
    """Get state code from ZIP code.

    Args:
        postal_code: ZIP code (5 or 9 digits with optional dash)

    Returns:
        Two-letter state code or None if invalid/unknown
    """
    if not postal_code:
        return None

    # Clean and validate zip code
    zip_clean = postal_code.strip().split("-")[0]  # Take first part if ZIP+4

    if not zip_clean.isdigit() or len(zip_clean) < 3:
        return None

    # Get first 3 digits
    prefix = int(zip_clean[:3])

    # Look up state by prefix
    for state, ranges in ZIP_RANGES_BY_STATE.items():
        for start, end in ranges:
            if start <= prefix <= end:
                return state

    return None


def get_state_from_city(city_name: Optional[str]) -> Optional[str]:
    """Get state code from city name.

    Args:
        city_name: City name

    Returns:
        Two-letter state code or None if not found
    """
    if not city_name:
        return None

    city_clean = city_name.strip().lower()
    return MAJOR_CITIES_TO_STATE.get(city_clean)


def validate_state_zip_match(state_code: str, postal_code: str) -> bool:
    """Check if state code matches ZIP code.

    Args:
        state_code: Two-letter state code
        postal_code: ZIP code

    Returns:
        True if they match, False otherwise
    """
    zip_state = get_state_from_zip(postal_code)
    return zip_state == state_code.upper() if zip_state else False


def validate_state_city_match(state_code: str, city_name: str) -> Optional[bool]:
    """Check if state code matches city name.

    Args:
        state_code: Two-letter state code
        city_name: City name

    Returns:
        True if match, False if mismatch, None if city not in database
    """
    city_state = get_state_from_city(city_name)
    if city_state is None:
        return None  # Unknown city
    return city_state == state_code.upper()


def resolve_state_conflict(
    claimed_state: Optional[str],
    postal_code: Optional[str],
    city_name: Optional[str],
    coord_state: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """Resolve conflicting state information using multiple sources.

    Args:
        claimed_state: State code from data
        postal_code: ZIP code
        city_name: City name
        coord_state: State from reverse geocoding coordinates

    Returns:
        Tuple of (resolved_state, resolution_reason)
    """
    zip_state = get_state_from_zip(postal_code) if postal_code else None
    city_state = get_state_from_city(city_name) if city_name else None

    # If ZIP and coordinates agree, that's most reliable
    if zip_state and coord_state and zip_state == coord_state:
        return zip_state, "zip_coord_agreement"

    # If ZIP and city agree
    if zip_state and city_state and zip_state == city_state:
        return zip_state, "zip_city_agreement"

    # If coordinates and city agree
    if coord_state and city_state and coord_state == city_state:
        return coord_state, "coord_city_agreement"

    # Trust ZIP if it exists (most specific)
    if zip_state:
        return zip_state, "zip_primary"

    # Trust coordinates next
    if coord_state:
        return coord_state, "coord_fallback"

    # City as last resort
    if city_state:
        return city_state, "city_fallback"

    # Keep claimed if no other evidence
    if claimed_state:
        return claimed_state.upper(), "no_correction_evidence"

    return None, "no_state_data"
