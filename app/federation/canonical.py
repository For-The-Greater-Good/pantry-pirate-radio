"""RFC 8785 JSON Canonicalization Scheme (JCS).

A minimal, correct JCS serializer used as the cryptographic substrate for HSDS
federation: in P1 the same ``jcs_bytes`` canonicalizes the full activity envelope
(including HSDS Location float coordinates) for the content-address
``id = sha256(jcs_bytes(envelope))`` and the Ed25519 ``proof``. It therefore takes
any JSON-serializable ``dict`` / ``list`` / scalar and returns canonical UTF-8 bytes
with no envelope-specific assumptions.

Number formatting follows the ECMAScript ``Number.prototype.toString()`` algorithm
(RFC 8785 §3.2.2.3); string escaping follows §3.2.2.2.
"""

from typing import Any

# Control characters with JSON short-form escapes (RFC 8785 §3.2.2.2).
_SHORT_ESCAPES = {
    0x08: "\\b",
    0x09: "\\t",
    0x0A: "\\n",
    0x0C: "\\f",
    0x0D: "\\r",
    0x22: '\\"',
    0x5C: "\\\\",
}


def jcs_bytes(obj: Any) -> bytes:
    """Serialize ``obj`` to canonical RFC 8785 JSON bytes (UTF-8)."""
    return _serialize(obj).encode("utf-8")


def _serialize(obj: Any) -> str:
    if obj is None:
        return "null"
    # bool is a subclass of int — check it FIRST.
    if isinstance(obj, bool):
        return "true" if obj else "false"
    if isinstance(obj, str):
        return _escape_string(obj)
    if isinstance(obj, int):
        return str(obj)
    if isinstance(obj, float):
        return _format_float(obj)
    if isinstance(obj, dict):
        return _serialize_object(obj)
    if isinstance(obj, list | tuple):
        return "[" + ",".join(_serialize(item) for item in obj) + "]"
    raise ValueError(f"unsupported type for JCS: {type(obj).__name__}")


def _serialize_object(obj: dict[Any, Any]) -> str:
    # NOTE: RFC 8785 sorts keys by UTF-16 code units. For our ASCII/BMP envelope
    # field names this equals Python's default sorted() over str keys. Non-BMP
    # keys would require UTF-16 ordering (out of scope; our keys are ASCII).
    items = []
    for key in sorted(obj.keys()):
        if not isinstance(key, str):
            raise ValueError("JCS object keys must be strings")
        items.append(_escape_string(key) + ":" + _serialize(obj[key]))
    return "{" + ",".join(items) + "}"


def _escape_string(s: str) -> str:
    out = ['"']
    for ch in s:
        code = ord(ch)
        escape = _SHORT_ESCAPES.get(code)
        if escape is not None:
            out.append(escape)
        elif code < 0x20:
            # Remaining control chars -> \u00XX (lowercase hex per RFC 8785).
            out.append(f"\\u{code:04x}")
        else:
            # Printable / non-ASCII emitted raw (UTF-8); solidus NOT escaped.
            out.append(ch)
    out.append('"')
    return "".join(out)


def _format_float(x: float) -> str:
    """Format a Python float per ECMAScript Number.prototype.toString (RFC 8785)."""
    if x != x or x in (float("inf"), float("-inf")):
        raise ValueError("NaN and Infinity are not valid JCS numbers")
    if x == 0.0:
        return "0"  # covers both 0.0 and -0.0

    sign = "-" if x < 0 else ""
    digits, n = _shortest_digits_and_point(abs(x))
    k = len(digits)

    if k <= n <= 21:
        body = digits + "0" * (n - k)
    elif 0 < n <= 21:
        body = digits[:n] + "." + digits[n:]
    elif -6 < n <= 0:
        body = "0." + "0" * (-n) + digits
    else:
        # Exponential: first digit, optional fraction, then e±exp.
        if k > 1:
            mantissa = digits[0] + "." + digits[1:]
        else:
            mantissa = digits[0]
        exp = n - 1
        exp_sign = "+" if exp >= 0 else "-"
        body = f"{mantissa}e{exp_sign}{abs(exp)}"
    return sign + body


def _shortest_digits_and_point(x: float) -> tuple[str, int]:
    """Return ``(digits, n)`` where ``x = digits * 10^(n - len(digits))``.

    ``digits`` is the shortest round-trip significant-digit string with no
    leading/trailing zeros; ``n`` is the position of the decimal point relative
    to the start of ``digits`` (the power of ten of the first digit, plus one).
    Built on Python's ``repr`` which already yields the shortest round-trip form.
    """
    rep = repr(x)  # x is positive, finite, nonzero here
    if "e" in rep or "E" in rep:
        mantissa, exp_part = rep.lower().split("e")
        exp = int(exp_part)
    else:
        mantissa, exp = rep, 0

    if "." in mantissa:
        int_part, frac_part = mantissa.split(".")
    else:
        int_part, frac_part = mantissa, ""

    # All significant digits, in order, with the decimal exponent of the last digit.
    raw_digits = int_part + frac_part
    # Decimal exponent applying to the least-significant digit of raw_digits.
    low_exp = exp - len(frac_part)

    # Strip leading zeros (track how many integer-side positions they were).
    stripped_leading = raw_digits.lstrip("0")
    if stripped_leading == "":
        # Should not happen (x != 0), but guard defensively.
        return "0", 1
    # Strip trailing zeros, folding them into the exponent.
    trailing_zeros = len(stripped_leading) - len(stripped_leading.rstrip("0"))
    digits = stripped_leading.rstrip("0")
    if digits == "":
        digits = "0"
    low_exp += trailing_zeros

    # n = exponent of the most-significant digit, + 1.
    # value = digits * 10^low_exp ; first digit weight = low_exp + (len(digits)-1).
    n = low_exp + len(digits)
    return digits, n
