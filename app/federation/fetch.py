"""Single hardened egress helper for ALL federation outbound HTTP (SSRF guard, §11.1).

NOTE (deferred to P2/P3, do NOT implement until real peer fetches are wired):
  1. DNS-rebinding connect-pin: connect to the *validated* IP while preserving SNI/Host
     via a custom httpx transport, so the address resolved+checked in
     ``_resolve_and_validate`` is the address actually dialed (closes the
     resolve-then-connect TOCTOU window).
  2. Streaming byte-counted hard cap: replace the header-only ``content-length`` check
     with ``client.stream()`` + an incremental counter that aborts once the running
     total exceeds ``_MAX_BYTES`` (defends against missing/lying content-length).
Both are deferred together; the tested core here is IP-range validation and
HTTPS-only enforcement.
"""

import ipaddress
import socket

import httpx

_MAX_BYTES = 5 * 1024 * 1024
_MAX_REDIRECTS = 3
_TIMEOUT = httpx.Timeout(5.0, connect=3.0)


class FederationFetchError(Exception):
    """Raised when a federation fetch is rejected or fails safety checks."""


def is_blocked_ip(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    # Un-map IPv4-mapped IPv6 (::ffff:a.b.c.d) before any range check: such an
    # address has version==6, so the v4-only CGNAT branch and (on some Python
    # versions) the private/loopback/link-local checks are skipped, letting an
    # attacker reach internal IPs (incl. IMDS 169.254.169.254) via a mapped
    # literal. Unwrap to the v4 address so every check below applies (SSRF).
    if addr.version == 6 and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return True
    if addr.is_multicast or addr.is_unspecified:
        return True
    # CGNAT 100.64.0.0/10 (not flagged is_private)
    if addr.version == 4 and addr in ipaddress.ip_network("100.64.0.0/10"):
        return True
    return False


def _resolve_and_validate(host: str) -> None:
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FederationFetchError(f"DNS resolution failed for {host}") from exc
    for info in infos:
        ip = str(info[4][0])  # sockaddr[0] is the address; str() narrows for mypy
        if is_blocked_ip(ip):
            raise FederationFetchError(f"blocked internal IP {ip} for host {host}")


async def hardened_get(url: str) -> httpx.Response:
    """HTTPS-only GET with internal-IP blocking, redirect cap + per-hop revalidation, size cap."""
    current = url
    for _ in range(_MAX_REDIRECTS + 1):
        parsed = httpx.URL(current)
        if parsed.scheme != "https":
            raise FederationFetchError(f"non-https URL rejected: {current}")
        if parsed.host is None or _is_ip_literal(parsed.host):
            raise FederationFetchError("IP-literal or hostless URL rejected")
        _resolve_and_validate(parsed.host)
        async with httpx.AsyncClient(
            follow_redirects=False, timeout=_TIMEOUT
        ) as client:
            resp = await client.get(current)
        if resp.is_redirect and resp.next_request is not None:
            current = str(resp.next_request.url)  # revalidate next hop on loop
            continue
        if int(resp.headers.get("content-length", 0)) > _MAX_BYTES:
            raise FederationFetchError("response exceeds size cap")
        return resp
    raise FederationFetchError("too many redirects")


def _is_ip_literal(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False
