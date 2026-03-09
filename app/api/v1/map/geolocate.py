"""IP geolocation endpoint for map API."""

import ipaddress
from typing import Optional

import httpx
import structlog
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel

router = APIRouter(prefix="/map", tags=["map"])
logger = structlog.get_logger(__name__)


class GeoLocationResponse(BaseModel):
    """Response model for IP-based geolocation."""

    lat: float
    lng: float
    city: Optional[str] = None
    state: Optional[str] = None
    country: str = "US"
    zip: Optional[str] = None
    ip: str
    source: str = "ip-api"


@router.get("/geolocate", response_model=GeoLocationResponse)
async def geolocate_ip(
    request: Request,
    ip: Optional[str] = Query(
        None, description="IP address to geolocate (defaults to client IP)"
    ),
) -> GeoLocationResponse:
    """
    Get approximate location from IP address.

    This endpoint provides fallback location detection when browser geolocation
    is unavailable or denied. Uses IP geolocation services to determine
    approximate user location.

    Returns city, state, and coordinates for centering the map.
    """
    # Get client IP if not provided
    client_ip = ip
    if not client_ip:
        # Try to get real IP from headers (for proxied requests)
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or request.headers.get("X-Real-IP")
            or (request.client.host if request.client else None)
        )

    # Validate IP format and reject non-IP strings, metadata IPs, and internal ranges
    if client_ip:
        try:
            addr = ipaddress.ip_address(client_ip)
            if (
                addr.is_private
                or addr.is_loopback
                or addr.is_link_local
                or addr.is_reserved
            ):
                return GeoLocationResponse(
                    lat=39.8283,
                    lng=-98.5795,
                    city="Geographic Center",
                    state="US",
                    country="US",
                    ip=client_ip,
                    source="default",
                )
        except ValueError:
            return GeoLocationResponse(
                lat=39.8283,
                lng=-98.5795,
                city="Geographic Center",
                state="US",
                country="US",
                ip="",
                source="default",
            )

    # Skip localhost/private IPs (legacy string check for coverage)
    if (
        client_ip in ["127.0.0.1", "localhost", "::1"]
        or (client_ip and client_ip.startswith("192.168."))
        or (client_ip and client_ip.startswith("10."))
    ):
        # Return center of US for local development
        return GeoLocationResponse(
            lat=39.8283,
            lng=-98.5795,
            city="Geographic Center",
            state="US",
            country="US",
            ip=client_ip or "",
            source="default",
        )

    try:
        # Try ip-api.com first (free, no key required, 45 requests per minute)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://ip-api.com/json/{client_ip}",
                params={
                    "fields": "status,country,countryCode,region,regionName,city,zip,lat,lon,query"
                },
                timeout=5.0,
            )

            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success":
                    return GeoLocationResponse(
                        lat=data.get("lat", 39.8283),
                        lng=data.get("lon", -98.5795),
                        city=data.get("city"),
                        state=data.get("region"),  # State code
                        country=data.get("countryCode", "US"),
                        zip=data.get("zip"),
                        ip=data.get("query", client_ip),
                        source="ip-api",
                    )
    except Exception as e:
        logger.warning(f"IP geolocation failed for {client_ip}: {e}")

    # Fallback to US center if geolocation fails
    return GeoLocationResponse(
        lat=39.8283,
        lng=-98.5795,
        city="United States",
        state="US",
        country="US",
        ip=client_ip or "",
        source="fallback",
    )
