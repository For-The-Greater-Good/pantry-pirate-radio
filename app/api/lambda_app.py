"""Lambda-optimized FastAPI application.

Creates a FastAPI app without Redis, RQ, or LLM startup dependencies.
Metrics are handled by CloudWatch instead of Prometheus.
"""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette import status

from app.api.v1.router import router as v1_router
from app.core.config import Settings
from app.middleware.correlation import CorrelationMiddleware
from app.middleware.errors import ErrorHandlingMiddleware
from app.middleware.security import SecurityHeadersMiddleware

_logger = logging.getLogger(__name__)

try:
    settings = Settings()
except Exception as exc:
    _logger.critical(
        "Failed to initialise Settings — check Secrets Manager access, "
        "IAM permissions, and DATABASE_SECRET_ARN configuration: %s",
        exc,
    )
    raise

app = FastAPI(
    title=settings.app_name,
    description="Food security data API using HSDS specification",
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=JSONResponse,
    redirect_slashes=True,
)

# Middleware (no MetricsMiddleware — Lambda uses CloudWatch)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "HEAD", "OPTIONS"],
    allow_headers=["Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationMiddleware)
app.add_middleware(ErrorHandlingMiddleware)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to docs."""
    return RedirectResponse(
        url="/api/docs", status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


app.include_router(v1_router, prefix=settings.api_prefix)
