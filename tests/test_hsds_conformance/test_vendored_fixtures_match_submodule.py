"""Fidelity guard: vendored fixture bytes must equal the submodule originals.

G1 (HSDS full-compliance epic, issue #593). The conformance fixtures vendored
under ``vendor/hsds_official_examples/`` (see
``tests/test_hsds_conformance/vendor/hsds_official_examples/README.md``) are
claimed to be byte-exact (``cp -p``) copies of
``docs/HSDS/examples/*.json`` / ``docs/HSDS/examples/csv/*.csv`` taken at the
pinned submodule commit (``test_submodule_pin_guard.py``). That claim was
never actually checked — a vendored file could silently diverge (a stray edit,
a partial re-vendor, a copy-paste typo) while the pin guard continues to pass
(the pin guard only checks the submodule commit SHA, not file contents).

This test reads every vendored file under ``VENDOR_DIR`` (recursing into
``csv/``) and asserts its bytes equal the corresponding file under
``docs/HSDS/examples/`` in the submodule, with one documented exception:
``csv/datapackage.json`` is vendored as a *resolved* copy of
``docs/HSDS/datapackage.json`` (the submodule's
``examples/csv/datapackage.json`` is a symlink to that file, per the README).

If ``docs/HSDS`` is not checked out, this test SKIPS LOUDLY (a clear message
naming the init command) rather than silently passing — CI initializes the
submodule (see ``ci.yml``), so this runs for real there.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_hsds_conformance._fixture_map import VENDOR_DIR

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SUBMODULE_EXAMPLES_DIR = _REPO_ROOT / "docs" / "HSDS" / "examples"
_SUBMODULE_ROOT = _REPO_ROOT / "docs" / "HSDS"

# Vendored files whose submodule "original" is NOT the same-relative-path file
# under docs/HSDS/examples/. csv/datapackage.json is vendored as a *resolved*
# copy of docs/HSDS/datapackage.json (examples/csv/datapackage.json is a
# symlink to it in the submodule — see the vendor README).
_RESOLVED_ORIGINAL_OVERRIDES: dict[str, Path] = {
    "csv/datapackage.json": _SUBMODULE_ROOT / "datapackage.json",
}


def _relative_vendored_files() -> list[str]:
    """Return relative paths (posix-style) of all vendored fixture files.

    Recurses into ``csv/``. Excludes non-fixture files (e.g. ``README.md``)
    at the top level of ``VENDOR_DIR``.
    """
    if not VENDOR_DIR.is_dir():
        return []
    paths = []
    for path in sorted(VENDOR_DIR.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(VENDOR_DIR)
        if rel.name == "README.md" and rel.parent == Path("."):
            continue
        paths.append(rel.as_posix())
    return paths


def _original_path_for(relpath: str) -> Path:
    """Return the submodule path that ``relpath`` (under VENDOR_DIR) was copied from."""
    if relpath in _RESOLVED_ORIGINAL_OVERRIDES:
        return _RESOLVED_ORIGINAL_OVERRIDES[relpath]
    return _SUBMODULE_EXAMPLES_DIR / relpath


def _skip_if_submodule_absent() -> None:
    """Skip loudly ONLY when docs/HSDS is genuinely uninitialized.

    Discriminator: an *initialized* submodule has a ``docs/HSDS/.git`` gitlink
    (the same signal ``test_submodule_pin_guard.py`` relies on); an
    uninitialized one is a bare mountpoint dir with no ``.git``. So:

    - no ``docs/HSDS/.git`` -> the submodule isn't checked out -> skip loud.
    - ``.git`` present but ``examples/`` missing -> a partial/corrupt checkout,
      NOT an uninitialized submodule -> FAIL loud. A partial delete must not be
      able to silently bypass the byte-fidelity guard while the pin-guard (which
      only checks the HEAD SHA) still passes (Gauntlet attack 6d).
    """
    if not (_SUBMODULE_ROOT / ".git").exists():
        pytest.skip(
            "docs/HSDS submodule not checked out; run `git submodule update "
            "--init docs/HSDS` to verify vendored fixture fidelity."
        )
    if not _SUBMODULE_EXAMPLES_DIR.is_dir():
        raise AssertionError(
            "docs/HSDS is initialized (.git present) but its examples/ dir is "
            f"missing at {_SUBMODULE_EXAMPLES_DIR} — a partial/corrupt submodule "
            "checkout. Fixture fidelity cannot be verified and must NOT be "
            "silently skipped; re-init with `git submodule update --init "
            "--force docs/HSDS`."
        )


_VENDORED_RELPATHS = _relative_vendored_files()


@pytest.mark.parametrize("relpath", _VENDORED_RELPATHS, ids=_VENDORED_RELPATHS)
def test_vendored_fixture_matches_submodule_original(relpath: str) -> None:
    """``vendor/hsds_official_examples/<relpath>`` must be byte-identical to its submodule source.

    Skips loudly (naming the init command) if ``docs/HSDS`` is not checked
    out. Otherwise asserts byte-for-byte equality with the original file in
    the submodule (resolving the ``csv/datapackage.json`` symlink override
    documented in the vendor README).
    """
    _skip_if_submodule_absent()

    vendored_path = VENDOR_DIR / relpath
    original_path = _original_path_for(relpath)

    assert original_path.is_file(), (
        f"submodule original for vendored file {relpath!r} not found at "
        f"{original_path} (docs/HSDS checked out but the expected source file "
        "is missing)."
    )

    vendored_bytes = vendored_path.read_bytes()
    original_bytes = original_path.read_bytes()

    assert vendored_bytes == original_bytes, (
        f"vendored fixture {relpath!r} ({vendored_path}) does not match its "
        f"submodule original ({original_path}) byte-for-byte. Re-vendor this "
        "file (byte-exact `cp -p`) from the pinned docs/HSDS submodule commit."
    )


def test_at_least_one_fixture_was_checked() -> None:
    """Sanity check: the parametrization must not be silently empty.

    If ``VENDOR_DIR`` ever became empty or unreadable, the parametrized test
    above would simply collect zero items and "pass" by vacuous truth. This
    test fails loudly in that scenario instead.
    """
    assert _VENDORED_RELPATHS, f"no vendored fixture files found under {VENDOR_DIR}"
