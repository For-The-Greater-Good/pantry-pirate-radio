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


def _hex_strings(obj, out: set | None = None) -> set:
    """Every ``>=16``-char even-length hex string anywhere in a JSON value."""
    out = set() if out is None else out
    if isinstance(obj, str):
        s = obj.lower()
        if len(s) >= 16 and len(s) % 2 == 0 and all(c in "0123456789abcdef" for c in s):
            out.add(s)
    elif isinstance(obj, dict):
        for v in obj.values():
            _hex_strings(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _hex_strings(v, out)
    return out


def _is_hex(s) -> bool:
    return (
        isinstance(s, str)
        and len(s) >= 2
        and len(s) % 2 == 0
        and all(c in "0123456789abcdefABCDEF" for c in s)
    )


def _vendored_anchors(suite_dir: Path) -> tuple[set[str], set[bytes]]:
    """The EXACT vendored values an anchored vector may reference — never a substring,
    so a mid-file fragment or a coincidental short byte run is NOT an anchor (the
    bug a prior Gauntlet found in the substring trace). Returns
    ``(hex_values, blobs)``: ``hex_values`` = every ``>=16`` hex string INSIDE the
    parsed fixture JSON (e.g. rfc6962 hashes, as text); ``blobs`` = each fixture
    file's whole bytes (and newline-stripped) PLUS every hex value raw-decoded — so a
    hash matches as raw bytes and a canonical-output file (jcs) matches as a whole."""
    hex_values: set[str] = set()
    blobs: set[bytes] = set()
    for p in sorted(suite_dir.rglob("*")):
        if not p.is_file() or p.suffix.lower() != ".json":
            continue  # fixtures only — README/NOTICE prose must not anchor a token
        raw = p.read_bytes()
        blobs.add(raw)
        blobs.add(raw.rstrip(b"\n"))
        try:
            _hex_strings(json.loads(raw.decode("utf-8")), hex_values)
        except (ValueError, UnicodeDecodeError):
            pass
    for h in hex_values:
        blobs.add(bytes.fromhex(h))
    return hex_values, blobs


def _token_anchored(token: str, hex_values: set[str], blobs: set[bytes]) -> bool:
    """A token is anchored iff it EXACTLY matches a complete vendored value: a hex
    token either equals a vendored hex string (rfc6962) or raw-decodes to a complete
    vendored value (a jcs output file); a non-hex token equals a vendored value as
    UTF-8. Exact membership, never a substring."""
    if _is_hex(token):
        if token.lower() in hex_values:
            return True
        try:
            return bytes.fromhex(token) in blobs
        except ValueError:
            return False
    return token.encode("utf-8") in blobs


def _expected_bytes(exp) -> bytes | None:
    """The byte form of a producer op's expected output (hex → raw; str → utf-8)."""
    if _is_hex(exp):
        return bytes.fromhex(exp)
    if isinstance(exp, str):
        return exp.encode("utf-8")
    return None


def _anchored_violations(manifest: dict, suite_dir: Path) -> list[str]:
    """Every way an anchored area's accept vectors fail to trace to its vendored
    suite (empty == honest). Factored out so the teeth tests can drive it on a forged
    manifest without the dir/derives_from scaffolding."""
    hex_values, blobs = _vendored_anchors(suite_dir)
    problems: list[str] = []
    checked_any = False
    for vec in manifest["vectors"]:
        if vec["must_reject"]:
            continue  # reject vectors carry deliberately-corrupted (non-vendored) bytes
        tokens = _hex_strings(vec.get("input")) | _hex_strings(vec.get("expected"))
        for token in tokens:
            if not _token_anchored(token, hex_values, blobs):
                problems.append(
                    f"{vec['id']}: token {token[:32]}… not a vendored value"
                )
        exp = vec.get("expected")
        if isinstance(exp, bool):
            # verify op: the anchored bytes are the (already-checked) input tokens.
            if not tokens:
                problems.append(
                    f"{vec['id']}: verify accept with no vendored input token"
                )
        else:
            # producer op: the OUTPUT ITSELF must be a complete vendored value — not
            # merely some input decoy (the hole a prior Gauntlet found: a
            # non-tokenizable expected + one public-blob decoy passed).
            eb = _expected_bytes(exp)
            if eb is None or eb not in blobs:
                problems.append(
                    f"{vec['id']}: expected output is not a complete vendored value"
                )
        checked_any = True
    if not checked_any:
        problems.append("area has no checkable accept vector (vacuous 'anchored')")
    return problems


def test_anchored_areas_actually_trace_to_a_vendored_suite():
    """The load-bearing honesty invariant (anti-self-grading). An area labeled
    interop_status=anchored MUST name a real vendor/<suite>/ in derives_from, and
    EVERY load-bearing value of EVERY accept vector must EXACTLY match a complete
    vendored value: a verify op's input hashes (rfc6962) and a producer op's output
    bytes (jcs canonical output) must each be a whole vendored value, never a
    substring/fragment. This is what stops a PPR-self-derived area (the export_wire
    #555-class defect) from wearing an 'anchored' label."""
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
        problems = _anchored_violations(manifest, suite_dir)
        assert not problems, (
            f"anchored area {manifest['area']} is not honestly anchored to {suite}:\n"
            + "\n".join(problems)
        )


@pytest.mark.parametrize(
    "forged_expected",
    [
        42,  # a non-tokenizable number output (the prior breach)
        "One",  # a short self-derived string
        "[1,2,3]",  # a short structure-as-string
        "3432",  # hex whose raw bytes ('42') only occur mid-file, not as a whole value
        "deadbeefdeadbeefdeadbeef",  # a self-derived long hex not in the suite
    ],
)
def test_honesty_check_catches_a_self_derived_anchored_output(forged_expected):
    """Teeth regression guard (pins the prior breach closed): a forged 'anchored' jcs
    vector whose self-derived OUTPUT is not a complete vendored value MUST be caught —
    EVEN when the input carries a genuinely-tracing decoy (the hex of a whole vendored
    output file). The expected-output rule is what catches it, not the decoy."""
    suite_dir = _VENDOR / "jcs_rfc8785"
    tracing_decoy = (suite_dir / "output" / "values.json").read_bytes().hex()
    forged = {
        "area": "jcs",
        "interop_status": "anchored",
        "vectors": [
            {
                "id": "jcs-FORGED-001",
                "op": "canonicalize",
                "input": {"value": {"decoy": tracing_decoy}},
                "expected": forged_expected,
                "must_reject": False,
            }
        ],
    }
    # The decoy itself DOES trace (proving the catch is the expected rule, not it):
    assert not _anchored_violations(
        {**forged, "vectors": [{**forged["vectors"][0], "expected": tracing_decoy}]},
        suite_dir,
    ), "the tracing decoy should itself be honestly anchored"
    assert _anchored_violations(
        forged, suite_dir
    ), f"honesty check FAILED to catch a forged anchored output {forged_expected!r}"


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


def test_merkle_inclusion_vectors_match_vendored_proof_tuples():
    """The merkle_inclusion anchor: each ACCEPT vector must be a COMPLETE vendored
    RFC-6962 inclusion-proof tuple (leaf, index, size, proof, root) — not vendored
    fragments reassembled into a degenerate/self-derived shape. This closes the
    n=1/empty-proof residual the generic honesty floor (which only checks that each
    token is independently vendored) would otherwise allow, completing the
    dedicated-anchor pattern (cf. the jcs + Go-KAT byte-for-byte tests)."""
    suite = json.loads(
        (_VENDOR / "rfc6962_transparency_dev" / "vectors.json").read_text("utf-8")
    )
    vendored = {
        (
            ip["leaf_input_hex"].lower(),
            ip["leaf_index"],
            ip["tree_size"],
            tuple(h.lower() for h in ip["proof_hex"]),
            ip["root_hex"].lower(),
        )
        for ip in suite["inclusion_proofs"]
    }
    area = next(
        m for _p, m in runner.iter_manifests() if m["area"] == "merkle_inclusion"
    )
    accepts = [v for v in area["vectors"] if not v["must_reject"]]
    assert accepts, "merkle_inclusion has no accept vectors"
    for v in accepts:
        i = v["input"]
        tup = (
            i["leaf_data_hex"].lower(),
            i["m"],
            i["n"],
            tuple(h.lower() for h in i["proof_hex"]),
            i["root_hex"].lower(),
        )
        assert (
            tup in vendored
        ), f"merkle accept {v['id']} is not a complete vendored inclusion-proof tuple"


def test_consistency_proof_vectors_match_vendored_proof_tuples():
    """The consistency_proof anchor (mirrors merkle_inclusion): each ACCEPT vector
    must be a COMPLETE vendored RFC-6962 consistency-proof tuple (first_size,
    second_size, proof, first_root, second_root), not vendored fragments reassembled."""
    suite = json.loads(
        (_VENDOR / "rfc6962_transparency_dev" / "vectors.json").read_text("utf-8")
    )
    vendored = {
        (
            cp["first_size"],
            cp["second_size"],
            tuple(h.lower() for h in cp["proof_hex"]),
            cp["first_root_hex"].lower(),
            cp["second_root_hex"].lower(),
        )
        for cp in suite["consistency_proofs"]
    }
    area = next(
        m for _p, m in runner.iter_manifests() if m["area"] == "consistency_proof"
    )
    accepts = [v for v in area["vectors"] if not v["must_reject"]]
    assert accepts, "consistency_proof has no accept vectors"
    for v in accepts:
        i = v["input"]
        tup = (
            i["first_size"],
            i["second_size"],
            tuple(h.lower() for h in i["proof_hex"]),
            i["first_root_hex"].lower(),
            i["second_root_hex"].lower(),
        )
        assert (
            tup in vendored
        ), f"consistency accept {v['id']} is not a complete vendored consistency-proof tuple"
