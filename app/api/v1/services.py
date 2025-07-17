"""Services API endpoints."""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.database.repositories import ServiceRepository
from app.models.hsds.service import Service
from app.models.hsds.response import ServiceResponse, LocationResponse, Page
from app.api.v1.utils import (
    create_pagination_links,
    calculate_pagination_metadata,
    validate_pagination_params,
    build_filter_dict,
)

router = APIRouter(prefix="/services", tags=["services"])


@router.get("/", response_model=Page[ServiceResponse])
async def list_services(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    organization_id: Optional[UUID] = Query(
        None, description="Filter by organization ID"
    ),
    status: Optional[str] = Query(None, description="Filter by service status"),
    include_locations: bool = Query(False, description="Include locations in response"),
    session: AsyncSession = Depends(get_session),
) -> Page[ServiceResponse]:
    """
    List services with optional filtering and pagination.

    Returns paginated list of services with optional location details.
    """
    validate_pagination_params(page, per_page)

    repository = ServiceRepository(session)

    # Calculate pagination
    pagination = calculate_pagination_metadata(0, page, per_page)

    # Get services based on filters
    if organization_id:
        services = await repository.get_services_by_organization(
            organization_id=organization_id,
            skip=pagination["skip"],
            limit=per_page,
        )
        # Get total count for this organization
        total = await repository.count(filters={"organization_id": organization_id})
    elif status:
        services = await repository.get_services_by_status(
            status=status,
            skip=pagination["skip"],
            limit=per_page,
        )
        # Get total count for this status
        total = await repository.count(filters={"status": status})
    else:
        # Get all services or services with locations
        if include_locations:
            services = await repository.get_services_with_locations(
                skip=pagination["skip"],
                limit=per_page,
            )
        else:
            services = await repository.get_all(
                skip=pagination["skip"],
                limit=per_page,
            )

        # Get total count
        total = await repository.count()

    # Update pagination metadata
    pagination["total_items"] = total
    pagination["total_pages"] = max(1, (total + per_page - 1) // per_page)

    # Convert to response models
    service_responses = []
    for service in services:
        service_data = ServiceResponse.model_validate(service)

        if include_locations and hasattr(service, "locations") and service.locations:
            service_data.locations = [
                LocationResponse.model_validate(sal.location)
                for sal in service.locations
            ]

        service_responses.append(service_data)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=pagination["total_pages"],
        per_page=per_page,
        extra_params={
            "organization_id": organization_id,
            "status": status,
            "include_locations": include_locations,
        },
    )

    return Page(
        count=len(service_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=pagination["total_pages"],
        links=links,
        data=service_responses,
    )


@router.get("/search", response_model=Page[ServiceResponse])
async def search_services(
    request: Request,
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    status: Optional[str] = Query(None, description="Filter by service status"),
    include_locations: bool = Query(False, description="Include locations in response"),
    session: AsyncSession = Depends(get_session),
) -> Page[ServiceResponse]:
    """
    Search services by name or description.

    Returns paginated search results based on the query string.
    """
    validate_pagination_params(page, per_page)

    repository = ServiceRepository(session)

    # Search services
    services = await repository.search_services(
        search_term=q,
        skip=(page - 1) * per_page,
        limit=per_page,
    )

    # Filter by status if provided
    if status:
        services = [s for s in services if s.status == status]

    total = len(services)  # Approximation for search results

    # Convert to response models
    service_responses = []
    for service in services:
        service_data = ServiceResponse.model_validate(service)

        if include_locations:
            # Load locations for this service
            from app.database.repositories import ServiceAtLocationRepository

            sal_repo = ServiceAtLocationRepository(session)
            locations_for_service = await sal_repo.get_locations_for_service(
                service_data.id
            )

            service_data.locations = [
                LocationResponse.model_validate(sal.location)
                for sal in locations_for_service
            ]

        service_responses.append(service_data)

    # Calculate pagination metadata
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=total_pages,
        per_page=per_page,
        extra_params={
            "q": q,
            "status": status,
            "include_locations": include_locations,
        },
    )

    return Page(
        count=len(service_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=total_pages,
        links=links,
        data=service_responses,
    )


@router.get("/{service_id}", response_model=ServiceResponse)
async def get_service(
    service_id: UUID,
    include_locations: bool = Query(False, description="Include locations in response"),
    session: AsyncSession = Depends(get_session),
) -> ServiceResponse:
    """
    Get a specific service by ID.

    Returns detailed information about a service with optional location details.
    """
    repository = ServiceRepository(session)

    service = await repository.get_by_id(service_id)
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")

    # Convert to response model
    service_response = ServiceResponse.model_validate(service)

    if include_locations:
        # Load locations for this service
        from app.database.repositories import ServiceAtLocationRepository

        sal_repo = ServiceAtLocationRepository(session)
        locations_for_service = await sal_repo.get_locations_for_service(service_id)

        service_response.locations = [
            LocationResponse.model_validate(sal.location)
            for sal in locations_for_service
        ]

    return service_response


@router.get("/active", response_model=Page[ServiceResponse])
async def get_active_services(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    include_locations: bool = Query(False, description="Include locations in response"),
    session: AsyncSession = Depends(get_session),
) -> Page[ServiceResponse]:
    """
    Get only active services.

    Returns paginated list of active services with optional location details.
    """
    return await list_services(
        request=request,
        page=page,
        per_page=per_page,
        organization_id=None,
        status="active",
        include_locations=include_locations,
        session=session,
    )
