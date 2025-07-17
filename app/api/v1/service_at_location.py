"""Service-at-Location API endpoints."""

from uuid import UUID
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_session
from app.database.repositories import ServiceAtLocationRepository
from app.models.hsds.service_at_location import ServiceAtLocation
from app.models.hsds.response import (
    ServiceAtLocationResponse,
    ServiceResponse,
    LocationResponse,
    Page,
)
from app.api.v1.utils import (
    create_pagination_links,
    calculate_pagination_metadata,
    validate_pagination_params,
    build_filter_dict,
)

router = APIRouter(prefix="/service-at-location", tags=["service-at-location"])


@router.get("/", response_model=Page[ServiceAtLocationResponse])
async def list_service_at_location(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    service_id: Optional[UUID] = Query(None, description="Filter by service ID"),
    location_id: Optional[UUID] = Query(None, description="Filter by location ID"),
    organization_id: Optional[UUID] = Query(
        None, description="Filter by organization ID"
    ),
    include_details: bool = Query(
        False, description="Include service and location details"
    ),
    session: AsyncSession = Depends(get_session),
) -> Page[ServiceAtLocationResponse]:
    """
    List service-at-location relationships with optional filtering and pagination.

    Returns paginated list of service-at-location relationships with optional details.
    """
    validate_pagination_params(page, per_page)

    repository = ServiceAtLocationRepository(session)

    # Calculate pagination
    pagination = calculate_pagination_metadata(0, page, per_page)

    # Build filters
    filters = build_filter_dict(
        service_id=service_id,
        location_id=location_id,
        organization_id=organization_id,
    )

    # Get service-at-location relationships
    service_at_locations = await repository.get_all(
        skip=pagination["skip"],
        limit=per_page,
        filters=filters,
    )

    # Get total count
    total = await repository.count(filters=filters)

    # Update pagination metadata
    pagination["total_items"] = total
    pagination["total_pages"] = max(1, (total + per_page - 1) // per_page)

    # Convert to response models
    sal_responses = []
    for sal in service_at_locations:
        sal_data = ServiceAtLocationResponse.model_validate(sal)

        if include_details:
            # Load service and location details
            if sal.service:
                sal_data.service = ServiceResponse.model_validate(sal.service)

            if sal.location:
                sal_data.location = LocationResponse.model_validate(sal.location)

        sal_responses.append(sal_data)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=pagination["total_pages"],
        per_page=per_page,
        extra_params={
            "service_id": service_id,
            "location_id": location_id,
            "organization_id": organization_id,
            "include_details": include_details,
        },
    )

    return Page(
        count=len(sal_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=pagination["total_pages"],
        links=links,
        data=sal_responses,
    )


@router.get("/{service_at_location_id}", response_model=ServiceAtLocationResponse)
async def get_service_at_location(
    service_at_location_id: UUID,
    include_details: bool = Query(
        False, description="Include service and location details"
    ),
    session: AsyncSession = Depends(get_session),
) -> ServiceAtLocationResponse:
    """
    Get a specific service-at-location relationship by ID.

    Returns detailed information about a service-at-location relationship.
    """
    repository = ServiceAtLocationRepository(session)

    sal = await repository.get_by_id(service_at_location_id)
    if not sal:
        raise HTTPException(status_code=404, detail="Service-at-location not found")

    # Convert to response model
    sal_response = ServiceAtLocationResponse.model_validate(sal)

    if include_details:
        # Load service and location details
        if sal.service:
            sal_response.service = ServiceResponse.model_validate(sal.service)

        if sal.location:
            sal_response.location = LocationResponse.model_validate(sal.location)

    return sal_response


@router.get(
    "/service/{service_id}/locations", response_model=Page[ServiceAtLocationResponse]
)
async def get_locations_for_service(
    request: Request,
    service_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    include_details: bool = Query(
        False, description="Include service and location details"
    ),
    session: AsyncSession = Depends(get_session),
) -> Page[ServiceAtLocationResponse]:
    """
    Get all locations for a specific service.

    Returns paginated list of locations where the service is offered.
    """
    validate_pagination_params(page, per_page)

    repository = ServiceAtLocationRepository(session)

    # Calculate pagination
    pagination = calculate_pagination_metadata(0, page, per_page)

    # Get locations for service
    locations_for_service = await repository.get_locations_for_service(
        service_id=service_id,
        skip=pagination["skip"],
        limit=per_page,
    )

    # Get total count (approximation)
    total = len(locations_for_service)

    # Update pagination metadata
    pagination["total_items"] = total
    pagination["total_pages"] = max(1, (total + per_page - 1) // per_page)

    # Convert to response models
    sal_responses = []
    for sal in locations_for_service:
        sal_data = ServiceAtLocationResponse.model_validate(sal)

        if include_details and sal.location:
            sal_data.location = LocationResponse.model_validate(sal.location)

        sal_responses.append(sal_data)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=pagination["total_pages"],
        per_page=per_page,
        extra_params={"include_details": include_details},
    )

    return Page(
        count=len(sal_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=pagination["total_pages"],
        links=links,
        data=sal_responses,
    )


@router.get(
    "/location/{location_id}/services", response_model=Page[ServiceAtLocationResponse]
)
async def get_services_at_location(
    request: Request,
    location_id: UUID,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    include_details: bool = Query(
        False, description="Include service and location details"
    ),
    session: AsyncSession = Depends(get_session),
) -> Page[ServiceAtLocationResponse]:
    """
    Get all services at a specific location.

    Returns paginated list of services offered at the location.
    """
    validate_pagination_params(page, per_page)

    repository = ServiceAtLocationRepository(session)

    # Calculate pagination
    pagination = calculate_pagination_metadata(0, page, per_page)

    # Get services at location
    services_at_location = await repository.get_services_at_location(
        location_id=location_id,
        skip=pagination["skip"],
        limit=per_page,
    )

    # Get total count (approximation)
    total = len(services_at_location)

    # Update pagination metadata
    pagination["total_items"] = total
    pagination["total_pages"] = max(1, (total + per_page - 1) // per_page)

    # Convert to response models
    sal_responses = []
    for sal in services_at_location:
        sal_data = ServiceAtLocationResponse.model_validate(sal)

        if include_details and sal.service:
            sal_data.service = ServiceResponse.model_validate(sal.service)

        sal_responses.append(sal_data)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=pagination["total_pages"],
        per_page=per_page,
        extra_params={"include_details": include_details},
    )

    return Page(
        count=len(sal_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=pagination["total_pages"],
        links=links,
        data=sal_responses,
    )
