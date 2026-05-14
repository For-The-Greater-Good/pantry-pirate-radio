"""Tests for the location creation utilities."""

import uuid
import time
from typing import Dict, Union
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import TextClause
from sqlalchemy.exc import IntegrityError

from app.reconciler.location_creator import LocationCreator


@pytest.fixture
def mock_db(mocker: MockerFixture) -> MagicMock:
    """Create a mock database session."""
    db = MagicMock(spec=Session)
    db.commit.return_value = None

    # Mock database result
    result = MagicMock()
    result.first.return_value = None
    db.execute.return_value = result

    return db


@pytest.fixture
def test_location_data() -> Dict[str, Union[str, float]]:
    """Create test location data."""
    return {
        "name": "Test Location",
        "description": "Test Description",
        "latitude": 37.7749,
        "longitude": -122.4194,
    }


@pytest.fixture
def test_address_data() -> Dict[str, str]:
    """Create test address data."""
    return {
        "address_1": "123 Test St",
        "city": "Test City",
        "state_province": "CA",
        "postal_code": "94105",
        "country": "US",
        "address_type": "physical",
    }


def test_find_matching_location_found(mock_db: MagicMock) -> None:
    """Test finding matching location when one exists."""
    location_creator = LocationCreator(mock_db)
    existing_id = str(uuid.uuid4())

    # Mock database responses for advisory lock and search
    # First call: acquire_location_lock - returns lock_id
    lock_result = MagicMock()
    lock_result.scalar.return_value = "mock_lock_id"

    # Second call: location search - returns location
    search_result = MagicMock()
    search_result.first.return_value = (existing_id,)

    # Third call: release_location_lock
    release_result = MagicMock()

    # Set up mock_db.execute to return different results for each call
    mock_db.execute.side_effect = [lock_result, search_result, release_result]

    result = location_creator.find_matching_location(37.7749, -122.4194)

    # Verify result
    assert result == existing_id

    # Verify SQL execution - should be called 3 times due to advisory locks
    # 1: acquire_location_lock, 2: location search, 3: release_location_lock
    assert mock_db.execute.call_count == 3

    # Verify the second call (location search) has correct parameters
    location_search_call = mock_db.execute.call_args_list[1]
    assert isinstance(location_search_call[0][0], TextClause)
    assert location_search_call[0][1] == {
        "lat1": 37.7749,
        "lon1": -122.4194,
        "tolerance": 0.0001,
    }


def test_find_matching_location_not_found(mock_db: MagicMock) -> None:
    """Test finding matching location when none exists."""
    location_creator = LocationCreator(mock_db)

    # Mock database response
    result = MagicMock()
    result.first.return_value = None
    mock_db.execute.return_value = result

    result = location_creator.find_matching_location(37.7749, -122.4194)

    # Verify result
    assert result is None


def _setup_two_tier_match_mocks(
    mock_db: MagicMock,
    strict_hit: tuple | None,
    fallback_hit: tuple | None,
) -> None:
    """Configure mock_db.execute to simulate the three SQL calls in
    find_matching_location: acquire_lock, strict-match SELECT, fallback
    SELECT (if reached), release_lock."""
    lock_result = MagicMock()
    lock_result.scalar.return_value = "mock_lock_id"

    strict_result = MagicMock()
    strict_result.first.return_value = strict_hit

    fallback_result = MagicMock()
    fallback_result.first.return_value = fallback_hit

    release_result = MagicMock()

    if strict_hit is not None:
        # Strict match returns hit; fallback SELECT never runs
        mock_db.execute.side_effect = [lock_result, strict_result, release_result]
    else:
        # Strict miss → fallback SELECT → release
        mock_db.execute.side_effect = [
            lock_result,
            strict_result,
            fallback_result,
            release_result,
        ]


def test_find_matching_location_strict_match_skips_fallback(
    mock_db: MagicMock,
) -> None:
    """When strict coord-only match hits, the same-name/same-org fallback
    SQL must not run (avoid extra DB round-trip and any risk of widening
    the match against the caller's intent)."""
    location_creator = LocationCreator(mock_db)
    existing_id = str(uuid.uuid4())
    _setup_two_tier_match_mocks(mock_db, strict_hit=(existing_id,), fallback_hit=None)

    result = location_creator.find_matching_location(
        37.7749, -122.4194, name="Some Pantry", organization_id=str(uuid.uuid4())
    )

    assert result == existing_id
    # Calls: acquire_lock + strict_select + release_lock = 3 (no fallback)
    assert mock_db.execute.call_count == 3


def test_find_matching_location_fallback_same_name(mock_db: MagicMock) -> None:
    """When strict coord match misses and a same-name location exists within
    the wider tolerance, the fallback returns it. Closes the 1,112-pair
    duplicate gap where the same pantry was geocoded slightly differently
    by two scrapers and the strict ~11m tolerance was too tight."""
    location_creator = LocationCreator(mock_db)
    duplicate_id = str(uuid.uuid4())
    _setup_two_tier_match_mocks(mock_db, strict_hit=None, fallback_hit=(duplicate_id,))

    result = location_creator.find_matching_location(
        37.7749, -122.4194, name="St. Benedict Church"
    )

    assert result == duplicate_id
    # Calls: acquire_lock + strict_select + fallback_select + release_lock
    assert mock_db.execute.call_count == 4
    fallback_call = mock_db.execute.call_args_list[2]
    fallback_params = fallback_call[0][1]
    assert fallback_params["name"] == "St. Benedict Church"
    assert fallback_params["org_id"] is None
    # Fallback tolerance must be wider than strict tolerance
    assert fallback_params["wide_tolerance"] > 0.0001


def test_find_matching_location_fallback_same_org(mock_db: MagicMock) -> None:
    """When strict coord match misses and a same-organization location
    exists within the wider tolerance, the fallback returns it."""
    location_creator = LocationCreator(mock_db)
    duplicate_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    _setup_two_tier_match_mocks(mock_db, strict_hit=None, fallback_hit=(duplicate_id,))

    result = location_creator.find_matching_location(
        37.7749, -122.4194, organization_id=org_id
    )

    assert result == duplicate_id
    fallback_call = mock_db.execute.call_args_list[2]
    fallback_params = fallback_call[0][1]
    assert fallback_params["org_id"] == org_id
    assert fallback_params["name"] is None


def test_find_matching_location_no_fallback_without_name_or_org(
    mock_db: MagicMock,
) -> None:
    """Without name or organization_id, the fallback path must be skipped —
    a wider radius without an identity constraint would merge unrelated
    nearby pantries."""
    location_creator = LocationCreator(mock_db)
    lock_result = MagicMock()
    lock_result.scalar.return_value = "mock_lock_id"
    strict_result = MagicMock()
    strict_result.first.return_value = None
    release_result = MagicMock()
    mock_db.execute.side_effect = [lock_result, strict_result, release_result]

    result = location_creator.find_matching_location(37.7749, -122.4194)

    assert result is None
    # Only acquire_lock + strict_select + release_lock (no fallback)
    assert mock_db.execute.call_count == 3


def test_find_matching_location_fallback_returns_none_when_no_match(
    mock_db: MagicMock,
) -> None:
    """Strict miss + fallback miss + Tier 3 fuzzy miss → returns None
    (no false-positive merge). Since `name` is provided, all three
    tiers fire and we need mocks for all three SELECTs."""
    location_creator = LocationCreator(mock_db)
    _setup_three_tier_match_mocks(
        mock_db, tier1_hit=None, tier2_hit=None, tier3_hit=None
    )

    result = location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="Distinct Pantry Name",
        organization_id=str(uuid.uuid4()),
    )

    assert result is None
    # acquire + tier1 + tier2 + tier3 + release = 5 calls
    assert mock_db.execute.call_count == 5


def test_find_matching_location_fallback_with_both_name_and_org(
    mock_db: MagicMock,
) -> None:
    """When both name and organization_id are passed, the fallback SQL
    must use an OR (either match qualifies) — not an AND. Locks the
    semantics against accidental AND regression."""
    location_creator = LocationCreator(mock_db)
    duplicate_id = str(uuid.uuid4())
    org_id = str(uuid.uuid4())
    _setup_two_tier_match_mocks(mock_db, strict_hit=None, fallback_hit=(duplicate_id,))

    result = location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="St. Benedict Church",
        organization_id=org_id,
    )

    assert result == duplicate_id
    fallback_call = mock_db.execute.call_args_list[2]
    fallback_sql = str(fallback_call[0][0])
    fallback_params = fallback_call[0][1]
    # Both params bound — the SQL itself uses OR so either can match
    assert fallback_params["name"] == "St. Benedict Church"
    assert fallback_params["org_id"] == org_id
    # The fallback SQL must contain OR between the two predicates;
    # a regression to AND would silently require both row.org_id == org_id
    # AND row.name == name, missing many real duplicates.
    assert " OR " in fallback_sql


def test_find_matching_location_fallback_name_is_lowercased_and_trimmed(
    mock_db: MagicMock,
) -> None:
    """The fallback name comparison normalizes via LOWER(TRIM(...)).
    Locks that the SQL preserves this normalization — otherwise
    'St. Benedict Church' vs '  St. Benedict Church  ' or
    'ST. BENEDICT CHURCH' wouldn't dedupe."""
    location_creator = LocationCreator(mock_db)
    _setup_two_tier_match_mocks(
        mock_db, strict_hit=None, fallback_hit=(str(uuid.uuid4()),)
    )
    location_creator.find_matching_location(
        37.7749, -122.4194, name="  St. Benedict Church  "
    )
    fallback_call = mock_db.execute.call_args_list[2]
    fallback_sql = str(fallback_call[0][0])
    assert "LOWER(TRIM(name))" in fallback_sql
    assert "LOWER(TRIM(:name))" in fallback_sql


def _setup_three_tier_match_mocks(
    mock_db: MagicMock,
    tier1_hit: tuple | None,
    tier2_hit: tuple | None,
    tier3_hit: tuple | None,
) -> None:
    """Configure mock_db.execute to simulate the 3-tier match path
    plus advisory-lock acquire/release.

    Call sequence: acquire_lock → tier1 → [tier2] → [tier3] → release.
    Tier 2 only runs if tier1 misses; Tier 3 only runs if tier2 misses.
    """
    lock_result = MagicMock()
    lock_result.scalar.return_value = "mock_lock_id"
    release_result = MagicMock()

    t1 = MagicMock()
    t1.first.return_value = tier1_hit
    t2 = MagicMock()
    t2.first.return_value = tier2_hit
    t3 = MagicMock()
    t3.first.return_value = tier3_hit

    if tier1_hit is not None:
        mock_db.execute.side_effect = [lock_result, t1, release_result]
    elif tier2_hit is not None:
        mock_db.execute.side_effect = [lock_result, t1, t2, release_result]
    else:
        # Both upper tiers miss → Tier 3 runs (when there's anything to
        # fuzzy-match on).
        mock_db.execute.side_effect = [lock_result, t1, t2, t3, release_result]


def test_find_matching_location_tier3_runs_after_tier2_miss(
    mock_db: MagicMock,
) -> None:
    """When Tier 1 (strict coord) and Tier 2 (exact-name OR same-org)
    both miss, Tier 3 (fuzzy name/address within ~200m) must run.
    Catches dupes where two scrapers produced different names AND
    different orgs for the same physical pantry."""
    location_creator = LocationCreator(mock_db)
    duplicate_id = str(uuid.uuid4())
    _setup_three_tier_match_mocks(
        mock_db, tier1_hit=None, tier2_hit=None, tier3_hit=(duplicate_id,)
    )

    result = location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="First Baptist Food Pantry",
        address_1="123 Main St",
        zip5="94105",
    )

    assert result == duplicate_id
    # acquire + tier1 + tier2 + tier3 + release = 5 execute() calls
    assert mock_db.execute.call_count == 5


def test_find_matching_location_tier3_skipped_without_name_or_address(
    mock_db: MagicMock,
) -> None:
    """Tier 3 must NOT run when the caller supplies neither name nor
    address_1 — there'd be nothing to fuzzy-match on, and running an
    unrestricted 200m geo query would risk merging unrelated pantries.

    The Tier 2 guard already filters callers without name-or-org, but
    Tier 3 has a separate guard because it doesn't accept org_id."""
    location_creator = LocationCreator(mock_db)
    lock_result = MagicMock()
    lock_result.scalar.return_value = "mock_lock_id"
    strict_result = MagicMock()
    strict_result.first.return_value = None
    release_result = MagicMock()
    # No tier 2 SQL either (no name, no org), no tier 3 (no name, no addr).
    mock_db.execute.side_effect = [lock_result, strict_result, release_result]

    result = location_creator.find_matching_location(37.7749, -122.4194)

    assert result is None
    assert mock_db.execute.call_count == 3


def test_find_matching_location_tier3_uses_dedup_module_sql(
    mock_db: MagicMock,
) -> None:
    """The Tier 3 SQL must come from `app.reconciler.dedup.tier3_match_sql()`
    so the threshold constants stay synced with the PTF API. Locking a
    few signature strings catches a copy-paste regression."""
    location_creator = LocationCreator(mock_db)
    _setup_three_tier_match_mocks(
        mock_db,
        tier1_hit=None,
        tier2_hit=None,
        tier3_hit=(str(uuid.uuid4()),),
    )
    location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="First Baptist Food Pantry",
        address_1="123 Main St",
        zip5="94105",
    )
    tier3_call = mock_db.execute.call_args_list[3]
    tier3_sql = str(tier3_call[0][0])
    # Hallmarks of dedup.tier3_match_sql():
    assert "similarity(" in tier3_sql
    assert "ST_DWithin" in tier3_sql
    assert "FOR UPDATE SKIP LOCKED" in tier3_sql
    # And it must NOT be the Tier 2 fallback SQL — Tier 2 uses
    # LOWER(TRIM(...)) for exact-name match; Tier 3 uses similarity().
    assert "LOWER(TRIM(name))" not in tier3_sql


def test_find_matching_location_tier3_binds_thresholds_as_params(
    mock_db: MagicMock,
) -> None:
    """The fuzzy thresholds (name_sim, addr_sim, loose_deg) must be
    bound as params from `app.reconciler.dedup`, not hard-coded into
    the call site. A regression that hard-coded `0.5` here would
    silently disable operator tuning."""
    from app.reconciler.dedup import (
        _ADDR_SIM_THRESHOLD,
        _DEDUP_LOOSE_DEG,
        _NAME_SIM_THRESHOLD,
    )

    location_creator = LocationCreator(mock_db)
    _setup_three_tier_match_mocks(
        mock_db,
        tier1_hit=None,
        tier2_hit=None,
        tier3_hit=(str(uuid.uuid4()),),
    )
    location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="Anyplace Pantry",
        address_1="500 Oak St",
        zip5="94110",
    )
    tier3_call = mock_db.execute.call_args_list[3]
    tier3_params = tier3_call[0][1]
    assert tier3_params["name_sim"] == _NAME_SIM_THRESHOLD
    assert tier3_params["addr_sim"] == _ADDR_SIM_THRESHOLD
    assert tier3_params["loose_deg"] == _DEDUP_LOOSE_DEG
    assert tier3_params["name"] == "Anyplace Pantry"
    assert tier3_params["addr_1"] == "500 Oak St"
    assert tier3_params["zip5"] == "94110"
    assert tier3_params["lat1"] == 37.7749
    assert tier3_params["lon1"] == -122.4194


def test_find_matching_location_tier3_logs_structlog_event_on_hit(
    mock_db: MagicMock,
) -> None:
    """When Tier 3 finds a match, the structlog event
    `reconciler_tier3_fuzzy_merge` must fire so operators can grep
    CloudWatch and audit fuzzy-merge volume."""
    location_creator = LocationCreator(mock_db)
    duplicate_id = str(uuid.uuid4())
    _setup_three_tier_match_mocks(
        mock_db, tier1_hit=None, tier2_hit=None, tier3_hit=(duplicate_id,)
    )

    with patch.object(location_creator, "logger") as mock_logger:
        location_creator.find_matching_location(
            37.7749,
            -122.4194,
            name="First Baptist Food Pantry",
            address_1="123 Main St",
            zip5="94105",
        )
        # info-level event; exact name `reconciler_tier3_fuzzy_merge`.
        mock_logger.info.assert_called()
        # Find at least one call whose message starts with the event name.
        events = [
            c.args[0]
            for c in mock_logger.info.call_args_list
            if c.args and isinstance(c.args[0], str)
        ]
        assert any("reconciler_tier3_fuzzy_merge" in e for e in events), (
            f"expected `reconciler_tier3_fuzzy_merge` in logged events, "
            f"got {events}"
        )


def test_find_matching_location_tier3_only_when_tier1_and_tier2_miss(
    mock_db: MagicMock,
) -> None:
    """If Tier 1 hits, Tier 3 must NOT run — even with name/address
    supplied. Saves a DB round-trip on the hot path."""
    location_creator = LocationCreator(mock_db)
    existing_id = str(uuid.uuid4())
    _setup_three_tier_match_mocks(
        mock_db,
        tier1_hit=(existing_id,),
        tier2_hit=None,
        tier3_hit=None,
    )

    result = location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="First Baptist",
        address_1="123 Main St",
        zip5="94105",
    )

    assert result == existing_id
    # Only acquire + tier1 + release; tier2 and tier3 must be skipped.
    assert mock_db.execute.call_count == 3


def test_find_matching_location_tier3_skipped_when_tier2_hits(
    mock_db: MagicMock,
) -> None:
    """If Tier 2 (exact-name OR same-org) hits, Tier 3 must NOT run.
    The exact-match tier is more conservative and should win first."""
    location_creator = LocationCreator(mock_db)
    tier2_hit_id = str(uuid.uuid4())
    _setup_three_tier_match_mocks(
        mock_db,
        tier1_hit=None,
        tier2_hit=(tier2_hit_id,),
        tier3_hit=None,
    )

    result = location_creator.find_matching_location(
        37.7749,
        -122.4194,
        name="First Baptist",
        address_1="123 Main St",
        zip5="94105",
    )

    assert result == tier2_hit_id
    # acquire + tier1 + tier2 + release; tier3 must be skipped.
    assert mock_db.execute.call_count == 4


def test_find_matching_location_tier3_name_only_no_address(
    mock_db: MagicMock,
) -> None:
    """Tier 3 must still run with only a name (no address) — the SQL's
    address gate is a separate OR branch that degrades cleanly."""
    location_creator = LocationCreator(mock_db)
    duplicate_id = str(uuid.uuid4())
    _setup_three_tier_match_mocks(
        mock_db, tier1_hit=None, tier2_hit=None, tier3_hit=(duplicate_id,)
    )

    result = location_creator.find_matching_location(
        37.7749, -122.4194, name="First Baptist Food Pantry"
    )

    assert result == duplicate_id
    tier3_call = mock_db.execute.call_args_list[3]
    tier3_params = tier3_call[0][1]
    assert tier3_params["name"] == "First Baptist Food Pantry"
    # Address and zip default to None when not supplied.
    assert tier3_params["addr_1"] is None
    assert tier3_params["zip5"] is None


def test_create_location(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test creating a new location."""
    location_creator = LocationCreator(mock_db)

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker, patch(
        "app.reconciler.location_creator.MergeStrategy"
    ) as mock_merge_strategy:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock database response for location creation
        location_result = MagicMock()
        # Mock database response for source record creation
        source_result = MagicMock()
        source_result.first.return_value = ("source_id",)

        # Set up the mock to return different results for each call
        mock_db.execute.side_effect = [location_result, source_result]

        location_id = location_creator.create_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
        )

        # Verify SQL execution - should be called twice
        assert mock_db.execute.call_count == 2

        # First call should be for location creation
        location_call = mock_db.execute.call_args_list[0]
        assert isinstance(location_call[0][0], TextClause)
        assert location_call[0][1]["name"] == test_location_data["name"]
        assert location_call[0][1]["description"] == test_location_data["description"]
        assert location_call[0][1]["latitude"] == test_location_data["latitude"]
        assert location_call[0][1]["longitude"] == test_location_data["longitude"]

        # Second call should be for source record creation
        source_call = mock_db.execute.call_args_list[1]
        assert isinstance(source_call[0][0], TextClause)
        assert source_call[0][1]["location_id"] == location_id
        assert source_call[0][1]["scraper_id"] == "test_scraper"

        # Verify version was created
        assert mock_tracker_instance.create_version.call_count >= 1
        version_call = mock_tracker_instance.create_version.call_args_list[0]
        assert version_call[0][0] == location_id
        assert version_call[0][1] == "location"
        assert version_call[0][3] == "reconciler"


def test_create_address(mock_db: MagicMock, test_address_data: Dict[str, str]) -> None:
    """Test creating a new address."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock database response
        result = MagicMock()
        mock_db.execute.return_value = result

        address_id = location_creator.create_address(
            test_address_data["address_1"],
            test_address_data["city"],
            test_address_data["state_province"],
            test_address_data["postal_code"],
            test_address_data["country"],
            test_address_data["address_type"],
            {"source": "test"},
            location_id,
        )

        # Verify address SQL execution (no longer overwrites location name)
        assert mock_db.execute.call_count == 1  # Address insert only
        address_call = mock_db.execute.call_args_list[0]
        assert isinstance(address_call[0][0], TextClause)
        assert address_call[0][1]["address_1"] == test_address_data["address_1"]
        assert address_call[0][1]["city"] == test_address_data["city"]
        assert address_call[0][1]["location_id"] == location_id

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == address_id
        assert version_call[0][1] == "address"
        assert version_call[0][3] == "reconciler"


def test_create_accessibility(mock_db: MagicMock) -> None:
    """Test creating a new accessibility record."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock database response
        result = MagicMock()
        mock_db.execute.return_value = result

        accessibility_id = location_creator.create_accessibility(
            location_id,
            {"source": "test"},
            description="Test accessibility",
            details="Test details",
            url="http://test.com",
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["location_id"] == location_id
        assert call_args[0][1]["description"] == "Test accessibility"
        assert call_args[0][1]["details"] == "Test details"
        assert call_args[0][1]["url"] == "http://test.com"

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == accessibility_id
        assert version_call[0][1] == "accessibility"
        assert version_call[0][3] == "reconciler"


def test_retry_with_backoff_success(mock_db: MagicMock) -> None:
    """Test retry with backoff succeeds on first attempt."""
    location_creator = LocationCreator(mock_db)

    # Mock operation that succeeds
    mock_operation = MagicMock(return_value="success")

    result = location_creator._retry_with_backoff(mock_operation)

    assert result == "success"
    mock_operation.assert_called_once()


def test_retry_with_backoff_retry_and_succeed(mock_db: MagicMock) -> None:
    """Test retry with backoff retries on IntegrityError then succeeds."""
    location_creator = LocationCreator(mock_db)

    # Mock operation that fails once then succeeds
    mock_operation = MagicMock(side_effect=[IntegrityError("", "", ""), "success"])

    with patch("time.sleep") as mock_sleep, patch(
        "app.reconciler.location_creator.secrets.SystemRandom"
    ) as mock_random:
        mock_random.return_value.uniform.return_value = 0.1

        result = location_creator._retry_with_backoff(mock_operation)

        assert result == "success"
        assert mock_operation.call_count == 2
        mock_sleep.assert_called_once()


def test_retry_with_backoff_max_retries(mock_db: MagicMock) -> None:
    """Test retry with backoff fails after max retries."""
    location_creator = LocationCreator(mock_db)

    # Mock operation that always fails
    error = IntegrityError("", "", "")
    mock_operation = MagicMock(side_effect=error)

    # Mock _log_constraint_violation to avoid database calls
    with patch.object(location_creator, "_log_constraint_violation") as mock_log, patch(
        "time.sleep"
    ) as mock_sleep:

        with pytest.raises(IntegrityError):
            location_creator._retry_with_backoff(mock_operation, max_attempts=3)

        assert mock_operation.call_count == 3
        mock_log.assert_called_once()
        assert mock_sleep.call_count == 2  # Should sleep 2 times (attempts 1 and 2)


def test_log_constraint_violation_success(mock_db: MagicMock) -> None:
    """Test logging constraint violation succeeds."""
    location_creator = LocationCreator(mock_db)

    location_creator._log_constraint_violation(
        "location", "INSERT", {"error": "duplicate key", "attempt": 1}
    )

    # Verify SQL execution for logging
    mock_db.execute.assert_called_once()
    call_args = mock_db.execute.call_args
    assert isinstance(call_args[0][0], TextClause)
    assert call_args[0][1]["table_name"] == "location"
    assert call_args[0][1]["operation"] == "INSERT"
    assert "duplicate key" in call_args[0][1]["conflicting_data"]

    mock_db.commit.assert_called_once()


def test_log_constraint_violation_exception(mock_db: MagicMock) -> None:
    """Test logging constraint violation handles exceptions."""
    location_creator = LocationCreator(mock_db)

    # Mock database execute to raise exception
    mock_db.execute.side_effect = Exception("Database error")

    # Mock logger to verify error is logged
    with patch.object(location_creator, "logger") as mock_logger:
        location_creator._log_constraint_violation(
            "location", "INSERT", {"error": "duplicate key", "attempt": 1}
        )

        # Should log the error but not raise
        mock_logger.error.assert_called_once()
        assert "Failed to log constraint violation" in mock_logger.error.call_args[0][0]


def test_process_location_new(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test processing a new location."""
    location_creator = LocationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = str(uuid.uuid4())

    # Mock retry with backoff to return new location
    with patch.object(
        location_creator, "_retry_with_backoff"
    ) as mock_retry, patch.object(
        location_creator, "create_location_source"
    ) as mock_create_source, patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:

        mock_retry.return_value = (test_uuid, True)
        mock_create_source.return_value = "source-id"
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        location_id, is_new = location_creator.process_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify version was created for new location
        mock_tracker_instance.create_version.assert_called_once()

        # Verify result
        assert location_id == test_uuid
        assert is_new is True


def test_process_location_existing(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test processing an existing location."""
    location_creator = LocationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = str(uuid.uuid4())

    # Mock retry with backoff to return existing location
    with patch.object(
        location_creator, "_retry_with_backoff"
    ) as mock_retry, patch.object(
        location_creator, "create_location_source"
    ) as mock_create_source, patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker, patch(
        "app.reconciler.location_creator.MergeStrategy"
    ) as mock_merge_strategy:

        mock_retry.return_value = (test_uuid, False)
        mock_create_source.return_value = "source-id"
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance
        mock_merge_instance = MagicMock()
        mock_merge_strategy.return_value = mock_merge_instance

        location_id, is_new = location_creator.process_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify version was NOT created for existing location
        mock_tracker_instance.create_version.assert_not_called()

        # Verify merge was called with location_id and confidence score
        mock_merge_instance.merge_location.assert_called_once()
        merge_call_args = mock_merge_instance.merge_location.call_args
        assert merge_call_args[0][0] == test_uuid

        # Verify result
        assert location_id == test_uuid
        assert is_new is False


def test_process_location_with_organization_id(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test processing location with organization ID update."""
    location_creator = LocationCreator(mock_db)

    # Create a valid UUID for testing
    test_uuid = str(uuid.uuid4())
    org_id = str(uuid.uuid4())

    # Mock retry with backoff to return existing location
    with patch.object(
        location_creator, "_retry_with_backoff"
    ) as mock_retry, patch.object(
        location_creator, "create_location_source"
    ) as mock_create_source, patch(
        "app.reconciler.location_creator.MergeStrategy"
    ) as mock_merge_strategy:

        mock_retry.return_value = (test_uuid, False)
        mock_create_source.return_value = "source-id"
        mock_merge_instance = MagicMock()
        mock_merge_strategy.return_value = mock_merge_instance

        location_id, is_new = location_creator.process_location(
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"scraper_id": "test_scraper"},
            organization_id=org_id,
        )

        # Verify retry was called
        mock_retry.assert_called_once()

        # Verify source was created
        mock_create_source.assert_called_once()

        # Verify db.execute called for org_id update + confidence score query
        assert mock_db.execute.call_count == 2
        # First call: organization ID update
        org_call_args = mock_db.execute.call_args_list[0]
        assert isinstance(org_call_args[0][0], TextClause)
        assert org_call_args[0][1]["id"] == test_uuid
        assert org_call_args[0][1]["organization_id"] == org_id

        # Verify merge was called with location_id and confidence score
        mock_merge_instance.merge_location.assert_called_once()
        merge_call_args = mock_merge_instance.merge_location.call_args
        assert merge_call_args[0][0] == test_uuid

        # Verify result
        assert location_id == test_uuid
        assert is_new is False


def test_create_location_source_with_result(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test creating location source when query returns result."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock database result for INSERT...ON CONFLICT
    result = MagicMock()
    result.first.return_value = ["returned-source-id"]
    mock_db.execute.return_value = result

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        source_id = location_creator.create_location_source(
            location_id,
            "test_scraper",
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"source": "test"},
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        assert call_args[0][1]["location_id"] == location_id
        assert call_args[0][1]["scraper_id"] == "test_scraper"
        assert call_args[0][1]["name"] == test_location_data["name"]
        assert call_args[0][1]["description"] == test_location_data["description"]
        assert call_args[0][1]["latitude"] == test_location_data["latitude"]
        assert call_args[0][1]["longitude"] == test_location_data["longitude"]

        # Verify version was created
        mock_tracker_instance.create_version.assert_called_once()
        version_call = mock_tracker_instance.create_version.call_args
        assert version_call[0][0] == "returned-source-id"
        assert version_call[0][1] == "location_source"
        assert version_call[0][3] == "reconciler"

        # Verify commit was called
        mock_db.commit.assert_called_once()
        assert source_id == "returned-source-id"


def test_create_location_source_with_submarine_type(
    mock_db: MagicMock, test_location_data: Dict[str, Union[str, float]]
) -> None:
    """Test creating location source with source_type='submarine'."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock database result for INSERT...ON CONFLICT
    result = MagicMock()
    result.first.return_value = ["returned-source-id"]
    mock_db.execute.return_value = result

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        source_id = location_creator.create_location_source(
            location_id,
            "submarine",
            str(test_location_data["name"]),
            str(test_location_data["description"]),
            float(test_location_data["latitude"]),
            float(test_location_data["longitude"]),
            {"source": "submarine_crawl"},
            source_type="submarine",
        )

        # Verify SQL execution
        mock_db.execute.assert_called_once()
        call_args = mock_db.execute.call_args
        assert isinstance(call_args[0][0], TextClause)
        # Verify source_type parameter is "submarine"
        assert call_args[0][1]["source_type"] == "submarine"
        assert call_args[0][1]["scraper_id"] == "submarine"
        assert call_args[0][1]["location_id"] == location_id

        # Verify commit and version were created
        mock_db.commit.assert_called_once()
        mock_tracker_instance.create_version.assert_called_once()
        assert source_id == "returned-source-id"


def test_create_address_missing_postal_code(mock_db: MagicMock) -> None:
    """Test creating address with missing postal code."""
    location_creator = LocationCreator(mock_db)
    location_id = str(uuid.uuid4())

    # Mock version tracker
    with patch(
        "app.reconciler.location_creator.VersionTracker"
    ) as mock_version_tracker:
        mock_tracker_instance = MagicMock()
        mock_version_tracker.return_value = mock_tracker_instance

        # Mock logger to verify warning is logged
        with patch.object(location_creator, "logger") as mock_logger:
            address_id = location_creator.create_address(
                "123 Test St",
                "Test City",
                "CA",
                "",  # Empty postal code
                "US",
                "physical",
                {"source": "test"},
                location_id,
            )

            # Verify logger warning was called
            mock_logger.warning.assert_called_once()
            assert "Using default postal code" in mock_logger.warning.call_args[0][0]

            # Verify SQL execution with default CA postal code
            address_call = mock_db.execute.call_args_list[0]
            assert isinstance(address_call[0][0], TextClause)
            assert address_call[0][1]["postal_code"] == "90001"  # Default for CA
            assert address_call[0][1]["address_1"] == "123 Test St"
            assert address_call[0][1]["location_id"] == location_id
