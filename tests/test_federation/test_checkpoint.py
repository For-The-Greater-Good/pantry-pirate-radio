"""Task 2b (PR-B): C2SP signed-note checkpoint (design §6.2b).

External anchors (NOT self-derived — the operator's conformance mandate):
  - The C2SP signed-note spec (github.com/C2SP/C2SP/blob/main/signed-note.md):
    text ending in newline, then a BLANK line, then signature lines of the form
    em-dash (U+2014), space, key name, space, base64(keyID32 || signature),
    newline. The signed bytes are the text INCLUDING its final newline but NOT
    the blank line. keyID = first 4 bytes of SHA-256(name || 0x0A || alg ||
    pubkey); algEd25519 = 1.
  - The Go reference vector from golang.org/x/mod/sumdb/note note_test.go
    (the PeterNeumann keypair + published signature). Ed25519 is deterministic
    (RFC 8032), so our sign_note MUST reproduce the published Go note
    byte-for-byte — if it does, any Go-ecosystem witness/verifier accepts our
    checkpoints.
"""

import base64

from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.federation import checkpoint, merkle

# --- golang.org/x/mod/sumdb/note note_test.go reference vector ---------------
_GO_VERIFIER_KEY = "PeterNeumann+c74f20a3+ARpc2QcUPDhMQegwxbzhKqiBfsVkmqq/LDE4izWy10TW"
_GO_SIGNER_KEY = (
    "PRIVATE+KEY+PeterNeumann+c74f20a3+AYEKFALVFGyNhPJEMzD1QIDr+Y7hfZx09iUvxdXHKDFz"
)
_GO_TEXT = (
    b"If you think cryptography is the answer to your problem,\n"
    b"then you don't know what your problem is.\n"
)
_GO_SIG_BLOB = "x08go/ZJkuBS9UG/SffcvIAQxVBtiFupLLr8pAcElZInNIuGUgYN1FFYC2pZSNXgKvqfqdngotpRZb6KE6RyyBwJnAM="
_GO_NOTE = _GO_TEXT.decode() + "\n" + "— PeterNeumann " + _GO_SIG_BLOB + "\n"


def _go_public_key_raw() -> bytes:
    # maxsplit: the base64 key material may itself contain '+' characters.
    decoded = base64.b64decode(_GO_VERIFIER_KEY.split("+", 2)[2])
    assert decoded[0] == 1  # algEd25519
    return decoded[1:]


def _go_public_key() -> Ed25519PublicKey:
    return Ed25519PublicKey.from_public_bytes(_go_public_key_raw())


def _go_signing_key() -> Ed25519PrivateKey:
    # maxsplit: this key's base64 portion contains an embedded '+'.
    decoded = base64.b64decode(_GO_SIGNER_KEY.split("+", 4)[4])
    assert decoded[0] == 1  # algEd25519
    return Ed25519PrivateKey.from_private_bytes(decoded[1:])


def test_go_vector_keypair_is_internally_consistent() -> None:
    """Transcription guard: the vendored signer seed must derive the vendored
    verifier pubkey (catches any copy error in the vector strings)."""
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    derived = (
        _go_signing_key().public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    )
    assert derived == _go_public_key_raw()


def test_key_hash_matches_go_reference() -> None:
    """keyID = SHA-256(name || 0x0A || 0x01 || pubkey)[:4] — must equal the
    c74f20a3 embedded in the published Go key strings."""
    assert checkpoint.key_hash("PeterNeumann", _go_public_key_raw()) == bytes.fromhex(
        "c74f20a3"
    )


def test_sign_note_reproduces_go_reference_byte_for_byte() -> None:
    """THE external KAT: deterministic Ed25519 + exact C2SP assembly means our
    sign_note over the reference text with the reference key must equal the
    published Go note exactly (em-dash, blank line, blob, trailing newline)."""
    ours = checkpoint.sign_note(_GO_TEXT, "PeterNeumann", _go_signing_key())
    assert ours == _GO_NOTE


def test_verify_accepts_go_reference_note() -> None:
    assert checkpoint.verify_note(_GO_NOTE, _go_public_key(), "PeterNeumann") is True


def test_verify_rejects_tampered_text_and_wrong_name() -> None:
    tampered = _GO_NOTE.replace("cryptography", "cryptozoology")
    assert checkpoint.verify_note(tampered, _go_public_key(), "PeterNeumann") is False
    assert checkpoint.verify_note(_GO_NOTE, _go_public_key(), "MalloryNeumann") is False


def test_verify_rejects_ascii_hyphen_signature_line() -> None:
    """The em-dash U+2014 is load-bearing (C2SP); an ASCII hyphen is not a
    signature line and the note must not verify."""
    hyphenated = _GO_NOTE.replace("— ", "- ")
    assert checkpoint.verify_note(hyphenated, _go_public_key(), "PeterNeumann") is False


# --- the checkpoint body (C2SP tlog-checkpoint shape, pinned) -----------------


def test_checkpoint_body_pinned_format() -> None:
    """origin \\n tree_size \\n base64(root) \\n 'Timestamp: <rfc3339>' \\n —
    the trailing newline is part of the SIGNED bytes (load-bearing)."""
    root = bytes(range(32))
    body = checkpoint.checkpoint_body(
        "did:web:example.com", 2, root, "2026-06-06T00:00:00Z"
    )
    expected = (
        b"did:web:example.com\n2\n"
        + base64.b64encode(root)
        + b"\nTimestamp: 2026-06-06T00:00:00Z\n"
    )
    assert body == expected
    assert body.endswith(b"\n")


def test_build_checkpoint_roundtrip_and_parse() -> None:
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    root = merkle.merkle_root([b"leaf-0", b"leaf-1", b"leaf-2"])
    note = checkpoint.build_checkpoint(
        origin="did:web:example.org",
        tree_size=3,
        root_hash=root,
        timestamp="2026-06-06T00:00:00Z",
        signing_key=key,
    )
    assert checkpoint.verify_note(note, key.public_key(), "did:web:example.org") is True
    parsed = checkpoint.parse_checkpoint(note)
    assert parsed == {
        "origin": "did:web:example.org",
        "tree_size": 3,
        "root_hash": root,
        "timestamp": "2026-06-06T00:00:00Z",
    }


def test_build_checkpoint_tamper_rejected() -> None:
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    root = merkle.merkle_root([b"leaf-0", b"leaf-1"])
    note = checkpoint.build_checkpoint(
        origin="did:web:example.org",
        tree_size=2,
        root_hash=root,
        timestamp="2026-06-06T00:00:00Z",
        signing_key=key,
    )
    # forge a bigger tree (truncation/extension lie) — signature must fail
    forged = note.replace("\n2\n", "\n3\n")
    assert (
        checkpoint.verify_note(forged, key.public_key(), "did:web:example.org") is False
    )
    # wrong key entirely
    other = Ed25519PrivateKey.from_private_bytes(bytes([7]) * 32)
    assert (
        checkpoint.verify_note(note, other.public_key(), "did:web:example.org") is False
    )


def test_verify_rejects_malformed_notes() -> None:
    pub = _go_public_key()
    assert checkpoint.verify_note("", pub, "PeterNeumann") is False
    assert checkpoint.verify_note("no blank line\n— x y\n", pub, "x") is False
    assert checkpoint.verify_note("text\n\n", pub, "PeterNeumann") is False
    assert (
        checkpoint.verify_note(
            "text\n\n— PeterNeumann notbase64!!\n", pub, "PeterNeumann"
        )
        is False
    )
