"""Tests for the .well-known/hsds-federation discovery document (§8.4 / §6.7).

The discovery doc is how a peer learns this node's DID, key location, supported
HSDS versions (set-membership, not exact-match), profile, endpoint URLs,
allow-list policy, and retention. It must render a valid (status-200-able) doc
with all defaults (domain -> "localhost") AND with a did:web DID (host derived).
"""

from app.core.config import Settings
from app.federation.discovery import build_discovery_doc

_EXPECTED_KEYS = {
    "did",
    "key_location",
    "hsds_versions",
    "profile_uri",
    "endpoints",
    "allow_list_policy",
    "retention_days",
    "contact",
}


def test_discovery_doc_with_defaults_is_valid() -> None:
    settings = Settings()
    doc = build_discovery_doc(settings)

    # Exactly the contracted keys, no extras (§8.4 / §6.7 contract).
    assert set(doc.keys()) == _EXPECTED_KEYS

    # hsds_versions is a non-empty LIST (set-membership, §8.4).
    assert isinstance(doc["hsds_versions"], list)
    assert doc["hsds_versions"]
    assert all(isinstance(v, str) for v in doc["hsds_versions"])
    assert doc["hsds_versions"] == settings.FEDERATION_HSDS_VERSIONS

    # allow_list_policy is one of the known values.
    assert doc["allow_list_policy"] in {"open", "mutual", "private"}
    assert doc["allow_list_policy"] == settings.FEDERATION_ALLOW_LIST_POLICY

    # retention mirrors settings.
    assert doc["retention_days"] == settings.FEDERATION_RETENTION_DAYS

    # profile_uri and contact mirror settings.
    assert doc["profile_uri"] == settings.FEDERATION_PROFILE_URI
    assert doc["contact"] == settings.FEDERATION_CONTACT

    # did may be None when unconfigured (allowed).
    assert doc["did"] == settings.FEDERATION_DID

    # With all defaults, domain falls back to "localhost".
    assert doc["key_location"] == "https://localhost/.well-known/did.json"

    # endpoints: absolute https:// URLs ending in the right paths.
    endpoints = doc["endpoints"]
    assert set(endpoints.keys()) == {"export", "inbox", "history"}
    for value in endpoints.values():
        assert value.startswith("https://")
    assert endpoints["export"].endswith("/api/v1/federation/export")
    assert endpoints["inbox"].endswith("/api/v1/federation/inbox")
    assert endpoints["history"].endswith("/api/v1/federation/history")
    # Default host is localhost.
    assert endpoints["export"] == "https://localhost/api/v1/federation/export"


def test_discovery_doc_derives_host_from_did_web() -> None:
    settings = Settings(FEDERATION_DID="did:web:h.example")
    doc = build_discovery_doc(settings)

    assert doc["did"] == "did:web:h.example"
    # Host derived from the did:web DID (FEDERATION_DOMAIN unset).
    assert doc["key_location"] == "https://h.example/.well-known/did.json"
    assert doc["endpoints"]["export"] == "https://h.example/api/v1/federation/export"
    assert doc["endpoints"]["inbox"] == "https://h.example/api/v1/federation/inbox"
    assert doc["endpoints"]["history"] == "https://h.example/api/v1/federation/history"


def test_discovery_doc_domain_overrides_did_host() -> None:
    settings = Settings(
        FEDERATION_DID="did:web:h.example",
        FEDERATION_DOMAIN="node.public.example",
    )
    doc = build_discovery_doc(settings)

    # FEDERATION_DOMAIN takes precedence over the DID-derived host.
    assert doc["key_location"] == "https://node.public.example/.well-known/did.json"
    assert (
        doc["endpoints"]["export"]
        == "https://node.public.example/api/v1/federation/export"
    )
