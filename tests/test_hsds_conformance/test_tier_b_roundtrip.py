"""Tier B KAT: round-trip byte-equality via RFC 8785 JCS canonicalization.

G1 (HSDS full-compliance epic, issue #593). For every fixture in
``_fixture_map.FIXTURE_MODEL_MAP``, validate the vendored official example into
the mapped response model, dump it back
(``model_dump(mode="json", by_alias=True, exclude_none=True)``), and assert the
JCS-canonicalized bytes of the dump equal the JCS-canonicalized bytes of the
original example (``app.federation.canonical.jcs_bytes`` — RFC 8785, externally
anchored by ``tests/test_federation/vendor/jcs_rfc8785/``).

Byte-equality after canonicalization (rather than raw ``==``) means key
ordering and number formatting differences are NOT failures by themselves —
only genuine content differences (missing/extra/renamed fields, different
values) are. Today every fixture fails Tier B too: Tier A
(``model_validate``) must succeed before Tier B can even attempt the dump, and
every fixture in the map currently fails Tier A (see
``test_tier_a_representation.py`` and ``xfail_manifest.json``). Each row is
present in ``xfail_manifest.json`` under ``tier: "B"`` and wrapped
``strict=True`` here.
"""

import pytest

from app.federation.canonical import jcs_bytes
from tests.test_hsds_conformance._fixture_map import (
    FIXTURE_MODEL_MAP,
    load_fixture_json,
    load_manifest,
    manifest_reason,
    resolve_model,
)

_MANIFEST = load_manifest()


def _make_params() -> list[pytest.param]:  # type: ignore[type-arg]
    params = []
    for fixture, model_path in FIXTURE_MODEL_MAP.items():
        reason = manifest_reason(_MANIFEST, fixture, "B")
        marks = []
        if reason is not None:
            marks.append(pytest.mark.xfail(strict=True, reason=reason))
        params.append(pytest.param(fixture, model_path, id=fixture, marks=marks))
    return params


@pytest.mark.parametrize("fixture, model_path", _make_params())
def test_example_roundtrips_byte_equal_via_jcs(fixture: str, model_path: str) -> None:
    """``jcs_bytes(model_dump(model_validate(example))) == jcs_bytes(example)``.

    Any exception raised along the way (``ModelNotFoundError`` for a model that
    doesn't exist yet, ``ValidationError`` for one that rejects the example's
    shape) counts as "this KAT fails" — real failures for non-manifested
    fixtures, real xfails for manifested ones.
    """
    model = resolve_model(model_path)
    example = load_fixture_json(fixture)

    instance = model.model_validate(example)
    dumped = instance.model_dump(mode="json", by_alias=True, exclude_none=True)

    expected = jcs_bytes(example)
    actual = jcs_bytes(dumped)
    assert actual == expected, (
        f"{fixture} does not round-trip byte-equal via JCS through {model_path}:\n"
        f"  expected (from example): {expected!r}\n"
        f"  actual   (from dump):    {actual!r}"
    )
