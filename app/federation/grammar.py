"""HSDS-FX ``federation_id`` grammar — the reference normalizer (design §135).

::

    federation_id = host ":" internal-id          ; split on the FIRST colon

* **host** — a reg-name (RFC 3986 §3.2.2) restricted to ASCII LDH+dot
  (letters/digits/hyphen/dot). ASCII-lowercased (RFC 4343 / §6.2.2.1) and one
  trailing FQDN-root ``"."`` stripped. Non-ASCII (U-label) hosts are out of scope
  for v1 — rejected; publishers pre-encode an IDN to its ``xn--`` A-label, which
  passes through as an opaque ASCII reg-name.
* **internal-id** — ``1*( unreserved / pct-encoded )``; ``unreserved`` =
  ``A-Za-z0-9-._~`` (§2.3). RFC 3986 §6.2.2 percent normalization: a ``%XX`` of an
  *unreserved* octet is DECODED to that char (§6.2.2.2, e.g. ``%2D`` → ``-``); any
  other ``%XX`` is KEPT with its hex UPPERCASED (§6.2.2.1, e.g. ``%3a`` → ``%3A``).
  A *raw* octet outside ``unreserved`` (a bare ``:``, ``/``, whitespace, a
  non-ASCII byte) is an ERROR on this normalize/compare path — a producer
  percent-encodes it, so a well-formed id never carries one. (Rejecting a bare raw
  ``:`` rather than silently re-encoding it is the collision-safest reading:
  re-encoding would merge ``loc:666`` and ``loc%3A666`` into one key.)

The normalized id is the §137 inbound exact-lookup PRIMARY KEY
(``source_type='federated_node'``), so this function is **deterministic**,
**idempotent** (``normalize(normalize(x)) == normalize(x)``), and **collision-safe**
(same logical id → identical bytes; distinct ids → never merge). ``str.lower()`` is
used, never ``str.casefold()`` — casefold maps ``ß`` → ``ss`` and would collapse two
distinct publisher hosts into one key (peer-shadowing). Malformed input raises
``ValueError`` (there is no canonical form for it).

This is a SEPARATE reference function: ``envelope.build_preimage`` and ``log.append``
stay verbatim pass-throughs so a relayed/foreign envelope's already-signed bytes are
NEVER re-canonicalized (Principle II). A node canonicalizes its OWN outbound id at
the publish build site (fail-soft). It is identity on every value the repo emits
today (lowercase host + uuid/``loc-N`` internal-id), so it cannot alter an
already-signed envelope id or Merkle leaf.

The grammar reading is PPR-native, pinned BY FIAT and tagged interop_pending
(``tests/test_federation/vendor/INTEROP_PENDING.md`` row 7) — only a second
independent implementation (the P2 two-node loop) finally settles it. Produce-path
encoding of a raw internal id (raw → ``%XX``) is a deliberately separate concern,
not this canonicalizer; today's location ids are uuids (already pure-unreserved).
"""

from __future__ import annotations

#: RFC 3986 §2.3 unreserved set.
_UNRESERVED = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~"
)
#: ASCII LDH + dot — the v1 host charset (DNS reg-name in practice).
_HOST_CHARS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-."
)
_HEXDIG = frozenset("0123456789abcdefABCDEF")


def normalize_federation_id(value: str) -> str:
    """Canonicalize a ``federation_id``; raise ``ValueError`` if malformed. Pure."""
    if not isinstance(value, str):
        raise ValueError("federation_id must be a string")
    if ":" not in value:
        raise ValueError("federation_id must be '<host>:<internal-id>' (no ':')")
    host_raw, id_raw = value.split(":", 1)  # split on the FIRST colon
    return _normalize_host(host_raw) + ":" + _normalize_internal_id(id_raw)


def _normalize_host(host_raw: str) -> str:
    if host_raw == "":
        raise ValueError("federation_id host is empty")
    if any(ord(c) >= 0x80 for c in host_raw):
        # v1 is ASCII/A-label only — do not auto-IDNA (dual-encoding collision risk).
        raise ValueError("federation_id host must be ASCII (pre-encode IDN to xn--)")
    host = host_raw.lower()  # str.lower, NOT casefold (casefold ß->ss collides hosts)
    if host.endswith("."):
        host = host[:-1]  # strip exactly one trailing FQDN-root dot (idempotent)
    if host == "":
        raise ValueError("federation_id host is empty after trailing-dot strip")
    if any(c not in _HOST_CHARS for c in host):
        raise ValueError("federation_id host has non-LDH/dot characters")
    if "" in host.split("."):
        raise ValueError("federation_id host has an empty DNS label")
    return host


def _normalize_internal_id(id_raw: str) -> str:
    if id_raw == "":
        raise ValueError("federation_id internal-id is empty")
    out: list[str] = []
    i, n = 0, len(id_raw)
    while i < n:
        c = id_raw[i]
        if c == "%":
            if (
                i + 2 >= n
                or id_raw[i + 1] not in _HEXDIG
                or id_raw[i + 2] not in _HEXDIG
            ):
                raise ValueError("malformed percent-escape in federation_id")
            octet = int(id_raw[i + 1 : i + 3], 16)
            ch = chr(octet)
            if octet < 0x80 and ch in _UNRESERVED:
                out.append(ch)  # §6.2.2.2 decode-unreserved
            else:
                out.append("%" + id_raw[i + 1 : i + 3].upper())  # §6.2.2.1 keep, upper
            i += 3
        elif c in _UNRESERVED:
            out.append(c)
            i += 1
        else:
            # a raw octet outside unreserved (bare ':', '/', whitespace, non-ASCII)
            # is not part of a well-formed id — a producer percent-encodes it.
            raise ValueError(
                f"federation_id internal-id has an unencoded reserved char {c!r}"
            )
    return "".join(out)
