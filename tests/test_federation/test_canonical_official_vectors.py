"""RFC 8785 (JCS) conformance against the AUTHORITATIVE upstream suite.

These vectors are the canonicalization test data published by the RFC 8785
author (Anders Rundgren): github.com/cyberphone/json-canonicalization, vendored
under ``vendor/jcs_rfc8785/`` (see that dir's README for the pinned commit). They
are an EXTERNAL anchor — unlike ``test_canonical.py``, whose expectations were
re-derived alongside the implementation and therefore share its blind spots.

The ``weird.json`` vector is the one that matters here: it has a non-BMP object
key (😂 U+1F602) that must sort by UTF-16 code units (RFC 8785 §3.2.3), not by
Unicode code point — the exact case our flattened ASCII-only test corpus never
exercised.
"""

import json
from pathlib import Path

import pytest

from app.federation.canonical import jcs_bytes

_VECTORS = Path(__file__).resolve().parent / "vendor" / "jcs_rfc8785"
_NAMES = ["arrays", "french", "structures", "unicode", "values", "weird"]


@pytest.mark.parametrize("name", _NAMES)
def test_jcs_matches_official_vector(name: str) -> None:
    """jcs_bytes(input) MUST equal the upstream canonical output, byte-for-byte."""
    obj = json.loads((_VECTORS / "input" / f"{name}.json").read_bytes().decode("utf-8"))
    expected = (_VECTORS / "output" / f"{name}.json").read_bytes()
    assert (
        jcs_bytes(obj) == expected
    ), f"JCS output diverges from RFC 8785 suite: {name}"


def test_non_bmp_key_ordering_is_utf16() -> None:
    """Direct regression lock for the UTF-16 key-ordering rule (RFC 8785 §3.2.3).

    U+1F602 (😂, UTF-16-BE lead unit 0xD83D) sorts BEFORE U+FB33 (דּ, 0xFB33),
    even though its code point is larger. A code-point sort gets this wrong.
    """
    out = jcs_bytes({"\U0001f602": 1, "דּ": 2}).decode("utf-8")
    assert out.index("\U0001f602") < out.index("דּ")
