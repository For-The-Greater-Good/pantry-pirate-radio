"""Regression guard: the advertised HSDS version MUST match the model shape.

P1 Task -1 (design §7/§8.5, plan ``2026-06-05-hsds-federation-p1-publish.md``).

Principle II (HSDS Specification Compliance — NON-NEGOTIABLE) requires that
federated ``object``s validate against the *unmodified* HSDS Pydantic models
(``app/models/hsds/response.py``). Those models currently implement HSDS
**3.1.1** — they lack the 3.2 additions (``additional_websites``,
``additional_urls``, ``attributes``, and a Location-level ``attributes``/
metadata block). ``Settings.FEDERATION_HSDS_VERSIONS`` advertises ``["3.1.1"]``.

These two facts must never silently diverge: advertising ``@context: .../3.2``
over a 3.1.1-shaped object is a lie a conformance fixture would have to either
ignore (defeating its purpose) or fail on. This test is the lock — it passes
today (both say 3.1.1) and fails the moment someone bumps the advertised
version to 3.2 without first implementing the 3.2 fields on the models (or
vice-versa).

Owner decision (recorded in
``docs/superpowers/research/2026-06-05-federation-hsds-version-pin.md``):
**pin 3.1.1 honestly for P1**; implement the 3.2 model fields as a separate
follow-up.
"""

from app.core.config import Settings
from app.models.hsds.response import LocationResponse

# The fields HSDS 3.2 adds to a Location that 3.1.1 does not have. Presence of
# these on the Pydantic model is the objective signal that the models emit 3.2.
_HSDS_32_LOCATION_FIELDS = {"additional_websites", "additional_urls", "attributes"}


def _models_emit_hsds_32() -> bool:
    """True iff the Location model carries the HSDS 3.2 field additions."""
    return _HSDS_32_LOCATION_FIELDS <= set(LocationResponse.model_fields)


def test_advertised_hsds_version_matches_model_shape() -> None:
    """The advertised ``@context`` version line MUST match what the models emit.

    Pin 3.1.1 until the 3.2 fields are implemented (owner-confirmed, #522).
    """
    s = Settings()
    advertised_32 = any(v.startswith("3.2") for v in s.FEDERATION_HSDS_VERSIONS)

    if _models_emit_hsds_32():
        # Models grew the 3.2 fields — the advertised version must follow.
        assert advertised_32, (
            "LocationResponse now carries HSDS 3.2 fields "
            f"({sorted(_HSDS_32_LOCATION_FIELDS)}) but FEDERATION_HSDS_VERSIONS="
            f"{s.FEDERATION_HSDS_VERSIONS} does not advertise 3.2."
        )
    else:
        # Models are still 3.1.1 — we must NOT advertise 3.2 over them.
        assert not advertised_32, (
            "FEDERATION_HSDS_VERSIONS advertises 3.2 "
            f"({s.FEDERATION_HSDS_VERSIONS}) but the Pydantic models are still "
            f"3.1.1-shaped (missing {sorted(_HSDS_32_LOCATION_FIELDS)}). "
            "Implement the 3.2 fields before advertising 3.2 (Principle II)."
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
