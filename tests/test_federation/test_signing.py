import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.federation.signing import (
    SignatureError,
    build_signature_base,
    sign_request,
    verify_request,
)


def _keys():
    priv = Ed25519PrivateKey.generate()
    return priv, priv.public_key()


def test_signature_base_is_rfc9421_shaped():
    base = build_signature_base(
        method="POST",
        target_uri="https://h.example/federation/inbox",
        content_digest="sha-256=:abc=:",
        created=1780600000,
        keyid="did:web:h.example#main-key",
    )
    assert '"@method": POST' in base
    assert '"@target-uri": https://h.example/federation/inbox' in base
    assert base.rstrip().endswith(
        '"@signature-params": ("@method" "@target-uri" "content-digest")'
        ';created=1780600000;keyid="did:web:h.example#main-key";alg="ed25519"'
    )


def test_sign_then_verify_roundtrips_and_rejects_tamper():
    priv, pub = _keys()
    headers = sign_request(
        priv,
        "did:web:h.example#main-key",
        "POST",
        "https://h.example/federation/inbox",
        body=b'{"x":1}',
        created=1780600000,
    )
    assert {"Content-Digest", "Signature-Input", "Signature"} <= set(headers)
    verify_request(
        pub,
        "POST",
        "https://h.example/federation/inbox",
        headers,
        body=b'{"x":1}',
        max_skew_seconds=300,
        now=1780600060,
    )
    with pytest.raises(SignatureError):
        verify_request(
            pub,
            "POST",
            "https://h.example/federation/inbox",
            headers,
            body=b'{"x":2}',
            max_skew_seconds=300,
            now=1780600060,
        )
