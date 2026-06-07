"""HSDS-FX activity verbs — the stateless wire validator (design §117/§160/§204-206).

``validate_activity(envelope)`` checks ONLY the stateless wire semantics of a single
activity envelope — the verb, the actor/attributedTo/origin authority relations per
verb, and the ``Delete`` Tombstone object shape. It is pure (no DB / allow-list /
peer cursor / corroboration / merge), and it does NOT re-verify ``id``/``proof``
(that is ``envelope.verify_envelope`` + the content-address/proof conformance areas)
nor the full ``federation_id`` grammar (that is ``grammar.normalize_federation_id`` +
the federation_id area) nor deep HSDS-object validity (Principle II / the aggregate).

Rules (a single envelope decides each):
  * verb ∈ {Update, Announce, Delete} — a CLOSED, case-sensitive set (Tombstone is an
    object type, never a verb; Flag/Move are reserved for later phases). The verb is
    the dispatch key, so §8.4 "ignore unknown FIELDS" does not make it open.
  * actor / attributedTo / origin are required non-empty strings on every verb;
    federation_id (top level) is a required non-empty string (shallow — grammar is
    its own area).
  * Update / Delete: actor == attributedTo == origin (own-authority self-assertion;
    §117 "actor == attributedTo for Update/Delete" + §218 PPR publishes own-authority
    Updates). A type=Update/Delete with origin != actor is therefore rejected (a
    relayed assertion must use Announce — the Update-vs-Announce wire discriminant).
  * Announce: origin present AND origin != actor (a DISTINCT corroborated authority,
    §160/§205 "MUST carry the original origin, not just its own actor") AND
    attributedTo == origin (the data is attributed to the corroborated origin, the
    unit of corroboration in §12.1 — not the relaying announcer).
  * Delete: object is a Tombstone — a dict with type == "Tombstone", a non-empty
    string federation_id, and redirectTo PRESENT and either null or a non-empty
    string. UNKNOWN extra keys are IGNORED, not rejected — §8.4 ("receivers MUST
    ignore unknown fields, never reject on them") governs forward-compatibility and
    is honored here rather than locally contradicted.
  * Update / Announce: object is a non-empty dict (deep HSDS validity deferred).

STATEFUL ingest policy is deliberately OUT of scope (P2): allow-list membership,
(actor, sequence) dedup, checkpoint consistency, per-peer budget, and the receiver
effects (merge_location + HUMAN_VERIFIED guard, origin-deduped corroboration,
Tombstone is_canonical + survivor-chain resolution).

The verb semantics are a PPR-native canonical reading, pinned BY FIAT and tagged
interop_pending (vendor/INTEROP_PENDING.md row 9) — settled only by a second
independent implementation (the P2 two-node loop; PPR emits no Announce until P6, so
the Announce rules are entirely un-exercised by PPR's own output today).
"""

from __future__ import annotations

from typing import Any

_VERBS = frozenset({"Update", "Announce", "Delete"})


def _clean_token(v: Any) -> bool:
    """A non-empty string with NO whitespace. DIDs and federation_ids are
    whitespace-free tokens, so a padded/whitespace variant (``"X "`` vs ``"X"``,
    ``" "``) is rejected — this closes the trailing-space self-corroboration evasion
    (an Announce whose ``origin`` is its own ``actor`` plus a space would otherwise
    pass the byte-exact ``origin != actor`` distinctness check; §11.2)."""
    return isinstance(v, str) and len(v) > 0 and not any(c.isspace() for c in v)


def validate_activity(envelope: Any) -> bool:
    """True iff ``envelope`` satisfies the stateless HSDS-FX verb wire rules. Total
    over arbitrary input — returns ``False`` (never raises) on any junk."""
    if not isinstance(envelope, dict):
        return False
    verb = envelope.get("type")
    # isinstance guard FIRST: an unhashable type (list/dict) would raise on the
    # frozenset membership test, and verbs are always strings anyway.
    if not isinstance(verb, str) or verb not in _VERBS:
        return False
    actor = envelope.get("actor")
    attributed_to = envelope.get("attributedTo")
    origin = envelope.get("origin")
    if not (
        _clean_token(actor) and _clean_token(attributed_to) and _clean_token(origin)
    ):
        return False
    if not _clean_token(envelope.get("federation_id")):
        return False

    if verb in ("Update", "Delete"):
        # Own-authority self-assertion: all three identity fields coincide.
        if not (actor == attributed_to == origin):
            return False
    else:  # Announce — corroborates a DISTINCT origin authority.
        if origin == actor:
            return False
        if attributed_to != origin:
            return False

    obj = envelope.get("object")
    if verb == "Delete":
        return _valid_tombstone(obj)
    # Update / Announce: the object is an HSDS aggregate — shallow check only here.
    return isinstance(obj, dict) and len(obj) > 0


def _valid_tombstone(obj: Any) -> bool:
    if not isinstance(obj, dict):
        return False
    if obj.get("type") != "Tombstone":
        return False
    if not _clean_token(obj.get("federation_id")):
        return False
    if "redirectTo" not in obj:  # a required known key (value may be null)
        return False
    redirect = obj["redirectTo"]
    if redirect is not None and not _clean_token(redirect):
        return False
    # Extra keys are IGNORED (§8.4 forward-compatibility), not rejected.
    return True
