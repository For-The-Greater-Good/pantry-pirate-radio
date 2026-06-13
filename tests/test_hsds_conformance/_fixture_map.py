"""Shared fixture <-> model map + lazy model resolution for the HSDS KAT harness.

G1 (HSDS full-compliance epic, issue #593): this module is the single source of
truth for which vendored official-example fixture maps to which response model,
consumed by both ``test_tier_a_representation.py`` (``model_validate``) and
``test_tier_b_roundtrip.py`` (JCS round-trip byte-equality).

Model resolution is LAZY and by dotted path so that a model which does not exist
yet (``TaxonomyResponse`` / ``TaxonomyTermResponse`` land in T1) produces a
``ModelNotFoundError`` at test-body time rather than a collection-time
``ImportError`` — that keeps a missing model an ordinary (manifested) xfail
instead of blowing up the whole module.

Two dotted-path forms are supported:
  - ``"app.models.hsds.response.OrganizationResponse"`` — a plain model.
  - ``"app.models.hsds.response.Page[app.models.hsds.response.OrganizationResponse]"``
    — the generic ``Page`` envelope parameterized over an item model. Both the
    outer ``Page`` and the inner item model are resolved independently, so a
    missing item model (e.g. ``TaxonomyResponse`` for ``taxonomy_list.json``)
    still surfaces as a clean ``ModelNotFoundError``.

``base.json`` and ``tabular.json`` are corpus-presence-only fixtures (no model
maps to them) and are intentionally NOT listed in ``FIXTURE_MODEL_MAP`` — they
are still vendored (see ``vendor/hsds_official_examples/``) but never appear in
a KAT parametrization.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

VENDOR_DIR = Path(__file__).resolve().parent / "vendor" / "hsds_official_examples"


class ModelNotFoundError(ImportError):
    """Raised by :func:`resolve_model` when a dotted path cannot be imported.

    A fixture whose target model does not exist yet (e.g. ``TaxonomyResponse``,
    landing in slice T1) resolves to this error. Tier-A/B tests catch it and
    treat it as "the fixture fails today" — exactly the manifested xfail state
    G1 is meant to capture.
    """


# fixture filename -> dotted model path (see module docstring for the
# ``Page[...]`` generic syntax). Every entry here MUST have a corresponding
# manifest row in ``xfail_manifest.json`` for tier "A" (and "B" where
# applicable) until the owning slice flips it.
FIXTURE_MODEL_MAP: dict[str, str] = {
    # Entity fixtures (Tier A + Tier B both fail today; flip in S5/A1/O4/T1/L1).
    "organization_full.json": "app.models.hsds.response.OrganizationResponse",
    "service_full.json": "app.models.hsds.response.ServiceResponse",
    "service_at_location_full.json": (
        "app.models.hsds.response.ServiceAtLocationResponse"
    ),
    "location.json": "app.models.hsds.response.LocationResponse",
    "taxonomy.json": "app.models.hsds.response.TaxonomyResponse",
    "taxonomy_term.json": "app.models.hsds.response.TaxonomyTermResponse",
    # List/envelope fixtures (official Page shape vs bespoke Page; flip in G3).
    "organization_list.json": (
        "app.models.hsds.response.Page[app.models.hsds.response.OrganizationResponse]"
    ),
    "service_list.json": (
        "app.models.hsds.response.Page[app.models.hsds.response.ServiceResponse]"
    ),
    "service_at_location_list.json": (
        "app.models.hsds.response.Page"
        "[app.models.hsds.response.ServiceAtLocationResponse]"
    ),
    "taxonomy_list.json": (
        "app.models.hsds.response.Page[app.models.hsds.response.TaxonomyResponse]"
    ),
    "taxonomy_term_list.json": (
        "app.models.hsds.response.Page"
        "[app.models.hsds.response.TaxonomyTermResponse]"
    ),
}

# Fixtures vendored for corpus completeness but with no model to validate
# against (no entry in FIXTURE_MODEL_MAP, and intentionally excluded from both
# KAT tiers).
NO_MODEL_FIXTURES: tuple[str, ...] = ("base.json", "tabular.json")


def load_fixture_bytes(fixture: str) -> bytes:
    """Return the raw bytes of a vendored example fixture, verbatim."""
    return (VENDOR_DIR / fixture).read_bytes()


def load_fixture_json(fixture: str) -> Any:
    """Return the parsed JSON content of a vendored example fixture."""
    return json.loads(load_fixture_bytes(fixture).decode("utf-8"))


MANIFEST_PATH = Path(__file__).resolve().parent / "xfail_manifest.json"


def load_manifest() -> list[dict[str, str]]:
    """Return the parsed ``xfail_manifest.json`` entries.

    Each entry is ``{"fixture": str, "tier": "A"|"B", "reason": str}``. See
    ``test_xfail_manifest_ratchet.py`` for the shrink-only invariants enforced
    over this data.
    """
    raw = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise TypeError("xfail_manifest.json must contain a JSON array")
    return raw


def manifest_reason(
    manifest: list[dict[str, str]], fixture: str, tier: str
) -> str | None:
    """Return the manifested xfail reason for ``(fixture, tier)``, or ``None``.

    ``None`` means the fixture is NOT in the manifest for this tier — i.e. it
    is expected to PASS the KAT.
    """
    for entry in manifest:
        if entry["fixture"] == fixture and entry["tier"] == tier:
            return entry["reason"]
    return None


def _resolve_dotted(path: str) -> Any:
    """Import and return the attribute named by a plain ``module.attr`` path."""
    module_path, _, attr = path.rpartition(".")
    if not module_path:
        raise ModelNotFoundError(f"invalid dotted path: {path!r}")
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise ModelNotFoundError(f"module not found for {path!r}: {exc}") from exc
    try:
        return getattr(module, attr)
    except AttributeError as exc:
        raise ModelNotFoundError(f"attribute not found for {path!r}: {exc}") from exc


def resolve_model(model_path: str) -> Any:
    """Resolve a dotted model path, including the ``Outer[Inner]`` generic form.

    Raises :class:`ModelNotFoundError` if any component (outer or inner) cannot
    be imported — this is the hook that turns "model doesn't exist yet" into a
    clean, manifestable xfail rather than a collection error.
    """
    if "[" in model_path:
        if not model_path.endswith("]"):
            raise ModelNotFoundError(f"malformed generic path: {model_path!r}")
        outer_path, inner_path = model_path[:-1].split("[", 1)
        outer = _resolve_dotted(outer_path)
        inner = resolve_model(inner_path)
        return outer[inner]
    return _resolve_dotted(model_path)
