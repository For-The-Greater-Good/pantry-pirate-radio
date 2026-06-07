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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from tests.test_federation.conformance.adapter import HsdsFxAdapter

# Repo-root corpus (in-repo now; ships verbatim as the published vectors package).
CORPUS_DIR = Path(__file__).resolve().parents[3] / "conformance" / "hsdsfx" / "vectors"


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


def _op_content_address(a: HsdsFxAdapter, i: dict) -> Any:
    return a.content_address(i["preimage"])


def _op_sign_envelope(a: HsdsFxAdapter, i: dict) -> Any:
    proof = a.sign_envelope(i["seed_hex"], i["preimage"])
    # Compare the load-bearing fields; verificationMethod is asserted via assembly.
    return {"type": proof["type"], "signature": proof["signature"]}


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


_OPS: dict[str, Callable[[HsdsFxAdapter, dict], Any]] = {
    "content_address": _op_content_address,
    "sign_envelope": _op_sign_envelope,
    "verify_envelope": _op_verify_envelope,
    "encode_note": _op_encode_note,
    "checkpoint_body": _op_checkpoint_body,
    "encode_checkpoint": _op_encode_checkpoint,
    "verify_note": _op_verify_note,
    "parse_checkpoint": _op_parse_checkpoint,
    "verify_inclusion": _op_verify_inclusion,
}

#: Ops whose normal return value already signals rejection (False), so a
#: ``must_reject`` vector passes on False as well as on a raise.
_BOOLEAN_OPS = frozenset({"verify_envelope", "verify_note", "verify_inclusion"})


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
    rows_total: int = 0
    rows_verified: int = 0
    below_floor_410: bool | None = None
    detail: str = ""

    @property
    def ok(self) -> bool:
        return (
            self.checkpoint_verified
            and self.rows_total > 0
            and self.rows_verified == self.rows_total
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

    # 1. Pin the signed checkpoint (tree_size N, root@N) and verify the note.
    cp = get("/api/v1/federation/checkpoint")
    if cp.status_code != 200 or cp.json_body is None:
        rep.detail = f"/checkpoint -> {cp.status_code}"
        return rep
    n = cp.json_body["tree_size"]
    root_hex = cp.json_body["root_hash"]
    rep.checkpoint_verified = adapter.verify_note(
        cp.json_body["note"], pubkey_hex, key_name
    )
    if not rep.checkpoint_verified:
        rep.detail = "checkpoint note failed verify"
        return rep

    # 2. Pull /export PINNED to N; verify each row's envelope + inclusion proof
    #    against the held root@N (proofs are unverifiable against a moving head).
    exp = get(f"/api/v1/federation/export?_since=0&tree_size={n}")
    if exp.status_code != 200:
        rep.detail = f"/export -> {exp.status_code}"
        return rep
    rows = [_loads(line) for line in exp.text.splitlines() if line.strip()]
    rep.rows_total = len(rows)
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

    return rep


def _loads(line: str) -> Any:
    return json.loads(line)
