"""Deterministic URL slug generation for beacon pages."""

from __future__ import annotations

from slugify import slugify

# US state abbreviation to full name mapping
_STATE_NAMES: dict[str, str] = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "FL": "Florida", "GA": "Georgia", "HI": "Hawaii", "ID": "Idaho",
    "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming", "DC": "District of Columbia",
    "PR": "Puerto Rico", "VI": "Virgin Islands", "GU": "Guam",
}


def state_slug(state_province: str) -> str:
    """Convert state abbreviation or name to URL slug.

    >>> state_slug("IL")
    'illinois'
    >>> state_slug("New York")
    'new-york'
    """
    full = _STATE_NAMES.get(state_province.upper(), state_province)
    return slugify(full, lowercase=True)


def state_full_name(abbrev: str) -> str:
    """Get full state name from abbreviation.

    >>> state_full_name("IL")
    'Illinois'
    """
    return _STATE_NAMES.get(abbrev.upper(), abbrev)


def city_slug(city: str) -> str:
    """Convert city name to URL slug.

    >>> city_slug("Springfield")
    'springfield'
    >>> city_slug("St. Louis")
    'st-louis'
    """
    return slugify(city, lowercase=True)


def location_slug(name: str, location_id: str | None = None) -> str:
    """Convert location name to URL slug.

    Appends truncated ID if the slug would be empty.

    >>> location_slug("Springfield Community Food Pantry")
    'springfield-community-food-pantry'
    """
    s = slugify(name, lowercase=True)
    if not s and location_id:
        return location_id[:8]
    return s or "location"


def org_slug(name: str) -> str:
    """Convert organization name to URL slug.

    >>> org_slug("Feeding America Eastern Illinois")
    'feeding-america-eastern-illinois'
    """
    return slugify(name, lowercase=True) or "org"
