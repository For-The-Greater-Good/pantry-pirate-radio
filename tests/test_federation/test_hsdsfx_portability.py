"""HSDS-FX portability gate — "implementable with zero reference to app/" as a RED
test, not a convention (design §8.5/§8.5a).

The canonical corpus + the runner + the generator MUST NOT import ``app.*`` — the
ONLY sanctioned coupling is ``adapter.py``'s ``RefAdapter`` (PPR's reference
adapter). An AST walk enforces it, so when the suite extracts to the standalone
HSDS-FX artifact (#540) it carries no PPR dependency.
"""

from __future__ import annotations

import ast
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent / "conformance"
_CORPUS = Path(__file__).resolve().parents[2] / "conformance" / "hsdsfx"


def _imports_app(py: Path) -> bool:
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "app" or a.name.startswith("app.") for a in node.names):
                return True
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod == "app" or mod.startswith("app."):
                return True
    return False


def test_runner_does_not_import_app():
    assert not _imports_app(_HARNESS / "runner.py"), (
        "runner.py must depend only on the adapter Protocol, not app.* — "
        "it ships verbatim to the standalone HSDS-FX artifact"
    )


def test_published_vectors_are_pure_data():
    """The published artifact (conformance/hsdsfx/vectors/, §8.6) is pure JSON —
    no code at all, so it is consumable by any-language impl with zero dependency.
    (generate.py is a repo-local regeneration tool that DOES couple to the
    reference impl by design — it recomputes the corpus from app.federation to
    prevent drift — and is excluded from the published vectors package.)"""
    py_in_vectors = list((_CORPUS / "vectors").rglob("*.py"))
    assert not py_in_vectors, f"vectors/ must be pure data; found code: {py_in_vectors}"
    # And it must actually contain the JSON manifests.
    assert list((_CORPUS / "vectors").glob("*.json")), "no vector manifests present"


def test_only_adapter_couples_to_app():
    """Across the harness, ONLY adapter.py may import app.* (the reference adapter)."""
    offenders = [
        py.name
        for py in _HARNESS.glob("*.py")
        if py.name != "adapter.py" and _imports_app(py)
    ]
    assert not offenders, f"only adapter.py may import app.*; offenders: {offenders}"
