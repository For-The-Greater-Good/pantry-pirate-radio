"""Repository pattern for database operations."""

from abc import ABC, abstractmethod
from typing import Any, Generic, Optional, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

# Try to import GeoAlchemy2 functions, use fallback if not available
try:
    from geoalchemy2.functions import ST_DWithin, ST_Intersects, ST_Distance

    HAS_GEOALCHEMY2 = True
except ImportError:
    HAS_GEOALCHEMY2 = False

from app.models.hsds.query import GeoBoundingBox, GeoPoint
from .models import (
    AddressModel,
    LocationModel,
    OrganizationModel,
    ServiceAtLocationModel,
    ServiceModel,
)

ModelType = TypeVar("ModelType")


class BaseRepository(ABC, Generic[ModelType]):
    """Base repository for common database operations."""

    def __init__(self, session: AsyncSession, model: type[ModelType]):
        self.session = session
        self.model = model

    async def get_by_id(self, id: UUID) -> Optional[ModelType]:
        """Get entity by ID."""
        result = await self.session.get(self.model, id)
        return result

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[ModelType]:
        """Get all entities with optional filtering."""
        query = select(self.model)

        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def count(self, filters: Optional[dict[str, Any]] = None) -> int:
        """Count entities with optional filtering."""
        query = select(func.count()).select_from(self.model)

        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def create(self, **kwargs) -> ModelType:
        """Create new entity."""
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.commit()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: UUID, **kwargs) -> Optional[ModelType]:
        """Update entity by ID."""
        instance = await self.get_by_id(id)
        if instance:
            for key, value in kwargs.items():
                if hasattr(instance, key):
                    setattr(instance, key, value)
            await self.session.commit()
            await self.session.refresh(instance)
        return instance

    async def delete(self, id: UUID) -> bool:
        """Delete entity by ID."""
        instance = await self.get_by_id(id)
        if instance:
            await self.session.delete(instance)
            await self.session.commit()
            return True
        return False


class OrganizationRepository(BaseRepository[OrganizationModel]):
    """Repository for Organization entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, OrganizationModel)

    async def get_by_id(self, id: UUID) -> Optional[OrganizationModel]:
        """Get organization by ID with eager loading."""
        query = (
            select(self.model)
            .options(selectinload(self.model.services))
            .filter(self.model.id == str(id))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[OrganizationModel]:
        """Get all organizations with eager loading to prevent lazy load errors."""
        query = select(self.model).options(selectinload(self.model.services))

        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_name(self, name: str) -> Optional[OrganizationModel]:
        """Get organization by name."""
        query = select(self.model).filter(self.model.name == name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def search_by_name(
        self, name: str, limit: int = 10
    ) -> Sequence[OrganizationModel]:
        """Search organizations by name (partial match)."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.services).selectinload(ServiceModel.locations),
                selectinload(self.model.services).selectinload(ServiceModel.schedules),
            )
            .filter(
                or_(
                    self.model.name.ilike(f"%{name}%"),
                    self.model.alternate_name.ilike(f"%{name}%"),
                )
            )
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_name_search(self, name: str) -> int:
        """Count organizations matching name search."""
        query = (
            select(func.count())
            .select_from(self.model)
            .filter(
                or_(
                    self.model.name.ilike(f"%{name}%"),
                    self.model.alternate_name.ilike(f"%{name}%"),
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_organizations_with_services(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[OrganizationModel]:
        """Get organizations with their services."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.services).selectinload(ServiceModel.locations),
                selectinload(self.model.services).selectinload(ServiceModel.schedules),
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class LocationRepository(BaseRepository[LocationModel]):
    """Repository for Location entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, LocationModel)

    async def get_by_id(self, id: UUID) -> Optional[LocationModel]:
        """Get location by ID with eager loading."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.services_at_location)
                # Temporarily disabled schedules due to async loading issues
                # selectinload(self.model.schedules)
            )
            .filter(self.model.id == str(id))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[LocationModel]:
        """Get all locations with eager loading to prevent lazy load errors."""
        query = select(self.model).options(
            selectinload(self.model.services_at_location)
            # Temporarily disabled schedules due to async loading issues
            # selectinload(self.model.schedules)
        )

        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_locations_by_radius(
        self,
        center: GeoPoint,
        radius_miles: float,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[LocationModel]:
        """Get locations within radius of a point."""
        if HAS_GEOALCHEMY2:
            # Use PostGIS for accurate distance calculations
            radius_meters = radius_miles * 1609.34

            # Calculate distance and include it in the result
            distance_col = ST_Distance(
                self.model.geometry,
                func.ST_SetSRID(
                    func.ST_MakePoint(center.longitude, center.latitude), 4326
                ),
                True,  # Use spheroid for accurate distance
            )

            query = select(
                self.model,
                (distance_col / 1609.34).label(
                    "distance_miles"
                ),  # Convert meters to miles
            ).filter(
                ST_DWithin(
                    self.model.geometry,
                    func.ST_SetSRID(
                        func.ST_MakePoint(center.longitude, center.latitude), 4326
                    ),
                    radius_meters,
                    True,  # Use spheroid for accurate distance
                )
            )

            # Order by distance
            query = query.order_by(distance_col)
        else:
            # Fallback: use bounding box approximation
            # Convert miles to approximate degrees
            lat_delta = radius_miles / 69.0
            lon_delta = radius_miles / (69.0 * 0.7)  # Approximate longitude scaling

            query = select(self.model).filter(
                and_(
                    self.model.latitude.between(
                        center.latitude - lat_delta, center.latitude + lat_delta
                    ),
                    self.model.longitude.between(
                        center.longitude - lon_delta, center.longitude + lon_delta
                    ),
                )
            )

        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        if HAS_GEOALCHEMY2:
            # When we include distance, we get tuples (LocationModel, distance_miles)
            # We need to attach the distance to each location model
            locations = []
            for row in result:
                location = row[0]
                location.distance_miles = row[1]  # Attach distance as an attribute
                locations.append(location)
            return locations
        else:
            return result.scalars().all()

    async def get_locations_by_bbox(
        self,
        bbox: GeoBoundingBox,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[LocationModel]:
        """Get locations within bounding box."""
        if HAS_GEOALCHEMY2:
            # Use PostGIS for accurate bounding box queries
            bbox_geom = func.ST_SetSRID(
                func.ST_MakeEnvelope(
                    bbox.min_longitude,
                    bbox.min_latitude,
                    bbox.max_longitude,
                    bbox.max_latitude,
                ),
                4326,
            )

            query = select(self.model).filter(
                ST_Intersects(self.model.geometry, bbox_geom)
            )
        else:
            # Fallback: use simple coordinate range filtering
            query = select(self.model).filter(
                and_(
                    self.model.latitude.between(bbox.min_latitude, bbox.max_latitude),
                    self.model.longitude.between(
                        bbox.min_longitude, bbox.max_longitude
                    ),
                )
            )

        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_locations_with_services(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[LocationModel]:
        """Get locations with their services."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.services_at_location).selectinload(
                    ServiceAtLocationModel.service
                )
                # Temporarily disabled schedules due to async loading issues
                # selectinload(self.model.schedules)
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_radius(
        self,
        center: GeoPoint,
        radius_miles: float,
        filters: Optional[dict[str, Any]] = None,
    ) -> int:
        """Count locations within radius of a point."""
        if HAS_GEOALCHEMY2:
            # Use PostGIS for accurate distance calculations
            radius_meters = radius_miles * 1609.34

            query = (
                select(func.count())
                .select_from(self.model)
                .filter(
                    ST_DWithin(
                        self.model.geometry,
                        func.ST_SetSRID(
                            func.ST_MakePoint(center.longitude, center.latitude), 4326
                        ),
                        radius_meters,
                        True,  # Use spheroid for accurate distance
                    )
                )
            )
        else:
            # Fallback: use bounding box approximation
            # Convert miles to approximate degrees
            lat_delta = radius_miles / 69.0
            lon_delta = radius_miles / (69.0 * 0.7)  # Approximate longitude scaling

            query = (
                select(func.count())
                .select_from(self.model)
                .filter(
                    and_(
                        self.model.latitude.between(
                            center.latitude - lat_delta, center.latitude + lat_delta
                        ),
                        self.model.longitude.between(
                            center.longitude - lon_delta, center.longitude + lon_delta
                        ),
                    )
                )
            )

        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def count_by_bbox(
        self,
        bbox: GeoBoundingBox,
        filters: Optional[dict[str, Any]] = None,
    ) -> int:
        """Count locations within bounding box."""
        if HAS_GEOALCHEMY2:
            # Use PostGIS for accurate bounding box queries
            bbox_geom = func.ST_SetSRID(
                func.ST_MakeEnvelope(
                    bbox.min_longitude,
                    bbox.min_latitude,
                    bbox.max_longitude,
                    bbox.max_latitude,
                ),
                4326,
            )

            query = (
                select(func.count())
                .select_from(self.model)
                .filter(ST_Intersects(self.model.geometry, bbox_geom))
            )
        else:
            # Fallback: use simple coordinate range filtering
            query = (
                select(func.count())
                .select_from(self.model)
                .filter(
                    and_(
                        self.model.latitude.between(
                            bbox.min_latitude, bbox.max_latitude
                        ),
                        self.model.longitude.between(
                            bbox.min_longitude, bbox.max_longitude
                        ),
                    )
                )
            )

        # Apply additional filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar() or 0


class ServiceRepository(BaseRepository[ServiceModel]):
    """Repository for Service entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ServiceModel)

    async def get_by_id(self, id: UUID) -> Optional[ServiceModel]:
        """Get service by ID with eager loading."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.organization),
                selectinload(self.model.locations),
                selectinload(self.model.schedules),
            )
            .filter(self.model.id == str(id))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[ServiceModel]:
        """Get all services with eager loading to prevent lazy load errors."""
        query = select(self.model).options(
            selectinload(self.model.organization),
            selectinload(self.model.locations),
            selectinload(self.model.schedules),
        )

        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_services_by_status(
        self, status: str, skip: int = 0, limit: int = 100
    ) -> Sequence[ServiceModel]:
        """Get services by status."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.organization),
                selectinload(self.model.locations),
                selectinload(self.model.schedules),
            )
            .filter(self.model.status == status)
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_services_by_organization(
        self, organization_id: UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[ServiceModel]:
        """Get services by organization."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.organization),
                selectinload(self.model.locations),
                selectinload(self.model.schedules),
            )
            .filter(self.model.organization_id == str(organization_id))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def search_services(
        self, search_term: str, skip: int = 0, limit: int = 100
    ) -> Sequence[ServiceModel]:
        """Search services by name or description."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.organization),
                selectinload(self.model.locations),
                selectinload(self.model.schedules),
            )
            .filter(
                or_(
                    self.model.name.ilike(f"%{search_term}%"),
                    self.model.alternate_name.ilike(f"%{search_term}%"),
                    self.model.description.ilike(f"%{search_term}%"),
                )
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_by_search(self, search_term: str) -> int:
        """Count services matching search term."""
        query = (
            select(func.count())
            .select_from(self.model)
            .filter(
                or_(
                    self.model.name.ilike(f"%{search_term}%"),
                    self.model.alternate_name.ilike(f"%{search_term}%"),
                    self.model.description.ilike(f"%{search_term}%"),
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_services_with_locations(
        self, skip: int = 0, limit: int = 100
    ) -> Sequence[ServiceModel]:
        """Get services with their locations."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.organization),
                selectinload(self.model.locations).selectinload(
                    ServiceAtLocationModel.location
                ),
                selectinload(self.model.schedules),
            )
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()


class ServiceAtLocationRepository(BaseRepository[ServiceAtLocationModel]):
    """Repository for ServiceAtLocation entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, ServiceAtLocationModel)

    async def get_by_id(self, id: UUID) -> Optional[ServiceAtLocationModel]:
        """Get service at location by ID with eager loading."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.service).selectinload(ServiceModel.schedules),
                selectinload(self.model.location).selectinload(LocationModel.schedules),
                selectinload(self.model.schedules),
            )
            .filter(self.model.id == str(id))
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        skip: int = 0,
        limit: int = 100,
        filters: Optional[dict[str, Any]] = None,
    ) -> Sequence[ServiceAtLocationModel]:
        """Get all service at locations with eager loading to prevent lazy load errors."""
        query = select(self.model).options(
            selectinload(self.model.service).selectinload(ServiceModel.locations),
            selectinload(self.model.service).selectinload(ServiceModel.schedules),
            selectinload(self.model.location).selectinload(LocationModel.schedules),
            selectinload(self.model.schedules),
        )

        # Apply filters
        if filters:
            for key, value in filters.items():
                if hasattr(self.model, key):
                    query = query.filter(getattr(self.model, key) == value)

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        return result.scalars().all()

    async def get_by_service_and_location(
        self, service_id: UUID, location_id: UUID
    ) -> Optional[ServiceAtLocationModel]:
        """Get service at location by service and location IDs."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.service).selectinload(ServiceModel.schedules),
                selectinload(self.model.location).selectinload(LocationModel.schedules),
                selectinload(self.model.schedules),
            )
            .filter(
                and_(
                    self.model.service_id == str(service_id),
                    self.model.location_id == str(location_id),
                )
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_services_at_location(
        self, location_id: UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[ServiceAtLocationModel]:
        """Get all services at a location."""
        query = (
            select(self.model)
            .options(
                selectinload(self.model.service).selectinload(ServiceModel.schedules),
                selectinload(self.model.schedules),
            )
            .filter(self.model.location_id == str(location_id))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_services_at_location(self, location_id: UUID) -> int:
        """Count services at a location."""
        query = (
            select(func.count())
            .select_from(self.model)
            .filter(self.model.location_id == str(location_id))
        )
        result = await self.session.execute(query)
        return result.scalar() or 0

    async def get_locations_for_service(
        self, service_id: UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[ServiceAtLocationModel]:
        """Get all locations for a service."""
        query = (
            select(self.model)
            .options(selectinload(self.model.location))
            .filter(self.model.service_id == str(service_id))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def count_locations_for_service(self, service_id: UUID) -> int:
        """Count locations for a service."""
        query = (
            select(func.count())
            .select_from(self.model)
            .filter(self.model.service_id == str(service_id))
        )
        result = await self.session.execute(query)
        return result.scalar() or 0


class AddressRepository(BaseRepository[AddressModel]):
    """Repository for Address entities."""

    def __init__(self, session: AsyncSession):
        super().__init__(session, AddressModel)

    async def get_by_location(
        self, location_id: UUID, skip: int = 0, limit: int = 100
    ) -> Sequence[AddressModel]:
        """Get addresses by location."""
        query = (
            select(self.model)
            .filter(self.model.location_id == str(location_id))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def search_by_postal_code(
        self, postal_code: str, skip: int = 0, limit: int = 100
    ) -> Sequence[AddressModel]:
        """Search addresses by postal code."""
        query = (
            select(self.model)
            .filter(self.model.postal_code.ilike(f"%{postal_code}%"))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()

    async def search_by_state(
        self, state: str, skip: int = 0, limit: int = 100
    ) -> Sequence[AddressModel]:
        """Search addresses by state."""
        query = (
            select(self.model)
            .filter(self.model.state_province.ilike(f"%{state}%"))
            .offset(skip)
            .limit(limit)
        )
        result = await self.session.execute(query)
        return result.scalars().all()
