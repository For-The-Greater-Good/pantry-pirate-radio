"""Hypothesis property tests for the RFC 8785 (JCS) canonicalizer.

These pin the invariants the content-address and ``proof`` substrate depends on
(design of record §P0.4): the canonical bytes are independent of dict insertion
order, deterministic across calls, valid UTF-8, and parse back to a value equal
to the input. Float-format spot pins reaffirm the official ECMAScript vectors.

NOTE: the JSON-safe strategy below excludes Unicode surrogates (category ``Cs``).
A lone surrogate is not a valid UTF-8-encodable string and is therefore outside
the set of JSON-serializable inputs JCS is defined over (``jcs_bytes`` correctly
raises ``UnicodeEncodeError`` on such input). Restricting the strategy keeps the
properties scoped to genuinely JSON-safe values.
"""

import json
import math

from hypothesis import given, settings
from hypothesis import strategies as st

import pytest

from app.federation.canonical import jcs_bytes

# Surrogate-free text: the JSON-safe string domain JCS is defined over.
_json_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",)),
    max_size=24,
)

# Recursive JSON-like values: str keys -> str / int / bool / None / list / dict.
_scalars = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(min_value=-(10**12), max_value=10**12),
    _json_text,
)
_json_values = st.recursive(
    _scalars,
    lambda children: st.one_of(
        st.lists(children, max_size=4),
        st.dictionaries(_json_text, children, max_size=4),
    ),
    max_leaves=12,
)
_json_dicts = st.dictionaries(_json_text, _json_values, max_size=6)


def _shuffle_dict_order(d, ordering):
    """Return a dict with the same items but a permuted insertion order."""
    keys = list(d.keys())
    if not keys:
        return dict(d)
    perm = ordering % math.factorial(len(keys)) if len(keys) <= 7 else ordering
    # Simple rotation-based reordering is enough to exercise insertion order:
    rotated = keys[perm % len(keys):] + keys[: perm % len(keys)]
    return {k: d[k] for k in rotated}


@settings(max_examples=300)
@given(obj=_json_dicts, ordering=st.integers(min_value=0, max_value=5039))
def test_canonical_bytes_are_independent_of_key_insertion_order(obj, ordering):
    """Permuting a dict's insertion order does not change its canonical bytes."""
    reordered = _shuffle_dict_order(obj, ordering)
    assert jcs_bytes(reordered) == jcs_bytes(obj)


@settings(max_examples=300)
@given(obj=_json_values)
def test_canonical_bytes_are_deterministic(obj):
    """``jcs_bytes`` is a pure function: same input, byte-identical output."""
    first = jcs_bytes(obj)
    assert first == jcs_bytes(obj)
    assert first == jcs_bytes(obj)


@settings(max_examples=300)
@given(obj=_json_values)
def test_canonical_output_is_valid_utf8_and_round_trips(obj):
    """Output decodes as UTF-8 and ``json.loads`` recovers the input value."""
    raw = jcs_bytes(obj)
    text = raw.decode("utf-8")  # must be valid UTF-8
    parsed = json.loads(text)  # must be parseable JSON
    assert parsed == obj  # value equality (ints/strs/bools/None compare exactly)


@settings(max_examples=200)
@given(x=st.floats(allow_nan=False, allow_infinity=False, min_value=-1e15, max_value=1e15))
def test_finite_floats_round_trip_by_value(x):
    """A finite float canonicalizes to a token that parses back to the same value."""
    raw = jcs_bytes({"n": x})
    parsed = json.loads(raw.decode("utf-8"))
    assert parsed["n"] == x


@pytest.mark.parametrize(
    "value, token",
    [
        (0.0, "0"),
        (-0.0, "0"),
        (1.0, "1"),
        (4.50, "4.5"),
        (0.002, "0.002"),
        (1e30, "1e+30"),
        (1e-7, "1e-7"),
        (1e21, "1e+21"),
        (1e20, "100000000000000000000"),
        (333333333.33333329, "333333333.3333333"),
        (1e-27, "1e-27"),
    ],
)
def test_float_format_reaffirms_official_vectors(value, token):
    """Spot pins on the ECMAScript Number.prototype.toString vectors (RFC 8785)."""
    assert jcs_bytes({"n": value}) == ('{"n":' + token + "}").encode("utf-8")
