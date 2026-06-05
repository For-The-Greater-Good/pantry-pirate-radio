import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation.identity import (
    build_actor,
    build_did_document,
    build_webfinger,
    load_signing_key,
    public_key_multibase,
)

_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58decode(data: str) -> bytes:
    """Minimal base58btc decoder used only to pin the multibase round-trip."""
    num = 0
    for char in data:
        num = num * 58 + _B58_ALPHABET.index(char)
    body = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = 0
    for char in data:
        if char == "1":
            pad += 1
        else:
            break
    return b"\x00" * pad + body


def test_build_did_document_priority_ordering_and_also_known_as() -> None:
    doc = build_did_document(
        "did:web:h.example", "zTEST", recovery_keys_multibase=["zRECOVERY"]
    )
    assert doc["id"] == "did:web:h.example"

    methods = doc["verificationMethod"]
    main = next(m for m in methods if m["id"] == "did:web:h.example#main-key")
    assert main["type"] == "Ed25519VerificationKey2020"
    assert main["controller"] == "did:web:h.example"
    assert main["publicKeyMultibase"] == "zTEST"
    assert isinstance(main["priority"], int)

    recovery = [m for m in methods if m["id"] != "did:web:h.example#main-key"]
    assert len(recovery) >= 1
    assert all(r["priority"] > main["priority"] for r in recovery)
    assert recovery[0]["publicKeyMultibase"] == "zRECOVERY"

    # Ordered highest-priority-first: recovery keys come before the main key.
    priorities = [m["priority"] for m in methods]
    assert priorities == sorted(priorities, reverse=True)
    assert methods[-1]["id"] == "did:web:h.example#main-key"

    assert doc["authentication"] == ["did:web:h.example#main-key"]
    assert doc["assertionMethod"] == ["did:web:h.example#main-key"]
    assert "https://h.example/api/v1/federation/actor" in doc["alsoKnownAs"]


def test_build_did_document_no_recovery_keys() -> None:
    doc = build_did_document("did:web:h.example", "zMAIN")
    methods = doc["verificationMethod"]
    assert len(methods) == 1
    assert methods[0]["id"] == "did:web:h.example#main-key"


def test_load_signing_key_none_returns_none() -> None:
    assert load_signing_key(None) is None


def test_load_signing_key_pem_roundtrips_and_signs() -> None:
    original = Ed25519PrivateKey.generate()
    pem = original.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode("ascii")

    loaded = load_signing_key(pem)
    assert isinstance(loaded, Ed25519PrivateKey)

    message = b"federation-proof"
    signature = loaded.sign(message)
    # Verifying with the original public key proves it is the same key.
    original.public_key().verify(signature, message)


def test_load_signing_key_base64_seed_roundtrips() -> None:
    import base64

    original = Ed25519PrivateKey.generate()
    raw = original.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    seed_b64 = base64.b64encode(raw).decode("ascii")

    loaded = load_signing_key(seed_b64)
    assert isinstance(loaded, Ed25519PrivateKey)
    message = b"seed-roundtrip"
    original.public_key().verify(loaded.sign(message), message)


def test_load_signing_key_raises_on_garbage() -> None:
    with pytest.raises(ValueError):
        load_signing_key("not-a-valid-key-!!!")


def test_public_key_multibase_roundtrips_with_multicodec_prefix() -> None:
    pub: Ed25519PublicKey = Ed25519PrivateKey.generate().public_key()
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )

    mb = public_key_multibase(pub)
    assert mb.startswith("z")

    decoded = _b58decode(mb[1:])
    assert decoded[0] == 0xED
    assert decoded[1] == 0x01
    assert decoded[2:] == raw
    assert len(raw) == 32


def test_build_actor_shape() -> None:
    actor = build_actor("did:web:h.example", "h.example", "zTEST")
    assert actor["id"] == "https://h.example/api/v1/federation/actor"
    assert actor["type"] == "Service"
    assert actor["inbox"].endswith("/api/v1/federation/inbox")
    assert actor["outbox"].endswith("/api/v1/federation/export")
    assert actor["publicKey"]["owner"] == "did:web:h.example"
    assert actor["publicKey"]["id"] == "did:web:h.example#main-key"
    assert actor["publicKey"]["publicKeyMultibase"] == "zTEST"


def test_build_webfinger_returns_jrd_with_self_link() -> None:
    jrd = build_webfinger(
        "acct:north-jersey-fb@h.example",
        "https://h.example/api/v1/federation/actor",
    )
    assert jrd["subject"] == "acct:north-jersey-fb@h.example"
    self_links = [link for link in jrd["links"] if link["rel"] == "self"]
    assert len(self_links) == 1
    assert self_links[0]["type"] == "application/activity+json"
    assert self_links[0]["href"] == "https://h.example/api/v1/federation/actor"
