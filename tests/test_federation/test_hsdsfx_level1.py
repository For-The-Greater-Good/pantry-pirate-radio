"""HSDS-FX Level-1 conformance — the reference adapter runs the canonical corpus.

This is PPR's CI conformance gate (design §8.5a): the reference implementation
(``RefAdapter`` over ``app.federation``) MUST pass every Level-1 wire-conformance
vector in ``conformance/hsdsfx/vectors/``. The same corpus is what a foreign
implementation runs through its own adapter to certify HSDS-FX conformance.

Slice 1 = the envelope areas (content-address, proof, assembly). Later slices add
checkpoint, merkle, export-wire, federation_id, activity by extending the corpus +
the adapter — this test file picks them up automatically.
"""

from __future__ import annotations

import json

import pytest

from tests.test_federation.conformance import runner
from tests.test_federation.conformance.adapter import RefAdapter


def _all_vectors():
    out = []
    for _path, manifest in runner.iter_manifests():
        for vec in manifest["vectors"]:
            out.append((manifest["area"], vec["id"]))
    return out


def test_corpus_is_present_and_nonempty():
    vectors = _all_vectors()
    assert (
        vectors
    ), "no HSDS-FX conformance vectors found in conformance/hsdsfx/vectors/"


def test_manifests_validate_against_schema():
    """Every manifest conforms to manifest.schema.json (accept⇒expected,
    reject⇒no-expected)."""
    import jsonschema

    schema = json.loads(
        (runner.CORPUS_DIR.parent / "manifest.schema.json").read_text(encoding="utf-8")
    )
    for _path, manifest in runner.iter_manifests():
        jsonschema.validate(manifest, schema)


def test_reference_impl_passes_every_level1_vector():
    """The load-bearing gate: RefAdapter reproduces every accept vector byte-for-
    byte and rejects every must_reject vector."""
    report = runner.verify_level1(RefAdapter())
    failures = [f"{r.area}/{r.vector_id}: {r.detail}" for r in report.failed]
    assert not failures, "Level-1 conformance failures:\n" + "\n".join(failures)
    assert report.passed > 0


def test_report_separates_anchored_from_interop_pending():
    """The report must distinguish externally-anchored passes from PPR-native
    (interop-pending) ones — honesty for the RFC (anti-self-grading)."""
    report = runner.verify_level1(RefAdapter())
    # The suite is genuinely mixed: interop_pending (new-canonical composition,
    # e.g. the envelope areas) AND anchored (externally validated, e.g. the
    # checkpoint Go sumdb/note KAT). Both halves must be non-empty so the
    # distinction is real, not vacuous.
    assert report.interop_pending_passed > 0
    assert report.anchored_passed > 0
    assert report.anchored_passed + report.interop_pending_passed == report.passed


@pytest.mark.parametrize("area,vector_id", _all_vectors())
def test_each_vector_individually(area, vector_id):
    """One node per vector so a single bad vector is pinpointed in CI output."""
    report = runner.verify_level1(RefAdapter())
    match = next(
        r for r in report.results if r.area == area and r.vector_id == vector_id
    )
    assert match.passed, f"{area}/{vector_id}: {match.detail}"
