# Vendored C2SP signed-note (Go `sumdb/note`) conformance vector

The **PeterNeumann** reference signed note published by Go's
`golang.org/x/mod/sumdb/note` package. It is an **external** conformance anchor
for `app/federation/checkpoint.py` (the C2SP signed-note checkpoint wire format)
and for the HSDS-FX conformance suite's `checkpoint` area
(`cp-note-go-kat-001`) — unlike a self-derived oracle, these bytes come from a
third party (Go) that independently implements the C2SP signed-note format.
Ed25519 is deterministic (RFC 8032), so our `sign_note` MUST reproduce
`signed_note` byte-for-byte; if it does, any Go-ecosystem witness/verifier
accepts our checkpoints.

- **Source:** https://github.com/golang/mod — `sumdb/note/note_test.go`
  (the `PeterNeumann` keypair + the documented `want` signed note).
- **Pinned commit:** `087f6515dd3ba3e8b06918fa425ffe7732321a7a` (default branch `master`).
- **License:** BSD-3-Clause — Copyright The Go Authors (see the repo `LICENSE`).
  Vendored solely as a test fixture, with attribution per the license.

## What's in `vectors.json`

Extracted verbatim from `note_test.go` at the pinned commit:

- `key_name` / `verifier_key` / `signer_key` — the `PeterNeumann` public verifier
  key, the matching private signer key (both in the Go `note` key encoding:
  `name+keyhash+base64(alg||key)`), and the bare key name.
- `text` — the note text (ends in a newline, as the format requires).
- `signature_blob_base64` — `base64(keyID[4] || signature[64])`, the body of the
  signature line.
- `signed_note` — the full signed note `want` value: `text`, then a blank line,
  then `— PeterNeumann <signature_blob_base64>\n` (em-dash U+2014). This is the
  byte-exact KAT a conforming encoder must reproduce.

## To refresh (rarely needed — this vector is a long-standing canonical example)

```
gh api repos/golang/mod/commits/master --jq .sha
gh api "repos/golang/mod/contents/sumdb/note/note_test.go?ref=<sha>" --jq .content | base64 -d
```

Then update the pinned SHA above and re-confirm `signed_note` is byte-identical.
