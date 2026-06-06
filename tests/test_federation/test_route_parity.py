"""PARITY-1: the federation public routes must be registered IDENTICALLY in the
full Uvicorn app (``app/main.py``) and the slim Lambda (``app/api/lambda_app.py``).

``register_federation_public_routes`` is the seam both apps call (Principle XV).
The existing ``test_public_routes.py`` exercises it on a *bare* ``FastAPI()`` —
so a dropped ``register_*`` call in one of the real apps would leave every test
green while ``/.well-known/did.json`` 404s in prod. This module asserts against
the REAL app objects (mirrors ``tests/test_ptf_locations_lambda_compat.py``).
"""

from __future__ import annotations

_FEDERATION_ROUTES = {
    "/.well-known/hsds-federation",
    "/.well-known/did.json",
    "/.well-known/webfinger",
    "/api/v1/federation/actor",
}


def _fed_route_methods(app) -> dict[str, frozenset[str]]:
    """Map each federation route path -> its HTTP methods on ``app``."""
    out: dict[str, frozenset[str]] = {}
    for route in app.routes:
        path = getattr(route, "path", None)
        if path in _FEDERATION_ROUTES:
            out[path] = frozenset(getattr(route, "methods", None) or set())
    return out


def test_federation_routes_registered_in_full_app() -> None:
    from app.main import app

    assert set(_fed_route_methods(app)) == _FEDERATION_ROUTES


def test_federation_routes_registered_in_lambda_app() -> None:
    import app.api.lambda_app as lambda_app

    assert set(_fed_route_methods(lambda_app.app)) == _FEDERATION_ROUTES


def test_federation_routes_identical_across_full_and_lambda() -> None:
    from app.main import app as full_app

    import app.api.lambda_app as lambda_app

    full = _fed_route_methods(full_app)
    slim = _fed_route_methods(lambda_app.app)
    # Same paths AND same methods in both apps — a drift in either is a prod 404.
    assert full == slim, f"federation route drift: full={full} slim={slim}"
    for path in _FEDERATION_ROUTES:
        assert "GET" in full[path], f"{path} is not a GET route in the full app"
