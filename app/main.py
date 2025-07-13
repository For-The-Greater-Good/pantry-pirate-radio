"""Main FastAPI application module."""

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette import status

from app.api.v1.router import router as v1_router
from app.core.config import Settings
from app.core.events import create_start_app_handler, create_stop_app_handler
from app.middleware.correlation import CorrelationMiddleware
from app.middleware.errors import ErrorHandlingMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.security import SecurityHeadersMiddleware

# Load settings
settings = Settings()

# Initialize FastAPI app with no default routes or exception handlers
app = FastAPI(
    title=settings.app_name,
    description="Food security data aggregation system using HSDS",
    version=settings.version,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    default_response_class=JSONResponse,
    redirect_slashes=True,  # Enable automatic trailing slash redirection
)

# Add middleware in order (inside -> out):
# 1. CORS (outermost)
# 2. Security headers
# 3. Correlation (adds request ID)
# 4. Metrics (tracks all requests)
# 5. Error handling (innermost - handles all errors)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CorrelationMiddleware)
app.add_middleware(MetricsMiddleware)
app.add_middleware(ErrorHandlingMiddleware)

# Metrics endpoint


@app.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    """Expose Prometheus metrics."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Root redirect to docs


@app.get("/", include_in_schema=False)
async def root_redirect() -> Response:
    """Redirect root path to docs."""
    return RedirectResponse(
        url="/api/docs", status_code=status.HTTP_307_TEMPORARY_REDIRECT
    )


# Event handlers
app.add_event_handler("startup", create_start_app_handler(app))
app.add_event_handler("shutdown", create_stop_app_handler(app))


# Include routers - mount v1 routes under prefix
app.include_router(v1_router, prefix=settings.api_prefix)
