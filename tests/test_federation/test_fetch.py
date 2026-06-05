import pytest
from app.federation.fetch import is_blocked_ip, FederationFetchError


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.1",
        "169.254.169.254",  # IMDS
        "100.64.0.1",  # CGNAT
        "::1",
        "fc00::1",
        "fe80::1",
    ],
)
def test_internal_ips_are_blocked(ip):
    assert is_blocked_ip(ip) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700::1111"])
def test_public_ips_are_allowed(ip):
    assert is_blocked_ip(ip) is False


async def test_fetch_rejects_non_https():  # asyncio auto-mode; no explicit marker (ruff PT)
    with pytest.raises(FederationFetchError):
        from app.federation.fetch import hardened_get

        await hardened_get("http://example.com/x")  # http -> reject
