"""Lambda dual-environment guard for PTF /locations (Principle XV).

Imports the Lambda-mode FastAPI app and asserts both PTF location
routes are present. If a future change wires routes only to main.py
this test goes red.
"""

from __future__ import annotations

import os


def test_ptf_locations_routes_registered_in_lambda_app(monkeypatch):
    # Simulate Lambda environment so router-level branches behave as in AWS.
    monkeypatch.setenv("AWS_LAMBDA_FUNCTION_NAME", "test-fn")
    # Re-import lambda_app fresh so module-level Settings sees the env var.
    import importlib
    import app.api.lambda_app as lambda_app

    importlib.reload(lambda_app)
    paths = {getattr(r, "path", None) for r in lambda_app.app.routes}
    assert "/api/v1/partners/ptf/locations" in paths, paths
    assert "/api/v1/partners/ptf/locations/{location_id}" in paths, paths


def test_ptf_locations_routes_also_registered_in_main_app():
    """Same routes must also be reachable in the Docker app."""
    from app.main import app

    paths = {getattr(r, "path", None) for r in app.routes}
    assert "/api/v1/partners/ptf/locations" in paths, paths
    assert "/api/v1/partners/ptf/locations/{location_id}" in paths, paths
