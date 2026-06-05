import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


def test_api_root_profile_is_ppr_not_generic():
    from app.core.config import settings
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/v1/")
    assert r.status_code == 200
    profile = r.json()["profile"]
    assert profile != "https://docs.openhumanservices.org/hsds/"
    assert profile == settings.FEDERATION_PROFILE_URI


def test_api_root_version_unchanged():
    """The advertised HSDS version must remain 3.1.1 (models are 3.1.1-shaped)."""
    from app.main import app

    client = TestClient(app)
    r = client.get("/api/v1/")
    assert r.status_code == 200
    assert r.json()["version"] == "3.1.1"


@pytest.mark.parametrize("name", ["location.json", "service.json", "openapi.json"])
def test_profile_patch_is_valid_json(name):
    path = Path("profiles/hsds-ppr") / name
    data = json.loads(path.read_text())
    assert isinstance(data, dict)


def test_location_profile_adds_only_optional_props():
    data = json.loads(Path("profiles/hsds-ppr/location.json").read_text())
    # the merge patch must NOT introduce required entries
    assert "required" not in data or data.get("required") in (None, [], {})
    props = data.get("properties", {})
    assert "confidence_score" in props and "verified_by" in props and "sources" in props


def test_service_profile_adds_only_optional_props():
    data = json.loads(Path("profiles/hsds-ppr/service.json").read_text())
    assert "required" not in data or data.get("required") in (None, [], {})
    props = data.get("properties", {})
    assert "confidence_score" in props and "verified_by" in props and "sources" in props


def test_openapi_patch_documents_federation_paths():
    data = json.loads(Path("profiles/hsds-ppr/openapi.json").read_text())
    paths = data.get("paths", {})
    assert "/api/v1/federation/export" in paths
    assert "/api/v1/federation/inbox" in paths
