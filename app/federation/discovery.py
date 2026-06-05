"""Federation discovery document (``.well-known/hsds-federation``) — §8.4 / §6.7.

A peer fetches this document to learn this node's DID, the location of its key
(did.json), the HSDS versions it supports, its profile URI, the absolute URLs of
its data endpoints, its allow-list policy, and its retention window.

Version handling is **set-membership** (a list), not exact-match (§8.4): a v1
node and a future v5 node can still federate if any advertised version is
mutually supported. Endpoints are advertised as **absolute** URLs (OPR-style,
§6.3) so partners never hard-code the ``/api/v1/federation`` prefix — the data
router itself lands in P1/P3, but advertising the forward URLs now is correct.

Imports are restricted to stdlib + ``app.core.config`` so this module stays
slim-Lambda-safe (no Redis/LLM deps); Task 0.7 serves it from the slim Lambda.
"""

from app.core.config import Settings


def _host_from_did(did: str | None) -> str | None:
    """Derive the host from a ``did:web:<host>`` or ``https://<host>`` DID.

    Returns ``None`` for ``None`` input. Port encoding
    (``did:web:host%3A8443``) is out of scope — a bare host is assumed per the
    design (matches ``app.federation.identity._host_from_did`` for non-None).
    """
    if did is None:
        return None
    if did.startswith("did:web:"):
        return did[len("did:web:") :]
    if did.startswith("https://"):
        return did[len("https://") :].split("/", 1)[0]
    return did


def build_discovery_doc(settings: Settings) -> dict:
    """Build the ``.well-known/hsds-federation`` discovery document.

    Renders a valid (status-200-able) doc even with all defaults: when neither
    ``FEDERATION_DOMAIN`` nor ``FEDERATION_DID`` is configured, the host falls
    back to ``"localhost"`` so endpoint/key URLs remain well-formed.
    """
    domain = settings.FEDERATION_DOMAIN or _host_from_did(settings.FEDERATION_DID)
    if not domain:
        domain = "localhost"

    base = f"https://{domain}/api/v1/federation"

    # FEDERATION_ALLOW_LIST_POLICY is a validated Literal on Settings, so a typo
    # already failed at construction — use the value directly, no substitution.
    policy = settings.FEDERATION_ALLOW_LIST_POLICY

    return {
        "did": settings.FEDERATION_DID,
        "key_location": f"https://{domain}/.well-known/did.json",
        "hsds_versions": settings.FEDERATION_HSDS_VERSIONS,
        "profile_uri": settings.FEDERATION_PROFILE_URI,
        "endpoints": {
            "export": f"{base}/export",
            "inbox": f"{base}/inbox",
            "history": f"{base}/history",
        },
        "allow_list_policy": policy,
        "retention_days": settings.FEDERATION_RETENTION_DAYS,
        "contact": settings.FEDERATION_CONTACT,
    }
