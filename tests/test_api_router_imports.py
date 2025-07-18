"""Tests for API router import functionality."""

import os
from unittest.mock import patch

import pytest


def test_router_includes_all_endpoints():
    """Test that the router includes all API endpoints."""
    from app.api.v1.router import router

    # Check that routes are included
    routes = [route.path for route in router.routes]

    # Should include organizations routes
    assert any("/organizations" in route for route in routes)

    # Should include locations routes
    assert any("/locations" in route for route in routes)

    # Should include services routes
    assert any("/services" in route for route in routes)

    # Should include service-at-location routes
    assert any("/service-at-location" in route for route in routes)

    # Should include health and metrics
    assert "/health" in routes
    assert "/metrics" in routes


def test_router_testing_mode_configuration():
    """Test router configuration in testing mode."""
    # Just test that we can import and use the router in testing mode
    # (which we're already doing since TESTING=true for these tests)
    from app.api.v1.router import router

    # Should still include endpoints for documentation
    routes = [route.path for route in router.routes]
    assert len(routes) > 5  # Should have more than just health checks


def test_router_includes_organizations_endpoints():
    """Test that organizations endpoints are properly included."""
    from app.api.v1.router import router

    routes = [route.path for route in router.routes]

    # Check for specific organizations endpoints
    organizations_routes = [route for route in routes if "/organizations" in route]
    assert len(organizations_routes) >= 3  # Should have list, search, and detail routes


def test_router_includes_locations_endpoints():
    """Test that locations endpoints are properly included."""
    from app.api.v1.router import router

    routes = [route.path for route in router.routes]

    # Check for specific locations endpoints
    locations_routes = [route for route in routes if "/locations" in route]
    assert len(locations_routes) >= 3  # Should have list, search, and detail routes


def test_router_includes_services_endpoints():
    """Test that services endpoints are properly included."""
    from app.api.v1.router import router

    routes = [route.path for route in router.routes]

    # Check for specific services endpoints
    services_routes = [route for route in routes if "/services" in route]
    assert len(services_routes) >= 3  # Should have list, search, and detail routes


def test_router_includes_service_at_location_endpoints():
    """Test that service-at-location endpoints are properly included."""
    from app.api.v1.router import router

    routes = [route.path for route in router.routes]

    # Check for specific service-at-location endpoints
    sal_routes = [route for route in routes if "/service-at-location" in route]
    assert len(sal_routes) >= 3  # Should have list and relationship routes


def test_router_basic_structure():
    """Test basic router structure and configuration."""
    from app.api.v1.router import router

    # Should be a proper APIRouter
    assert hasattr(router, "routes")
    assert hasattr(router, "include_router")

    # Should have routes configured
    assert len(router.routes) > 0

    # Should have default response class configured
    from fastapi.responses import JSONResponse

    assert router.default_response_class is JSONResponse
