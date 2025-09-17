"""Tests for database repository classes."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from uuid import UUID, uuid4
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.database.repositories import (
    BaseRepository,
    OrganizationRepository,
    LocationRepository,
    ServiceRepository,
    ServiceAtLocationRepository,
)
from app.database.models import (
    OrganizationModel,
    LocationModel,
    ServiceModel,
    ServiceAtLocationModel,
    AddressModel,
)


class TestBaseRepository:
    """Test cases for BaseRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def base_repo(self, mock_session):
        """Create a BaseRepository instance with mock model."""
        # Use a real SQLAlchemy model for testing
        return BaseRepository(mock_session, OrganizationModel)

    @pytest.mark.asyncio
    async def test_get_by_id(self, base_repo, mock_session):
        """Test getting entity by ID."""
        test_id = uuid4()
        mock_entity = MagicMock(spec=OrganizationModel)
        mock_entity.id = test_id
        mock_entity.name = "Test Entity"

        mock_session.get = AsyncMock(return_value=mock_entity)

        result = await base_repo.get_by_id(test_id)

        assert result == mock_entity
        mock_session.get.assert_called_once_with(OrganizationModel, test_id)

    @pytest.mark.asyncio
    async def test_get_by_id_not_found(self, base_repo, mock_session):
        """Test getting entity by ID when not found."""
        test_id = uuid4()

        mock_session.get = AsyncMock(return_value=None)

        result = await base_repo.get_by_id(test_id)

        assert result is None
        mock_session.get.assert_called_once_with(OrganizationModel, test_id)

    @pytest.mark.asyncio
    async def test_get_all(self, base_repo, mock_session):
        """Test getting all entities."""
        mock_entity1 = MagicMock(spec=OrganizationModel)
        mock_entity1.id = uuid4()
        mock_entity1.name = "Entity 1"

        mock_entity2 = MagicMock(spec=OrganizationModel)
        mock_entity2.id = uuid4()
        mock_entity2.name = "Entity 2"

        mock_entities = [mock_entity1, mock_entity2]

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = mock_entities
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await base_repo.get_all(skip=0, limit=10)

        assert result == mock_entities
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_all_with_filters(self, base_repo, mock_session):
        """Test getting all entities with filters."""
        mock_entity = MagicMock(spec=OrganizationModel)
        mock_entity.id = uuid4()
        mock_entity.name = "Entity 1"
        mock_entity.status = "active"

        mock_entities = [mock_entity]

        mock_result = MagicMock()
        mock_result.scalars().all.return_value = mock_entities
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await base_repo.get_all(skip=0, limit=10, filters={"name": "Entity 1"})

        assert result == mock_entities
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count(self, base_repo, mock_session):
        """Test counting entities."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 42
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await base_repo.count()

        assert result == 42
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_count_with_filters(self, base_repo, mock_session):
        """Test counting entities with filters."""
        mock_result = MagicMock()
        mock_result.scalar.return_value = 10
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await base_repo.count(filters={"name": "Test Org"})

        assert result == 10
        mock_session.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_create(self, base_repo, mock_session):
        """Test creating new entity."""
        new_entity_data = {"name": "New Entity", "description": "Test description"}

        # Mock the async methods
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        with patch.object(
            OrganizationModel, "__init__", return_value=None
        ) as mock_init:
            result = await base_repo.create(**new_entity_data)

            # The result will be an instance of OrganizationModel
            assert result is not None
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()
            mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update(self, base_repo, mock_session):
        """Test updating entity."""
        test_id = uuid4()
        mock_entity = MagicMock(spec=OrganizationModel)
        mock_entity.id = test_id
        mock_entity.name = "Old Name"
        mock_entity.description = "Old description"

        mock_session.get = AsyncMock(return_value=mock_entity)
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock()

        result = await base_repo.update(
            test_id, name="New Name", description="New description"
        )

        assert result.name == "New Name"
        assert result.description == "New description"
        mock_session.commit.assert_called_once()
        mock_session.refresh.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_not_found(self, base_repo, mock_session):
        """Test updating entity that doesn't exist."""
        test_id = uuid4()

        mock_session.get = AsyncMock(return_value=None)

        result = await base_repo.update(test_id, name="New Name")

        assert result is None
        mock_session.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete(self, base_repo, mock_session):
        """Test deleting entity."""
        test_id = uuid4()
        mock_entity = MagicMock(spec=OrganizationModel)
        mock_entity.id = test_id
        mock_entity.name = "To Delete"

        mock_session.get = AsyncMock(return_value=mock_entity)
        mock_session.delete = AsyncMock()
        mock_session.commit = AsyncMock()

        result = await base_repo.delete(test_id)

        assert result is True
        mock_session.delete.assert_called_once_with(mock_entity)
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_not_found(self, base_repo, mock_session):
        """Test deleting entity that doesn't exist."""
        test_id = uuid4()

        mock_session.get = AsyncMock(return_value=None)

        result = await base_repo.delete(test_id)

        assert result is False
        mock_session.delete.assert_not_called()


class TestOrganizationRepository:
    """Test cases for OrganizationRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def org_repo(self, mock_session):
        """Create an OrganizationRepository instance."""
        return OrganizationRepository(mock_session)

    @pytest.mark.asyncio
    async def test_get_by_name(self, org_repo, mock_session):
        """Test getting organization by name."""
        mock_org = MagicMock(spec=OrganizationModel)
        mock_org.name = "Test Org"

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_org
        mock_session.execute = AsyncMock(return_value=mock_result)

        result = await org_repo.get_by_name("Test Org")

        assert result == mock_org
        assert result.name == "Test Org"
        mock_session.execute.assert_called_once()


class TestLocationRepository:
    """Test cases for LocationRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def location_repo(self, mock_session):
        """Create a LocationRepository instance."""
        return LocationRepository(mock_session)


class TestServiceRepository:
    """Test cases for ServiceRepository."""

    @pytest.fixture
    def mock_session(self):
        """Create a mock database session."""
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def service_repo(self, mock_session):
        """Create a ServiceRepository instance."""
        return ServiceRepository(mock_session)
