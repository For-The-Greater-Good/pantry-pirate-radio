"""Map API endpoints for serving location data to web interface."""

from typing import Optional, Dict, Any
from uuid import UUID
import httpx
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.v1.map.models import (
    MapLocationsResponse,
    MapLocation,
    MapSource,
    MapSchedule,
    MapMetadata,
    MapStatesResponse,
    StateInfo,
    MapSearchResponse,
    MapCluster,
    MapClustersResponse,
)
from app.api.v1.map.services import MapDataService
from app.api.v1.map.search_service import MapSearchService, OutputFormat
from app.core.db import get_session

router = APIRouter(prefix="/map", tags=["map"])
logger = logging.getLogger(__name__)


@router.get("/search", response_model=MapSearchResponse)
async def search_map_locations(
    request: Request,
    # Full-text search
    q: Optional[str] = Query(None, description="Search query text"),
    # Geographic filters
    min_lat: Optional[float] = Query(
        None, ge=-90, le=90, description="Minimum latitude for bounding box"
    ),
    min_lng: Optional[float] = Query(
        None, ge=-180, le=180, description="Minimum longitude for bounding box"
    ),
    max_lat: Optional[float] = Query(
        None, ge=-90, le=90, description="Maximum latitude for bounding box"
    ),
    max_lng: Optional[float] = Query(
        None, ge=-180, le=180, description="Maximum longitude for bounding box"
    ),
    center_lat: Optional[float] = Query(
        None, ge=-90, le=90, description="Center latitude for radius search"
    ),
    center_lng: Optional[float] = Query(
        None, ge=-180, le=180, description="Center longitude for radius search"
    ),
    radius: Optional[float] = Query(
        None, gt=0, le=500, description="Search radius in miles"
    ),
    # Filter parameters
    state: Optional[str] = Query(
        None, max_length=2, description="State code (e.g., 'CA')"
    ),
    services: Optional[str] = Query(
        None, description="Comma-separated list of services to filter"
    ),
    languages: Optional[str] = Query(
        None, description="Comma-separated list of languages to filter"
    ),
    schedule_days: Optional[str] = Query(
        None, description="Comma-separated days (e.g., 'monday,wednesday')"
    ),
    open_now: bool = Query(False, description="Filter to locations open now"),
    confidence_min: Optional[int] = Query(
        None, ge=0, le=100, description="Minimum confidence score"
    ),
    validation_status: Optional[str] = Query(
        None, description="Validation status filter"
    ),
    has_multiple_sources: Optional[bool] = Query(
        None, description="Filter by source count"
    ),
    # Output format
    format: OutputFormat = Query(
        OutputFormat.FULL, description="Output format: full, compact, or geojson"
    ),
    # Pagination
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(100, ge=1, le=1000, description="Items per page"),
    session: AsyncSession = Depends(get_session),
) -> MapSearchResponse:
    """
    Get map locations optimized for geographic display (HAARRRvest-style).

    This endpoint is optimized for map rendering with location-based queries.
    It returns aggregated location data suitable for displaying on interactive maps.

    ### Primary Use Case - Geographic Queries:
    - **Bounding Box** (RECOMMENDED): Use min_lat, min_lng, max_lat, max_lng for current map view
    - **Radius Search**: Use center_lat, center_lng, and radius (miles) for proximity search
    - **State Filter**: Use state code (e.g., 'CA', 'NY') for state-level data

    ### Output Formats:
    - **compact** (RECOMMENDED for maps): Minimal data for map markers (id, lat, lng, name, confidence)
    - **geojson**: GeoJSON FeatureCollection for map libraries
    - **full**: Complete location data with sources (use sparingly, larger payload)

    ### Quality Filters:
    - `confidence_min=70` - Only high-confidence locations
    - `has_multiple_sources=true` - Verified by multiple sources

    ### Example Map Integration:
    ```javascript
    // Fetch locations for current map view
    const bbox = map.getBounds();
    fetch(`/api/v1/map/search?min_lat=${bbox.south}&max_lat=${bbox.north}&min_lng=${bbox.west}&max_lng=${bbox.east}&format=compact&per_page=500`)
    ```

    ### Performance Notes:
    - Bounding box queries are fastest
    - Use `format=compact` for map display
    - Limit results with `per_page` based on zoom level
    - Text search (q parameter) is simplified and only searches location names
    """

    # Build bounding box if all parameters provided
    bbox = None
    if all(v is not None for v in [min_lat, min_lng, max_lat, max_lng]):
        bbox = (min_lat, min_lng, max_lat, max_lng)

    # Parse comma-separated lists
    services_list = services.split(",") if services else None
    languages_list = languages.split(",") if languages else None
    days_list = schedule_days.split(",") if schedule_days else None

    # Initialize search service
    search_service = MapSearchService(session)

    # Calculate offset from page
    offset = (page - 1) * per_page

    # Execute search
    locations, metadata, total_count = await search_service.search_locations(
        query=q,
        bbox=bbox,
        center_lat=center_lat,
        center_lng=center_lng,
        radius_miles=radius,
        state=state,
        services=services_list,
        languages=languages_list,
        schedule_days=days_list,
        open_now=open_now,
        confidence_min=confidence_min,
        validation_status=validation_status,
        has_multiple_sources=has_multiple_sources,
        output_format=format,
        limit=per_page,
        offset=offset,
    )

    # Calculate pagination info
    has_more = (offset + per_page) < total_count

    return MapSearchResponse(
        metadata=metadata,
        locations=locations,
        total=total_count,
        page=page,
        per_page=per_page,
        has_more=has_more,
    )


@router.get("/locations", response_model=MapLocationsResponse)
async def get_map_locations(
    request: Request,
    # Bounding box parameters
    min_lat: Optional[float] = Query(
        None, ge=-90, le=90, description="Minimum latitude"
    ),
    min_lng: Optional[float] = Query(
        None, ge=-180, le=180, description="Minimum longitude"
    ),
    max_lat: Optional[float] = Query(
        None, ge=-90, le=90, description="Maximum latitude"
    ),
    max_lng: Optional[float] = Query(
        None, ge=-180, le=180, description="Maximum longitude"
    ),
    # Filter parameters
    state: Optional[str] = Query(
        None, max_length=2, description="State code (e.g., 'CA')"
    ),
    confidence_min: Optional[int] = Query(
        None, ge=0, le=100, description="Minimum confidence score"
    ),
    validation_status: Optional[str] = Query(
        None, description="Validation status filter"
    ),
    # Pagination parameters
    page: Optional[int] = Query(None, ge=1, description="Page number (if paginating)"),
    per_page: Optional[int] = Query(None, ge=1, le=1000, description="Items per page"),
    # Aggregation parameters
    clustering_radius: int = Query(
        150, ge=0, le=1000, description="Aggregation radius in meters"
    ),
    session: AsyncSession = Depends(get_session),
) -> MapLocationsResponse:
    """
    Get locations for map display with optional filtering and aggregation.

    This endpoint returns aggregated location data suitable for map visualization.
    Locations within the clustering radius are grouped together with source tracking.

    Use bounding box parameters to fetch only visible locations for better performance.
    """

    # Build bounding box if all parameters provided
    bbox = None
    if all(v is not None for v in [min_lat, min_lng, max_lat, max_lng]):
        bbox = (min_lat, min_lng, max_lat, max_lng)

    # Initialize service
    service = MapDataService(session, grouping_radius_meters=clustering_radius)

    # Fetch locations
    locations_data, metadata = await service.get_locations_for_map(
        bbox=bbox,
        state=state,
        confidence_min=confidence_min,
        validation_status=validation_status,
        limit=per_page if per_page else 10000,
    )

    # Convert to response models
    locations = []
    for loc_data in locations_data:
        # Convert sources
        sources = []
        for source_data in loc_data.get("sources", []):
            schedule = None
            if source_data.get("schedule"):
                schedule = MapSchedule(**source_data["schedule"])

            source = MapSource(
                scraper=source_data["scraper"],
                name=source_data.get("name", ""),
                org=source_data.get("org", ""),
                description=source_data.get("description", ""),
                services=source_data.get("services", ""),
                languages=source_data.get("languages", ""),
                schedule=schedule,
                phone=source_data.get("phone", ""),
                website=source_data.get("website", ""),
                email=source_data.get("email", ""),
                address=source_data.get("address", ""),
                first_seen=source_data.get("first_seen"),
                last_updated=source_data.get("last_updated"),
                confidence_score=source_data.get("confidence_score", 50),
            )
            sources.append(source)

        # Create location
        location = MapLocation(
            id=UUID(loc_data["id"]),
            lat=loc_data["lat"],
            lng=loc_data["lng"],
            name=loc_data["name"],
            org=loc_data.get("org", ""),
            address=loc_data.get("address", ""),
            city=loc_data.get("city", ""),
            state=loc_data.get("state", ""),
            zip=loc_data.get("zip", ""),
            phone=loc_data.get("phone", ""),
            website=loc_data.get("website", ""),
            email=loc_data.get("email", ""),
            description=loc_data.get("description", ""),
            source_count=loc_data.get("source_count", 1),
            sources=sources,
            confidence_score=loc_data.get("confidence_score", 50),
            validation_status=loc_data.get("validation_status", "needs_review"),
            geocoding_source=loc_data.get("geocoding_source", ""),
            location_type=loc_data.get("location_type", ""),
        )
        locations.append(location)

    # Handle pagination if requested
    if page and per_page:
        total_pages = (len(locations) + per_page - 1) // per_page
        start = (page - 1) * per_page
        end = start + per_page
        paginated_locations = locations[start:end]

        return MapLocationsResponse(
            metadata=metadata,
            locations=paginated_locations,
            page=page,
            per_page=per_page,
            total_pages=total_pages,
            has_more=end < len(locations),
        )

    return MapLocationsResponse(metadata=metadata, locations=locations, has_more=False)


@router.get("/clusters", response_model=MapClustersResponse)
async def get_map_clusters(
    request: Request,
    # Bounding box parameters
    min_lat: float = Query(..., ge=-90, le=90, description="Minimum latitude"),
    min_lng: float = Query(..., ge=-180, le=180, description="Minimum longitude"),
    max_lat: float = Query(..., ge=-90, le=90, description="Maximum latitude"),
    max_lng: float = Query(..., ge=-180, le=180, description="Maximum longitude"),
    # Zoom level for clustering
    zoom: int = Query(..., ge=0, le=20, description="Map zoom level"),
    # Clustering parameters
    cluster_radius: int = Query(
        80, ge=0, le=200, description="Cluster radius in pixels"
    ),
    session: AsyncSession = Depends(get_session),
) -> MapClustersResponse:
    """
    Get clustered locations for efficient map display.
    
    This endpoint returns both clusters and individual locations based on zoom level.
    At lower zoom levels, locations are clustered together. At higher zoom levels,
    individual locations are returned.
    
    The clustering algorithm groups nearby locations to prevent overcrowding the map.
    """
    
    from sqlalchemy import text
    import math
    
    # Calculate pixel-to-degree ratio based on zoom level
    # At zoom 0, 256 pixels = 360 degrees
    # Each zoom level doubles the pixels
    pixels_per_degree = (256 * (2 ** zoom)) / 360
    
    # Convert cluster radius from pixels to degrees
    cluster_radius_degrees = cluster_radius / pixels_per_degree
    
    # Query locations within bounding box
    locations_query = """
        SELECT DISTINCT
            l.id,
            l.latitude as lat,
            l.longitude as lng,
            l.name,
            l.confidence_score
        FROM location l
        WHERE l.latitude BETWEEN :min_lat AND :max_lat
          AND l.longitude BETWEEN :min_lng AND :max_lng
          AND l.latitude IS NOT NULL
          AND l.longitude IS NOT NULL
          AND l.is_canonical = true
          AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
        ORDER BY l.confidence_score DESC
        LIMIT 5000
    """
    
    result = await session.execute(
        text(locations_query),
        {
            "min_lat": min_lat,
            "min_lng": min_lng,
            "max_lat": max_lat,
            "max_lng": max_lng,
        }
    )
    
    locations = result.fetchall()
    
    # Perform clustering if zoom level is low enough
    clusters = []
    unclustered_locations = []
    processed = set()
    
    if zoom < 15:  # Only cluster at lower zoom levels
        for i, loc in enumerate(locations):
            if i in processed:
                continue
                
            # Start a new cluster
            cluster_lats = [loc.lat]
            cluster_lngs = [loc.lng]
            cluster_ids = [str(loc.id)]
            cluster_confidence = [loc.confidence_score or 50]
            
            # Find nearby locations to add to cluster
            for j, other in enumerate(locations[i+1:], start=i+1):
                if j in processed:
                    continue
                    
                # Calculate distance
                lat_diff = abs(loc.lat - other.lat)
                lng_diff = abs(loc.lng - other.lng)
                
                if lat_diff <= cluster_radius_degrees and lng_diff <= cluster_radius_degrees:
                    # Add to cluster
                    cluster_lats.append(other.lat)
                    cluster_lngs.append(other.lng)
                    cluster_ids.append(str(other.id))
                    cluster_confidence.append(other.confidence_score or 50)
                    processed.add(j)
            
            if len(cluster_lats) > 1:
                # Create cluster
                avg_lat = sum(cluster_lats) / len(cluster_lats)
                avg_lng = sum(cluster_lngs) / len(cluster_lngs)
                
                # Calculate bounds
                bounds = {
                    "north": max(cluster_lats),
                    "south": min(cluster_lats),
                    "east": max(cluster_lngs),
                    "west": min(cluster_lngs),
                }
                
                clusters.append(MapCluster(
                    id=f"cluster_{i}",
                    lat=avg_lat,
                    lng=avg_lng,
                    count=len(cluster_lats),
                    bounds=bounds,
                    zoom_expand=zoom + 2,
                ))
                processed.add(i)
            else:
                # Single location, add as unclustered
                unclustered_locations.append(MapLocation(
                    id=UUID(str(loc.id)),
                    lat=loc.lat,
                    lng=loc.lng,
                    name=loc.name or "Food Assistance Location",
                    confidence_score=loc.confidence_score or 50,
                    validation_status="verified",
                ))
                processed.add(i)
    else:
        # At high zoom, return all as individual locations
        for loc in locations:
            unclustered_locations.append(MapLocation(
                id=UUID(str(loc.id)),
                lat=loc.lat,
                lng=loc.lng,
                name=loc.name or "Food Assistance Location",
                confidence_score=loc.confidence_score or 50,
                validation_status="verified",
            ))
    
    return MapClustersResponse(
        clusters=clusters,
        locations=unclustered_locations,
        zoom=zoom,
        bounds={
            "north": max_lat,
            "south": min_lat,
            "east": max_lng,
            "west": min_lng,
        },
    )


@router.get("/locations/{location_id}", response_model=MapLocation)
async def get_map_location_detail(
    location_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> MapLocation:
    """
    Get detailed information for a specific location.

    Returns full details including all source data for a single location.
    """

    service = MapDataService(session)

    # Query for specific location
    query = """
        SELECT
            l.id,
            l.latitude as lat,
            l.longitude as lng,
            l.name as location_name,
            o.name as org_name,
            o.website,
            o.email,
            COALESCE(o.description, l.description) as description,
            CONCAT_WS(', ',
                NULLIF(a.address_1, ''),
                NULLIF(a.address_2, ''),
                NULLIF(a.city, ''),
                NULLIF(a.state_province, ''),
                NULLIF(a.postal_code, '')
            ) as address,
            a.city,
            a.state_province as state,
            a.postal_code as zip,
            p.number as phone,
            l.confidence_score,
            l.validation_status,
            l.geocoding_source,
            l.location_type
        FROM location l
        LEFT JOIN address a ON a.location_id = l.id
        LEFT JOIN organization o ON o.id = l.organization_id
        LEFT JOIN phone p ON p.location_id = l.id
        WHERE l.id = :location_id
    """

    from sqlalchemy import text

    result = await session.execute(text(query), {"location_id": str(location_id)})
    row = result.fetchone()

    if not row:
        raise HTTPException(status_code=404, detail="Location not found")

    # Get source information
    sources_query = """
        SELECT
            ls.scraper_id,
            ls.created_at as first_seen,
            ls.updated_at as last_updated
        FROM location_source ls
        WHERE ls.location_id = :location_id
    """

    sources_result = await session.execute(
        text(sources_query), {"location_id": str(location_id)}
    )
    sources_rows = sources_result.fetchall()

    # Build sources list
    sources = []
    for source_row in sources_rows:
        source = MapSource(
            scraper=source_row.scraper_id,
            name=row.location_name or row.org_name or "",
            org=row.org_name or "",
            description=row.description or "",
            services="",  # Would need additional query for services
            languages="",  # Would need additional query for languages
            schedule=None,  # Would need additional query for schedule
            phone=row.phone or "",
            website=row.website or "",
            email=row.email or "",
            address=row.address or "",
            first_seen=(
                source_row.first_seen.isoformat() if source_row.first_seen else None
            ),
            last_updated=(
                source_row.last_updated.isoformat() if source_row.last_updated else None
            ),
            confidence_score=row.confidence_score or 50,
        )
        sources.append(source)

    # Validate state code
    state_value = row.state or ""
    if len(state_value) > 2:
        if len(state_value) >= 2 and state_value[:2].isalpha():
            state_value = state_value[:2].upper()
        else:
            state_value = ""

    return MapLocation(
        id=location_id,
        lat=row.lat,
        lng=row.lng,
        name=row.location_name or row.org_name or "Food Assistance Location",
        org=row.org_name or "",
        address=row.address or "",
        city=row.city or "",
        state=state_value,
        zip=row.zip or "",
        phone=row.phone or "",
        website=row.website or "",
        email=row.email or "",
        description=row.description or "",
        source_count=len(sources),
        sources=sources,
        confidence_score=row.confidence_score or 50,
        validation_status=row.validation_status or "needs_review",
        geocoding_source=row.geocoding_source or "",
        location_type=row.location_type or "",
    )


@router.get("/metadata", response_model=MapMetadata)
async def get_map_metadata(
    session: AsyncSession = Depends(get_session),
) -> MapMetadata:
    """
    Get metadata about the map data.

    Returns statistics and coverage information for all map data.
    """

    from sqlalchemy import text
    from datetime import datetime, UTC

    # Get statistics
    stats_query = """
        SELECT
            COUNT(DISTINCT l.id) as total_locations,
            COUNT(DISTINCT ls.id) as total_sources,
            COUNT(DISTINCT a.state_province) as states_covered
        FROM location l
        LEFT JOIN location_source ls ON ls.location_id = l.id
        LEFT JOIN address a ON a.location_id = l.id
        WHERE l.latitude IS NOT NULL
          AND l.longitude IS NOT NULL
          AND l.is_canonical = true
          AND (l.validation_status IS NULL OR l.validation_status != 'rejected')
    """

    result = await session.execute(text(stats_query))
    stats = result.fetchone()

    # Get multi-source locations count
    multi_query = """
        SELECT COUNT(*) as multi_source_count
        FROM (
            SELECT location_id, COUNT(*) as source_count
            FROM location_source
            GROUP BY location_id
            HAVING COUNT(*) > 1
        ) as multi
    """

    multi_result = await session.execute(text(multi_query))
    multi_row = multi_result.fetchone()
    multi_count = multi_row.multi_source_count if multi_row else 0

    if not stats:
        # Return default values if no stats available
        return MapMetadata(
            generated=datetime.now(UTC).isoformat(),
            total_locations=0,
            total_source_records=0,
            multi_source_locations=0,
            states_covered=0,
            coverage="0 US states/territories",
            source="Pantry Pirate Radio HSDS API",
            format_version="4.0",
            export_method="API Query",
            aggregation_radius_meters=150,
        )

    return MapMetadata(
        generated=datetime.now(UTC).isoformat(),
        total_locations=stats.total_locations or 0,
        total_source_records=stats.total_sources or 0,
        multi_source_locations=multi_count,
        states_covered=stats.states_covered or 0,
        coverage=f"{stats.states_covered or 0} US states/territories",
        source="Pantry Pirate Radio HSDS API",
        format_version="4.0",
        export_method="API Query",
        aggregation_radius_meters=150,
    )


@router.get("/states", response_model=MapStatesResponse)
async def get_states_coverage(
    session: AsyncSession = Depends(get_session),
) -> MapStatesResponse:
    """
    Get coverage information for all states.

    Returns a list of states with location counts and bounding boxes.
    """

    service = MapDataService(session)
    states = await service.get_states_coverage()

    return MapStatesResponse(total_states=len(states), states=states)


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
    ip: Optional[str] = Query(None, description="IP address to geolocate (defaults to client IP)"),
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
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip() or
            request.headers.get("X-Real-IP") or
            request.client.host
        )
    
    # Skip localhost/private IPs
    if client_ip in ["127.0.0.1", "localhost", "::1"] or client_ip.startswith("192.168.") or client_ip.startswith("10."):
        # Return center of US for local development
        return GeoLocationResponse(
            lat=39.8283,
            lng=-98.5795,
            city="Geographic Center",
            state="US",
            country="US",
            ip=client_ip,
            source="default"
        )
    
    try:
        # Try ip-api.com first (free, no key required, 45 requests per minute)
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"http://ip-api.com/json/{client_ip}",
                params={"fields": "status,country,countryCode,region,regionName,city,zip,lat,lon,query"},
                timeout=5.0
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
                        source="ip-api"
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
        ip=client_ip,
        source="fallback"
    )
