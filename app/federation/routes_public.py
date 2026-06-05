"""Root-level public federation routes (Task 0.7, Principle XV).

These make PPR *discoverable*. A peer fetches:

* ``GET /.well-known/hsds-federation`` — the discovery doc (§8.4 / §6.7):
  DID, key location, supported HSDS versions, profile, endpoint URLs,
  allow-list policy, retention.
* ``GET /.well-known/did.json`` — the W3C DID document with the node's keys.
* ``GET /.well-known/webfinger?resource=...`` — RFC 7033 JRD resolving an
  ``acct:`` handle to the actor URL.
* ``GET /api/v1/federation/actor`` — the ActivityStreams actor doc advertised
  by did.json (``alsoKnownAs``) and the discovery doc.

did:web and WebFinger REQUIRE the ``.well-known`` paths at the domain root, so
they cannot live under the ``/api/v1`` prefix. ``register_federation_public_routes``
is the single seam both the Uvicorn app (``app/main.py``) and the slim Lambda
(``app/api/lambda_app.py``) call, so the routes behave identically in both.

Imports are restricted to ``fastapi`` + ``app.federation.{identity,discovery}``
+ ``app.core.config`` — NO Redis/RQ/LLM — so the slim Lambda image stays slim.
Handlers read the module-level ``settings`` singleton at call time so tests can
monkeypatch it.
"""

import structlog
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.federation.discovery import _host_from_did, build_discovery_doc
from app.federation.identity import (
    build_actor,
    build_did_document,
    build_webfinger,
    load_signing_key,
    public_key_multibase,
)

_logger = structlog.get_logger(__name__)


def _node_domain() -> str:
    """Resolve the node's public host, matching the discovery doc derivation."""
    domain = settings.FEDERATION_DOMAIN or _host_from_did(settings.FEDERATION_DID)
    return domain or "localhost"


def _actor_url() -> str:
    """The absolute actor URL this node serves (from the resolved node domain)."""
    return f"https://{_node_domain()}/api/v1/federation/actor"


def _signing_key_multibase() -> str | None:
    """Return the node's online public key as multibase, or ``None``.

    ``None`` when ``FEDERATION_DID`` is unset or no signing key is configured.
    A *malformed* ``FEDERATION_SIGNING_KEY`` (``load_signing_key`` raises
    ``ValueError``) is logged and treated as "no key" → callers 404 instead of
    surfacing an opaque, un-logged 500 (Principle XI graceful / XII observable).
    """
    if not settings.FEDERATION_DID:
        return None
    try:
        private_key = load_signing_key(settings.FEDERATION_SIGNING_KEY)
    except ValueError as exc:
        _logger.error("federation_signing_key_invalid", error=str(exc))
        return None
    if private_key is None:
        return None
    return public_key_multibase(private_key.public_key())


def register_federation_public_routes(app: FastAPI) -> None:
    """Register the root-level public federation routes onto ``app``.

    Called by both ``app/main.py`` and ``app/api/lambda_app.py`` so the
    discovery surface is identical across Uvicorn and the slim Lambda
    (Principle XV).
    """

    @app.get("/.well-known/hsds-federation", include_in_schema=False)
    async def hsds_federation_discovery() -> JSONResponse:
        """Serve the federation discovery doc — always 200 (renders defaults)."""
        return JSONResponse(build_discovery_doc(settings))

    @app.get("/.well-known/did.json", include_in_schema=False)
    async def did_document() -> JSONResponse:
        """Serve the DID document — 404 until DID + signing key are configured."""
        mb = _signing_key_multibase()
        if settings.FEDERATION_DID is None or mb is None:
            raise HTTPException(status_code=404, detail="DID not configured")
        return JSONResponse(
            build_did_document(settings.FEDERATION_DID, mb, actor_url=_actor_url()),
            media_type="application/json",
        )

    @app.get("/.well-known/webfinger", include_in_schema=False)
    async def webfinger(resource: str) -> JSONResponse:
        """Resolve an ``acct:`` handle to the actor URL (RFC 7033).

        ``resource`` is a required query parameter — FastAPI returns 422 when
        it is absent.
        """
        return JSONResponse(
            build_webfinger(resource, _actor_url()),
            media_type="application/jrd+json",
        )

    @app.get("/api/v1/federation/actor", include_in_schema=False)
    async def federation_actor() -> JSONResponse:
        """Serve the actor doc — 404 until DID + signing key are configured."""
        mb = _signing_key_multibase()
        if settings.FEDERATION_DID is None or mb is None:
            raise HTTPException(status_code=404, detail="actor not configured")
        return JSONResponse(build_actor(settings.FEDERATION_DID, _node_domain(), mb))
