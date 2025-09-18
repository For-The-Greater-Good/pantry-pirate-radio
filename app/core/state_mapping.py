"""State name to code mapping utilities for consistent state normalization."""

from typing import Optional

VALID_STATE_CODES = {
    "AL",
    "AK",
    "AZ",
    "AR",
    "CA",
    "CO",
    "CT",
    "DE",
    "FL",
    "GA",
    "HI",
    "ID",
    "IL",
    "IN",
    "IA",
    "KS",
    "KY",
    "LA",
    "ME",
    "MD",
    "MA",
    "MI",
    "MN",
    "MS",
    "MO",
    "MT",
    "NE",
    "NV",
    "NH",
    "NJ",
    "NM",
    "NY",
    "NC",
    "ND",
    "OH",
    "OK",
    "OR",
    "PA",
    "RI",
    "SC",
    "SD",
    "TN",
    "TX",
    "UT",
    "VT",
    "VA",
    "WA",
    "WV",
    "WI",
    "WY",
    "DC",
    "PR",
    "VI",
    "GU",
    "AS",
    "MP",
}

STATE_NAME_TO_CODE = {
    # States
    "ALABAMA": "AL",
    "ALASKA": "AK",
    "ARIZONA": "AZ",
    "ARKANSAS": "AR",
    "CALIFORNIA": "CA",
    "COLORADO": "CO",
    "CONNECTICUT": "CT",
    "DELAWARE": "DE",
    "FLORIDA": "FL",
    "GEORGIA": "GA",
    "HAWAII": "HI",
    "IDAHO": "ID",
    "ILLINOIS": "IL",
    "INDIANA": "IN",
    "IOWA": "IA",
    "KANSAS": "KS",
    "KENTUCKY": "KY",
    "LOUISIANA": "LA",
    "MAINE": "ME",
    "MARYLAND": "MD",
    "MASSACHUSETTS": "MA",
    "MICHIGAN": "MI",
    "MINNESOTA": "MN",
    "MISSISSIPPI": "MS",
    "MISSOURI": "MO",
    "MONTANA": "MT",
    "NEBRASKA": "NE",
    "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH",
    "NEW JERSEY": "NJ",
    "NEW MEXICO": "NM",
    "NEW YORK": "NY",
    "NORTH CAROLINA": "NC",
    "NORTH DAKOTA": "ND",
    "OHIO": "OH",
    "OKLAHOMA": "OK",
    "OREGON": "OR",
    "PENNSYLVANIA": "PA",
    "RHODE ISLAND": "RI",
    "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD",
    "TENNESSEE": "TN",
    "TEXAS": "TX",
    "UTAH": "UT",
    "VERMONT": "VT",
    "VIRGINIA": "VA",
    "WASHINGTON": "WA",
    "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI",
    "WYOMING": "WY",
    # Federal District and Territories
    "DISTRICT OF COLUMBIA": "DC",
    "WASHINGTON DC": "DC",
    "WASHINGTON D.C.": "DC",
    "D.C.": "DC",
    "PUERTO RICO": "PR",
    "VIRGIN ISLANDS": "VI",
    "US VIRGIN ISLANDS": "VI",
    "U.S. VIRGIN ISLANDS": "VI",
    "GUAM": "GU",
    "AMERICAN SAMOA": "AS",
    "NORTHERN MARIANA ISLANDS": "MP",
}


def normalize_state_to_code(state_str: Optional[str]) -> str:
    """
    Normalize a state string to a 2-letter state code.

    Args:
        state_str: State name or code (can be full name, abbreviation, or partial)

    Returns:
        2-letter state code if matched, original value if already valid,
        or empty string if unrecognizable
    """
    if not state_str:
        return ""

    # Clean and uppercase the input
    state_clean = state_str.strip().upper()

    # If it's already a valid 2-letter code, return it
    if state_clean in VALID_STATE_CODES:
        return state_clean

    # Try exact match with full state names
    if state_clean in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[state_clean]

    # Handle common variations
    # Remove periods from abbreviations
    state_no_periods = state_clean.replace(".", "")
    if state_no_periods in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[state_no_periods]
    # Also check if the version without periods is a valid state code
    if state_no_periods in VALID_STATE_CODES:
        return state_no_periods

    # Check if it's already a 2-letter code (might not be in our valid set)
    if len(state_clean) == 2:
        # Still try to validate it
        if state_clean in VALID_STATE_CODES:
            return state_clean

    # Try to handle multi-word states by checking prefixes
    multi_word_prefixes = {
        "NEW",
        "NORTH",
        "SOUTH",
        "WEST",
        "RHODE",
        "DISTRICT",
        "AMERICAN",
        "NORTHERN",
        "VIRGIN",
        "U.S.",
        "US",
    }

    words = state_clean.split()
    if words and words[0] in multi_word_prefixes:
        # Try two-word combination
        if len(words) >= 2:
            two_word = " ".join(words[:2])
            if two_word in STATE_NAME_TO_CODE:
                return STATE_NAME_TO_CODE[two_word]

        # Try three-word combination for special cases
        if len(words) >= 3:
            three_word = " ".join(words[:3])
            if three_word in STATE_NAME_TO_CODE:
                return STATE_NAME_TO_CODE[three_word]

    # Single word state name
    if len(words) == 1 and words[0] in STATE_NAME_TO_CODE:
        return STATE_NAME_TO_CODE[words[0]]

    # If we can't match it, return empty string
    return ""


def is_valid_state_code(state_code: str) -> bool:
    """
    Check if a string is a valid US state code.

    Args:
        state_code: String to check

    Returns:
        True if valid state code, False otherwise
    """
    return state_code.upper() in VALID_STATE_CODES
