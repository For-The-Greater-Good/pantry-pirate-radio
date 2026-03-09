"""Map clusters endpoint for efficient map display at various zoom levels."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.map.models import (
    MapLocation,
    MapCluster,
    MapClustersResponse,
)
from app.core.db import get_session

router = APIRouter(prefix="/map", tags=["map"])


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

    # Calculate pixel-to-degree ratio based on zoom level
    # At zoom 0, 256 pixels = 360 degrees
    # Each zoom level doubles the pixels
    pixels_per_degree = (256 * (2**zoom)) / 360

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
        },
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
            for j, other in enumerate(locations[i + 1 :], start=i + 1):
                if j in processed:
                    continue

                # Calculate distance
                lat_diff = abs(loc.lat - other.lat)
                lng_diff = abs(loc.lng - other.lng)

                if (
                    lat_diff <= cluster_radius_degrees
                    and lng_diff <= cluster_radius_degrees
                ):
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

                clusters.append(
                    MapCluster(
                        id=f"cluster_{i}",
                        lat=avg_lat,
                        lng=avg_lng,
                        count=len(cluster_lats),
                        bounds=bounds,
                        zoom_expand=zoom + 2,
                    )
                )
                processed.add(i)
            else:
                # Single location, add as unclustered
                unclustered_locations.append(
                    MapLocation(
                        id=UUID(str(loc.id)),
                        lat=loc.lat,
                        lng=loc.lng,
                        name=loc.name or "Food Assistance Location",
                        confidence_score=loc.confidence_score or 50,
                        validation_status="verified",
                    )
                )
                processed.add(i)
    else:
        # At high zoom, return all as individual locations
        for loc in locations:
            unclustered_locations.append(
                MapLocation(
                    id=UUID(str(loc.id)),
                    lat=loc.lat,
                    lng=loc.lng,
                    name=loc.name or "Food Assistance Location",
                    confidence_score=loc.confidence_score or 50,
                    validation_status="verified",
                )
            )

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
