"""Pure formatting functions for PTF partner sync.

All functions are stateless and have no side effects, making them
easy to test in isolation.
"""

import re
from typing import Any, Optional

from app.core.state_mapping import normalize_state_to_code

# Facebook IDs are 15+ digit numbers — not phone numbers
_FACEBOOK_ID_MIN_LEN = 13

# Junk URL patterns — file shares, not food bank websites
_JUNK_URL_PATTERNS = [
    "dropbox.com",
    "drive.google.com",
    "docs.google.com",
    "forms.google.com",
    "sharepoint.com",
    "onedrive.live.com",
    "box.com/s/",
]

# IANA timezone by US state code
_STATE_TIMEZONES: dict[str, str] = {
    # Eastern
    "CT": "America/New_York",
    "DC": "America/New_York",
    "DE": "America/New_York",
    "FL": "America/New_York",
    "GA": "America/New_York",
    "IN": "America/Indiana/Indianapolis",
    "KY": "America/New_York",
    "MA": "America/New_York",
    "MD": "America/New_York",
    "ME": "America/New_York",
    "MI": "America/Detroit",
    "NC": "America/New_York",
    "NH": "America/New_York",
    "NJ": "America/New_York",
    "NY": "America/New_York",
    "OH": "America/New_York",
    "PA": "America/New_York",
    "RI": "America/New_York",
    "SC": "America/New_York",
    "VA": "America/New_York",
    "VT": "America/New_York",
    "WV": "America/New_York",
    # Central
    "AL": "America/Chicago",
    "AR": "America/Chicago",
    "IA": "America/Chicago",
    "IL": "America/Chicago",
    "KS": "America/Chicago",
    "LA": "America/Chicago",
    "MN": "America/Chicago",
    "MO": "America/Chicago",
    "MS": "America/Chicago",
    "ND": "America/Chicago",
    "NE": "America/Chicago",
    "OK": "America/Chicago",
    "SD": "America/Chicago",
    "TN": "America/Chicago",
    "TX": "America/Chicago",
    "WI": "America/Chicago",
    # Mountain
    "CO": "America/Denver",
    "ID": "America/Boise",
    "MT": "America/Denver",
    "NM": "America/Denver",
    "UT": "America/Denver",
    "WY": "America/Denver",
    # Pacific
    "CA": "America/Los_Angeles",
    "NV": "America/Los_Angeles",
    "OR": "America/Los_Angeles",
    "WA": "America/Los_Angeles",
    # Other
    "AK": "America/Anchorage",
    "AZ": "America/Phoenix",
    "HI": "Pacific/Honolulu",
    # Territories
    "PR": "America/Puerto_Rico",
    "VI": "America/Virgin",
    "GU": "Pacific/Guam",
    "AS": "Pacific/Pago_Pago",
    "MP": "Pacific/Guam",
}

# Day abbreviation to full name
_DAY_NAMES: dict[str, str] = {
    "MO": "Monday",
    "TU": "Tuesday",
    "WE": "Wednesday",
    "TH": "Thursday",
    "FR": "Friday",
    "SA": "Saturday",
    "SU": "Sunday",
}


def normalize_phone(number: Optional[str]) -> Optional[str]:
    """Extract a valid US phone number as a string.

    Strips non-digit characters, filters Facebook IDs and invalid lengths.
    Returns 10 or 11 digit number as string, or None.
    """
    if not number:
        return None

    # Strip extension info before extracting digits
    number = re.split(r"\s*(?:ext|x|#)\s*", number, flags=re.IGNORECASE)[0]

    # Strip everything except digits
    digits = re.sub(r"\D", "", number)

    if not digits:
        return None

    # Facebook IDs are very long numeric strings
    if len(digits) >= _FACEBOOK_ID_MIN_LEN:
        return None

    # Valid US phones are 10 digits, or 11 with leading 1
    if len(digits) not in (10, 11):
        return None

    return digits


def filter_website(url: Optional[str]) -> Optional[str]:
    """Return URL if it's a real website, None if it's a file share or junk."""
    if not url:
        return None

    lower = url.lower()
    for pattern in _JUNK_URL_PATTERNS:
        if pattern in lower:
            return None

    return url


def format_schedule(rows: list[Any]) -> Optional[str]:
    """Format schedule DB rows into human-readable string.

    Output: "Monday: 9:00 AM - 5:00 PM; 1st Friday: 10:00 AM - 2:00 PM"
    Handles ordinal day patterns like "1FR" (1st Friday), "2WE" (2nd Wednesday).
    Falls back to description field if no structured times available.
    """
    if not rows:
        return None

    parts: list[str] = []
    seen: set[str] = set()

    for row in rows:
        byday = getattr(row, "byday", None)
        opens_at = getattr(row, "opens_at", None)
        closes_at = getattr(row, "closes_at", None)
        description = getattr(row, "description", None)

        if byday:
            days = [d.strip() for d in byday.split(",")]
            for day_code in days:
                label = _parse_day_label(day_code)
                if not label:
                    continue
                if label in seen:
                    continue
                seen.add(label)
                if opens_at and closes_at:
                    open_fmt = _format_time(opens_at)
                    close_fmt = _format_time(closes_at)
                    parts.append(f"{label}: {open_fmt} - {close_fmt}")
                elif description:
                    parts.append(f"{label}: {description}")
        elif description:
            parts.append(description)

    if not parts:
        return None

    return "; ".join(parts)


_ORDINAL_SUFFIXES = {1: "st", 2: "nd", 3: "rd"}


def _parse_day_label(code: str) -> Optional[str]:
    """Parse a byday code like 'MO', '1FR', '2WE' into a human-readable label.

    Returns e.g. 'Monday', '1st Friday', '2nd Wednesday', or None if invalid.
    """
    code = code.strip().upper()
    match = re.match(r"^(\d+)?([A-Z]{2})$", code)
    if not match:
        return None

    ordinal_str, day_code = match.groups()
    day_name = _DAY_NAMES.get(day_code)
    if not day_name:
        return None

    if ordinal_str:
        n = int(ordinal_str)
        suffix = _ORDINAL_SUFFIXES.get(n, "th")
        return f"{n}{suffix} {day_name}"

    return day_name


def _format_time(time_str: str) -> str:
    """Convert HH:MM:SS or HH:MM to 12-hour format like '9:00 AM'."""
    parts = str(time_str).split(":")
    hour = int(parts[0])
    minute = int(parts[1]) if len(parts) > 1 else 0

    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12
    if display_hour == 0:
        display_hour = 12

    if minute == 0:
        return f"{display_hour}:{minute:02d} {period}"
    return f"{display_hour}:{minute:02d} {period}"


def state_to_timezone(state: Optional[str]) -> Optional[str]:
    """Map a US state code to IANA timezone string."""
    if not state:
        return None

    code = normalize_state_to_code(state)
    if not code:
        return None

    return _STATE_TIMEZONES.get(code)


def build_additional_info(
    description: Optional[str] = None,
    services: Optional[list[str]] = None,
    extra_phones: Optional[list[str]] = None,
) -> str:
    """Build the additional_info text field from components."""
    parts: list[str] = []

    if description:
        parts.append(description)

    if services:
        parts.append(f"Services: {', '.join(services)}")

    if extra_phones:
        for phone in extra_phones:
            formatted = _format_phone_display(phone)
            parts.append(f"Additional phone: {formatted}")

    parts.append(
        "Data sourced from Pantry Pirate Radio (pantrypirate.radio). "
        "Please verify hours and availability directly with the organization."
    )

    return "\n\n".join(parts)


def _format_phone_display(phone: str) -> str:
    """Format phone string for display: 5551234567 -> 555-123-4567."""
    s = phone
    if len(s) == 11:
        return f"{s[0]}-{s[1:4]}-{s[4:7]}-{s[7:]}"
    if len(s) == 10:
        return f"{s[:3]}-{s[3:6]}-{s[6:]}"
    return s


def parse_zip_code(postal: Optional[str]) -> Optional[str]:
    """Parse postal code string to zero-padded 5-digit ZIP string.

    Handles ZIP+4 format (takes first 5 digits).
    Returns None for invalid inputs.
    """
    if not postal:
        return None

    # Take first 5 digits from ZIP+4
    base = postal.split("-")[0].strip()

    if not base.isdigit():
        return None

    if len(base) < 5:
        return None

    return base[:5].zfill(5)


def humanize_scraper_id(scraper_id: Optional[str]) -> Optional[str]:
    """Convert scraper_id to human-readable source name.

    'capital_area_food_bank_dc' -> 'Capital Area Food Bank DC'
    """
    if not scraper_id:
        return None

    # Remove _scraper suffix
    name = re.sub(r"_scraper$", "", scraper_id)

    # Split on underscores and title case, but keep state codes uppercase
    words = name.split("_")
    result = []
    for word in words:
        if len(word) <= 2:
            result.append(word.upper())
        else:
            result.append(word.capitalize())

    return " ".join(result)
