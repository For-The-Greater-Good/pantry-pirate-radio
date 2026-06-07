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


def _traceable(token: str, blob: bytes) -> bool:
    """Is ``token`` present in the vendored suite (read as raw bytes) in ANY
    representation a vendored file could carry it? A hex token may appear as hex TEXT
    (rfc6962 vectors.json stores hashes as hex) OR as its raw decoded bytes (jcs
    output files store the canonical bytes, and the jcs vector's expected is the hex
    OF those bytes). A non-hex string token appears as its UTF-8 bytes. Trying every
    representation keeps the check correct across suites while staying teeth-bearing:
    a self-derived value present in NO representation still fails."""
    cands: list[bytes] = [token.encode("utf-8")]
    is_hex = (
        len(token) >= 2
        and len(token) % 2 == 0
        and all(c in "0123456789abcdefABCDEF" for c in token)
    )
    if is_hex:
        cands.append(token.lower().encode("ascii"))
        cands.append(token.upper().encode("ascii"))
        try:
            cands.append(bytes.fromhex(token))
        except ValueError:
            pass
    return any(c in blob for c in cands)


def _anchorable_tokens(vec: dict) -> set[str]:
    """The load-bearing values of an accept vector that must trace to the vendor:
    every hex string (≥16) in input+expected, plus a non-hex string ``expected``
    (e.g. a canonical JSON output)."""
    tokens = set(_hex_strings(vec.get("input"))) | set(
        _hex_strings(vec.get("expected"))
    )
    exp = vec.get("expected")
    if isinstance(exp, str) and len(exp) >= 8:
        tokens.add(exp)
    return tokens


def test_anchored_areas_actually_trace_to_a_vendored_suite():
    """The load-bearing honesty invariant (anti-self-grading). An area labeled
    interop_status=anchored MUST name a real vendor/<suite>/ in derives_from AND
    EVERY load-bearing value of EVERY accept vector (the values actually under test)
    must appear verbatim in that vendored suite (read as raw bytes, any
    representation). Checking only ONE incidental match would let a PPR-self-derived
    area (the export_wire mislabel #555-class defect) wear an "anchored" label by
    carrying a single decoy vendored value — so the trace is a full subset check, not
    an existence check. Reject vectors carry deliberately-corrupted bytes (a flipped
    proof, a wrong root) and are excluded."""
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
        # Read the WHOLE vendored suite as raw bytes (covers hex-text suites like
        # rfc6962/vectors.json AND raw-text suites like jcs_rfc8785/output/*.json).
        blob = b"".join(
            p.read_bytes() for p in sorted(suite_dir.rglob("*")) if p.is_file()
        )
        checked_any = False
        for vec in manifest["vectors"]:
            if vec["must_reject"]:
                continue  # reject vectors deliberately carry non-vendored corrupt bytes
            tokens = _anchorable_tokens(vec)
            checked_any = checked_any or bool(tokens)
            for token in tokens:
                assert _traceable(token, blob), (
                    f"anchored area {manifest['area']} accept vector {vec['id']} carries "
                    f"a value NOT found in vendored suite {suite}: {token[:32]!r}… — the "
                    "value under test is self-derived, 'anchored' is unsubstantiated"
                )
        assert checked_any, (
            f"anchored area {manifest['area']} has no checkable vendored values — an "
            "'anchored' label with nothing traceable is vacuous"
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


def test_jcs_vectors_match_the_vendored_output_byte_for_byte():
    """The jcs area's anchor: each vector's expected (hex) MUST byte-decode to the
    exact vendored RFC-8785 output file, and the input to the vendored input file —
    so the anchored bytes are the upstream cyberphone bytes, not re-authored."""
    jcs = next(m for _p, m in runner.iter_manifests() if m["area"] == "jcs")
    suite = _VENDOR / "jcs_rfc8785"
    assert jcs["vectors"], "jcs area is empty"
    for vec in jcs["vectors"]:
        assert vec["interop_pending"] is False, f"{vec['id']} must be anchored"
        name = vec["id"].split("-")[1]  # jcs-<name>-001
        expected_bytes = bytes.fromhex(vec["expected"])
        assert (
            expected_bytes == (suite / "output" / f"{name}.json").read_bytes()
        ), f"jcs vector {vec['id']} expected != vendored output/{name}.json"
        assert vec["input"]["value"] == json.loads(
            (suite / "input" / f"{name}.json").read_text(encoding="utf-8")
        ), f"jcs vector {vec['id']} input != vendored input/{name}.json"
