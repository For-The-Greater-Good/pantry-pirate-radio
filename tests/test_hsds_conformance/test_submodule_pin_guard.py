"""Drift guard: the live ``docs/HSDS`` submodule HEAD must match the vendored pin.

G1 (HSDS full-compliance epic, issue #593). The conformance fixtures vendored
under ``vendor/hsds_official_examples/`` are verbatim copies of
``docs/HSDS/examples/*.json`` (+ ``examples/csv/*.csv`` + a resolved
``datapackage.json``) taken at submodule commit ``74fcf85b0534fd8c6e61eae13d246b4b375a4495``
(tag ``v3.2.3``). If the submodule is later bumped without re-vendoring, the
fixtures silently go stale relative to the spec they claim to represent.

This test reads the LIVE submodule HEAD and asserts it equals the pin. If the
submodule is absent, not checked out, or its HEAD cannot be resolved, the test
FAILS with a clear message (never skips) — drift (including "submodule went
missing") must be loud per constitution Principle III.

Resolution strategy (in order):

1. **Read the gitdir files directly** (no ``git`` subprocess). ``docs/HSDS/.git``
   is a gitlink pointer file (``gitdir: ../../.git/modules/docs/HSDS``); its
   target's ``HEAD`` file holds either a raw 40-hex-char SHA (detached HEAD —
   the normal state for a commit-pinned submodule) or a ``ref: refs/...``
   indirection, resolved via the loose ref file or ``packed-refs``.
2. **Fall back to** ``git -C docs/HSDS rev-parse HEAD``, for layouts the
   file-based resolution doesn't anticipate.

The file-based path exists primarily because containerized test runs hit git's
"detected dubious ownership" guard (the repo's files are owned by a different
uid than the process running git) — ``git`` then refuses to run at all
regardless of ``-c safe.directory=...`` on this git version, even though the
on-disk ``.git/modules/docs/HSDS/HEAD`` is perfectly readable.
"""

import re
import subprocess
from pathlib import Path

# Pinned at vendoring time (2026-06-13). See
# tests/test_hsds_conformance/vendor/hsds_official_examples/README.md for the
# full provenance record.
PINNED_HSDS_SUBMODULE_COMMIT = "74fcf85b0534fd8c6e61eae13d246b4b375a4495"

_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# Repo root: tests/test_hsds_conformance/test_submodule_pin_guard.py -> repo root.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_HSDS_SUBMODULE_DIR = _REPO_ROOT / "docs" / "HSDS"


def _resolve_ref(gitdir: Path, ref: str, depth: int = 0) -> str | None:
    """Resolve a ref name (e.g. ``refs/heads/main``) to a 40-hex-char SHA.

    Checks the loose ref file first, then ``packed-refs``. Returns ``None`` if
    unresolvable. ``depth`` guards against pathological symref cycles.
    """
    if depth > 5:
        return None
    loose = gitdir / ref
    if loose.is_file():
        content = loose.read_text(encoding="utf-8").strip()
        if _SHA_RE.match(content):
            return content
        if content.startswith("ref: "):
            return _resolve_ref(gitdir, content[len("ref: ") :].strip(), depth + 1)
        return None
    packed = gitdir / "packed-refs"
    if packed.is_file():
        for line in packed.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2 and parts[1].strip() == ref and _SHA_RE.match(parts[0]):
                return parts[0]
    return None


def _resolve_head_via_gitdir(submodule_dir: Path) -> str | None:
    """Resolve ``submodule_dir``'s HEAD commit SHA by reading gitdir files directly.

    Returns ``None`` (never raises) if any expected file/format is missing —
    callers fall back to ``git rev-parse``.
    """
    gitlink = submodule_dir / ".git"
    if not gitlink.is_file():
        # A real (non-submodule) checkout has .git/ as a directory here, not a
        # gitlink file; that layout is handled by the git-subprocess fallback.
        return None

    pointer = gitlink.read_text(encoding="utf-8").strip()
    if not pointer.startswith("gitdir: "):
        return None
    gitdir = (submodule_dir / pointer[len("gitdir: ") :].strip()).resolve()
    if not gitdir.is_dir():
        return None

    head_file = gitdir / "HEAD"
    if not head_file.is_file():
        return None
    head_content = head_file.read_text(encoding="utf-8").strip()
    if _SHA_RE.match(head_content):
        return head_content  # detached HEAD: raw SHA (normal for a pinned submodule)
    if head_content.startswith("ref: "):
        return _resolve_ref(gitdir, head_content[len("ref: ") :].strip())
    return None


def _resolve_head_via_git_subprocess(submodule_dir: Path) -> str | None:
    """Resolve HEAD via ``git -C <dir> rev-parse HEAD``. Returns ``None`` on failure."""
    try:
        result = subprocess.run(
            ["git", "-C", str(submodule_dir), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
    except (subprocess.CalledProcessError, OSError, subprocess.TimeoutExpired):
        return None
    head = result.stdout.strip()
    return head if _SHA_RE.match(head) else None


def test_hsds_submodule_pin_matches_vendored_fixtures() -> None:
    """The live ``docs/HSDS`` submodule HEAD MUST equal the vendored pin.

    A mismatch means either the submodule was bumped without re-vendoring the
    conformance fixtures (re-vendor + bump the pin here), or the submodule is
    missing/broken (restore it) — both are real drift and must fail CI, not be
    skipped.
    """
    if not _HSDS_SUBMODULE_DIR.is_dir():
        raise AssertionError(
            f"docs/HSDS submodule directory not found at {_HSDS_SUBMODULE_DIR}. "
            "The HSDS conformance fixtures are pinned to submodule commit "
            f"{PINNED_HSDS_SUBMODULE_COMMIT} (tag v3.2.3); without the submodule "
            "this pin cannot be verified. Run `git submodule update --init "
            "docs/HSDS` (drift must be loud, not silently skipped)."
        )

    live_head = _resolve_head_via_gitdir(
        _HSDS_SUBMODULE_DIR
    ) or _resolve_head_via_git_subprocess(_HSDS_SUBMODULE_DIR)

    if live_head is None:
        raise AssertionError(
            f"Unable to resolve docs/HSDS submodule HEAD (tried reading "
            f"{_HSDS_SUBMODULE_DIR}/.git's gitdir target directly, and "
            f"`git -C {_HSDS_SUBMODULE_DIR} rev-parse HEAD`). The HSDS "
            f"conformance fixtures are pinned to commit "
            f"{PINNED_HSDS_SUBMODULE_COMMIT} (tag v3.2.3) and cannot be "
            "verified without a resolvable submodule checkout."
        )

    assert live_head == PINNED_HSDS_SUBMODULE_COMMIT, (
        f"docs/HSDS submodule HEAD ({live_head}) has drifted from the pin "
        f"vendored into tests/test_hsds_conformance/vendor/hsds_official_examples/ "
        f"({PINNED_HSDS_SUBMODULE_COMMIT}, tag v3.2.3). Re-vendor the official "
        "HSDS examples from the new commit and update "
        "PINNED_HSDS_SUBMODULE_COMMIT here (and the vendor README) to match, "
        "or check out the pinned commit if this drift was unintentional."
    )
