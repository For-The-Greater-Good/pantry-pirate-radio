"""The HSDS-FX Level-1 conformance runner.

Loads the language-agnostic vector manifests (``conformance/hsdsfx/vectors/``) and
drives each vector through a supplied :class:`HsdsFxAdapter`, asserting accept
vectors produce ``expected`` byte-for-byte and ``must_reject`` vectors are
rejected. Pure dispatch — imports NO ``app.*`` (only the adapter does), so this
module is portable to the standalone HSDS-FX artifact (#540) verbatim.

Level 2 (live-node, httpx against §6.3 endpoints) lands in Slice 3.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    # Type-only — under PEP 563 (`from __future__ import annotations`) this never
    # loads at runtime, so the runner has ZERO ``tests.*`` dependency and ships
    # verbatim to the standalone HSDS-FX artifact (#540). A foreign repo supplies
    # its own adapter satisfying this Protocol; it does not need PPR's package tree.
    from tests.test_federation.conformance.adapter import HsdsFxAdapter


def _find_corpus_dir() -> Path:
    """Locate ``conformance/hsdsfx/vectors`` robustly across layouts so the runner is
    portable (the in-repo tree AND the published artifact where ``vectors/`` sits
    next to ``runner.py``). Override with ``HSDSFX_CORPUS_DIR``."""
    env = os.environ.get("HSDSFX_CORPUS_DIR")
    if env:
        return Path(env)
    here = Path(__file__).resolve()
    sibling = here.parent / "vectors"  # published-artifact layout
    if sibling.is_dir():
        return sibling
    for parent in here.parents:  # in-repo layout: search upward
        cand = parent / "conformance" / "hsdsfx" / "vectors"
        if cand.is_dir():
            return cand
    # Last resort: the historical fixed depth (clear failure if truly absent).
    return here.parents[3] / "conformance" / "hsdsfx" / "vectors"


CORPUS_DIR = _find_corpus_dir()


@dataclass
class VectorResult:
    area: str
    vector_id: str
    passed: bool
    interop_pending: bool
    detail: str = ""


@dataclass
class Report:
    results: list[VectorResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> list[VectorResult]:
        return [r for r in self.results if not r.passed]

    @property
    def anchored_passed(self) -> int:
        return sum(1 for r in self.results if r.passed and not r.interop_pending)

    @property
    def interop_pending_passed(self) -> int:
        return sum(1 for r in self.results if r.passed and r.interop_pending)


def load_manifest(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def iter_manifests(corpus_dir: Path = CORPUS_DIR):
    """Yield (path, manifest) for every area manifest, sorted for determinism."""
    for path in sorted(corpus_dir.glob("*.json")):
        yield path, load_manifest(path)


# --- op dispatch ----------------------------------------------------------------
# Each vector names the adapter ``op`` it exercises; the runner calls that op with
# the vector's ``input`` and compares to ``expected`` (accept) or asserts rejection
# (must_reject). The op set IS the spec's testable surface — see adapter.py. These
# handlers depend only on the adapter Protocol (no app.* — portability).


def _op_canonicalize(a: HsdsFxAdapter, i: dict) -> Any:
    # RFC 8785 JCS: a JSON value in, canonical bytes out (compared as hex).
    return a.canonicalize(i["value"]).hex()


def _op_content_address(a: HsdsFxAdapter, i: dict) -> Any:
    return a.content_address(i["preimage"])


def _op_sign_envelope(a: HsdsFxAdapter, i: dict) -> Any:
    # Pin the WHOLE W3C Data Integrity proof object — every key (@context, type,
    # cryptosuite, created, verificationMethod, proofPurpose, proofValue) — so an
    # impl emitting any wrong field (a spoofed verificationMethod, a drifted
    # cryptosuite, a non-deterministic proofValue) is failed. The eddsa-jcs-2022
    # suite is deterministic (RFC 8032 + created defaulting to published), so the
    # full object is reproducible byte-for-byte and a sound conformance pin.
    return dict(a.sign_envelope(i["seed_hex"], i["preimage"]))


def _op_verify_envelope(a: HsdsFxAdapter, i: dict) -> Any:
    return a.verify_envelope(i["envelope"], i["pubkey_hex"])


def _op_encode_note(a: HsdsFxAdapter, i: dict) -> Any:
    return a.encode_note(i["seed_hex"], i["text"], i["key_name"])


def _op_checkpoint_body(a: HsdsFxAdapter, i: dict) -> Any:
    return a.checkpoint_body(i["origin"], i["tree_size"], i["root_hex"], i["timestamp"])


def _op_encode_checkpoint(a: HsdsFxAdapter, i: dict) -> Any:
    return a.encode_checkpoint(
        i["seed_hex"], i["origin"], i["tree_size"], i["root_hex"], i["timestamp"]
    )


def _op_verify_note(a: HsdsFxAdapter, i: dict) -> Any:
    return a.verify_note(i["note"], i["pubkey_hex"], i["key_name"])


def _op_parse_checkpoint(a: HsdsFxAdapter, i: dict) -> Any:
    return a.parse_checkpoint(i["note"])


def _op_verify_inclusion(a: HsdsFxAdapter, i: dict) -> Any:
    return a.verify_inclusion(
        i["leaf_data_hex"], i["m"], i["n"], i["proof_hex"], i["root_hex"]
    )


def _op_verify_consistency(a: HsdsFxAdapter, i: dict) -> Any:
    return a.verify_consistency(
        i["first_size"],
        i["second_size"],
        i["proof_hex"],
        i["first_root_hex"],
        i["second_root_hex"],
    )


def _op_normalize_federation_id(a: HsdsFxAdapter, i: dict) -> Any:
    return a.normalize_federation_id(i["federation_id"])


def _op_validate_activity(a: HsdsFxAdapter, i: dict) -> Any:
    return a.validate_activity(i["envelope"])


_OPS: dict[str, Callable[[HsdsFxAdapter, dict], Any]] = {
    "canonicalize": _op_canonicalize,
    "content_address": _op_content_address,
    "sign_envelope": _op_sign_envelope,
    "verify_envelope": _op_verify_envelope,
    "encode_note": _op_encode_note,
    "checkpoint_body": _op_checkpoint_body,
    "encode_checkpoint": _op_encode_checkpoint,
    "verify_note": _op_verify_note,
    "parse_checkpoint": _op_parse_checkpoint,
    "verify_inclusion": _op_verify_inclusion,
    "verify_consistency": _op_verify_consistency,
    "normalize_federation_id": _op_normalize_federation_id,
    "validate_activity": _op_validate_activity,
}

#: Ops whose normal return value already signals rejection (False), so a
#: ``must_reject`` vector passes on False as well as on a raise.
_BOOLEAN_OPS = frozenset(
    {
        "verify_envelope",
        "verify_note",
        "verify_inclusion",
        "verify_consistency",
        "validate_activity",
    }
)


def verify_level1(adapter: HsdsFxAdapter, corpus_dir: Path = CORPUS_DIR) -> Report:
    """Run every Level-1 vector through ``adapter``; return a :class:`Report`."""
    report = Report()
    for _path, manifest in iter_manifests(corpus_dir):
        area = manifest["area"]
        area_pending = manifest.get("interop_status") == "interop_pending"
        for vec in manifest["vectors"]:
            pending = vec.get("interop_pending", area_pending)
            report.results.append(_run_one(adapter, area, vec, pending))
    return report


def _run_one(adapter, area, vec, pending) -> VectorResult:
    op = _OPS.get(vec["op"])
    if op is None:
        return VectorResult(
            area, vec["id"], False, pending, f"unknown op {vec['op']!r}"
        )
    must_reject = vec["must_reject"]
    try:
        got = op(adapter, vec["input"])
    except Exception as exc:  # a raise is a valid rejection
        if must_reject:
            return VectorResult(area, vec["id"], True, pending)
        return VectorResult(area, vec["id"], False, pending, f"unexpected raise: {exc}")
    if must_reject:
        # A boolean op rejects by returning False; any other op must have raised.
        if vec["op"] in _BOOLEAN_OPS and got is False:
            return VectorResult(area, vec["id"], True, pending)
        return VectorResult(
            area, vec["id"], False, pending, f"accepted a reject vector (got {got!r})"
        )
    ok = got == vec["expected"]
    return VectorResult(
        area,
        vec["id"],
        ok,
        pending,
        "" if ok else f"got {got!r} != expected {vec['expected']!r}",
    )


# --- Level 2: live-node conformance --------------------------------------------
# Drives a LIVE HSDS-FX node over its §6.3 endpoints and verifies the full
# publish->pull->verify loop a real peer performs: pin the signed checkpoint,
# pull /export at that tree_size, and verify every row's envelope signature AND
# its inclusion proof against the checkpoint root. Transport-agnostic: the caller
# passes a `get(path) -> Resp` (TestClient in CI; a real httpx client against a
# deployed URL for an external Readiness Check), so the runner couples to neither
# PPR nor a transport — only the adapter Protocol + the §6.3 wire contract.


@dataclass
class Resp:
    status_code: int
    text: str
    headers: dict[str, str]
    json_body: Any = None


@dataclass
class Level2Report:
    checkpoint_verified: bool = False
    tree_size: int = 0
    rows_total: int = 0
    rows_verified: int = 0
    rows_complete: bool = False
    below_floor_410: bool | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        # A conforming node serves EXACTLY the committed prefix: tree_size rows, each
        # with a verifying envelope AND inclusion proof, sequences 1..N complete. The
        # tree_size/completeness checks defeat a row-WITHHOLDING node (a valid subset
        # would otherwise pass) — equivocation a Merkle checkpoint exists to expose.
        return (
            self.checkpoint_verified
            and self.tree_size > 0
            and self.rows_total == self.tree_size
            and self.rows_verified == self.tree_size
            and self.rows_complete
        )


def verify_level2(
    get: Callable[[str], Resp],
    adapter: HsdsFxAdapter,
    pubkey_hex: str,
    key_name: str,
) -> Level2Report:
    """Verify a live node end-to-end (the §6.6 pull contract). ``get`` performs an
    HTTP GET and returns a :class:`Resp` (status/text/headers/json_body)."""
    rep = Level2Report()

    # 1. Pin the signed checkpoint. The SIGNED NOTE is the trust anchor, so derive
    #    tree_size N and root@N from the note itself (parse_checkpoint), NOT the
    #    unsigned sibling JSON — then require the JSON convenience fields to AGREE
    #    (a §6.3 consumer-side internal-consistency check).
    cp = get("/api/v1/federation/checkpoint")
    if cp.status_code != 200 or cp.json_body is None:
        rep.detail = f"/checkpoint -> {cp.status_code}"
        return rep
    note = cp.json_body.get("note")
    if not isinstance(note, str):
        rep.detail = "/checkpoint missing note"
        return rep
    if not adapter.verify_note(note, pubkey_hex, key_name):
        rep.detail = "checkpoint note failed verify"
        return rep
    try:
        parsed = adapter.parse_checkpoint(note)
    except Exception as exc:  # noqa: BLE001 — a hostile/garbage note must not crash
        rep.detail = f"checkpoint note unparseable: {exc}"
        return rep
    n = parsed["tree_size"]
    root_hex = parsed["root_hex"]
    if cp.json_body.get("tree_size") != n or cp.json_body.get("root_hash") != root_hex:
        rep.detail = "checkpoint JSON fields disagree with the signed note"
        return rep
    rep.checkpoint_verified = True
    rep.tree_size = n

    # 2. Pull /export PINNED to N, FOLLOWING the keyset cursor across pages (the §6.6
    #    pull contract — a real peer assembles the full committed prefix page by page;
    #    pulling one page would wrongly fail any honest node larger than the export
    #    page size). _since is exclusive; Federation-Next-Cursor is the last sequence
    #    emitted (absent on the final page). Verify each row against the held root@N
    #    (proofs are unverifiable against a moving head). Bound the loop so a hostile
    #    node cannot stall the cursor or stream past tree_size forever.
    rows: list[Any] = []
    cursor = 0
    for _page in range(n + 1):  # dense 1..N: at most N pages even at page size 1
        exp = get(f"/api/v1/federation/export?_since={cursor}&tree_size={n}")
        if exp.status_code != 200:
            rep.detail = f"/export -> {exp.status_code}"
            return rep
        for line in exp.text.splitlines():
            if not line.strip():
                continue
            try:
                rows.append(_loads(line))
            except (
                Exception
            ):  # noqa: BLE001 — a garbage row is a failed node, not a crash
                rep.detail = "malformed /export row (non-JSON)"
                return rep
        nxt = _header(exp.headers, "Federation-Next-Cursor")
        if not nxt:
            break
        try:
            nxt_i = int(nxt)
        except (TypeError, ValueError):
            rep.detail = f"invalid next-cursor {nxt!r}"
            return rep
        if nxt_i <= cursor or len(rows) > n:
            rep.detail = "export pagination did not converge (cursor stalled / overran)"
            return rep
        cursor = nxt_i
    rep.rows_total = len(rows)
    # Completeness: the assembled rows must be EXACTLY sequences 1..N — no withholding,
    # no duplicates, no extras (truncation/padding is detectable after page assembly).
    seqs = sorted(r["sequence"] for r in rows if isinstance(r.get("sequence"), int))
    rep.rows_complete = seqs == list(range(1, n + 1))
    for row in rows:
        env = {k: v for k, v in row.items() if k != "inclusion_proof"}
        if not adapter.verify_envelope(env, pubkey_hex):
            continue
        preimage = {k: v for k, v in env.items() if k not in ("id", "proof")}
        leaf_hex = adapter.canonicalize(preimage).hex()
        if adapter.verify_inclusion(
            leaf_hex, row["sequence"] - 1, n, row["inclusion_proof"], root_hex
        ):
            rep.rows_verified += 1
    if not rep.rows_complete and not rep.detail:
        rep.detail = f"export incomplete: served sequences {seqs}, expected 1..{n}"

    return rep


@dataclass
class ConsistencyReport:
    current_verified: bool = False
    proof_present: bool = False
    consistent: bool = False
    tree_size: int = 0
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.current_verified and self.proof_present and self.consistent


def verify_consistency_to_head(
    get: Callable[[str], Resp],
    adapter: HsdsFxAdapter,
    pubkey_hex: str,
    key_name: str,
    held_size: int,
    held_root_hex: str,
) -> ConsistencyReport:
    """Verify a node's log only GREW (RFC-6962 append-only) from a checkpoint the
    consumer already holds (``held_size`` / ``held_root_hex``, itself note-anchored
    when it was pinned) to the node's current head — the §6.6 incremental-pull trust
    step, and the only note-anchored consumer of ``verify_consistency`` in the loop.

    Like ``verify_level2``, the head root is taken from the SIGNED note (the trust
    anchor) via ``parse_checkpoint``, and the unsigned /checkpoint JSON is required
    to AGREE with it (the §6.3 consumer-side internal-consistency check) — never
    trusted on its own. This is load-bearing: an equivocating node can serve an
    honest signed note but a lying unsigned JSON ``root_hash`` over a FORKED tree;
    anchoring to the JSON field would accept the fork (a forged proof can be made
    self-consistent with attacker-chosen JSON roots), while anchoring to the note —
    and cross-checking the JSON — rejects it. A partner reusing this app inherits
    the correct pattern instead of trusting an attacker-controllable field."""
    rep = ConsistencyReport()
    cp = get(f"/api/v1/federation/checkpoint?from_tree_size={held_size}")
    if cp.status_code != 200 or cp.json_body is None:
        rep.detail = f"/checkpoint -> {cp.status_code}"
        return rep
    note = cp.json_body.get("note")
    if not isinstance(note, str) or not adapter.verify_note(note, pubkey_hex, key_name):
        rep.detail = "checkpoint note missing or failed verify"
        return rep
    try:
        parsed = adapter.parse_checkpoint(note)
    except Exception as exc:  # noqa: BLE001 — a hostile/garbage note must not crash
        rep.detail = f"checkpoint note unparseable: {exc}"
        return rep
    n = parsed["tree_size"]
    root_n = parsed["root_hex"]
    # §6.3: the unsigned convenience fields MUST agree with the signed note, else a
    # node equivocates between what it signs and what it serves.
    if cp.json_body.get("tree_size") != n or cp.json_body.get("root_hash") != root_n:
        rep.detail = "checkpoint JSON fields disagree with the signed note"
        return rep
    rep.current_verified = True
    rep.tree_size = n
    proof = cp.json_body.get("consistency_proof")
    if cp.json_body.get("consistency_from") != held_size or not isinstance(proof, list):
        rep.detail = "no consistency proof for the held size"
        return rep
    rep.proof_present = True
    # Append-only over NOTE-ANCHORED roots: held_root_hex was note-anchored by the
    # consumer when it pinned held_size; root_n comes from the signed note above. A
    # malformed proof (e.g. non-hex element) is a failed node, not a crash — mirror
    # the note-parse guard so the consumer never raises on hostile input.
    try:
        rep.consistent = adapter.verify_consistency(
            held_size, n, proof, held_root_hex, root_n
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 — a garbage proof must not crash the consumer
        rep.detail = f"consistency proof malformed: {exc}"
        return rep
    if not rep.consistent:
        rep.detail = "consistency proof did not verify (forked/rewritten history?)"
    return rep


def _loads(line: str) -> Any:
    return json.loads(line)


def _header(headers: dict[str, str], name: str) -> str | None:
    """Case-insensitive header lookup (transports differ on header case)."""
    name = name.lower()
    for k, v in headers.items():
        if k.lower() == name:
            return v
    return None
