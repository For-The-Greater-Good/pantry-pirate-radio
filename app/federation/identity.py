"""Federation identity: did:web document, ActivityStreams actor, key loading.

Implements the recovery-key hierarchy schema (design §6.1a, did:plc-inspired).
``did:web`` derives trust from DNS+TLS, which is trust-on-first-use and as
strong as the operator's domain control. To harden key rotation we ship an
**ordered** ``verificationMethod`` list carrying an explicit integer
``priority`` per entry: offline recovery keys outrank the online signing key,
so a compromised online key cannot authorize an unbounded key change.

P0 ships the forward-compatible SCHEMA only (issue #532). The verify-side
priority-enforcement rule — a key-change must be signed by a key of
``>=`` the priority being changed — ships in **P3** per the implementation
plan; this module deliberately does NOT implement that enforcement.

multibase encoding: ``publicKeyMultibase`` follows the W3C
Ed25519VerificationKey2020 suite — base58btc ("z" prefix) over the
``0xed 0x01`` ed25519-pub multicodec prefix followed by the 32 raw public key
bytes. The encoding is hand-rolled (no ``base58`` dependency) so non-PPR
partners can implement against the standard without our exact toolchain.
"""

import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

# Bitcoin / base58btc alphabet.
_B58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
# multicodec varint prefix for ed25519-pub.
_ED25519_PUB_MULTICODEC = b"\xed\x01"

# Priority convention: HIGHER priority == HIGHER authority. Recovery keys
# (offline) outrank the online signing key so they can authorize key changes
# the online key cannot. The list is ordered highest-priority-first.
_MAIN_KEY_PRIORITY = 1
_RECOVERY_KEY_PRIORITY_BASE = 10


def _b58encode(data: bytes) -> str:
    """Encode bytes as base58btc. Used only when ``base58`` is unavailable."""
    num = int.from_bytes(data, "big")
    encoded = ""
    while num > 0:
        num, rem = divmod(num, 58)
        encoded = _B58_ALPHABET[rem] + encoded
    # Each leading zero byte maps to a leading '1'.
    pad = 0
    for byte in data:
        if byte == 0:
            pad += 1
        else:
            break
    return "1" * pad + encoded


def public_key_multibase(public_key: Ed25519PublicKey) -> str:
    """Encode an Ed25519 public key as a W3C ``publicKeyMultibase`` string."""
    raw = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    payload = _ED25519_PUB_MULTICODEC + raw
    try:
        import base58

        return "z" + base58.b58encode(payload).decode("ascii")
    except ImportError:
        return "z" + _b58encode(payload)


def load_signing_key(material: str | None) -> Ed25519PrivateKey | None:
    """Load an Ed25519 private key from PEM or a base64 raw 32-byte seed.

    ``None`` material yields ``None`` (no key configured). PEM material (starts
    with ``-----BEGIN``) is parsed via PKCS8; otherwise the material is treated
    as a base64-encoded 32-byte raw seed. Any parse failure raises
    ``ValueError`` — never a silent ``None`` (Principle XI).
    """
    if material is None:
        return None

    if material.lstrip().startswith("-----BEGIN"):
        try:
            key = serialization.load_pem_private_key(
                material.encode("utf-8"), password=None
            )
        except (ValueError, TypeError) as exc:
            raise ValueError("invalid PEM Ed25519 private key") from exc
        if not isinstance(key, Ed25519PrivateKey):
            raise ValueError("PEM key is not an Ed25519 private key")
        return key

    try:
        raw = base64.b64decode(material, validate=True)
        return Ed25519PrivateKey.from_private_bytes(raw)
    except (ValueError, base64.binascii.Error) as exc:  # type: ignore[attr-defined]
        raise ValueError("invalid base64 Ed25519 seed") from exc


def _host_from_did(did: str) -> str:
    """Derive the host from a ``did:web:<host>`` or ``https://<host>`` DID.

    Port encoding (``did:web:host%3A8443``) is out of scope — a bare host is
    assumed per the design.
    """
    if did.startswith("did:web:"):
        return did[len("did:web:") :]
    if did.startswith("https://"):
        return did[len("https://") :].split("/", 1)[0]
    return did


def build_did_document(
    did: str,
    public_key_multibase: str,
    recovery_keys_multibase: list[str] | None = None,
    actor_url: str | None = None,
) -> dict:
    """Build a W3C DID document with an ordered, priority-tagged key list.

    The ``verificationMethod`` list is ordered highest-priority-first: recovery
    keys (offline, ``priority >= 10``) precede the online signing key
    (``#main-key``, ``priority == 1``). P3 enforces that a key change must be
    signed by a key of ``>=`` priority; P0 ships the schema only.

    ``alsoKnownAs`` advertises where the actor doc is served. When ``actor_url``
    is given it is used verbatim (the caller passes the URL built from the
    resolved node domain, which may differ from the DID host); when ``None`` it
    falls back to the did-host-derived URL.
    """
    main_key = {
        "id": f"{did}#main-key",
        "type": "Ed25519VerificationKey2020",
        "controller": did,
        "publicKeyMultibase": public_key_multibase,
        "priority": _MAIN_KEY_PRIORITY,
    }

    recovery_methods = [
        {
            "id": f"{did}#recovery-key-{i}",
            "type": "Ed25519VerificationKey2020",
            "controller": did,
            "publicKeyMultibase": mb,
            "priority": _RECOVERY_KEY_PRIORITY_BASE + i,
        }
        for i, mb in enumerate(recovery_keys_multibase or [])
    ]
    # Highest priority first: recovery keys before the main key.
    verification_method = [*reversed(recovery_methods), main_key]

    if actor_url is None:
        host = _host_from_did(did)
        actor_url = f"https://{host}/api/v1/federation/actor"
    return {
        "@context": [
            "https://www.w3.org/ns/did/v1",
            "https://w3id.org/security/suites/ed25519-2020/v1",
        ],
        "id": did,
        "verificationMethod": verification_method,
        "authentication": [f"{did}#main-key"],
        "assertionMethod": [f"{did}#main-key"],
        "alsoKnownAs": [actor_url],
    }


def build_actor(did: str, domain: str, public_key_multibase: str) -> dict:
    """Build an ActivityStreams-style federation actor document.

    Federation data endpoints mount under ``/api/v1/federation/*`` and are
    advertised as absolute URLs. The ``inbox`` lands in P3 and the ``outbox``
    (export) in P1; advertising the forward URLs now is intentional.
    """
    base = f"https://{domain}/api/v1/federation"
    return {
        "@context": [
            "https://www.w3.org/ns/activitystreams",
            "https://w3id.org/security/v1",
        ],
        "id": f"{base}/actor",
        "type": "Service",
        "inbox": f"{base}/inbox",
        "outbox": f"{base}/export",
        "publicKey": {
            "id": f"{did}#main-key",
            "owner": did,
            "publicKeyMultibase": public_key_multibase,
        },
    }


def build_webfinger(resource: str, actor_url: str) -> dict:
    """Build a WebFinger JRD (RFC 7033) resolving an ``acct:`` handle.

    A peer queries ``/.well-known/webfinger?resource=acct:<handle>`` to
    discover the actor document URL — the discovery entry point alongside
    ``did.json``. This is a pure shape builder; query parsing and the
    ``resource``-absent 422 are HTTP concerns handled by the route (Task 0.7).
    """
    return {
        "subject": resource,
        "links": [
            {
                "rel": "self",
                "type": "application/activity+json",
                "href": actor_url,
            },
        ],
    }
