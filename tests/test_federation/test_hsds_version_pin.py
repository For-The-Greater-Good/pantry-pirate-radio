"""Regression guard: the advertised HSDS version MUST match the model shape.

P1 Task -1 (design §7/§8.5, plan ``2026-06-05-hsds-federation-p1-publish.md``).

Principle II (HSDS Specification Compliance — NON-NEGOTIABLE) requires that
federated ``object``s validate against the *unmodified* HSDS Pydantic models
(``app/models/hsds/response.py``). PPR's ``LocationResponse`` is a deliberately
flattened, curated **subset** of the canonical HSDS Location shape — it omits a
number of HSDS fields. ``Settings.FEDERATION_HSDS_VERSIONS`` advertises
``["3.1.1"]`` to reflect that curated-subset reality.

This test is a **drift lock**: it couples the model shape to the advertised
version so the two can never silently diverge. Advertising the newer HSDS line
(``3.2.x``) over a model that still omits these HSDS fields would publish a
``@context`` the bytes do not satisfy — a conformance fixture would have to
either ignore the mismatch (defeating its purpose) or fail on it. Conversely,
if the models are later expanded to expose these fields, the version pin must be
re-reviewed (not left stale).

The tripwire fields below are HSDS fields PPR's flattened ``LocationResponse``
does **not** expose today. Their exact HSDS provenance (verified against the
vendored ``docs/HSDS`` submodule, so the comment doesn't lie):
  - ``attributes`` — a **core** HSDS object present on the Location schema
    (``docs/HSDS/schema/location.json``); PPR omits it.
  - ``additional_websites`` — an HSDS **organization** field (added in v3.1);
    not Location-native, would be anomalous on ``LocationResponse``.
  - ``additional_urls`` — an HSDS **service** field (added in v3.1); likewise
    not Location-native.
Together their appearance on ``LocationResponse`` is a strong proxy for "the
model was expanded toward fuller HSDS coverage," which is exactly when the
advertised version must be revisited. (None of the three is a "3.2 Location
addition"; v3.2 added no new Location schema fields.)

Owner decision (recorded in
``docs/superpowers/research/2026-06-05-federation-hsds-version-pin.md``):
**pin 3.1.1 honestly for P1**; expanding the models to fuller HSDS coverage is a
separate follow-up that must re-examine this pin.
"""

from app.core.config import Settings
from app.models.hsds.response import LocationResponse

# HSDS fields PPR's curated LocationResponse does NOT expose. Presence of these
# on the model signals it was expanded toward fuller HSDS coverage (see the
# module docstring for each field's exact HSDS provenance — none is a 3.2
# Location addition; this set is a model-shape drift tripwire, not a precise
# 3.2-conformance assertion).
_FULLER_HSDS_FIELDS = {"additional_websites", "additional_urls", "attributes"}


def _models_expose_fuller_hsds() -> bool:
    """True iff LocationResponse carries the fuller-HSDS tripwire fields."""
    return _FULLER_HSDS_FIELDS <= set(LocationResponse.model_fields)


def test_advertised_hsds_version_matches_model_shape() -> None:
    """The advertised ``@context`` version line MUST match what the models emit.

    Pin 3.1.1 while the models stay a curated subset (owner-confirmed, #522);
    if they grow toward the fuller (3.2.x) HSDS shape, the advertised version
    must follow — and vice-versa.
    """
    s = Settings()
    advertised_32 = any(v.startswith("3.2") for v in s.FEDERATION_HSDS_VERSIONS)

    if _models_expose_fuller_hsds():
        # Models grew toward fuller HSDS coverage — the advertised version must
        # follow rather than stay pinned to the older line.
        assert advertised_32, (
            "LocationResponse now exposes fuller-HSDS fields "
            f"({sorted(_FULLER_HSDS_FIELDS)}) but FEDERATION_HSDS_VERSIONS="
            f"{s.FEDERATION_HSDS_VERSIONS} still advertises the older line. "
            "Re-review the version pin (Principle II)."
        )
    else:
        # Models are still the curated subset — we must NOT advertise 3.2 over
        # them (that would publish a @context the objects don't satisfy).
        assert not advertised_32, (
            "FEDERATION_HSDS_VERSIONS advertises 3.2 "
            f"({s.FEDERATION_HSDS_VERSIONS}) but LocationResponse is still a "
            f"curated subset (missing {sorted(_FULLER_HSDS_FIELDS)}). Expose "
            "the fuller HSDS shape before advertising 3.2 (Principle II)."
        )


def test_hsds_version_pin_is_nonempty() -> None:
    """A federated node must advertise at least one HSDS version (no empty set).

    An empty advertised-version list would let a consumer assume any version,
    defeating the compatibility contract.
    """
    s = Settings()
    assert s.FEDERATION_HSDS_VERSIONS, "FEDERATION_HSDS_VERSIONS must not be empty"
    assert all(
        isinstance(v, str) and v.strip() for v in s.FEDERATION_HSDS_VERSIONS
    ), "every advertised HSDS version must be a non-empty string"
