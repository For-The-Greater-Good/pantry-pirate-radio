import base64
import json
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import settings as hyp_settings
from hypothesis import strategies as st
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation import identity
from app.federation.identity import (
    build_actor,
    build_did_document,
    build_webfinger,
    load_signing_key,
    public_key_multibase,
)

_VENDOR = Path(__file__).resolve().parent / "vendor"

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


def test_build_did_document_uses_explicit_actor_url() -> None:
    # When the node is served from a domain that differs from the DID host,
    # alsoKnownAs must point at where the actor is actually served, not the
    # did-host-derived fallback.
    doc = build_did_document(
        did="did:web:h.example",
        public_key_multibase="zX",
        actor_url="https://node.example/api/v1/federation/actor",
    )
    assert doc["alsoKnownAs"] == ["https://node.example/api/v1/federation/actor"]
    assert "https://h.example/api/v1/federation/actor" not in doc["alsoKnownAs"]


def test_build_did_document_actor_url_fallback_to_did_host() -> None:
    # No actor_url provided: keep the did-host-derived fallback (P0.4 behavior).
    doc = build_did_document(did="did:web:h.example", public_key_multibase="zX")
    assert doc["alsoKnownAs"] == ["https://h.example/api/v1/federation/actor"]


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


# --- public_key_from_multibase: the inverse decoder (RED-tier, #558 discover) ----
# A federating peer RESOLVES a node's trust anchor from its published
# /.well-known/did.json `publicKeyMultibase` string — so the verify side needs the
# exact byte-inverse of `public_key_multibase`. These pin the round-trip and the
# guard rails (a malformed/forged multibase MUST raise, never silently yield a
# wrong key a verifier would then trust).


def _craft_multibase(payload: bytes) -> str:
    """A 'z'-prefixed base58btc multibase over arbitrary payload bytes (for
    negatives) — uses the module's own encoder so the base58 layer is honest and
    only the multicodec/length is what the negative exercises."""
    return "z" + identity._b58encode(payload)


def test_public_key_from_multibase_roundtrips_with_encoder() -> None:
    pub: Ed25519PublicKey = Ed25519PrivateKey.generate().public_key()
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    decoded = identity.public_key_from_multibase(public_key_multibase(pub))
    assert isinstance(decoded, Ed25519PublicKey)
    assert (
        decoded.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        == raw
    )


@hyp_settings(max_examples=200, deadline=None)
@given(seed=st.binary(min_size=32, max_size=32))
def test_public_key_from_multibase_roundtrips_property(seed: bytes) -> None:
    pub = Ed25519PrivateKey.from_private_bytes(seed).public_key()
    raw = pub.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    decoded = identity.public_key_from_multibase(public_key_multibase(pub))
    assert (
        decoded.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        == raw
    )


def test_public_key_from_multibase_rejects_missing_z_prefix() -> None:
    pub = Ed25519PrivateKey.generate().public_key()
    mb = public_key_multibase(pub)
    with pytest.raises(ValueError):
        identity.public_key_from_multibase("f" + mb[1:])  # 'f' = base16 multibase
    with pytest.raises(ValueError):
        identity.public_key_from_multibase(mb[1:])  # no multibase prefix at all


def test_public_key_from_multibase_rejects_empty() -> None:
    with pytest.raises(ValueError):
        identity.public_key_from_multibase("")
    with pytest.raises(ValueError):
        identity.public_key_from_multibase("z")  # prefix only, empty payload


def test_public_key_from_multibase_rejects_wrong_multicodec() -> None:
    # 32 bytes under a DIFFERENT multicodec prefix (0xec01 = x25519-pub, not ed25519).
    bad = _craft_multibase(b"\xec\x01" + bytes(range(32)))
    with pytest.raises(ValueError):
        identity.public_key_from_multibase(bad)


def test_public_key_from_multibase_rejects_wrong_length() -> None:
    # Correct multicodec but 31 / 33 key bytes — not a valid Ed25519 public key.
    with pytest.raises(ValueError):
        identity.public_key_from_multibase(_craft_multibase(b"\xed\x01" + bytes(31)))
    with pytest.raises(ValueError):
        identity.public_key_from_multibase(_craft_multibase(b"\xed\x01" + bytes(33)))


def test_public_key_from_multibase_rejects_bad_base58_char() -> None:
    # '0', 'O', 'I', 'l' are excluded from the base58btc alphabet.
    with pytest.raises(ValueError):
        identity.public_key_from_multibase("z" + "0OIl")


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


# --- CONF-1: pin load_signing_key's base64-seed branch to EXTERNAL truth.
# The primitive (Ed25519 seed->pubkey->signature) is already anchored by the Go
# note + RFC 9421 KATs, but the load_signing_key base64 WRAPPER was tested only
# self-consistently. Reuse the already-vendored RFC 9421 raw-hex seed (no new
# vendored files) so a seed/decoding regression in this wrapper is caught.
def test_load_signing_key_base64_seed_matches_rfc9421_vector() -> None:
    v = json.loads(
        (_VENDOR / "rfc9421_appendix_b" / "vector.json").read_text(encoding="utf-8")
    )
    seed = bytes.fromhex(v["private_key_raw_hex"])
    key = load_signing_key(base64.b64encode(seed).decode("ascii"))
    assert key is not None
    raw_pub = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    # External truth: the seed derives the published public key...
    assert raw_pub.hex() == v["public_key_raw_hex"]
    # ...and re-signs the vendored signature base to the published signature.
    sig = key.sign(v["signature_base"].encode("utf-8"))
    assert base64.b64encode(sig).decode("ascii") == v["signature_b64"]


# --- CONF-2: pin the base58btc encoder + did:key composition to EXTERNAL truth.
# The hand-rolled _b58encode (the prod fallback path) was pinned only by a
# self-derived decoder in this same file; a leading-zero/pad refactor could
# silently emit a publicKeyMultibase every peer rejects.
_B58_VECTORS = json.loads(
    (_VENDOR / "base58btc" / "vectors.json").read_text(encoding="utf-8")
)["vectors"]


@pytest.mark.parametrize("vec", _B58_VECTORS)
def test_b58encode_matches_external_base58_vectors(vec) -> None:
    """_b58encode reproduces the canonical base58btc vectors (incl. leading-zero)."""
    assert identity._b58encode(bytes.fromhex(vec["input_hex"])) == vec["base58"]


# The canonical W3C did:key Ed25519 example (did-key-spec, "Create" section).
_W3C_DID_KEY_ED25519 = "z6MkhaXgBZDvotDkL5257faiztiGiC2QtKLGpbnnEGta2doK"


def test_public_key_multibase_reproduces_w3c_did_key_vector() -> None:
    """public_key_multibase re-encodes the W3C-published z6Mk… string exactly.

    We recover the raw key by decoding the published multibase, then re-encode
    with the (externally-pinned, see above) encoder and assert byte-equality with
    the published string — so a composition bug (multicodec prefix / 'z' prefix /
    base58) cannot pass. The decoder is only a means to recover candidate bytes;
    correctness rests on reproducing the published string via the pinned encoder.
    """
    body = _b58decode(_W3C_DID_KEY_ED25519[1:])  # strip the 'z' multibase prefix
    assert body[:2] == b"\xed\x01"  # ed25519-pub multicodec varint
    raw = body[2:]
    assert len(raw) == 32
    pub = Ed25519PublicKey.from_public_bytes(raw)
    assert public_key_multibase(pub) == _W3C_DID_KEY_ED25519


def test_all_ed25519_did_keys_share_the_z6mk_prefix() -> None:
    """Documented external invariant: every Ed25519 did:key starts 'z6Mk'
    (base58btc of the 0xed01 multicodec prefix)."""
    for seed in (bytes(range(32)), bytes([7]) * 32, bytes([255]) * 32):
        pub = Ed25519PrivateKey.from_private_bytes(seed).public_key()
        assert public_key_multibase(pub).startswith("z6Mk")
