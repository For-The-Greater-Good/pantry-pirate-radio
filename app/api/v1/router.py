"""API v1 router module."""

import os

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import settings
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

router.include_router(organizations_router)
router.include_router(locations_router)
router.include_router(services_router)
router.include_router(service_at_location_router)


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
