"""C2SP signed-note checkpoint for the federation log (design §6.2b).

Pure (no DB/IO). The log head is published as a **C2SP signed note** so that any
Go-ecosystem verifier/witness (sumdb ``note``, sigsum, transparency-dev tooling)
can verify our checkpoints — the format is witness-compatible from day one
(§6.2c) even though the witness mesh itself ships in P6.

Format (C2SP signed-note.md, verified against the spec text and reproduced
byte-for-byte against the Go ``sumdb/note`` reference vector in the tests):

  - The note **text** ends in a newline; the SIGNED bytes are the text
    *including* that final newline (the trailing newline is load-bearing).
  - A **blank line** (a lone newline) separates the text from the signatures;
    it is NOT part of the signed bytes.
  - Each signature line is: em-dash (U+2014), space, key name, space,
    ``base64-std( keyID[4] || ed25519_signature[64] )``, newline.
  - ``keyID`` = first 4 bytes of ``SHA-256(key_name || 0x0A || alg || pubkey)``
    with ``algEd25519 = 0x01``.

Checkpoint body (C2SP tlog-checkpoint shape; the timestamp rides as an
extension line *inside* the signed body so it is covered by the signature):

    <origin_did>\\n<tree_size>\\n<base64(root_hash)>\\nTimestamp: <rfc3339>\\n
"""

from __future__ import annotations

import base64
import hashlib
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

#: C2SP signed-note algorithm identifier for Ed25519.
ALG_ED25519 = 0x01

_EM_DASH = "—"
_SIG_PREFIX = _EM_DASH + " "
#: A canonical non-negative decimal (no leading zeros, sign, or whitespace).
_CANONICAL_DECIMAL = re.compile(r"^(0|[1-9][0-9]*)$")


def key_hash(key_name: str, public_key_raw: bytes) -> bytes:
    """C2SP key ID: first 4 bytes of SHA-256(name || 0x0A || alg || pubkey)."""
    digest = hashlib.sha256(
        key_name.encode("utf-8") + b"\n" + bytes([ALG_ED25519]) + public_key_raw
    ).digest()
    return digest[:4]


def checkpoint_body(
    origin: str, tree_size: int, root_hash: bytes, timestamp: str
) -> bytes:
    """The signed checkpoint text: origin, decimal tree size, base64-std root,
    and a ``Timestamp:`` extension line — each line newline-terminated,
    INCLUDING the last (the trailing newline is part of the signed bytes).

    Rejects an embedded newline in ``origin``/``timestamp`` (note-injection
    hardening): a multi-line field would forge extra body lines, so a
    misconfigured value must fail loudly at build time, not emit an ambiguous
    note.
    """
    if "\n" in origin or "\n" in timestamp:
        raise ValueError("checkpoint origin/timestamp must not contain a newline")
    root_b64 = base64.b64encode(root_hash).decode("ascii")
    return f"{origin}\n{tree_size}\n{root_b64}\nTimestamp: {timestamp}\n".encode()


def sign_note(text: bytes, key_name: str, signing_key: Ed25519PrivateKey) -> str:
    """Wrap ``text`` (which must end in a newline) as a full C2SP signed note."""
    if not text.endswith(b"\n"):
        raise ValueError("C2SP note text must end with a newline")
    if "\n" in key_name or " " in key_name or not key_name:
        # A signature line is "— <name> <base64>"; a name with a space/newline
        # would break the single-line grammar a Go witness parses.
        raise ValueError("C2SP signature key name must be a single token")
    public_raw = signing_key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    blob = key_hash(key_name, public_raw) + signing_key.sign(text)
    sig_line = f"{_SIG_PREFIX}{key_name} {base64.b64encode(blob).decode('ascii')}\n"
    return text.decode("utf-8") + "\n" + sig_line


def build_checkpoint(
    *,
    origin: str,
    tree_size: int,
    root_hash: bytes,
    timestamp: str,
    signing_key: Ed25519PrivateKey,
) -> str:
    """A signed checkpoint note for the log head. Key name = the origin DID."""
    body = checkpoint_body(origin, tree_size, root_hash, timestamp)
    return sign_note(body, origin, signing_key)


def _split_note(note: str) -> tuple[bytes, list[str]] | None:
    """Split a note into (signed_text_bytes, signature_lines) or None if malformed.

    Splits at the LAST blank line (Go ``note.Open`` semantics): the text may
    itself contain blank lines, and the signature block is always the final run
    of lines. Splitting at the first blank line would compute different signed
    bytes than a Go witness and break interop.
    """
    text_part, sep, sig_part = note.rpartition("\n\n")
    if not sep or not sig_part.endswith("\n"):
        return None
    # rpartition consumes the rightmost "\n\n", so a non-empty sig_part ending in
    # "\n" always yields at least one non-empty line (it can never be a lone blank
    # line) — no empty-list case to guard here.
    sig_lines = [line for line in sig_part.split("\n") if line]
    return (text_part + "\n").encode("utf-8"), sig_lines


def _is_signature_line(line: str) -> bool:
    """True iff ``line`` matches the C2SP signature grammar ``— <name> <b64>``
    with a single-token name and a base64 blob of at least the keyID (4 bytes)."""
    if not line.startswith(_SIG_PREFIX):
        return False
    rest = line[len(_SIG_PREFIX) :]
    parts = rest.split(" ")
    if len(parts) != 2 or not parts[0]:
        return False
    try:
        blob = base64.b64decode(parts[1], validate=True)
    except (ValueError, TypeError):
        return False
    return len(blob) >= 4


def verify_note(note: str, public_key: Ed25519PublicKey, key_name: str) -> bool:
    """True iff the note carries a valid signature line for ``key_name`` whose
    key ID matches ``public_key`` and whose Ed25519 signature verifies over the
    signed text (including its final newline).

    Every line in the signature section MUST be a well-formed signature line: a
    Go witness rejects a note with any malformed signature line, so silently
    skipping garbage would make our accept-set wider than Go's (split-brain risk
    in the witness mesh). Multiple well-formed lines (co-signers/witnesses) are
    allowed; only the matching ``key_name`` line need verify.
    """
    split = _split_note(note)
    if split is None:
        return False
    signed_text, sig_lines = split
    if not all(_is_signature_line(line) for line in sig_lines):
        return False
    public_raw = public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
    expected_id = key_hash(key_name, public_raw)
    wanted = f"{_SIG_PREFIX}{key_name} "
    for line in sig_lines:
        if not line.startswith(wanted):
            continue
        # base64 already validated by _is_signature_line above.
        blob = base64.b64decode(line[len(wanted) :], validate=True)
        if len(blob) != 4 + 64 or blob[:4] != expected_id:
            continue
        try:
            public_key.verify(blob[4:], signed_text)
        except InvalidSignature:
            continue
        return True
    return False


def parse_checkpoint(note: str) -> dict | None:
    """Extract (origin, tree_size, root_hash, timestamp) from a checkpoint note.

    Parsing only — callers MUST :func:`verify_note` before trusting the fields.
    Returns None if the body does not have the checkpoint shape.
    """
    split = _split_note(note)
    if split is None:
        return None
    lines = split[0].decode("utf-8").split("\n")
    # body lines: origin, tree_size, root_b64, "Timestamp: <ts>", "" (trailing)
    if len(lines) < 4 or not lines[3].startswith("Timestamp: "):
        return None
    # tree_size must be a canonical decimal (no sign/whitespace/leading zeros) so
    # the parsed size can never disagree with the C2SP byte form int() tolerates.
    if not _CANONICAL_DECIMAL.match(lines[1]):
        return None
    try:
        return {
            "origin": lines[0],
            "tree_size": int(lines[1]),
            "root_hash": base64.b64decode(lines[2], validate=True),
            "timestamp": lines[3][len("Timestamp: ") :],
        }
    except (ValueError, TypeError):
        return None
