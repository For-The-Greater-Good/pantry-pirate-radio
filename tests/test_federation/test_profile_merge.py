"""CONF-4: the HSDS Profile applied as RFC 7386 merge patches OVER the base.

``profiles/hsds-ppr/*`` are RFC-7386 JSON Merge Patches over the base HSDS
schemas (``profiles/hsds-ppr/README.md``). The existing ``test_profile.py``
inspects the patch files in isolation — it cannot catch the load-bearing risk:
a patch that, merged over the base, DELETES a base ``required`` field (RFC 7386
null-deletion) or replaces rather than extends. This module:

1. pins a local ``merge_patch`` implementation against the vendored RFC 7386
   Appendix A vectors (external truth — constitution v1.7.0), then
2. merges each real Profile patch over its base schema and asserts the merge
   ADDS only the three profile fields and removes nothing.
"""

import json
from pathlib import Path

import pytest

_VENDOR = Path(__file__).resolve().parent / "vendor" / "rfc7386_merge_patch"
_CASES = json.loads((_VENDOR / "vectors.json").read_text(encoding="utf-8"))["cases"]

_BASE = Path(__file__).resolve().parents[2] / "docs" / "HSDS" / "schema"
_PROFILE = Path(__file__).resolve().parents[2] / "profiles" / "hsds-ppr"
_PROFILE_FIELDS = {"confidence_score", "verified_by", "sources"}


def merge_patch(target, patch):
    """RFC 7386 JSON Merge Patch (§2). A null value in the patch deletes the key;
    a non-object patch replaces the target wholesale; objects recurse."""
    if not isinstance(patch, dict):
        return patch
    if not isinstance(target, dict):
        target = {}
    else:
        target = dict(target)
    for key, value in patch.items():
        if value is None:
            target.pop(key, None)
        else:
            target[key] = merge_patch(target.get(key), value)
    return target


@pytest.mark.parametrize("case", _CASES)
def test_merge_patch_matches_rfc7386_appendix_a(case) -> None:
    """The merge implementation must reproduce every RFC 7386 Appendix A case."""
    assert merge_patch(case["original"], case["patch"]) == case["result"]


def _has_none(obj) -> bool:
    """True iff any value anywhere in the structure is None (the deletion token)."""
    if obj is None:
        return True
    if isinstance(obj, dict):
        return any(_has_none(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_has_none(v) for v in obj)
    return False


@pytest.mark.parametrize(
    "name,base_required",
    [
        ("location.json", ["id", "location_type"]),
        ("service.json", ["id", "name", "status"]),
    ],
)
def test_profile_patch_over_base_adds_only_profile_fields(name, base_required) -> None:
    base = json.loads((_BASE / name).read_text(encoding="utf-8"))
    patch = json.loads((_PROFILE / name).read_text(encoding="utf-8"))

    # The patch must not carry any null (would DELETE a base field on merge).
    assert not _has_none(patch), f"{name} profile patch contains a null deletion token"

    merged = merge_patch(base, patch)

    # required is neither shrunk nor grown.
    assert merged.get("required") == base_required
    # properties gain ONLY the three profile fields; none are removed.
    assert set(merged["properties"]) == set(base["properties"]) | _PROFILE_FIELDS
    # every base property survives unchanged.
    for key, val in base["properties"].items():
        assert merged["properties"][key] == val


def test_openapi_patch_adds_only_federation_paths() -> None:
    base = json.loads((_BASE / "openapi.json").read_text(encoding="utf-8"))
    patch = json.loads((_PROFILE / "openapi.json").read_text(encoding="utf-8"))
    assert not _has_none(patch)
    merged = merge_patch(base, patch)
    added = set(merged.get("paths", {})) - set(base.get("paths", {}))
    assert added == set(patch.get("paths", {}).keys())
    assert added <= {
        "/api/v1/federation/export",
        "/api/v1/federation/inbox",
        "/api/v1/federation/history",
        "/api/v1/federation/actor",
    }
    # No base path is dropped.
    assert set(base.get("paths", {})) <= set(merged.get("paths", {}))
