"""Task 2b (PR-B): C2SP signed-note checkpoint (design §6.2b).

External anchors (NOT self-derived — the operator's conformance mandate):
  - The C2SP signed-note spec (github.com/C2SP/C2SP/blob/main/signed-note.md):
    text ending in newline, then a BLANK line, then signature lines of the form
    em-dash (U+2014), space, key name, space, base64(keyID[4] || signature[64]),
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


# --- RED-tier Gauntlet CHECKPOINT findings: keep our accept-set == a Go
# witness's. A wider accept-set causes split-brain in the P6 witness mesh and is
# hard to retrofit once peers exist.


def test_verify_note_rejects_garbage_line_in_signature_section() -> None:
    """A note with a valid signature for our key BUT a non-signature line in the
    signature section must be rejected (Go note.Open rejects malformed lines; we
    must not silently skip them)."""
    assert checkpoint.verify_note(_GO_NOTE, _go_public_key(), "PeterNeumann") is True
    # Splice a garbage line into the signature section.
    polluted = _GO_NOTE[:-1] + "\nGARBAGE NOT A SIG LINE\n"
    assert checkpoint.verify_note(polluted, _go_public_key(), "PeterNeumann") is False


def test_sign_note_rejects_multi_token_or_empty_key_name() -> None:
    """A C2SP signature line is '— <name> <b64>'; the key name must be a single
    non-empty token (no space/newline), else the grammar breaks."""
    import pytest

    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    for bad_name in ("two words", "", "has\nnewline"):
        with pytest.raises(ValueError):
            checkpoint.sign_note(b"text\n", bad_name, key)


def test_verify_note_rejects_emdash_line_with_bad_grammar() -> None:
    """A line that starts with the em-dash prefix but is NOT a well-formed
    signature line (wrong token count / empty name) makes the whole note invalid
    (matches Go note.Open strictness)."""
    pub = _go_public_key()
    valid_sig = _GO_NOTE.split("\n\n", 1)[1].rstrip("\n")
    text = _GO_TEXT.decode()
    # An em-dash line with only one token (no base64) in the signature section.
    one_token = f"{text}\n{valid_sig}\n— justonetoken\n"
    assert checkpoint.verify_note(one_token, pub, "PeterNeumann") is False
    # An em-dash line with an empty name ('—  <b64>' -> empty first token).
    empty_name = f"{text}\n{valid_sig}\n—  AAAAAAAA\n"
    assert checkpoint.verify_note(empty_name, pub, "PeterNeumann") is False


def _genuine_note_and_key():
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    note = checkpoint.build_checkpoint(
        origin="did:web:example.org",
        tree_size=1,
        root_hash=merkle.merkle_root([b"leaf-0"]),
        timestamp="2026-06-06T00:00:00Z",
        signing_key=key,
    )
    return note, key


def test_verify_note_rejects_four_byte_blob_witness_line() -> None:
    """Go note.Open requires a signature blob >=5 bytes (keyID4 + >=1 sig byte).
    A co-signed note with a 4-byte-blob line must be rejected (accept-set == Go)."""
    note, key = _genuine_note_and_key()
    four_byte = base64.b64encode(b"\x00\x00\x00\x00").decode("ascii")  # keyID only
    polluted = note + f"— witness.example {four_byte}\n"
    assert (
        checkpoint.verify_note(polluted, key.public_key(), "did:web:example.org")
        is False
    )


def test_verify_note_rejects_witness_name_with_whitespace_or_plus() -> None:
    """Go isValidName forbids Unicode whitespace and '+' in a key name."""
    note, key = _genuine_note_and_key()
    blob = base64.b64encode(b"\x01" * 68).decode("ascii")  # >=5 bytes, valid b64
    for bad_name in ("wit\tness", "wit+ness"):
        polluted = note + f"— {bad_name} {blob}\n"
        assert (
            checkpoint.verify_note(polluted, key.public_key(), "did:web:example.org")
            is False
        ), f"accepted Go-invalid witness name {bad_name!r}"


def test_verify_note_rejects_excess_signature_count() -> None:
    """Go note.Open caps the signature count; >100 lines is rejected."""
    note, key = _genuine_note_and_key()
    blob = base64.b64encode(b"\x02" * 68).decode("ascii")
    extra = "".join(f"— wit{i} {blob}\n" for i in range(101))
    assert (
        checkpoint.verify_note(note + extra, key.public_key(), "did:web:example.org")
        is False
    )


def test_verify_note_accepts_multi_witness_note() -> None:
    """Multiple WELL-FORMED signature lines (different keys) are legal — only our
    matching line need verify. Guards that the strict-grammar fix does not break
    co-signed/witnessed notes."""
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    note = checkpoint.build_checkpoint(
        origin="did:web:example.org",
        tree_size=1,
        root_hash=merkle.merkle_root([b"leaf-0"]),
        timestamp="2026-06-06T00:00:00Z",
        signing_key=key,
    )
    # Append a second, well-formed witness signature line (different key/name).
    witness = Ed25519PrivateKey.from_private_bytes(bytes([9]) * 32)
    body = checkpoint.checkpoint_body(
        "did:web:example.org",
        1,
        merkle.merkle_root([b"leaf-0"]),
        "2026-06-06T00:00:00Z",
    )
    witness_note = checkpoint.sign_note(body, "did:web:witness.example", witness)
    witness_sig_line = witness_note.split("\n\n", 1)[1]
    co_signed = note + witness_sig_line
    assert (
        checkpoint.verify_note(co_signed, key.public_key(), "did:web:example.org")
        is True
    )


def test_verify_note_handles_text_with_internal_blank_line() -> None:
    """The signed text may itself contain a blank line; the note must split at the
    LAST blank line (Go note.Open semantics), not the first."""
    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    body = b"paragraph one\n\nparagraph two\n"  # internal blank line in the text
    note = checkpoint.sign_note(body, "did:web:example.org", key)
    assert checkpoint.verify_note(note, key.public_key(), "did:web:example.org") is True


def test_parse_checkpoint_rejects_non_canonical_tree_size() -> None:
    """parse_checkpoint must report only a canonical decimal tree_size; the
    lenient int() form ('+3', ' 3', '03', '-1') could disagree with the C2SP
    byte form even before verification."""
    root_b64 = base64.b64encode(bytes(range(32))).decode("ascii")
    for bad in (" 3", "03", "+3", "-1"):
        note = (
            f"did:web:example.org\n{bad}\n{root_b64}\n"
            f"Timestamp: 2026-06-06T00:00:00Z\n"
            f"\n— did:web:example.org AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
        )
        assert checkpoint.parse_checkpoint(note) is None, f"accepted {bad!r}"
    # The canonical form still parses.
    good = (
        f"did:web:example.org\n3\n{root_b64}\nTimestamp: 2026-06-06T00:00:00Z\n"
        f"\n— did:web:example.org AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=\n"
    )
    assert checkpoint.parse_checkpoint(good)["tree_size"] == 3


def test_build_checkpoint_rejects_newline_in_fields() -> None:
    """Note injection hardening: a newline in origin/timestamp/key_name must fail
    loudly at build time, never silently emit an ambiguous multi-line note."""
    import pytest

    key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    root = merkle.merkle_root([b"leaf-0"])
    with pytest.raises(ValueError):
        checkpoint.build_checkpoint(
            origin="did:web:evil\n2\nFAKEROOT",
            tree_size=1,
            root_hash=root,
            timestamp="2026-06-06T00:00:00Z",
            signing_key=key,
        )
    with pytest.raises(ValueError):
        checkpoint.build_checkpoint(
            origin="did:web:example.org",
            tree_size=1,
            root_hash=root,
            timestamp="2026-06-06T00:00:00Z\ninjected",
            signing_key=key,
        )
