"""API v1 router module."""

import os
from datetime import datetime
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Response, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.db import get_session
from app.llm.providers.openai import OpenAIConfig, OpenAIProvider

# Override settings for tests
if os.getenv("TESTING") == "true":
    settings.LLM_MODEL_NAME = "test-model"
    settings.LLM_PROVIDER = "openai"
router = APIRouter(default_response_class=JSONResponse)

# Always include API routers for comprehensive documentation
from app.api.v1.organizations import router as organizations_router
from app.api.v1.locations import router as locations_router
from app.api.v1.services import router as services_router
from app.api.v1.service_at_location import router as service_at_location_router
from app.api.v1.taxonomies import router as taxonomies_router
from app.api.v1.taxonomy_terms import router as taxonomy_terms_router
from app.api.v1.map import router as map_router

# Define locations/export-simple BEFORE including locations router to avoid conflicts
@router.get("/locations/export-simple")
async def export_simple_priority(
    session: AsyncSession = Depends(get_session),
    grouping_radius: Optional[int] = Query(
        None,
        description="Radius in meters for grouping nearby locations. Set to 0 to disable grouping. Defaults to MAP_GROUPING_RADIUS_METERS env var (150m)",
        ge=0,
        le=10000
    )
) -> Dict[str, Any]:
    """
    Export all locations in a simplified format for mobile app caching.
    Returns data compatible with Flutter app's CompactPantryLocation model.
    
    Args:
        grouping_radius: Optional radius in meters for deduplicating nearby locations.
                        Defaults to MAP_GROUPING_RADIUS_METERS env var (typically 150m).
                        Set to 0 to disable deduplication.
    """
    try:
        # Get grouping radius from query param or environment variable
        if grouping_radius is None:
            grouping_radius = int(os.getenv("MAP_GROUPING_RADIUS_METERS", "150"))
        
        # Convert meters to approximate degrees for ST_ClusterDBSCAN
        # At the equator, 1 degree latitude = ~111,000 meters
        eps = grouping_radius / 111000.0 if grouping_radius > 0 else None
        
        # Main query for location data with optional clustering
        if eps and grouping_radius > 0:
            # Query with PostGIS clustering for deduplication
            location_query = text("""
                WITH clustered_locations AS (
                    SELECT DISTINCT ON (l.id)
                        l.id,
                        l.latitude as lat,
                        l.longitude as lng,
                        l.name,
                        o.name as org,
                        a.address_1,
                        a.city,
                        a.state_province as state,
                        a.postal_code as zip,
                        p.number as phone,
                        l.url as website,
                        l.description,
                        l.confidence_score,
                        l.validation_status,
                        l.geocoding_source,
                        l.is_canonical,
                        ST_ClusterDBSCAN(
                            ST_SetSRID(ST_MakePoint(l.longitude, l.latitude), 4326),
                            eps := :eps,
                            minpoints := 1
                        ) OVER() as cluster_id
                    FROM location l
                    LEFT JOIN organization o ON l.organization_id = o.id
                    LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical'
                    LEFT JOIN phone p ON p.location_id = l.id
                    WHERE l.validation_status != 'rejected' OR l.validation_status IS NULL
                    ORDER BY l.id
                ),
                cluster_representatives AS (
                    SELECT DISTINCT ON (cluster_id)
                        id,
                        lat,
                        lng,
                        name,
                        org,
                        address_1,
                        city,
                        state,
                        zip,
                        phone,
                        website,
                        description,
                        confidence_score,
                        validation_status,
                        geocoding_source,
                        cluster_id
                    FROM clustered_locations
                    WHERE cluster_id IS NOT NULL
                    ORDER BY cluster_id, 
                             CASE WHEN is_canonical THEN 0 ELSE 1 END,
                             confidence_score DESC NULLS LAST,
                             id
                )
                SELECT * FROM cluster_representatives
                UNION ALL
                SELECT 
                    id, lat, lng, name, org, address_1, city, state, zip,
                    phone, website, description, confidence_score,
                    validation_status, geocoding_source, NULL as cluster_id
                FROM clustered_locations
                WHERE cluster_id IS NULL
            """)
            
            result = await session.execute(location_query, {"eps": eps})
        else:
            # Query without clustering (original behavior)
            location_query = text("""
                SELECT DISTINCT ON (l.id)
                    l.id,
                    l.latitude as lat,
                    l.longitude as lng,
                    l.name,
                    o.name as org,
                    a.address_1,
                    a.city,
                    a.state_province as state,
                    a.postal_code as zip,
                    p.number as phone,
                    l.url as website,
                    l.description,
                    l.confidence_score,
                    l.validation_status,
                    l.geocoding_source
                FROM location l
                LEFT JOIN organization o ON l.organization_id = o.id
                LEFT JOIN address a ON a.location_id = l.id AND a.address_type = 'physical'
                LEFT JOIN phone p ON p.location_id = l.id
                WHERE l.validation_status != 'rejected' OR l.validation_status IS NULL
                ORDER BY l.id
            """)
            
            result = await session.execute(location_query)
        
        locations_raw = result.fetchall()
        
        # Get all location IDs for batch queries
        location_ids = [row.id for row in locations_raw]
        
        # Query schedules for all locations
        schedule_dict = {}
        if location_ids:
            schedule_query = text("""
                SELECT 
                    s.location_id,
                    s.freq,
                    s.byday,
                    s.opens_at,
                    s.closes_at,
                    s.description,
                    s.valid_from,
                    s.valid_to
                FROM schedule s
                WHERE s.location_id = ANY(:location_ids)
                ORDER BY s.location_id, s.opens_at
            """)
            
            schedule_result = await session.execute(
                schedule_query, 
                {"location_ids": location_ids}
            )
            
            for row in schedule_result:
                if row.location_id not in schedule_dict:
                    schedule_dict[row.location_id] = {
                        "freq": row.freq,
                        "byday": row.byday,
                        "opens_at": str(row.opens_at) if row.opens_at else None,
                        "closes_at": str(row.closes_at) if row.closes_at else None,
                        "description": row.description,
                        "valid_from": row.valid_from.isoformat() if row.valid_from else None,
                        "valid_to": row.valid_to.isoformat() if row.valid_to else None
                    }
        
        # Query services for all locations
        services_dict = {}
        if location_ids:
            services_query = text("""
                SELECT 
                    sal.location_id,
                    sv.name as service_name
                FROM service_at_location sal
                JOIN service sv ON sal.service_id = sv.id
                WHERE sal.location_id = ANY(:location_ids)
                ORDER BY sal.location_id, sv.name
            """)
            
            services_result = await session.execute(
                services_query,
                {"location_ids": location_ids}
            )
            
            for row in services_result:
                if row.location_id not in services_dict:
                    services_dict[row.location_id] = []
                services_dict[row.location_id].append(row.service_name)
        
        # Count distinct states
        state_query = text("""
            SELECT COUNT(DISTINCT a.state_province) as state_count
            FROM location l
            JOIN address a ON a.location_id = l.id
            WHERE (l.validation_status != 'rejected' OR l.validation_status IS NULL)
            AND a.state_province IS NOT NULL
        """)
        
        state_result = await session.execute(state_query)
        states_covered = state_result.scalar() or 0
        
        # Format locations for response
        locations = []
        for row in locations_raw:
            # Build address string
            address_parts = []
            if row.address_1:
                address_parts.append(row.address_1)
            if row.city:
                address_parts.append(row.city)
            if row.state:
                address_parts.append(row.state)
            if row.zip:
                address_parts.append(row.zip)
            
            location_data = {
                "id": row.id,
                "lat": float(row.lat) if row.lat else 0.0,
                "lng": float(row.lng) if row.lng else 0.0,
                "name": row.name or "Unknown",
                "org": row.org or row.name or "",
                "address": ", ".join(address_parts),
                "city": row.city,
                "state": row.state,
                "zip": row.zip,
                "phone": row.phone,
                "website": row.website,
                "email": None,  # Email not in current schema
                "description": row.description,
                "confidence_score": row.confidence_score or 50,
                "validation_status": row.validation_status or "needs_review",
                "services": services_dict.get(row.id, []),
                "schedule": schedule_dict.get(row.id)
            }
            locations.append(location_data)
        
        # Add deduplication info to metadata
        metadata = {
            "generated": datetime.utcnow().isoformat(),
            "total_locations": len(locations),
            "states_covered": states_covered,
            "format_version": "1.0",
            "source": "Pantry Pirate Radio API",
            "deduplication": {
                "enabled": grouping_radius > 0,
                "radius_meters": grouping_radius
            }
        }
        
        # If deduplication was applied, calculate how many locations were grouped
        if grouping_radius > 0:
            # Count original locations before deduplication
            count_query = text("""
                SELECT COUNT(*) as total_before_dedup
                FROM location l
                WHERE l.validation_status != 'rejected' OR l.validation_status IS NULL
            """)
            count_result = await session.execute(count_query)
            total_before = count_result.scalar() or 0
            metadata["deduplication"]["locations_before"] = total_before
            metadata["deduplication"]["locations_after"] = len(locations)
            metadata["deduplication"]["locations_grouped"] = total_before - len(locations)
        
        return {
            "metadata": metadata,
            "locations": locations
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error fetching location data: {str(e)}"
        )

router.include_router(organizations_router)
router.include_router(locations_router)
router.include_router(services_router)
router.include_router(service_at_location_router)
router.include_router(taxonomies_router)
router.include_router(taxonomy_terms_router)
router.include_router(map_router)




@router.get("/")
async def get_api_metadata() -> dict[str, str]:
    """
    Get API metadata including HSDS version and profile information.

    Returns information about this API and its relationship with HSDS.
    """
    return {
        "version": "3.1.1",
        "profile": "https://docs.openhumanservices.org/hsds/",
        "openapi_url": "/openapi.json",
        "documentation_url": "/docs",
        "api_status": "healthy",
        "implementation": "Pantry Pirate Radio HSDS API",
    }


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(
        content=generate_latest().decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )


# Health check endpoint


@router.get("/health")
async def health_check(request: Request) -> dict[str, str]:
    """
    Health check endpoint.

    Returns
    -------
        Dict containing health status information
    """
    return {
        "status": "healthy",
        "version": settings.version,
        "correlation_id": request.state.correlation_id,
    }


@router.get("/health/llm")
async def llm_health_check(request: Request) -> dict[str, str]:
    """
    LLM health check endpoint.

    Returns
    -------
        Dict containing LLM provider health status information
    """
    # Create provider based on configuration
    if settings.LLM_PROVIDER == "openai":
        config = OpenAIConfig(
            model_name=settings.LLM_MODEL_NAME,
            temperature=settings.LLM_TEMPERATURE,
            max_tokens=settings.LLM_MAX_TOKENS,
        )
        provider = OpenAIProvider(config)
    else:
        return {
            "status": "unhealthy",
            "error": f"Unsupported LLM provider: {settings.LLM_PROVIDER}",
            "correlation_id": request.state.correlation_id,
        }

    try:
        # Test LLM provider connection
        await provider.health_check()
        return {
            "status": "healthy",
            "provider": settings.LLM_PROVIDER,
            "model": settings.LLM_MODEL_NAME,
            "correlation_id": request.state.correlation_id,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "correlation_id": request.state.correlation_id,
        }


@router.get("/health/redis")
async def redis_health_check(request: Request) -> dict[str, str]:
    """
    Redis health check endpoint.

    Returns
    -------
        Dict containing Redis health status information
    """
    redis = Redis.from_url(settings.REDIS_URL)
    try:
        # Test Redis connection
        await redis.ping()
        info = await redis.info()
        return {
            "status": "healthy",
            "redis_version": str(info["redis_version"]),
            "connected_clients": str(info["connected_clients"]),
            "used_memory_human": str(info["used_memory_human"]),
            "correlation_id": request.state.correlation_id,
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "correlation_id": request.state.correlation_id,
        }
    finally:
        await redis.close()


@router.get("/health/db")
async def db_health_check(request: Request) -> dict[str, str]:
    """
    Database health check endpoint.

    Returns
    -------
        Dict containing database health status information
    """
    try:
        # Use a synchronous connection for the health check
        from sqlalchemy import create_engine

        # Create engine with standard psycopg2 dialect
        engine = create_engine(
            settings.DATABASE_URL,
            echo=False,
            pool_pre_ping=True,
        )

        with engine.connect() as conn:
            # Check PostgreSQL version
            result = conn.execute(text("SELECT version()"))
            version = result.scalar_one()

            # Check PostGIS version
            result = conn.execute(text("SELECT postgis_full_version()"))
            postgis_version = result.scalar_one()

            return {
                "status": "healthy",
                "database": "postgresql",
                "version": str(version),
                "postgis_version": str(postgis_version),
                "correlation_id": request.state.correlation_id,
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "correlation_id": request.state.correlation_id,
        }
