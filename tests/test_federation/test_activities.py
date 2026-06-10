"""HSDS-FX activity verbs — stateless wire validator (design §117/§160/§204-206).

``validate_activity`` is a pure boolean wire check: verb ∈ {Update, Announce,
Delete}; the per-verb actor/attributedTo/origin authority relations; the Delete
Tombstone object shape. It is NOT stateful (no allow-list / sequence-dedup /
corroboration / merge) and does NOT re-verify id/proof or the full federation_id
grammar. The verb semantics are a PPR-native reading pinned by fiat (interop_pending,
vendor/INTEROP_PENDING.md row 9), settled only by the P2 two-node loop.
"""

from __future__ import annotations

import pytest

from app.federation.activities import validate_activity

_DID_A = "did:web:a.example"
_DID_B = "did:web:b.example"
_OBJ = {"id": "loc-1", "name": "Test Pantry"}


def _env(verb, actor, attributed_to, origin, obj, federation_id="a.example:loc-1"):
    """A verb-shape envelope (id/proof omitted — validate_activity ignores them)."""
    return {
        "@context": "https://hsds-federation.pantrypirateradio.org/profile",
        "type": verb,
        "actor": actor,
        "attributedTo": attributed_to,
        "origin": origin,
        "federation_id": federation_id,
        "object": obj,
        "published": "2026-06-07T00:00:00Z",
        "sequence": 1,
        "license": "sandia-ftgg-nc-os-1.0",
    }


def _tombstone(federation_id="a.example:dead", redirect="a.example:survivor", **extra):
    obj = {"type": "Tombstone", "federation_id": federation_id, "redirectTo": redirect}
    obj.update(extra)
    return obj


# --- accept cases --------------------------------------------------------------
ACCEPT = {
    "update-own-authority": _env("Update", _DID_A, _DID_A, _DID_A, _OBJ),
    # Announce relays a DISTINCT origin: actor=announcer, attributedTo==origin
    "announce-distinct-origin": _env("Announce", _DID_B, _DID_A, _DID_A, _OBJ),
    "delete-survivor": _env("Delete", _DID_A, _DID_A, _DID_A, _tombstone()),
    "delete-null-redirect": _env(
        "Delete", _DID_A, _DID_A, _DID_A, _tombstone(redirect=None)
    ),
    # §8.4: receivers MUST ignore unknown fields — an extra Tombstone key is accepted
    "tombstone-extra-key-ignored": _env(
        "Delete", _DID_A, _DID_A, _DID_A, _tombstone(reason="duplicate")
    ),
    # id/proof are a SEPARATE seam — a verb-shape-valid envelope without them passes
    "update-no-id-proof": _env("Update", _DID_A, _DID_A, _DID_A, _OBJ),
}

# --- reject cases --------------------------------------------------------------
REJECT = {
    # authority relations
    "update-actor-ne-attributedto": _env("Update", _DID_A, _DID_B, _DID_A, _OBJ),
    "update-origin-ne-actor": _env("Update", _DID_A, _DID_A, _DID_B, _OBJ),
    "delete-actor-ne-attributedto": _env(
        "Delete", _DID_A, _DID_B, _DID_A, _tombstone()
    ),
    "delete-origin-ne-actor": _env("Delete", _DID_A, _DID_A, _DID_B, _tombstone()),
    "announce-origin-eq-actor": _env("Announce", _DID_A, _DID_A, _DID_A, _OBJ),
    "announce-attributedto-eq-actor": _env("Announce", _DID_B, _DID_B, _DID_A, _OBJ),
    # required identity fields
    "missing-actor": _env("Update", "", _DID_A, _DID_A, _OBJ),
    "missing-attributedto": _env("Update", _DID_A, "", _DID_A, _OBJ),
    "missing-origin": _env("Announce", _DID_B, _DID_A, "", _OBJ),
    "empty-federation-id": _env(
        "Update", _DID_A, _DID_A, _DID_A, _OBJ, federation_id=""
    ),
    # verb set — CLOSED frozenset {Update, Announce, Delete}; everything else
    # rejected (wire-freeze closed-verb-registry coverage evidence). Move/Flag are
    # reserved-for-later-phase verbs; Tombstone is an object type, never a verb.
    "verb-create": _env("Create", _DID_A, _DID_A, _DID_A, _OBJ),
    "verb-flag": _env("Flag", _DID_A, _DID_A, _DID_A, _OBJ),
    "verb-move": _env("Move", _DID_A, _DID_A, _DID_A, _OBJ),
    "verb-tombstone-as-verb": _env("Tombstone", _DID_A, _DID_A, _DID_A, _OBJ),
    "verb-lowercase": _env("update", _DID_A, _DID_A, _DID_A, _OBJ),
    "verb-empty-string": _env("", _DID_A, _DID_A, _DID_A, _OBJ),
    # object shape (Update/Announce)
    "update-empty-object": _env("Update", _DID_A, _DID_A, _DID_A, {}),
    "update-null-object": _env("Update", _DID_A, _DID_A, _DID_A, None),
    "update-list-object": _env("Update", _DID_A, _DID_A, _DID_A, [1, 2]),
    # Tombstone shape (Delete)
    "tombstone-bad-type": _env(
        "Delete",
        _DID_A,
        _DID_A,
        _DID_A,
        {"type": "Delete", "federation_id": "a.example:d", "redirectTo": None},
    ),
    "tombstone-missing-redirect": _env(
        "Delete",
        _DID_A,
        _DID_A,
        _DID_A,
        {"type": "Tombstone", "federation_id": "a.example:d"},
    ),
    "tombstone-redirect-nonstring": _env(
        "Delete",
        _DID_A,
        _DID_A,
        _DID_A,
        {"type": "Tombstone", "federation_id": "a.example:d", "redirectTo": 123},
    ),
    "tombstone-empty-fedid": _env(
        "Delete",
        _DID_A,
        _DID_A,
        _DID_A,
        {"type": "Tombstone", "federation_id": "", "redirectTo": None},
    ),
    "tombstone-object-not-dict": _env("Delete", _DID_A, _DID_A, _DID_A, "Tombstone"),
    # whitespace tokens (§11.2 self-corroboration evasion + whitespace-only identity)
    "announce-whitespace-origin": _env(
        "Announce", _DID_A, _DID_A + " ", _DID_A + " ", _OBJ
    ),
    "whitespace-only-actor": _env("Update", " ", " ", " ", _OBJ),
    "tombstone-whitespace-redirect": _env(
        "Delete",
        _DID_A,
        _DID_A,
        _DID_A,
        {
            "type": "Tombstone",
            "federation_id": "a.example:d",
            "redirectTo": "a.example:s ",
        },
    ),
}


@pytest.mark.parametrize("bad_type", [[], {}, {"x": 1}, ["Update"]])
def test_unhashable_type_is_rejected_not_raised(bad_type):
    """Totality: an unhashable 'type' (list/dict) must return False, NOT raise
    TypeError on the frozenset membership test (a direct caller — future P2 ingest —
    relies on the never-raises contract)."""
    env = _env("Update", _DID_A, _DID_A, _DID_A, _OBJ)
    env["type"] = bad_type
    assert validate_activity(env) is False


@pytest.mark.parametrize("bad_type", [123, None, True, 1.5, b"Update"])
def test_non_string_hashable_verb_is_rejected(bad_type):
    """Closed-verb-registry coverage (wire-freeze evidence): a non-string but
    HASHABLE 'type' (int/None/bool/float/bytes) must return False. The verb must be
    ``isinstance(str)`` BEFORE the frozenset test — ``True`` is the trap, since
    ``True == 1`` hashes/compares as 1 and ``1 in frozenset({...str...})`` is False
    only because the set holds strings; the isinstance guard is what truly closes it,
    and a bytes ``b"Update"`` is never == the str ``"Update"``."""
    env = _env("Update", _DID_A, _DID_A, _DID_A, _OBJ)
    env["type"] = bad_type
    assert validate_activity(env) is False


def test_trailing_space_origin_is_not_a_distinct_authority():
    """§11.2: an Announce whose origin is its own actor + a trailing space must NOT
    pass the distinct-authority check (the byte-exact origin!=actor would otherwise
    accept it). Identity tokens are whitespace-free."""
    evasion = _env("Announce", _DID_A, _DID_A + " ", _DID_A + " ", _OBJ)
    assert validate_activity(evasion) is False


@pytest.mark.parametrize("name", sorted(ACCEPT))
def test_accept(name):
    assert validate_activity(ACCEPT[name]) is True


@pytest.mark.parametrize("name", sorted(REJECT))
def test_reject(name):
    assert validate_activity(REJECT[name]) is False


def test_missing_type_and_non_dict_are_rejected():
    """Defensive: a missing 'type' key and a non-dict envelope are rejected, not
    raised — the validator is total over arbitrary input."""
    assert validate_activity({"actor": _DID_A}) is False  # no type
    assert validate_activity(None) is False
    assert validate_activity("Update") is False
    assert validate_activity([_DID_A]) is False


def test_accepts_what_publish_emits():
    """The validator must ACCEPT PPR's own emitted shapes (log.append defaults
    actor/attributedTo to origin_did; publish builds the Tombstone). A regression
    that rejected our own output would silently break the §137 ingest path."""
    # A PPR Update: actor == attributedTo == origin == the node DID.
    own_update = _env(
        "Update",
        "did:web:node.example",
        "did:web:node.example",
        "did:web:node.example",
        _OBJ,
        federation_id="node.example:loc-7",
    )
    assert validate_activity(own_update) is True
    # A PPR Delete: the Tombstone publish.py builds (redirectTo present, may be null).
    own_delete = _env(
        "Delete",
        "did:web:node.example",
        "did:web:node.example",
        "did:web:node.example",
        {
            "type": "Tombstone",
            "federation_id": "node.example:dead",
            "redirectTo": "node.example:surv",
        },
        federation_id="node.example:dead",
    )
    assert validate_activity(own_delete) is True
