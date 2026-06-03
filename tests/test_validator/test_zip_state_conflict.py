"""VAL-4 regression guard: a coarse ZIP lookup must not unilaterally override
a source-asserted state.

resolve_state_conflict previously returned the ZIP-derived state ("zip_primary")
whenever a ZIP mapped to a state, overwriting a non-empty claimed state with no
corroboration. get_state_from_zip is a coarse 3-digit-prefix table with gaps and
collisions, so this corrupted correct addresses. The fix keeps the claimed state
unless coordinates or city corroborate the ZIP.
"""

from app.core.zip_state_mapping import get_state_from_zip, resolve_state_conflict


def test_zip_does_not_override_claimed_without_corroboration():
    zip_state = get_state_from_zip("07102")  # Newark, NJ
    assert zip_state and zip_state != "NY"  # sanity: ZIP resolves, differs from claim

    resolved, reason = resolve_state_conflict(
        claimed_state="NY",
        postal_code="07102",
        city_name=None,
        coord_state=None,
    )
    assert resolved == "NY"  # claimed kept — not overwritten by the coarse ZIP
    assert reason == "zip_conflict_unverified_kept_claimed"


def test_zip_used_when_no_claimed_state():
    resolved, reason = resolve_state_conflict(
        claimed_state=None,
        postal_code="07102",
        city_name=None,
        coord_state=None,
    )
    assert resolved == get_state_from_zip("07102")
    assert reason == "zip_primary"


def test_coordinate_corroboration_still_corrects_claimed():
    """When coordinates agree with the ZIP, the correction still happens."""
    zip_state = get_state_from_zip("07102")
    resolved, reason = resolve_state_conflict(
        claimed_state="NY",
        postal_code="07102",
        city_name=None,
        coord_state=zip_state,
    )
    assert resolved == zip_state
    assert reason == "zip_coord_agreement"


def test_matching_claimed_and_zip_unchanged():
    zip_state = get_state_from_zip("07102")
    resolved, reason = resolve_state_conflict(
        claimed_state=zip_state,
        postal_code="07102",
        city_name=None,
        coord_state=None,
    )
    assert resolved == zip_state
    assert reason == "zip_primary"
