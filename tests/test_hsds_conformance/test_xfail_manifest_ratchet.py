"""Shrink-only ratchet over ``xfail_manifest.json`` (constitution coverage-ratchet style).

G1 (HSDS full-compliance epic, issue #593). ``xfail_manifest.json`` is the
SHRINK-ONLY baseline of currently-failing HSDS conformance KATs (Tier A
``model_validate`` and Tier B JCS round-trip). Each later slice (G3, T1, L1-L5,
S1-S5, O1-O4, A1, ...) flips a fixture from failing to passing by REMOVING its
manifest row(s) — `test_tier_a_representation.py` / `test_tier_b_roundtrip.py`
then enforce (via ``strict=True`` xfail) that a flipped fixture's row is
actually gone, because a still-passing-but-still-manifested row becomes an
XPASS failure.

This module enforces the manifest's own integrity:
  (a) entries are unique (no duplicate ``(fixture, tier)`` pairs masking a
      double-count or a copy-paste error);
  (b) every manifest fixture file actually exists in the vendor dir (no
      phantom rows referencing typo'd or deleted fixtures);
  (c) ``len(manifest) <= BASELINE`` — the shrink-only invariant itself.

BASELINE-bump procedure (the ONLY legitimate way to increase this number):
A future PR adds a genuinely NEW fixture to ``FIXTURE_MODEL_MAP`` (e.g. a new
official HSDS example file is vendored, or a new model is mapped to an
existing fixture for a second tier) that ALSO currently fails its KAT. That PR
adds the corresponding manifest row(s) AND bumps ``BASELINE`` by the same
count, with a comment explaining which new fixture/tier pair(s) were added and
why. Bumping BASELINE to merely accommodate a regression (an existing fixture
that used to pass and now doesn't) is NOT legitimate — that is a real
regression and must be fixed instead.
"""

from tests.test_hsds_conformance._fixture_map import VENDOR_DIR, load_manifest

# Initial committed count (G1, issue #593): 11 fixtures x 2 tiers (A and B),
# every entity/list fixture in FIXTURE_MODEL_MAP fails both KATs today. See
# the module docstring for the bump procedure.
BASELINE = 22


def test_manifest_entries_are_unique() -> None:
    """No duplicate ``(fixture, tier)`` pairs in the manifest."""
    manifest = load_manifest()
    seen: set[tuple[str, str]] = set()
    duplicates: list[tuple[str, str]] = []
    for entry in manifest:
        key = (entry["fixture"], entry["tier"])
        if key in seen:
            duplicates.append(key)
        seen.add(key)
    assert not duplicates, f"duplicate (fixture, tier) manifest entries: {duplicates}"


def test_manifest_fixtures_exist_in_vendor_dir() -> None:
    """Every manifest ``fixture`` must be a real file under the vendor dir."""
    manifest = load_manifest()
    missing = [
        entry["fixture"]
        for entry in manifest
        if not (VENDOR_DIR / entry["fixture"]).is_file()
    ]
    assert (
        not missing
    ), f"manifest references fixtures not present in {VENDOR_DIR}: {missing}"


def test_manifest_entries_have_valid_tiers() -> None:
    """Every manifest entry's ``tier`` must be ``"A"`` or ``"B"``."""
    manifest = load_manifest()
    invalid = [
        (entry["fixture"], entry["tier"])
        for entry in manifest
        if entry["tier"] not in ("A", "B")
    ]
    assert (
        not invalid
    ), f"manifest entries with invalid tier (must be A or B): {invalid}"


def test_manifest_does_not_exceed_baseline() -> None:
    """SHRINK-ONLY: the manifest must never grow beyond BASELINE without review.

    See the module docstring for the legitimate BASELINE-bump procedure. If
    this fails because the manifest SHRANK (a fixture was flipped to passing
    and its rows removed), lower BASELINE to ``len(manifest)`` in the same PR
    that flips the fixture.
    """
    manifest = load_manifest()
    assert len(manifest) <= BASELINE, (
        f"xfail_manifest.json grew to {len(manifest)} entries, exceeding "
        f"BASELINE={BASELINE}. Growth is only legitimate when a genuinely NEW "
        "fixture/tier pair was added (see the BASELINE-bump procedure in this "
        "module's docstring) — bump BASELINE in the same PR with a comment "
        "explaining the new entries. Otherwise this is a regression."
    )


def test_manifest_is_at_baseline() -> None:
    """Track manifest shrinkage: a shrunk manifest should lower BASELINE too.

    This test is intentionally exact (not ``<=``) so a successful flip (which
    removes manifest rows) is immediately visible as a failure here, prompting
    the BASELINE edit in the same PR — keeping the ratchet honest rather than
    silently permitting slack between the real count and BASELINE.
    """
    manifest = load_manifest()
    assert len(manifest) == BASELINE, (
        f"xfail_manifest.json has {len(manifest)} entries but BASELINE="
        f"{BASELINE}. If entries were REMOVED (a fixture was flipped to "
        "passing), lower BASELINE to match in this PR. If entries were ADDED, "
        "see the BASELINE-bump procedure in this module's docstring."
    )
