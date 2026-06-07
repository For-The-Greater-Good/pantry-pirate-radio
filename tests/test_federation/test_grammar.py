"""HSDS-FX ``federation_id`` grammar — reference normalizer (design §135, Slice 4).

The normalized ``federation_id`` is the §137 inbound exact-lookup PRIMARY KEY
(``source_type='federated_node'``), so ``normalize_federation_id`` MUST be
deterministic, idempotent, and COLLISION-SAFE: two spellings of the same logical id
collapse to identical bytes, and two genuinely-different ids never merge. These
tests pin the behavior table the design workflow synthesized from design §135 +
RFC 3986, and prove the two properties that make it usable as a key.

Grammar reading is PPR-native and pinned by fiat (interop_pending, vendor/
INTEROP_PENDING.md row 7) — only a second independent implementation (the P2
two-node loop) finally settles it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app.federation.grammar import normalize_federation_id, normalize_uri_component

_VENDOR = Path(__file__).resolve().parent / "vendor"

# --- accept vectors: input -> canonical output ---------------------------------
ACCEPT = [
    # host ASCII-lowercased (§135 "host lowercasing" / RFC 3986 §6.2.2.1)
    ("Example.ORG:abc-123", "example.org:abc-123"),
    # single trailing FQDN-root dot stripped (§135 / RFC 4343)
    ("example.org.:abc-123", "example.org:abc-123"),
    # the §8.1 worked wire example — already canonical (identity)
    ("northjerseyfoodbank.org:abc-123", "northjerseyfoodbank.org:abc-123"),
    # %XX of an unreserved octet is DECODED (§6.2.2.2): %2D -> '-', %41 -> 'A'
    ("example.org:abc%2D123", "example.org:abc-123"),
    ("example.org:%41BC", "example.org:ABC"),
    # %XX of a RESERVED octet is KEPT, hex UPPERCASED (§6.2.2.1): %3a -> %3A
    ("example.org:abc%3adef", "example.org:abc%3Adef"),
    ("example.org:abc%2fdef", "example.org:abc%2Fdef"),
    # a properly percent-encoded UTF-8 (non-ASCII) internal-id octet stays encoded
    ("example.org:caf%c3%a9", "example.org:caf%C3%A9"),
    # a pre-encoded xn-- A-label host is an opaque ASCII reg-name (v1: no IDNA decode)
    ("xn--mnchen-3ya.example:loc-1", "xn--mnchen-3ya.example:loc-1"),
    # the casefold-collision probe: STRASSE lowercases normally (straße is rejected
    # as non-ASCII), so the two NEVER converge — str.lower(), not str.casefold()
    ("STRASSE.example.org:x", "strasse.example.org:x"),
    # backward-compat: a real uuid4 internal-id is pure-unreserved -> identity
    (
        "example.org:550e8400-e29b-41d4-a716-446655440000",
        "example.org:550e8400-e29b-41d4-a716-446655440000",
    ),
]

# --- reject vectors: malformed -> ValueError -----------------------------------
REJECT = [
    "x",  # no delimiter colon (§135 requires host ':' internal-id)
    "<dead>",  # no colon AND non-reg-name chars (tombstone prose sentinel)
    ":abc-123",  # empty <publisher-host>
    "example.org:",  # empty <internal-id> (production is 1*(...))
    "example.org:abc%2g3",  # malformed percent-escape ('g' not hex)
    "example.org:%4",  # truncated percent-escape
    "example.org:trailing%",  # bare trailing percent
    "münchen.example:loc-1",  # non-ASCII (U-label) host — v1 requires xn-- A-labels
    "ex%41mple.org:x",  # percent in HOST — host is LDH+dot only, not pct-encoded
    "example.org:loc:666",  # raw embedded ':' in internal-id (must be %3A) — strict
    "did:web:example.org:abc-123",  # full DID pasted: internal-id has raw ':'
    "example.org:a/b",  # raw reserved '/' in internal-id (must be %2F) — strict
    "  example.org:x  ",  # surrounding whitespace — not trimmed (would collide x/ x)
    "exa mple.org:x",  # space in host
    ".:abc-123",  # host is only a dot -> empty after trailing-dot strip
    "a..b.example:x",  # empty DNS label between dots
    ".example.org:x",  # leading empty DNS label
]


@pytest.mark.parametrize("bad", [123, None, ["example.org:x"], b"example.org:x"])
def test_non_string_input_raises(bad):
    """Defensive API contract: a non-str id has no canonical form -> ValueError."""
    with pytest.raises(ValueError):
        normalize_federation_id(bad)  # type: ignore[arg-type]


@pytest.mark.parametrize("raw,expected", ACCEPT)
def test_accept_canonicalizes(raw, expected):
    assert normalize_federation_id(raw) == expected


@pytest.mark.parametrize("raw", REJECT)
def test_reject_raises(raw):
    with pytest.raises(ValueError):
        normalize_federation_id(raw)


def test_idempotent_on_every_accept_output():
    """normalize(normalize(x)) == normalize(x) — required of a stable primary key."""
    for raw, expected in ACCEPT:
        once = normalize_federation_id(raw)
        assert once == expected
        assert normalize_federation_id(once) == once


def test_lower_not_casefold_no_peer_shadow_collision():
    """str.lower() (NOT casefold): casefold('straße')=='strasse' would collapse a
    non-ASCII host into a DISTINCT ASCII host, a §137 PK collision letting one
    publisher shadow another. straße is rejected (non-ASCII); STRASSE normalizes to
    its own distinct host — the two can never become the same key."""
    assert normalize_federation_id("STRASSE.example.org:x") == "strasse.example.org:x"
    with pytest.raises(ValueError):
        normalize_federation_id("straße.example.org:x")


def test_distinct_ids_never_collide():
    """Decode-unreserved only collapses spellings of the SAME octet; a real reserved
    char stays %XX-encoded, so an encoded colon never merges with a raw delimiter."""
    a = normalize_federation_id("example.org:abc%3Adef")  # id 'abc:def' (colon encoded)
    b = normalize_federation_id("example.org:abcXdef")  # a different literal id
    c = normalize_federation_id("example.org:abc-def")  # and another
    assert a != b != c and a != c
    # the encoded-colon id keeps %3A — it never decodes to a raw delimiter
    assert a == "example.org:abc%3Adef"


def test_identity_on_all_current_repo_values():
    """Every federation_id the repo emits today is already canonical (lowercase host
    + pure-unreserved internal-id), so normalize is the IDENTITY — it cannot alter an
    already-signed envelope id / Merkle leaf (build_preimage stays a verbatim
    pass-through; the normalizer is a separate reference function)."""
    current = [
        "example.org:abc-123",
        "example.org:loc-1",
        "node.example:loc-0",
        "pantry.example.org:loc-666",
        "northjerseyfoodbank.org:abc-123",
        "example.org:w0-5",
    ]
    for fid in current:
        assert normalize_federation_id(fid) == fid


# --- property: idempotency + acceptance over the generated valid grammar --------
_LDH_LABEL = st.from_regex(r"[a-z0-9]([a-z0-9-]{0,20}[a-z0-9])?", fullmatch=True)
_HOSTS = st.lists(_LDH_LABEL, min_size=1, max_size=4).map(lambda ls: ".".join(ls))
_UNRESERVED_ID = st.from_regex(r"[A-Za-z0-9._~-]{1,40}", fullmatch=True)


@given(host=_HOSTS, internal=_UNRESERVED_ID)
def test_property_canonical_input_is_identity_and_idempotent(host, internal):
    """A well-formed all-canonical federation_id round-trips unchanged, and a second
    pass is a no-op (the headline idempotency property over the accept grammar)."""
    fid = f"{host}:{internal}"
    once = normalize_federation_id(fid)
    assert once == fid  # already canonical -> identity
    assert normalize_federation_id(once) == once  # idempotent


@given(
    host=_HOSTS,
    body=st.text(alphabet="ABCDEFabcdef0123456789-._~", min_size=1, max_size=12),
)
def test_property_hex_case_and_idempotency(host, body):
    """Uppercasing percent-encoded hex is idempotent and never changes which octet is
    encoded — normalize twice == normalize once for any unreserved-bodied id."""
    fid = f"{host}:{body}"
    once = normalize_federation_id(fid)
    assert normalize_federation_id(once) == once
    # output contains no lowercase hex inside a percent-escape
    assert not re.search(r"%[0-9a-f]", once.split(":", 1)[1])


# --- normalize_uri_component: the RFC 3986 §6.2.2 primitive ---------------------
URI_NORM = [
    ("%7Esmith", "~smith"),  # RFC §6.2.2.2 verbatim example (decode unreserved)
    ("%3a", "%3A"),  # RFC §6.2.2.1 verbatim example (uppercase hex, ':' reserved)
    ("%7E", "~"),
    ("%41%42%43", "ABC"),  # decode unreserved ALPHA
    ("%2f", "%2F"),  # reserved '/' kept, hex uppercased
    ("%c3%a9", "%C3%A9"),  # non-ASCII octet kept, hex uppercased
    ("raw:colon/slash", "raw:colon/slash"),  # lenient: raw reserved kept verbatim
    ("%zz", "%zz"),  # lenient: malformed % kept verbatim (no raise)
    ("%4", "%4"),  # lenient: truncated % kept verbatim
    ("plain-text_~.", "plain-text_~."),  # all-unreserved/raw: identity
]


@pytest.mark.parametrize("raw,expected", URI_NORM)
def test_normalize_uri_component(raw, expected):
    assert normalize_uri_component(raw) == expected


@pytest.mark.parametrize("raw,expected", URI_NORM)
def test_normalize_uri_component_idempotent(raw, expected):
    once = normalize_uri_component(raw)
    assert once == expected
    assert normalize_uri_component(once) == once


@given(s=st.text(alphabet="ABCDEFabcdef0123456789%~-._:/ ", min_size=0, max_size=24))
def test_normalize_uri_component_total_and_idempotent(s):
    """Total over arbitrary input (never raises) and idempotent."""
    once = normalize_uri_component(s)
    assert normalize_uri_component(once) == once


def test_normalize_uri_component_matches_vendored_rfc3986_examples():
    """The EXTERNAL ANCHOR: normalize_uri_component reproduces every RFC 3986 §6.2.2
    worked example / rule-application in the vendored suite byte-for-byte. This is
    what converts federation_id's percent/case MECHANIC from self-derived to
    RFC-anchored (registry: vendored:rfc3986_normalization). The federation_id
    COMPOSITION (host:internal-id, reject-raw-reserved) stays interop_pending."""
    suite = json.loads(
        (_VENDOR / "rfc3986_normalization" / "vectors.json").read_text(encoding="utf-8")
    )
    examples = suite["examples"]
    assert examples, "vendored rfc3986_normalization suite is empty"
    assert any(
        ex["kind"] == "rfc-example" for ex in examples
    ), "the anchor needs at least one verbatim RFC worked example"
    for ex in examples:
        assert normalize_uri_component(ex["input"]) == ex["output"], (
            f"normalize_uri_component diverges from RFC 3986 example {ex['input']!r} "
            f"({ex['source']})"
        )
