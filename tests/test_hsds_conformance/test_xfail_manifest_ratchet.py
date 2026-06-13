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

from tests.test_hsds_conformance._fixture_map import (
    FIXTURE_MODEL_MAP,
    NO_MODEL_FIXTURES,
    VENDOR_DIR,
    ModelNotFoundError,
    load_manifest,
    resolve_model,
)

_VALID_FAILURE_MODES = ("model_missing", "validation")


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


def test_every_vendored_json_is_mapped_or_no_model() -> None:
    """Every top-level vendored ``*.json`` fixture must be tracked somewhere.

    ``VENDOR_DIR`` (``vendor/hsds_official_examples/``, NOT its ``csv/``
    subdirectory) holds the official HSDS example JSON files. Each one must be
    either a key in ``FIXTURE_MODEL_MAP`` (exercised by the Tier A/B KATs) or
    listed in ``NO_MODEL_FIXTURES`` (corpus-presence-only, intentionally
    unexercised). A fixture in neither set has silently fallen out of the
    conformance gate entirely — still vendored, but no longer checked by
    anything. This test is UNCONDITIONAL (no xfail) so that hole cannot hide.
    """
    vendored_json = {p.name for p in VENDOR_DIR.glob("*.json")}
    tracked = set(FIXTURE_MODEL_MAP) | set(NO_MODEL_FIXTURES)
    untracked = sorted(vendored_json - tracked)
    assert not untracked, (
        f"vendored fixture(s) {untracked} under {VENDOR_DIR} are neither a key "
        "in FIXTURE_MODEL_MAP nor listed in NO_MODEL_FIXTURES — they have "
        "silently fallen out of the conformance gate. Add each to "
        "FIXTURE_MODEL_MAP (with a manifest row if it currently fails) or to "
        "NO_MODEL_FIXTURES if it is intentionally corpus-presence-only."
    )


def test_no_orphan_manifest_rows() -> None:
    """Every manifest row's ``fixture`` must be a key in ``FIXTURE_MODEL_MAP``.

    If a fixture is dropped from ``FIXTURE_MODEL_MAP`` (e.g. by accident, or
    during a refactor) but its manifest rows are left behind, those rows
    become orphans: ``test_tier_a_representation.py`` /
    ``test_tier_b_roundtrip.py`` iterate ``FIXTURE_MODEL_MAP`` to build their
    parametrizations, so the fixture silently stops being exercised at all
    while its now-meaningless xfail rows continue to count toward BASELINE.
    This test is UNCONDITIONAL (no xfail) so that orphan signature cannot hide.
    """
    manifest = load_manifest()
    orphans = sorted(
        {
            entry["fixture"]
            for entry in manifest
            if entry["fixture"] not in FIXTURE_MODEL_MAP
        }
    )
    assert not orphans, (
        f"xfail_manifest.json references fixture(s) {orphans} that are NOT "
        "keys in FIXTURE_MODEL_MAP. These rows are orphaned — the fixture has "
        "fallen out of the Tier A/B KAT parametrizations entirely while its "
        "manifest rows remain. Either restore the FIXTURE_MODEL_MAP entry or "
        "remove the orphaned manifest row(s)."
    )


def test_manifest_failure_modes_are_consistent() -> None:
    """Cross-check every manifest row's ``failure_mode`` against ``resolve_model``.

    Each row must carry a ``failure_mode`` of either ``"model_missing"`` (the
    fixture's target model does not exist yet — ``resolve_model`` raises
    ``ModelNotFoundError``) or ``"validation"`` (the model exists but
    ``model_validate`` rejects the example's shape — ``resolve_model`` must
    SUCCEED).

    This distinguishes "not implemented yet" from "implemented but wrong" and
    catches a typo'd dotted path in ``FIXTURE_MODEL_MAP``: a ``"validation"``
    row whose model path is misspelled would make ``resolve_model`` raise
    ``ModelNotFoundError`` — which this test flags as inconsistent (a typo
    masquerading as a clean not-yet-implemented xfail) rather than letting it
    silently pass as an ordinary xfail.

    For ``"model_missing"`` rows, ``resolve_model`` must raise
    ``ModelNotFoundError`` — confirming the model is genuinely absent. When a
    later slice (e.g. T1) adds the model, ``resolve_model`` starts succeeding,
    this test starts failing for that row, and the fixture's KAT either passes
    (XPASS under ``strict=True`` in test_tier_a/b) or now fails for
    ``"validation"`` reasons — either way the manifest row must be updated,
    which this failure forces.
    """
    manifest = load_manifest()
    bad_modes: list[tuple[str, str, str]] = []
    inconsistent: list[tuple[str, str, str, str]] = []

    for entry in manifest:
        fixture = entry["fixture"]
        tier = entry["tier"]
        failure_mode = entry.get("failure_mode")

        if failure_mode not in _VALID_FAILURE_MODES:
            bad_modes.append((fixture, tier, str(failure_mode)))
            continue

        model_path = FIXTURE_MODEL_MAP.get(fixture)
        if model_path is None:
            # Orphan rows are reported by test_no_orphan_manifest_rows; skip
            # here to avoid a confusing double-failure on the same root cause.
            continue

        try:
            resolve_model(model_path)
        except ModelNotFoundError:
            resolved = False
        else:
            resolved = True

        if failure_mode == "model_missing" and resolved:
            inconsistent.append(
                (
                    fixture,
                    tier,
                    failure_mode,
                    f"resolve_model({model_path!r}) succeeded, but this row "
                    'claims "model_missing" — the model now exists; update '
                    "failure_mode (and likely flip/remove this row).",
                )
            )
        elif failure_mode == "validation" and not resolved:
            inconsistent.append(
                (
                    fixture,
                    tier,
                    failure_mode,
                    f"resolve_model({model_path!r}) raised ModelNotFoundError, "
                    'but this row claims "validation" (model exists but '
                    "rejects the example). Either FIXTURE_MODEL_MAP has a "
                    "typo'd/incorrect dotted path for this fixture, or "
                    'failure_mode should be "model_missing".',
                )
            )

    assert not bad_modes, (
        f"manifest rows with invalid/missing failure_mode (must be one of "
        f"{_VALID_FAILURE_MODES}): {bad_modes}"
    )
    assert not inconsistent, "manifest failure_mode inconsistencies:\n" + "\n".join(
        f"  {fixture} (tier {tier}, failure_mode={failure_mode}): {msg}"
        for fixture, tier, failure_mode, msg in inconsistent
    )
