# RFC 7386 JSON Merge Patch — Appendix A test cases (vendored)

Pins the merge-patch semantics the HSDS Profile relies on. The Profile
(`profiles/hsds-ppr/`) is defined as RFC-7386 merge patches over the base HSDS
schemas (`profiles/hsds-ppr/README.md`); a conformant merge is what guarantees a
patch only ADDS the three profile fields and never deletes a base `required`
field. The dangerous failure mode (`{"properties":{"id":null}}` silently
deleting the base's required `id`) is exactly RFC-7386 null-deletion semantics,
covered by the `{"a":"b"} + {"a":null} -> {}` case.

- **Source**: RFC 7386 §Appendix A "Example Test Cases" — https://www.rfc-editor.org/rfc/rfc7386.txt
- **Retrieved**: 2026-06-06 (fetched and reproduced verbatim)
- **License**: IETF Trust (RFC text; BSD-style for code components).

Used by `tests/test_federation/test_profile_merge.py`: the test's `merge_patch`
helper must reproduce every case here before it is trusted to merge the real
Profile patches over the base schemas.
