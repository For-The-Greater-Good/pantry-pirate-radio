"""Tests for the root-level public federation routes (Task 0.7, Principle XV).

These routes make PPR discoverable: a peer hits ``/.well-known/hsds-federation``
and ``/.well-known/did.json`` to learn the node's identity, keys, versions, and
endpoints. did:web + WebFinger REQUIRE the ``.well-known`` paths at the domain
root, so they cannot live under the ``/api/v1`` prefix. The same routes must
register identically in the Uvicorn app (``app/main.py``) and the slim Lambda
(``app/api/lambda_app.py``).

``register_federation_public_routes`` is the seam both apps call; this module
exercises it in isolation on a bare ``FastAPI`` instance.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.federation.routes_public import register_federation_public_routes


def _client() -> TestClient:
    app = FastAPI()
    register_federation_public_routes(app)
    return TestClient(app)


def _client_with_settings(monkeypatch, settings: Settings) -> TestClient:
    """Build a client whose route handlers read an overridden settings object."""
    monkeypatch.setattr("app.federation.routes_public.settings", settings)
    return _client()


def _b64_seed() -> str:
    """A fictional, deterministic base64 Ed25519 seed for the 200-path tests."""
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    raw = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return base64.b64encode(raw).decode("ascii")


def test_well_known_discovery_served() -> None:
    r = _client().get("/.well-known/hsds-federation")
    assert r.status_code == 200
    assert isinstance(r.json()["hsds_versions"], list)  # §8.4 set-membership


def test_did_json_served() -> None:
    r = _client().get("/.well-known/did.json")
    # 404 only if FEDERATION_DID unset; 200 when configured.
    assert r.status_code in (200, 404)


def test_webfinger_requires_resource() -> None:
    assert _client().get("/.well-known/webfinger").status_code == 422


def test_actor_route_served() -> None:
    r = _client().get("/api/v1/federation/actor")
    # 200 when FEDERATION_DID + signing key configured, 404 when not.
    assert r.status_code in (200, 404)


def test_did_json_200_when_configured(monkeypatch) -> None:
    settings = Settings(
        FEDERATION_DID="did:web:node.example",
        FEDERATION_SIGNING_KEY=_b64_seed(),
    )
    client = _client_with_settings(monkeypatch, settings)
    r = client.get("/.well-known/did.json")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "did:web:node.example"
    assert isinstance(body["verificationMethod"], list)
    assert body["verificationMethod"]
    assert body["verificationMethod"][-1]["id"] == "did:web:node.example#main-key"


def test_actor_200_when_configured(monkeypatch) -> None:
    settings = Settings(
        FEDERATION_DID="did:web:node.example",
        FEDERATION_SIGNING_KEY=_b64_seed(),
    )
    client = _client_with_settings(monkeypatch, settings)
    r = client.get("/api/v1/federation/actor")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "Service"
    assert body["id"] == "https://node.example/api/v1/federation/actor"


def test_did_json_404_when_unconfigured(monkeypatch) -> None:
    settings = Settings(FEDERATION_DID=None, FEDERATION_SIGNING_KEY=None)
    client = _client_with_settings(monkeypatch, settings)
    assert client.get("/.well-known/did.json").status_code == 404


def test_did_json_404_when_did_set_but_no_signing_key(monkeypatch) -> None:
    # DID configured before the signing key is provisioned: still 404 (no key
    # to publish), exercising the missing-key guard distinct from missing-DID.
    settings = Settings(
        FEDERATION_DID="did:web:node.example", FEDERATION_SIGNING_KEY=None
    )
    client = _client_with_settings(monkeypatch, settings)
    assert client.get("/.well-known/did.json").status_code == 404
    assert client.get("/api/v1/federation/actor").status_code == 404


def test_did_json_404_when_signing_key_malformed(monkeypatch) -> None:
    # A misconfigured (malformed) signing key must be logged and treated as
    # "no key" → 404, never an opaque 500 (Principle XI/XII).
    settings = Settings(
        FEDERATION_DID="did:web:node.example",
        FEDERATION_SIGNING_KEY="not-a-valid-key",
    )
    client = _client_with_settings(monkeypatch, settings)
    assert client.get("/.well-known/did.json").status_code == 404


def test_webfinger_resolves_actor_url(monkeypatch) -> None:
    settings = Settings(FEDERATION_DOMAIN="node.public.example")
    client = _client_with_settings(monkeypatch, settings)
    r = client.get("/.well-known/webfinger", params={"resource": "acct:node@example"})
    assert r.status_code == 200
    body = r.json()
    assert body["subject"] == "acct:node@example"
    assert (
        body["links"][0]["href"]
        == "https://node.public.example/api/v1/federation/actor"
    )
