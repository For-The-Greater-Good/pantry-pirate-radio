"""Taxonomy Terms API endpoints (stub implementation)."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.hsds.response import Page

router = APIRouter(prefix="/taxonomy-terms", tags=["taxonomy-terms"])


@router.get("/")
async def list_taxonomy_terms(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search query"),
    taxonomy_id: Optional[UUID] = Query(None, description="Filter by taxonomy ID"),
) -> dict:
    """
    List taxonomy terms (not yet implemented).

    This endpoint is part of HSDS v3.1.1 specification but taxonomy term
    models are not yet implemented in this system.
    """
    return {
        "message": "Taxonomy term endpoints are not yet implemented",
        "status": "not_implemented",
        "note": "This system currently focuses on core HSDS entities: organizations, services, locations, and service_at_location",
        "hsds_version": "3.1.1",
    }


@router.get("/{taxonomy_term_id}")
async def get_taxonomy_term(
    taxonomy_term_id: UUID,
) -> dict:
    """
    Get a specific taxonomy term by ID (not yet implemented).

    This endpoint is part of HSDS v3.1.1 specification but taxonomy term
    models are not yet implemented in this system.
    """
    return {
        "message": "Taxonomy term endpoints are not yet implemented",
        "status": "not_implemented",
        "requested_id": str(taxonomy_term_id),
        "note": "This system currently focuses on core HSDS entities: organizations, services, locations, and service_at_location",
        "hsds_version": "3.1.1",
    }
