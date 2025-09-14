"""Service layer for Consumer API endpoints."""

import logging
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, UTC
from uuid import UUID

from sqlalchemy import text, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.consumer.models import (
    LocationPin,
    GroupedPin,
    MapPinsMetadata,
    SourceData,
    CanonicalData,
    LocationDetail,
    NearbyLocation,
)

logger = logging.getLogger(__name__)


class ConsumerLocationService:
    """Service for fetching and processing location data for consumers."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_map_pins(
        self,
        min_lat: float,
        max_lat: float,
        min_lng: float,
        max_lng: float,
        grouping_radius: int = 150,
        min_confidence: Optional[int] = None,
        open_now: Optional[bool] = None,
        services: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], MapPinsMetadata]:
        """
        Get location pins for map display with dynamic grouping.

        Args:
            min_lat, max_lat, min_lng, max_lng: Viewport boundaries
            grouping_radius: Radius in meters for clustering (0 to disable)
            min_confidence: Minimum confidence score filter
            open_now: Filter for currently open locations
            services: Filter by service types

        Returns:
            Tuple of pins list and metadata
        """
        # Build the base query for locations in viewport
        base_query = """
            WITH viewport_locations AS (
                SELECT
                    l.id,
                    l.latitude,
                    l.longitude,
                    l.name,
                    l.confidence_score,
                    COUNT(DISTINCT ls.scraper_id) as source_count,
                    EXISTS(
                        SELECT 1 FROM schedule s
                        JOIN service_at_location sal ON s.service_id = sal.service_id
                        WHERE sal.location_id = l.id
                    ) as has_schedule
                FROM location l
                LEFT JOIN location_source ls ON ls.location_id = l.id
                WHERE l.latitude BETWEEN :min_lat AND :max_lat
                  AND l.longitude BETWEEN :min_lng AND :max_lng
                  AND l.is_canonical = true
                  AND (l.validation_status != 'rejected' OR l.validation_status IS NULL)
        """

        params = {
            "min_lat": min_lat,
            "max_lat": max_lat,
            "min_lng": min_lng,
            "max_lng": max_lng,
        }

        # Add optional filters
        if min_confidence is not None:
            base_query += " AND l.confidence_score >= :min_confidence"
            params["min_confidence"] = min_confidence

        if services:
            # Filter by services (requires join with service tables)
            base_query += """
                AND EXISTS (
                    SELECT 1 FROM service_at_location sal
                    JOIN service s ON s.id = sal.service_id
                    WHERE sal.location_id = l.id
                      AND s.name IN :services
                )
            """
            params["services"] = tuple(services)

        base_query += """
                GROUP BY l.id, l.latitude, l.longitude, l.name, l.confidence_score
                LIMIT 1000
            )
        """

        # Apply clustering if radius > 0
        if grouping_radius > 0:
            # Convert meters to degrees (approximate)
            # 1 degree latitude ~ 111,000 meters
            eps_degrees = grouping_radius / 111000.0

            query = base_query + f"""
            , clustered AS (
                SELECT *,
                    ST_ClusterDBSCAN(
                        ST_SetSRID(ST_MakePoint(longitude, latitude), 4326),
                        eps := {eps_degrees},
                        minpoints := 1
                    ) OVER() as cluster_id
                FROM viewport_locations
            )
            SELECT
                cluster_id,
                json_agg(
                    json_build_object(
                        'id', id,
                        'lat', latitude,
                        'lng', longitude,
                        'name', name,
                        'confidence', confidence_score,
                        'source_count', source_count,
                        'has_schedule', has_schedule
                    )
                ) as locations
            FROM clustered
            GROUP BY cluster_id
            """
        else:
            # No clustering - return individual locations
            query = base_query + """
            SELECT
                id,
                latitude as lat,
                longitude as lng,
                name,
                confidence_score as confidence,
                source_count,
                has_schedule
            FROM viewport_locations
            """

        # Execute query
        result = await self.session.execute(text(query), params)
        rows = result.fetchall()

        # Process results into pins
        pins = []
        total_locations = 0

        if grouping_radius > 0:
            # Process clustered results
            for row in rows:
                locations = row.locations
                total_locations += len(locations)

                if len(locations) == 1:
                    # Single location pin
                    loc = locations[0]
                    pins.append({
                        "type": "single",
                        "lat": loc["lat"],
                        "lng": loc["lng"],
                        "location_ids": [loc["id"]],
                        "name": loc["name"],
                        "confidence": loc["confidence"],
                        "source_count": loc["source_count"],
                        "has_schedule": loc["has_schedule"],
                        "open_now": None  # Would require schedule evaluation
                    })
                else:
                    # Grouped pin
                    lats = [loc["lat"] for loc in locations]
                    lngs = [loc["lng"] for loc in locations]
                    avg_confidence = sum(loc["confidence"] for loc in locations) / len(locations)
                    total_sources = sum(loc["source_count"] for loc in locations)

                    # Find most common name
                    names = [loc["name"] for loc in locations if loc["name"]]
                    primary_name = max(set(names), key=names.count) if names else None

                    pins.append({
                        "type": "group",
                        "lat": sum(lats) / len(lats),  # Centroid
                        "lng": sum(lngs) / len(lngs),
                        "location_ids": [loc["id"] for loc in locations],
                        "name": f"{len(locations)} locations",
                        "primary_name": primary_name,
                        "confidence_avg": int(avg_confidence),
                        "source_count": total_sources,
                        "bounds": {
                            "north": max(lats),
                            "south": min(lats),
                            "east": max(lngs),
                            "west": min(lngs),
                        }
                    })
        else:
            # Process individual results
            for row in rows:
                total_locations += 1
                pins.append({
                    "type": "single",
                    "lat": float(row.lat),
                    "lng": float(row.lng),
                    "location_ids": [str(row.id)],
                    "name": row.name,
                    "confidence": row.confidence or 50,
                    "source_count": row.source_count or 1,
                    "has_schedule": row.has_schedule or False,
                    "open_now": None
                })

        # Create metadata
        metadata = MapPinsMetadata(
            total_pins=len(pins),
            total_locations=total_locations,
            viewport_bounds={
                "north": max_lat,
                "south": min_lat,
                "east": max_lng,
                "west": min_lng,
            },
            grouping_radius=grouping_radius,
            timestamp=datetime.now(UTC),
        )

        return pins, metadata

    async def get_multiple_locations(
        self,
        location_ids: List[str],
        include_sources: bool = True,
        include_schedule: bool = True,
    ) -> List[LocationDetail]:
        """
        Fetch detailed information for multiple locations.

        Args:
            location_ids: List of location UUIDs (max 100)
            include_sources: Include source data
            include_schedule: Include schedule data

        Returns:
            List of LocationDetail objects
        """
        if len(location_ids) > 100:
            raise ValueError("Maximum 100 locations can be fetched at once")

        # Query for location details
        query = """
            SELECT
                l.id,
                l.name,
                l.alternate_name,
                l.description,
                l.latitude,
                l.longitude,
                l.confidence_score,
                l.validation_status,
                l.geocoding_source,
                a.address_1,
                a.address_2,
                a.city,
                a.state_province,
                a.postal_code,
                a.country,
                p.number as phone,
                o.email,
                o.website
            FROM location l
            LEFT JOIN address a ON a.location_id = l.id
            LEFT JOIN organization o ON o.id = l.organization_id
            LEFT JOIN LATERAL (
                SELECT number FROM phone
                WHERE location_id = l.id
                LIMIT 1
            ) p ON true
            WHERE l.id = ANY(:location_ids)
        """

        result = await self.session.execute(
            text(query),
            {"location_ids": location_ids}
        )
        location_rows = result.fetchall()

        locations = []
        for row in location_rows:
            # Build canonical data
            canonical = CanonicalData(
                name=row.name,
                alternate_name=row.alternate_name,
                description=row.description,
                address={
                    "street": row.address_1 or "",
                    "city": row.city or "",
                    "state": row.state_province or "",
                    "zip": row.postal_code or "",
                    "country": row.country or "US",
                } if row.address_1 else None,
                coordinates={
                    "lat": float(row.latitude) if row.latitude else None,
                    "lng": float(row.longitude) if row.longitude else None,
                    "geocoding_source": row.geocoding_source,
                    "confidence": row.confidence_score or 50,
                },
                contact={
                    "phone": row.phone or None,
                    "email": row.email or None,
                    "website": row.website or None,
                } if any([row.phone, row.email, row.website]) else None,
                confidence=row.confidence_score or 50,
                validation_status=row.validation_status,
            )

            # Get source data if requested
            sources = []
            if include_sources:
                source_query = """
                    SELECT
                        ls.scraper_id,
                        ls.created_at as first_seen,
                        ls.updated_at as last_updated,
                        ls.name,
                        ls.description,
                        a2.address_1,
                        a2.city,
                        a2.state_province,
                        a2.postal_code,
                        p2.number as phone,
                        o2.website,
                        o2.email
                    FROM location_source ls
                    LEFT JOIN location l2 ON l2.id = ls.location_id
                    LEFT JOIN address a2 ON a2.location_id = l2.id
                    LEFT JOIN organization o2 ON o2.id = l2.organization_id
                    LEFT JOIN LATERAL (
                        SELECT number FROM phone WHERE location_id = l2.id LIMIT 1
                    ) p2 ON true
                    WHERE ls.location_id = :location_id
                """

                source_result = await self.session.execute(
                    text(source_query),
                    {"location_id": str(row.id)}
                )
                source_rows = source_result.fetchall()

                for src_row in source_rows:
                    address = None
                    if src_row.address_1:
                        address = f"{src_row.address_1}, {src_row.city}, {src_row.state_province} {src_row.postal_code}".strip()

                    sources.append(SourceData(
                        scraper_id=src_row.scraper_id,
                        last_updated=src_row.last_updated,
                        first_seen=src_row.first_seen,
                        name=src_row.name,
                        address=address,
                        phone=src_row.phone,
                        website=src_row.website,
                        email=src_row.email,
                        confidence=50,  # Default confidence for sources
                    ))

            # Get schedule data if requested
            schedule_merged = None
            if include_schedule:
                schedule_query = """
                    SELECT
                        s.opens_at,
                        s.closes_at,
                        s.byday,
                        s.freq,
                        s.description
                    FROM schedule s
                    JOIN service_at_location sal ON s.service_id = sal.service_id
                    WHERE sal.location_id = :location_id
                    LIMIT 5
                """

                schedule_result = await self.session.execute(
                    text(schedule_query),
                    {"location_id": str(row.id)}
                )
                schedule_rows = schedule_result.fetchall()

                if schedule_rows:
                    # Simple merge - just take first schedule for now
                    sched = schedule_rows[0]
                    schedule_merged = {
                        "opens_at": str(sched.opens_at) if sched.opens_at else None,
                        "closes_at": str(sched.closes_at) if sched.closes_at else None,
                        "byday": sched.byday,
                        "freq": sched.freq,
                        "description": sched.description,
                    }

            locations.append(LocationDetail(
                id=str(row.id),
                canonical=canonical,
                sources=sources,
                schedule_merged=schedule_merged,
            ))

        return locations

    async def get_single_location(
        self,
        location_id: UUID,
        include_nearby: bool = False,
        nearby_radius: int = 500,
        include_history: bool = False,
    ) -> Dict[str, Any]:
        """
        Get comprehensive details for a single location.

        Args:
            location_id: Location UUID
            include_nearby: Include nearby locations
            nearby_radius: Radius in meters for nearby locations
            include_history: Include version history

        Returns:
            Dictionary with location details and optional nearby/history data
        """
        # Get main location details using the multi-fetch method
        locations = await self.get_multiple_locations(
            [str(location_id)],
            include_sources=True,
            include_schedule=True,
        )

        if not locations:
            return None

        location = locations[0]
        result = {"location": location}

        # Get nearby locations if requested
        if include_nearby:
            # Get the location's coordinates
            coords_query = """
                SELECT latitude, longitude
                FROM location
                WHERE id = :location_id
            """
            coords_result = await self.session.execute(
                text(coords_query),
                {"location_id": str(location_id)}
            )
            coords = coords_result.fetchone()

            if coords and coords.latitude and coords.longitude:
                # Find nearby locations using PostGIS
                nearby_query = """
                    SELECT
                        l.id,
                        l.name,
                        a.address_1,
                        a.city,
                        ST_Distance(
                            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                            ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326)::geography
                        ) as distance_meters,
                        CASE
                            WHEN l.latitude > :lat AND l.longitude > :lng THEN 'NE'
                            WHEN l.latitude > :lat AND l.longitude < :lng THEN 'NW'
                            WHEN l.latitude < :lat AND l.longitude > :lng THEN 'SE'
                            WHEN l.latitude < :lat AND l.longitude < :lng THEN 'SW'
                            WHEN l.latitude > :lat THEN 'N'
                            WHEN l.latitude < :lat THEN 'S'
                            WHEN l.longitude > :lng THEN 'E'
                            ELSE 'W'
                        END as bearing
                    FROM location l
                    LEFT JOIN address a ON a.location_id = l.id
                    WHERE l.id != :location_id
                      AND l.is_canonical = true
                      AND (l.validation_status != 'rejected' OR l.validation_status IS NULL)
                      AND ST_DWithin(
                          ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326)::geography,
                          ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography,
                          :radius
                      )
                    ORDER BY distance_meters
                    LIMIT 10
                """

                nearby_result = await self.session.execute(
                    text(nearby_query),
                    {
                        "location_id": str(location_id),
                        "lat": float(coords.latitude),
                        "lng": float(coords.longitude),
                        "radius": nearby_radius,
                    }
                )
                nearby_rows = nearby_result.fetchall()

                nearby_locations = []
                for nb_row in nearby_rows:
                    address = f"{nb_row.address_1}, {nb_row.city}" if nb_row.address_1 else None
                    nearby_locations.append(NearbyLocation(
                        id=str(nb_row.id),
                        name=nb_row.name,
                        distance_meters=float(nb_row.distance_meters),
                        bearing=nb_row.bearing,
                        address=address,
                    ))

                result["nearby_locations"] = nearby_locations

        # Version history would be implemented here if needed
        if include_history:
            result["version_history"] = []  # Placeholder for future implementation

        return result