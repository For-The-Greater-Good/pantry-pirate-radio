"""fetch.hardened_get egress paths (SSRF guard, design §11.1).

The audit found the entire egress path of ``hardened_get`` untested (46.58%
coverage): these are reachable guard paths a hostile peer URL hits, so they get
direct tests. DNS is faked with a recording ``getaddrinfo`` (no real network);
HTTP is faked with respx. The deferred P2/P3 hardenings (DNS-rebinding
connect-pin, streaming byte cap) are documented in fetch.py and NOT tested here.
"""

import socket

import httpx
import pytest
import respx

from app.federation import fetch

_PUBLIC_IP = "93.184.216.34"


class _RecordingResolver:
    """Fake socket.getaddrinfo that records hosts and returns a public IP."""

    def __init__(self, ip: str = _PUBLIC_IP):
        self.ip = ip
        self.hosts: list[str] = []

    def __call__(self, host, port, **kwargs):
        self.hosts.append(host)
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (self.ip, 443))
        ]


def test_is_ip_literal() -> None:
    assert fetch._is_ip_literal("93.184.216.34") is True
    assert fetch._is_ip_literal("2606:2800:220:1:248:1893:25c8:1946") is True
    assert fetch._is_ip_literal("example.org") is False


async def test_ip_literal_url_rejected_before_any_io(monkeypatch) -> None:
    resolver = _RecordingResolver()
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    with pytest.raises(fetch.FederationFetchError, match="IP-literal"):
        await fetch.hardened_get(f"https://{_PUBLIC_IP}/peer")
    assert resolver.hosts == []  # rejected before resolution


async def test_dns_failure_raises(monkeypatch) -> None:
    def _fail(host, port, **kwargs):
        raise socket.gaierror("NXDOMAIN")

    monkeypatch.setattr(socket, "getaddrinfo", _fail)
    with pytest.raises(fetch.FederationFetchError, match="DNS resolution failed"):
        await fetch.hardened_get("https://nonexistent.example.org/x")


async def test_host_resolving_to_internal_ip_blocked(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _RecordingResolver(ip="127.0.0.1"))
    with pytest.raises(fetch.FederationFetchError, match="blocked internal IP"):
        await fetch.hardened_get("https://rebound.example.org/x")


@respx.mock
async def test_success_path_returns_response(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _RecordingResolver())
    respx.get("https://peer.example.org/doc").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    resp = await fetch.hardened_get("https://peer.example.org/doc")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


@respx.mock
async def test_redirect_is_followed_and_next_hop_revalidated(monkeypatch) -> None:
    resolver = _RecordingResolver()
    monkeypatch.setattr(socket, "getaddrinfo", resolver)
    respx.get("https://a.example.org/start").mock(
        return_value=httpx.Response(
            301, headers={"location": "https://b.example.org/final"}
        )
    )
    respx.get("https://b.example.org/final").mock(
        return_value=httpx.Response(200, text="done")
    )
    resp = await fetch.hardened_get("https://a.example.org/start")
    assert resp.status_code == 200
    # EVERY hop's host was independently resolved + validated (per-hop SSRF check)
    assert resolver.hosts == ["a.example.org", "b.example.org"]


@respx.mock
async def test_redirect_to_non_https_rejected(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _RecordingResolver())
    respx.get("https://a.example.org/start").mock(
        return_value=httpx.Response(
            301, headers={"location": "http://a.example.org/downgrade"}
        )
    )
    with pytest.raises(fetch.FederationFetchError, match="non-https"):
        await fetch.hardened_get("https://a.example.org/start")


@respx.mock
async def test_oversized_content_length_rejected(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _RecordingResolver())
    respx.get("https://big.example.org/blob").mock(
        return_value=httpx.Response(
            200, headers={"content-length": str(6 * 1024 * 1024)}
        )
    )
    with pytest.raises(fetch.FederationFetchError, match="size cap"):
        await fetch.hardened_get("https://big.example.org/blob")


@respx.mock
async def test_too_many_redirects_rejected(monkeypatch) -> None:
    monkeypatch.setattr(socket, "getaddrinfo", _RecordingResolver())
    respx.get("https://loop.example.org/x").mock(
        return_value=httpx.Response(
            301, headers={"location": "https://loop.example.org/x"}
        )
    )
    with pytest.raises(fetch.FederationFetchError, match="too many redirects"):
        await fetch.hardened_get("https://loop.example.org/x")
