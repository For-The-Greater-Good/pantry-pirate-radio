# Vendored RFC 3986 §6.2.2 normalization vectors

Percent-encoding + case normalization vectors for `app/federation/grammar.py:
normalize_uri_component` — the RFC 3986 §6.2.2 primitive that `federation_id`'s
internal-id normalization composes (so the `federation_id` percent/case **mechanics**
are externally anchored even though the `host:internal-id` **composition** remains
interop-pending; design §135 / INTEROP_PENDING.md row 7).

**RFC 3986 does not publish a separate machine-readable conformance suite** — it
states normalization *rules* and (for these mechanics) **one** inline worked
example. `vectors.json` is:

- the **one verbatim worked example** RFC 3986 §6.2.2 publishes for this mechanic
  (`"kind": "rfc-example"`) — the genuine external anchor, written by the spec
  author, that pins the reading:
  - §6.2.2.1: `"%3a"` vs `"%3A"` — verbatim, *"the hexadecimal digits within a
    percent-encoding triplet (e.g., `"%3a"` versus `"%3A"`) … should be normalized to
    use uppercase letters"*.
  - **Note:** §6.2.2.2 (Percent-Encoding Normalization) states the
    *decode-an-unreserved-octet* RULE with **no worked URI**. The familiar
    `…/%7Euser/` ≡ `…/~user/` example with that wording is **RFC 3987 §5.3.2.3** (a
    *different* RFC — IRIs), **not** RFC 3986. So `%7Esmith`→`~smith` is carried here
    as a rule-application, not as a verbatim RFC 3986 example.
- plus **direct applications of the §6.2.2 rules** (`"kind": "rfc-rule-application"`)
  to the RFC §2.3 `unreserved` set (`A-Za-z0-9-._~`) and to reserved / non-ASCII
  octets, each citing the rule it applies. These extend coverage **under the reading
  the verbatim `%3a` example anchors** — they are grounded in the RFC's explicit
  rules + the §2.3 set (external), not in PPR's implementation.

WHATWG's `urltestdata.json` is deliberately **not** used: the WHATWG URL Standard
has its own percent-encode sets that diverge from RFC 3986 §6.2.2 (it does not
decode `%41`→`A`), so it would produce false failures against an RFC-3986 normalizer.

- **Source:** https://datatracker.ietf.org/doc/html/rfc3986#section-6.2.2
  (§6.2.2.1 Case Normalization, §6.2.2.2 Percent-Encoding Normalization; §2.3
  Unreserved Characters).
- **Pinned:** RFC 3986 is an IETF Internet Standard (STD 66), published 2005,
  stable / never revised — there is no commit to pin; the section anchors above are
  the authoritative reference.
- **License:** IETF Trust / RFC text (BCP 78). Vendored as test fixtures with
  attribution.

`normalize_uri_component` is the **lenient** normalization primitive: it
canonicalizes percent-encodings and leaves raw characters and any malformed `%`
verbatim (it does not validate). `federation_id`'s stricter internal-id rule
(reject a raw reserved char / a malformed escape) applies the same per-`%XX` step
(`_pct_canon`) behind its own validation gate.
