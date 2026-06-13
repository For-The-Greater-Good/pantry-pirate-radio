"""Tier A KAT: each vendored HSDS example must ``model_validate`` cleanly.

G1 (HSDS full-compliance epic, issue #593). For every fixture in
``_fixture_map.FIXTURE_MODEL_MAP``, validate the vendored official example
against the mapped response model with ``extra="forbid"`` (the ratchet —
``HSDSBaseModel.model_config["extra"] = "forbid"`` is never relaxed by this
slice or any later one).

Today every fixture in the map fails this KAT (thin models, missing
``TaxonomyResponse``/``TaxonomyTermResponse``, and the bespoke vs official
``Page`` envelope) — each row is therefore present in ``xfail_manifest.json``
under ``tier: "A"`` and wrapped ``strict=True`` here. A later slice that makes a
fixture pass MUST remove its manifest row (shrink-only, enforced by
``test_xfail_manifest_ratchet.py``) or this test starts failing (XPASS under
``strict=True``) — that failure IS the signal to shrink the manifest.

Model resolution is lazy (``_fixture_map.resolve_model``) so a model that does
not exist yet (``TaxonomyResponse``/``TaxonomyTermResponse``, landing in T1)
raises ``ModelNotFoundError`` INSIDE the test body — an ordinary xfail, not a
collection-time error.
"""

import pytest
from pydantic import ValidationError

from tests.test_hsds_conformance._fixture_map import (
    FIXTURE_MODEL_MAP,
    ModelNotFoundError,
    load_fixture_json,
    load_manifest,
    manifest_reason,
    resolve_model,
)

_MANIFEST = load_manifest()


def _make_params() -> list[pytest.param]:  # type: ignore[type-arg]
    params = []
    for fixture, model_path in FIXTURE_MODEL_MAP.items():
        reason = manifest_reason(_MANIFEST, fixture, "A")
        marks = []
        if reason is not None:
            marks.append(pytest.mark.xfail(strict=True, reason=reason))
        params.append(pytest.param(fixture, model_path, id=fixture, marks=marks))
    return params


@pytest.mark.parametrize("fixture, model_path", _make_params())
def test_example_validates_against_response_model(
    fixture: str, model_path: str
) -> None:
    """``model_validate(example)`` must succeed under ``extra="forbid"``.

    A ``ModelNotFoundError`` (target model doesn't exist yet) or a
    ``ValidationError`` (model exists but the example carries fields/shape the
    model doesn't accept) both count as "this KAT fails" — both are real
    failures for non-manifested fixtures and real xfails for manifested ones.
    """
    model = resolve_model(model_path)
    example = load_fixture_json(fixture)
    try:
        model.model_validate(example)
    except ValidationError as exc:
        raise AssertionError(
            f"{fixture} failed model_validate against {model_path}: {exc}"
        ) from exc


@pytest.mark.parametrize(
    "fixture, model_path",
    [
        pytest.param(fixture, model_path, id=fixture)
        for fixture, model_path in FIXTURE_MODEL_MAP.items()
    ],
)
def test_model_not_found_is_isolated_to_manifested_fixtures(
    fixture: str, model_path: str
) -> None:
    """A ``ModelNotFoundError`` must only occur for manifested fixtures.

    This is a meta-check distinct from the main KAT above (deliberately
    UNMARKED — it must always pass): it confirms that when ``resolve_model``
    raises, it is *expected* (the fixture has a tier-A manifest row) rather
    than a typo in ``FIXTURE_MODEL_MAP`` masquerading as a "model not
    implemented yet" xfail.
    """
    try:
        resolve_model(model_path)
    except ModelNotFoundError:
        reason = manifest_reason(_MANIFEST, fixture, "A")
        assert reason is not None, (
            f"{fixture} -> {model_path} could not be resolved, but {fixture} "
            "has no tier-A manifest row. Either the model path is a typo, or "
            "this fixture needs a manifest entry."
        )
