"""Simple integration tests for API endpoints that work reliably."""

import pytest
import uuid
from unittest.mock import AsyncMock, patch
from fastapi.testclient import TestClient

from app.main import app
from app.models.hsds.organization import Organization
from app.models.hsds.location import Location
from app.models.hsds.service import Service
from app.models.hsds.service_at_location import ServiceAtLocation


@pytest.fixture
def client(db_session):
    """Create test client with database session override."""
    from app.core.db import get_session

    # Override the database session dependency
    async def override_get_session():
        yield db_session

    # Create a new app instance with the overridden dependency
    app.dependency_overrides[get_session] = override_get_session

    client = TestClient(app)

    yield client

    # Clean up the override
    app.dependency_overrides.clear()


@pytest.fixture
def mock_organization():
    """Create mock organization."""
    return Organization(
        id=uuid.uuid4(),
        name="Test Food Bank",
        description="A test food bank serving the community",
        email="contact@testfoodbank.org",
        url="https://testfoodbank.org",
        tax_status="501c3",
        year_incorporated=1990,
        legal_status="nonprofit",
    )


@pytest.fixture
def mock_location():
    """Create mock location."""
    return Location(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Main Distribution Center",
        description="Primary food distribution location",
        latitude=40.7128,
        longitude=-74.0060,
        transportation="Bus routes 51, 52, and 53",
        location_type="physical",
    )


@pytest.fixture
def mock_service():
    """Create mock service."""
    return Service(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Food Distribution",
        description="Weekly food distribution service",
        status="active",
        program_id=uuid.uuid4(),
    )


@pytest.fixture
def mock_service_at_location():
    """Create mock service at location."""
    return ServiceAtLocation(
        id=uuid.uuid4(),
        service_id=uuid.uuid4(),
        location_id=uuid.uuid4(),
        description="Food distribution at main center",
    )


class TestOrganizationsAPI:
    """Test organizations API endpoints."""

    @patch("app.api.v1.organizations.OrganizationRepository")
    def test_list_organizations_basic(self, mock_repo_class, client, mock_organization):
        """Test basic organization listing."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_organization]
        mock_repo.count.return_value = 1

        response = client.get("/api/v1/organizations/")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data

    @patch("app.api.v1.organizations.OrganizationRepository")
    def test_list_organizations_with_pagination(
        self, mock_repo_class, client, mock_organization
    ):
        """Test organization listing with pagination."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_organization]
        mock_repo.count.return_value = 1

        response = client.get("/api/v1/organizations/?page=1&per_page=5")

        assert response.status_code == 200
        data = response.json()
        assert data["per_page"] == 5
        assert data["current_page"] == 1

    @patch("app.api.v1.organizations.OrganizationRepository")
    def test_list_organizations_with_name_filter(
        self, mock_repo_class, client, mock_organization
    ):
        """Test organization listing with name filter."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.search_by_name.return_value = [mock_organization]
        mock_repo.count_by_name_search.return_value = 1

        response = client.get("/api/v1/organizations/?name=food+bank")

        assert response.status_code == 200

    @patch("app.api.v1.organizations.OrganizationRepository")
    def test_get_organization_by_id(self, mock_repo_class, client, mock_organization):
        """Test getting organization by ID."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = mock_organization

        org_id = str(mock_organization.id)
        response = client.get(f"/api/v1/organizations/{org_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == mock_organization.name

    @patch("app.api.v1.organizations.OrganizationRepository")
    def test_get_organization_not_found(self, mock_repo_class, client):
        """Test getting non-existent organization."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = None

        org_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/organizations/{org_id}")

        assert response.status_code == 404


class TestLocationsAPI:
    """Test locations API endpoints."""

    @patch("app.api.v1.locations.get_location_schedules")
    @patch("app.api.v1.locations.get_location_sources")
    @patch("app.api.v1.locations.LocationRepository")
    def test_list_locations_basic(
        self,
        mock_repo_class,
        mock_get_sources,
        mock_get_schedules,
        client,
        mock_location,
    ):
        """Test basic location listing."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_location]
        mock_repo.count.return_value = 1

        # Mock helper functions to return empty lists
        mock_get_sources.return_value = []
        mock_get_schedules.return_value = []

        response = client.get("/api/v1/locations/")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data

    @patch("app.api.v1.locations.get_location_schedules")
    @patch("app.api.v1.locations.get_location_sources")
    @patch("app.api.v1.locations.LocationRepository")
    def test_list_locations_with_organization_filter(
        self,
        mock_repo_class,
        mock_get_sources,
        mock_get_schedules,
        client,
        mock_location,
    ):
        """Test location listing with organization filter."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_location]
        mock_repo.count.return_value = 1

        # Mock helper functions to return empty lists
        mock_get_sources.return_value = []
        mock_get_schedules.return_value = []

        org_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/locations/?organization_id={org_id}")

        assert response.status_code == 200

    @patch("app.api.v1.locations.get_location_schedules")
    @patch("app.api.v1.locations.get_location_sources")
    @patch("app.api.v1.locations.LocationRepository")
    def test_search_locations_radius(
        self,
        mock_repo_class,
        mock_get_sources,
        mock_get_schedules,
        client,
        mock_location,
    ):
        """Test location search with radius."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_locations_by_radius.return_value = [mock_location]
        mock_repo.count_by_radius.return_value = 1

        # Mock helper functions to return empty lists
        mock_get_sources.return_value = []
        mock_get_schedules.return_value = []

        response = client.get(
            "/api/v1/locations/search?latitude=40.7128&longitude=-74.0060&radius_miles=10"
        )

        assert response.status_code == 200

    @patch("app.api.v1.locations.get_location_schedules")
    @patch("app.api.v1.locations.get_location_sources")
    @patch("app.api.v1.locations.LocationRepository")
    def test_search_locations_bounding_box(
        self,
        mock_repo_class,
        mock_get_sources,
        mock_get_schedules,
        client,
        mock_location,
    ):
        """Test location search with bounding box."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_locations_by_bbox.return_value = [mock_location]
        mock_repo.count_by_bbox.return_value = 1

        # Mock helper functions to return empty lists
        mock_get_sources.return_value = []
        mock_get_schedules.return_value = []

        response = client.get(
            "/api/v1/locations/search?min_latitude=40.7&max_latitude=40.8&min_longitude=-74.1&max_longitude=-74.0"
        )

        assert response.status_code == 200

    @patch("app.api.v1.locations.get_location_schedules")
    @patch("app.api.v1.locations.get_location_sources")
    @patch("app.api.v1.locations.LocationRepository")
    def test_get_location_by_id(
        self,
        mock_repo_class,
        mock_get_sources,
        mock_get_schedules,
        client,
        mock_location,
    ):
        """Test getting location by ID."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = mock_location

        # Mock helper functions to return empty lists
        mock_get_sources.return_value = []
        mock_get_schedules.return_value = []

        location_id = str(mock_location.id)
        response = client.get(f"/api/v1/locations/{location_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == mock_location.name

    @patch("app.api.v1.locations.LocationRepository")
    def test_get_location_not_found(self, mock_repo_class, client):
        """Test getting non-existent location."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = None

        location_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/locations/{location_id}")

        assert response.status_code == 404


class TestServicesAPI:
    """Test services API endpoints."""

    @patch("app.api.v1.services.ServiceRepository")
    def test_list_services_basic(self, mock_repo_class, client, mock_service):
        """Test basic service listing."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_service]
        mock_repo.count.return_value = 1

        response = client.get("/api/v1/services/")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data

    @patch("app.api.v1.services.ServiceRepository")
    def test_list_services_by_organization(self, mock_repo_class, client, mock_service):
        """Test service listing by organization."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_service]
        mock_repo.count.return_value = 1

        org_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/services/?organization_id={org_id}")

        assert response.status_code == 200

    @patch("app.api.v1.services.ServiceRepository")
    def test_list_services_by_status(self, mock_repo_class, client, mock_service):
        """Test service listing by status."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_service]
        mock_repo.count.return_value = 1

        response = client.get("/api/v1/services/?status=active")

        assert response.status_code == 200

    @patch("app.api.v1.services.ServiceRepository")
    def test_search_services(self, mock_repo_class, client, mock_service):
        """Test service search."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.search_by_name.return_value = [mock_service]
        mock_repo.count_by_search.return_value = 1

        response = client.get("/api/v1/services/search?q=food")

        assert response.status_code == 200

    @patch("app.api.v1.services.ServiceRepository")
    def test_search_services_with_status_filter(
        self, mock_repo_class, client, mock_service
    ):
        """Test service search with status filter."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.search_by_name.return_value = [mock_service]
        mock_repo.count_by_search.return_value = 1

        response = client.get("/api/v1/services/search?q=food&status=active")

        assert response.status_code == 200

    @patch("app.api.v1.services.ServiceRepository")
    def test_get_service_by_id(self, mock_repo_class, client, mock_service):
        """Test getting service by ID."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = mock_service

        service_id = str(mock_service.id)
        response = client.get(f"/api/v1/services/{service_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == mock_service.name

    @patch("app.api.v1.services.ServiceRepository")
    def test_get_service_not_found(self, mock_repo_class, client):
        """Test getting non-existent service."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = None

        service_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/services/{service_id}")

        assert response.status_code == 404


class TestServiceAtLocationAPI:
    """Test service-at-location API endpoints."""

    @patch("app.api.v1.service_at_location.ServiceAtLocationRepository")
    def test_list_service_at_location_basic(
        self, mock_repo_class, client, mock_service_at_location
    ):
        """Test basic service-at-location listing."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_service_at_location]
        mock_repo.count.return_value = 1

        response = client.get("/api/v1/service-at-location/")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "count" in data

    @patch("app.api.v1.service_at_location.ServiceAtLocationRepository")
    def test_list_service_at_location_with_filters(
        self, mock_repo_class, client, mock_service_at_location
    ):
        """Test service-at-location listing with filters."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_all.return_value = [mock_service_at_location]
        mock_repo.count.return_value = 1

        service_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/service-at-location/?service_id={service_id}")

        assert response.status_code == 200

    @patch("app.api.v1.service_at_location.ServiceAtLocationRepository")
    def test_get_service_at_location_by_id(
        self, mock_repo_class, client, mock_service_at_location
    ):
        """Test getting service-at-location by ID."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = mock_service_at_location

        sal_id = str(mock_service_at_location.id)
        response = client.get(f"/api/v1/service-at-location/{sal_id}")

        assert response.status_code == 200

    @patch("app.api.v1.service_at_location.ServiceAtLocationRepository")
    def test_get_service_at_location_not_found(self, mock_repo_class, client):
        """Test getting non-existent service-at-location."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_by_id.return_value = None

        sal_id = str(uuid.uuid4())
        response = client.get(f"/api/v1/service-at-location/{sal_id}")

        assert response.status_code == 404

    @patch("app.api.v1.service_at_location.ServiceAtLocationRepository")
    def test_get_locations_for_service(
        self, mock_repo_class, client, mock_service_at_location
    ):
        """Test getting locations for a service."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_locations_for_service.return_value = [mock_service_at_location]
        mock_repo.count_locations_for_service.return_value = 1

        service_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/service-at-location/service/{service_id}/locations"
        )

        assert response.status_code == 200

    @patch("app.api.v1.service_at_location.ServiceAtLocationRepository")
    def test_get_services_at_location(
        self, mock_repo_class, client, mock_service_at_location
    ):
        """Test getting services at a location."""
        mock_repo = AsyncMock()
        mock_repo_class.return_value = mock_repo

        mock_repo.get_services_at_location.return_value = [mock_service_at_location]
        mock_repo.count_services_at_location.return_value = 1

        location_id = str(uuid.uuid4())
        response = client.get(
            f"/api/v1/service-at-location/location/{location_id}/services"
        )

        assert response.status_code == 200


class TestAPIErrorHandling:
    """Test API error handling."""

    def test_invalid_uuid_format(self, client):
        """Test handling of invalid UUID format."""
        response = client.get("/api/v1/organizations/invalid-uuid")

        assert response.status_code == 422  # Validation error
