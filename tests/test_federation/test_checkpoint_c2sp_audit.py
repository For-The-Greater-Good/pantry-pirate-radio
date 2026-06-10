"""Slice W wire-freeze: C2SP signed-note accept-set audit of ``verify_note``.

Spec: C2SP signed-note (https://c2sp.org/signed-note), raw markdown
https://raw.githubusercontent.com/C2SP/C2SP/main/signed-note.md, fetched and
diffed against ``app/federation/checkpoint.py`` (verify_note / _split_note /
_is_signature_line / _is_valid_name / _MAX_SIGNATURES) on 2026-06-10. The Go
reference (golang.org/x/mod/sumdb/note, ``note.Open``) — the format's de-facto
oracle and the anchor checkpoint.py claims to match — was diffed alongside it.

AUDIT RESULT — the accept-set already MATCHES the spec/Go on:
  * split at the LAST blank line (spec §50-52 "separated ... by the last empty
    line"; Go ``bytes.LastIndex(msg, "\\n\\n")``) — ``_split_note`` uses
    ``rpartition("\\n\\n")``.
  * the trailing newline of the text is part of the signed bytes (spec §50 "The
    note text includes the final newline"; Go ``text = msg[:split+1]``) —
    ``_split_note`` re-appends ``"\\n"`` to the text bytes.
  * signature-line grammar: em dash (U+2014), space, name, space, base64 sig
    (spec §42-45) — ``_is_signature_line`` / ``_SIG_PREFIX``.
  * name rules: non-empty, no Unicode space, no '+' (spec §54-55; Go
    ``isValidName``) — ``_is_valid_name``.
  * signature blob >= 5 bytes (4-byte keyID + >=1 sig byte) (Go
    ``len(sig) < 5``) — ``_is_signature_line`` ``len(blob) >= 5``.
  * <= 100 signatures (spec §62-65 MUST accept >= 16; Go caps at 100) —
    ``_MAX_SIGNATURES = 100``, which satisfies the MUST.
  * EVERY signature-block line must be well-formed; a malformed line rejects the
    WHOLE note (Go ``Open`` returns ``errMalformedNote`` on the first non-
    conforming line, it does not skip) — ``verify_note`` ``all(_is_signature_line
    ...)``.
  * unknown-key signatures are tolerated, only the matching key must verify (spec
    §72-77 "MUST ignore signatures from unknown keys") — ``verify_note`` continues
    past non-matching lines.

AUDIT RESULT — ONE divergence found (a FAILING test below pins the fix):
  * C2SP §47-48: "Signed notes MUST be valid UTF-8 and MUST NOT contain any ASCII
    control characters (those below U+0020) other than newline." Go ``Open`` scans
    the WHOLE message and returns ``errMalformedNote`` on any rune ``< 0x20``
    except ``\\n`` (or invalid UTF-8). ``checkpoint.py`` performs NO such scan, so
    ``verify_note`` ACCEPTS a note whose text contains a TAB / CR / NUL that a Go
    witness rejects as malformed — a real accept-set divergence (split-brain risk
    in the witness mesh, directly contradicting checkpoint.py's own docstring
    "Keeps our accept-set == a Go witness's").
"""

from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.federation import checkpoint as cp

_SEED = bytes(range(32))
_NAME = "did:web:node.example"
#: checkpoint.py's signature-line prefix (em-dash U+2014 + space). Imported by name
#: so the keyID-skip evidence test builds lines through the same grammar.
_SIG_PREFIX = cp._SIG_PREFIX


def _key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.from_private_bytes(_SEED)


def _signed_note(text_bytes: bytes) -> str:
    """Build a fully valid C2SP signed note over ``text_bytes`` (which must end in a
    newline) using checkpoint.py's own signer — the only thing we vary is the
    presence of a forbidden control character in the text."""
    return cp.sign_note(text_bytes, _NAME, _key())


# --- the DIVERGENCE: forbidden ASCII control chars in the note text -------------
@pytest.mark.parametrize(
    "ctrl,label",
    [
        (b"\t", "TAB U+0009"),
        (b"\r", "CR U+000D"),
        (b"\x00", "NUL U+0000"),
        (b"\x1f", "US U+001F"),
    ],
)
def test_verify_note_rejects_forbidden_ascii_control_chars(
    ctrl: bytes, label: str
) -> None:
    """C2SP §47-48 / Go note.Open: a note containing any ASCII control character
    below U+0020 other than newline is MALFORMED and MUST be rejected. checkpoint.py
    currently accepts it (no control-char scan) — this FAILING test pins the spec
    behavior, to be fixed in green by adding the validity scan to verify_note /
    _split_note.

    The note is otherwise perfectly valid: real em-dash signature line, real
    Ed25519 signature over the (control-char-bearing) text, correct keyID. Only the
    forbidden control byte in the text distinguishes it — exactly the byte a Go
    witness would reject and our verifier must too."""
    text = b"checkpoint" + ctrl + b"body\n"
    note = _signed_note(text)
    # Sanity: the signature itself is valid over these bytes (so a green fix must
    # reject on the control-char rule, not because the signature fails).
    assert note.startswith("checkpoint")
    assert cp.verify_note(note, _key().public_key(), _NAME) is False, (
        f"verify_note accepted a note with a forbidden control char ({label}); "
        f"C2SP §47-48 and Go note.Open reject it as malformed (accept-set drift)."
    )


# --- audit-record assertions for the MATCHING properties (passing evidence) -----
def test_audit_split_at_last_blank_line() -> None:
    """A note whose TEXT itself contains a blank line must split at the LAST blank
    line, so the signature over the full text (incl. the internal blank line)
    verifies (spec §50-52; Go LastIndex)."""
    text = b"line one\n\nline three\n"  # an internal blank line in the text
    note = _signed_note(text)
    assert cp.verify_note(note, _key().public_key(), _NAME) is True


def test_audit_max_100_signatures_satisfies_must_accept_16() -> None:
    """Spec §62-65: verifiers MUST accept at least 16 signatures; checkpoint.py's
    cap of 100 satisfies the MUST. (>16 lines below the cap stay parseable.)"""
    assert cp._MAX_SIGNATURES == 100
    assert cp._MAX_SIGNATURES >= 16


def test_audit_malformed_signature_line_rejects_whole_note() -> None:
    """Go note.Open returns errMalformedNote on the FIRST non-conforming signature
    line (it does not skip); checkpoint.py rejects the whole note on any malformed
    line. Appending a garbage line to a valid note must flip verify to False."""
    note = _signed_note(b"checkpoint body\n")
    assert cp.verify_note(note, _key().public_key(), _NAME) is True  # baseline
    poisoned = note + "this-is-not-a-signature-line\n"
    assert cp.verify_note(poisoned, _key().public_key(), _NAME) is False


def test_audit_name_rules_no_space_no_plus() -> None:
    """Names are non-empty, whitespace-free, '+'-free (spec §54-55; Go isValidName)."""
    assert cp._is_valid_name("did:web:node.example") is True
    assert cp._is_valid_name("") is False
    assert cp._is_valid_name("has space") is False
    assert cp._is_valid_name("has+plus") is False


def test_audit_keyid_mismatch_signature_is_skipped() -> None:
    """C2SP: "Verifiers MUST ignore signatures from unknown keys, even if they
    share a name or ID with a known key." A second signature line that carries our
    OWN key_name but a WRONG keyID (first 4 bytes != SHA-256(name||0x0A||alg||pub))
    must be SKIPPED, not trusted; the genuine matching-keyID line still verifies, so
    the note as a whole stays valid. checkpoint.py skips on ``blob[:4] != expected_id``
    — this exercises that accept-set property (evidence for the wire-freeze audit)."""
    note = _signed_note(b"checkpoint body\n")
    assert cp.verify_note(note, _key().public_key(), _NAME) is True  # baseline
    # A same-name line with a deliberately wrong keyID + 64 junk signature bytes
    # (well-formed grammar: >=5-byte blob, valid base64, valid name) — spliced into
    # the signature block AHEAD of the genuine line.
    wrong_blob = base64.b64encode(b"\xff\xff\xff\xff" + b"\x00" * 64).decode("ascii")
    text_part, _, sig_part = note.rpartition("\n\n")
    spliced = f"{text_part}\n\n{_SIG_PREFIX}{_NAME} {wrong_blob}\n{sig_part}"
    # The wrong-keyID line is skipped; the genuine line behind it still verifies.
    assert cp.verify_note(spliced, _key().public_key(), _NAME) is True
    # With ONLY the wrong-keyID line (genuine removed), nothing verifies.
    only_wrong = f"{text_part}\n\n{_SIG_PREFIX}{_NAME} {wrong_blob}\n"
    assert cp.verify_note(only_wrong, _key().public_key(), _NAME) is False
