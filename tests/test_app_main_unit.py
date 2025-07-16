"""Unit tests for app.main module."""

import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import CONTENT_TYPE_LATEST


def test_main_module_import() -> None:
    """Test that the main module can be imported successfully."""
    import app.main

    assert hasattr(app.main, "app")
    assert isinstance(app.main.app, FastAPI)


def test_app_configuration() -> None:
    """Test FastAPI app configuration."""
    from app.main import app

    # Test app metadata
    assert app.title == "Pantry Pirate Radio"
    assert "Food security data aggregation system" in app.description
    assert app.version == "0.1.0"
    assert app.docs_url == "/docs"
    assert app.redoc_url == "/redoc"
    assert app.openapi_url == "/openapi.json"


def test_middleware_configuration() -> None:
    """Test middleware is properly configured."""
    from app.main import app

    # Check that middleware is added
    middleware_stack = app.user_middleware

    # Should have CORS, Security, Correlation, Metrics, Error handling middleware
    assert len(middleware_stack) >= 5

    # Get middleware classes
    middleware_classes = []
    for middleware_item in middleware_stack:
        if hasattr(middleware_item, "cls"):
            middleware_classes.append(middleware_item.cls)
        else:
            # Handle different FastAPI versions
            middleware_classes.append(type(middleware_item))

    # CORS should be in the middleware stack
    assert CORSMiddleware in middleware_classes


def test_routes_configuration() -> None:
    """Test routes are properly configured."""
    from app.main import app

    # Check that routes exist
    routes = [route.path for route in app.routes if hasattr(route, "path")]

    assert "/" in routes
    assert "/metrics" in routes
    assert any(route.startswith("/api/") for route in routes)


@pytest.mark.asyncio
async def test_metrics_endpoint_function() -> None:
    """Test the metrics endpoint function directly."""
    from app.main import metrics

    response = await metrics()

    assert response.media_type == CONTENT_TYPE_LATEST
    assert len(response.body) > 0


@pytest.mark.asyncio
async def test_root_redirect_function() -> None:
    """Test the root redirect function directly."""
    from app.main import root_redirect

    response = await root_redirect()

    assert response.status_code == 307
    assert response.headers["location"] == "/api/docs"


def test_settings_import() -> None:
    """Test that settings are properly imported and used."""
    from app.main import settings

    assert hasattr(settings, "app_name")
    assert hasattr(settings, "version")
    assert hasattr(settings, "api_prefix")
    assert hasattr(settings, "cors_origins")


def test_event_handlers_registered() -> None:
    """Test that startup and shutdown handlers are registered."""
    from app.main import app

    # Check event handlers are registered
    startup_handlers = app.router.on_startup
    shutdown_handlers = app.router.on_shutdown

    assert len(startup_handlers) > 0
    assert len(shutdown_handlers) > 0
