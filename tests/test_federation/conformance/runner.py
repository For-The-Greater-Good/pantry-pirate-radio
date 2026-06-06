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


# --- per-area assertion handlers ------------------------------------------------
# Each handler maps one vector's input -> a comparable result, OR raises to signal
# a must_reject rejection. They depend only on the adapter Protocol.


def _check_content_address(adapter: HsdsFxAdapter, vec: dict) -> tuple[Any, Any]:
    return adapter.content_address(vec["input"]["preimage"]), vec.get("expected")


def _check_envelope_proof(adapter: HsdsFxAdapter, vec: dict) -> tuple[Any, Any]:
    proof = adapter.sign_envelope(vec["input"]["seed_hex"], vec["input"]["preimage"])
    exp = vec.get("expected")
    # Compare the load-bearing fields (signature + type); verificationMethod is
    # derived from actor and asserted in envelope_assembly.
    got = {"type": proof["type"], "signature": proof["signature"]}
    return got, exp


def _check_envelope_verify(adapter: HsdsFxAdapter, vec: dict) -> tuple[Any, Any]:
    ok = adapter.verify_envelope(vec["input"]["envelope"], vec["input"]["pubkey_hex"])
    if vec["must_reject"]:
        # A reject vector for verify means "must return False". Normalize to the
        # reject protocol: raise so the runner records a correct rejection.
        if ok:
            raise AssertionError("verify_envelope returned True for a reject vector")
        raise _RejectedError()
    return ok, vec.get("expected", True)


class _RejectedError(Exception):
    """Signals a correct rejection of a must_reject vector."""


_HANDLERS: dict[str, Callable[[HsdsFxAdapter, dict], tuple[Any, Any]]] = {
    "envelope_content_address": _check_content_address,
    "envelope_proof": _check_envelope_proof,
    "envelope_assembly": _check_envelope_verify,
}


def verify_level1(adapter: HsdsFxAdapter, corpus_dir: Path = CORPUS_DIR) -> Report:
    """Run every Level-1 vector through ``adapter``; return a :class:`Report`."""
    report = Report()
    for _path, manifest in iter_manifests(corpus_dir):
        area = manifest["area"]
        handler = _HANDLERS.get(area)
        area_pending = manifest.get("interop_status") == "interop_pending"
        for vec in manifest["vectors"]:
            pending = vec.get("interop_pending", area_pending)
            if handler is None:
                report.results.append(
                    VectorResult(area, vec["id"], False, pending, "no handler for area")
                )
                continue
            report.results.append(_run_one(handler, adapter, area, vec, pending))
    return report


def _run_one(handler, adapter, area, vec, pending) -> VectorResult:
    must_reject = vec["must_reject"]
    try:
        got, expected = handler(adapter, vec)
    except _RejectedError:
        return VectorResult(area, vec["id"], must_reject, pending)
    except Exception as exc:  # any raise == a rejection
        if must_reject:
            return VectorResult(area, vec["id"], True, pending)
        return VectorResult(area, vec["id"], False, pending, f"unexpected raise: {exc}")
    if must_reject:
        return VectorResult(area, vec["id"], False, pending, "accepted a reject vector")
    ok = got == expected
    return VectorResult(
        area,
        vec["id"],
        ok,
        pending,
        "" if ok else f"got {got!r} != expected {expected!r}",
    )
