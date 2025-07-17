"""Organizations API endpoints."""

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.utils import create_pagination_links
from app.core.db import get_session
from app.database.repositories import OrganizationRepository
from app.models.hsds.organization import Organization
from app.models.hsds.response import OrganizationResponse, Page, ServiceResponse

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("/", response_model=Page[OrganizationResponse])
async def list_organizations(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    name: Optional[str] = Query(None, description="Filter by organization name"),
    include_services: bool = Query(False, description="Include services in response"),
    session: AsyncSession = Depends(get_session),
) -> Page[OrganizationResponse]:
    """
    List organizations with optional filtering and pagination.

    Returns paginated list of organizations with optional service details.
    """
    repository = OrganizationRepository(session)

    # Calculate pagination
    skip = (page - 1) * per_page

    # Apply filters
    filters: dict[str, Any] = {}
    if name:
        # Use search method for name filtering
        organizations = await repository.search_by_name(name, limit=per_page)
        total = len(organizations)  # Approximation for search results
    else:
        # Get all organizations
        if include_services:
            organizations = await repository.get_organizations_with_services(
                skip=skip, limit=per_page
            )
        else:
            organizations = await repository.get_all(skip=skip, limit=per_page)

        total = await repository.count()

    # Convert to response models
    org_responses = []
    for org in organizations:
        org_data = OrganizationResponse.model_validate(org)

        if include_services and hasattr(org, "services") and org.services:
            # Add service details (simplified for now)
            org_data.services = [
                ServiceResponse.model_validate(service) for service in org.services
            ]

        org_responses.append(org_data)

    # Calculate pagination metadata
    total_pages = (total + per_page - 1) // per_page

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=total_pages,
        per_page=per_page,
        extra_params={"name": name, "include_services": include_services},
    )

    return Page(
        count=len(org_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=total_pages,
        links=links,
        data=org_responses,
    )


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: UUID,
    include_services: bool = Query(False, description="Include services in response"),
    session: AsyncSession = Depends(get_session),
) -> OrganizationResponse:
    """
    Get a specific organization by ID.

    Returns detailed information about an organization with optional service details.
    """
    repository = OrganizationRepository(session)

    organization = await repository.get_by_id(organization_id)
    if not organization:
        raise HTTPException(status_code=404, detail="Organization not found")

    # Convert to response model
    org_response = OrganizationResponse.model_validate(organization)

    if include_services:
        # Load services for this organization
        from app.database.repositories import ServiceRepository

        service_repo = ServiceRepository(session)
        services = await service_repo.get_services_by_organization(organization_id)

        org_response.services = [
            ServiceResponse.model_validate(service) for service in services
        ]

    return org_response


@router.get("/search", response_model=Page[OrganizationResponse])
async def search_organizations(
    request: Request,
    q: str = Query(..., description="Search query"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    session: AsyncSession = Depends(get_session),
) -> Page[OrganizationResponse]:
    """
    Search organizations by name or description.

    Returns paginated search results based on the query string.
    """
    repository = OrganizationRepository(session)

    # Search organizations
    organizations = await repository.search_by_name(q, limit=per_page)
    total = len(organizations)  # Approximation for search results

    # Convert to response models
    org_responses = [OrganizationResponse.model_validate(org) for org in organizations]

    # Calculate pagination metadata
    total_pages = max(1, (total + per_page - 1) // per_page)

    # Create pagination links
    links = create_pagination_links(
        request=request,
        current_page=page,
        total_pages=total_pages,
        per_page=per_page,
        extra_params={"q": q},
    )

    return Page(
        count=len(org_responses),
        total=total,
        per_page=per_page,
        current_page=page,
        total_pages=total_pages,
        links=links,
        data=org_responses,
    )
