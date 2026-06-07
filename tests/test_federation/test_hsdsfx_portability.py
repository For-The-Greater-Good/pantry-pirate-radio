"""HSDS-FX portability gate — "implementable with zero reference to PPR" as a RED
test, not a convention (design §8.5/§8.5a).

The canonical corpus + the runner MUST carry no PPR runtime dependency — the ONLY
sanctioned coupling is ``adapter.py``'s ``RefAdapter`` (PPR's reference adapter).
Two layers enforce it: (1) an AST walk that flags RUNTIME imports of ``app.*`` /
``tests.*`` (TYPE_CHECKING-only imports are excluded — they never load in a foreign
repo), and (2) an actual EXECUTION of the runner from a temp tree with the PPR repo
off ``sys.path`` — because an AST scan alone cannot certify "runs in a fresh repo"
(the hard-import + hardwired-corpus-path breach the Gauntlet surfaced).
"""

from __future__ import annotations

import ast
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

_HARNESS = Path(__file__).resolve().parent / "conformance"
_CORPUS = Path(__file__).resolve().parents[2] / "conformance" / "hsdsfx"


def _is_type_checking_guard(node: ast.If) -> bool:
    test = node.test
    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _runtime_imports(py: Path) -> list[str]:
    """Module names imported at RUNTIME — imports nested under ``if TYPE_CHECKING:``
    are excluded (they are never evaluated, so they impose no real dependency), and
    dynamic ``importlib.import_module("…")`` / ``__import__("…")`` string targets are
    included (an AST scan for literal imports alone would miss them)."""
    tree = ast.parse(py.read_text(encoding="utf-8"), filename=str(py))
    guarded: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_guard(node):
            for child in node.body:
                for sub in ast.walk(child):
                    guarded.add(id(sub))
    mods: list[str] = []
    for node in ast.walk(tree):
        if id(node) in guarded:
            continue
        if isinstance(node, ast.Import):
            mods.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            mods.append(node.module or "")
        elif isinstance(node, ast.Call):
            fn = node.func
            is_dyn = (isinstance(fn, ast.Name) and fn.id == "__import__") or (
                isinstance(fn, ast.Attribute) and fn.attr == "import_module"
            )
            if is_dyn and node.args and isinstance(node.args[0], ast.Constant):
                val = node.args[0].value
                if isinstance(val, str):
                    mods.append(val)
    return mods


def _imports_app(py: Path) -> bool:
    """Whole-tree literal import of ``app`` / ``app.*`` (RefAdapter's function-local
    app imports count — they are runtime). Used for the only-adapter-couples test."""
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


def _depends_on(mod: str, prefix: str) -> bool:
    return mod == prefix or mod.startswith(prefix + ".")


def test_runner_has_no_runtime_ppr_dependency():
    """runner.py must not RUNTIME-import app.* or tests.* — it ships verbatim to the
    standalone HSDS-FX artifact, so a foreign repo (no PPR package tree) can load it.
    A TYPE_CHECKING-guarded adapter import for type hints is allowed."""
    runtime = _runtime_imports(_HARNESS / "runner.py")
    offenders = [m for m in runtime if _depends_on(m, "app") or _depends_on(m, "tests")]
    assert not offenders, (
        f"runner.py runtime-imports PPR modules {offenders} — it must depend only on "
        "the adapter Protocol (TYPE_CHECKING-guarded) + the pure-data corpus"
    )


def test_published_vectors_are_pure_data():
    """The published artifact (conformance/hsdsfx/vectors/, §8.6) is pure JSON —
    no code at all, so it is consumable by any-language impl with zero dependency.
    (generate.py is a repo-local regeneration tool that DOES couple to the reference
    impl by design — it lives in the parent dir, outside this scoped check.)"""
    py_in_vectors = list((_CORPUS / "vectors").rglob("*.py"))
    assert not py_in_vectors, f"vectors/ must be pure data; found code: {py_in_vectors}"
    assert list((_CORPUS / "vectors").glob("*.json")), "no vector manifests present"


def test_only_adapter_couples_to_app():
    """Across the harness, ONLY adapter.py may import app.* (the reference adapter)."""
    offenders = [
        py.name
        for py in _HARNESS.glob("*.py")
        if py.name != "adapter.py" and _imports_app(py)
    ]
    assert not offenders, f"only adapter.py may import app.*; offenders: {offenders}"


def test_runner_executes_in_a_ppr_free_tree(tmp_path):
    """The real portability proof (an AST scan cannot certify "runs in a fresh
    repo"): copy vectors/ + runner.py into a PPR-free temp tree, supply a foreign
    stub adapter, and run verify_level1 in a subprocess whose cwd is the temp tree
    and whose PYTHONPATH excludes the PPR repo. The runner must LOAD (no tests.*
    import error) and DISPATCH every vector (corpus path resolves via the published
    sibling layout), with zero app.*/tests.* dependency."""
    pkg = tmp_path / "hsdsfx_pkg"
    (pkg / "vectors").mkdir(parents=True)
    for j in (_CORPUS / "vectors").glob("*.json"):
        shutil.copy(j, pkg / "vectors" / j.name)
    shutil.copy(_HARNESS / "runner.py", pkg / "runner.py")
    (pkg / "stub_adapter.py").write_text(
        textwrap.dedent(
            """
            class StubAdapter:  # a foreign adapter need not be correct to prove load+dispatch
                def canonicalize(self, obj): return b""
                def content_address(self, preimage): return ""
                def sign_envelope(self, seed_hex, preimage): return {}
                def verify_envelope(self, envelope, pubkey_hex): return False
                def encode_note(self, seed_hex, text, key_name): return ""
                def checkpoint_body(self, origin, tree_size, root_hex, timestamp): return ""
                def encode_checkpoint(self, *a, **k): return ""
                def verify_note(self, note, pubkey_hex, key_name): return False
                def parse_checkpoint(self, note): return {}
                def verify_inclusion(self, *a, **k): return False
                def verify_consistency(self, *a, **k): return False
                def normalize_federation_id(self, value): return ""
                def validate_activity(self, envelope): return False
            """
        )
    )
    (pkg / "drive.py").write_text(
        textwrap.dedent(
            """
            import sys

            class _PprBlocker:
                # Hard-fail on ANY attempt to import a PPR module — dynamic, aliased,
                # or plain. The execution gate (not just the AST lint) is then the
                # authoritative detector of a reintroduced runtime coupling.
                def find_spec(self, name, path=None, target=None):
                    top = name.split(".", 1)[0]
                    if top in ("app", "tests"):
                        raise ImportError(f"PPR module {name!r} imported in a portable run")
                    return None

            sys.meta_path.insert(0, _PprBlocker())
            import runner
            from stub_adapter import StubAdapter
            rep = runner.verify_level1(StubAdapter())
            assert len(rep.results) > 0, "no vectors executed"
            assert "app" not in sys.modules, "runner pulled in app at runtime"
            assert not any(m == "tests" or m.startswith("tests.") for m in sys.modules)
            print("EXECUTED", len(rep.results))
            """
        )
    )
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)  # scrub the repo so a stray app/tests import fails hard
    proc = subprocess.run(
        [sys.executable, "drive.py"],
        cwd=str(pkg),
        env=env,
        capture_output=True,
        text=True,
    )
    assert (
        proc.returncode == 0
    ), f"portable run failed:\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
    assert "EXECUTED" in proc.stdout, proc.stdout
