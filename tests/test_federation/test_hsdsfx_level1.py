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

import importlib.util
import json
from pathlib import Path

import pytest

from tests.test_federation.conformance import runner
from tests.test_federation.conformance.adapter import RefAdapter

_VENDOR = Path(__file__).resolve().parent / "vendor"


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


# --- structural / honesty invariants (Gauntlet remediation) --------------------
# The runner globs every vectors/*.json while generate.py --check only regenerates
# the _AREAS it knows about. A hand-authored manifest (e.g. falsely labeled
# "anchored") could otherwise be executed and counted while sailing past the drift
# gate. These tests pin the invariants in the pytest gate too, not only in --check.


def _load_generator():
    gen_path = runner.CORPUS_DIR.parent / "generate.py"
    spec = importlib.util.spec_from_file_location("hsdsfx_generate", gen_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_corpus_is_closed_world():
    """Every vectors/*.json MUST be produced by the generator — no orphan/smuggled
    manifest (the open-set drift hole), and none missing."""
    gen = _load_generator()
    on_disk = {p.name for p in runner.CORPUS_DIR.glob("*.json")}
    expected = set(gen._AREAS)
    assert on_disk == expected, (
        f"corpus/generator mismatch — orphan: {sorted(on_disk - expected)}, "
        f"missing: {sorted(expected - on_disk)}"
    )


def test_every_boolean_verify_area_ships_a_reject_vector():
    """Teeth invariant: a positive verify vector is rubber-stampable (an always-True
    adapter passes it), so any area exercising a boolean verify op MUST also ship at
    least one must_reject vector — otherwise the area is silently toothless."""
    for _path, manifest in runner.iter_manifests():
        ops = {v["op"] for v in manifest["vectors"]}
        if not (ops & runner._BOOLEAN_OPS):
            continue
        has_reject = any(v["must_reject"] for v in manifest["vectors"])
        assert has_reject, (
            f"area {manifest['area']} exercises boolean verify op(s) "
            f"{sorted(ops & runner._BOOLEAN_OPS)} but ships no must_reject vector"
        )


def _hex_strings(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, str):
        s = obj.lower()
        if len(s) >= 16 and len(s) % 2 == 0 and all(c in "0123456789abcdef" for c in s):
            out.append(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_hex_strings(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(_hex_strings(v))
    return out


def test_anchored_areas_actually_trace_to_a_vendored_suite():
    """The load-bearing honesty invariant (anti-self-grading). An area labeled
    interop_status=anchored MUST name a real vendor/<suite>/ in derives_from AND at
    least one of its byte values must appear verbatim in that vendored suite — so a
    PPR-self-derived area (the export_wire mislabel #555-class defect) cannot wear an
    "anchored" label undetected."""
    anchored = [
        m for _p, m in runner.iter_manifests() if m["interop_status"] == "anchored"
    ]
    assert anchored, "no anchored area present — the suite would be all self-graded"
    for manifest in anchored:
        df = manifest.get("derives_from", "")
        assert (
            "vendor/" in df
        ), f"anchored area {manifest['area']} must name vendor/<suite> in derives_from"
        suite = df.split("vendor/", 1)[1].split()[0].rstrip("/")
        suite_dir = _VENDOR / suite
        assert (
            suite_dir.is_dir()
        ), f"anchored area {manifest['area']} derives_from missing vendor dir {suite_dir}"
        vendor_text = "".join(
            p.read_text(encoding="utf-8") for p in suite_dir.glob("*.json")
        ).lower()
        area_hex = set()
        for vec in manifest["vectors"]:
            area_hex.update(_hex_strings(vec.get("input")))
            area_hex.update(_hex_strings(vec.get("expected")))
        traced = [h for h in area_hex if h in vendor_text]
        assert traced, (
            f"anchored area {manifest['area']} has NO byte value present in its "
            f"vendored suite {suite} — 'anchored' is unsubstantiated (self-graded?)"
        )


def test_go_kat_vector_matches_the_vendored_note_byte_for_byte():
    """The one per-vector anchor in the (interop_pending) checkpoint area: the Go
    sumdb/note KAT expected MUST equal the vendored signed note exactly."""
    vendored = json.loads(
        (_VENDOR / "c2sp_sumdb_note" / "vectors.json").read_text(encoding="utf-8")
    )
    checkpoint = next(
        m for _p, m in runner.iter_manifests() if m["area"] == "checkpoint"
    )
    kat = next(v for v in checkpoint["vectors"] if v["id"] == "cp-note-go-kat-001")
    assert kat["interop_pending"] is False, "the Go KAT must be marked anchored"
    assert kat["expected"] == vendored["signed_note"]
