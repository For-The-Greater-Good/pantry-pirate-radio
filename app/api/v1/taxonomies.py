"""Taxonomy API endpoints (stub implementation)."""

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from app.models.hsds.response import Page

router = APIRouter(prefix="/taxonomies", tags=["taxonomies"])


@router.get("/")
async def list_taxonomies(
    request: Request,
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(25, ge=1, le=100, description="Items per page"),
    search: Optional[str] = Query(None, description="Search query"),
) -> dict:
    """
    List taxonomies (not yet implemented).

    This endpoint is part of HSDS v3.1.1 specification but taxonomy
    models are not yet implemented in this system.
    """
    return {
        "message": "Taxonomy endpoints are not yet implemented",
        "status": "not_implemented",
        "note": "This system currently focuses on core HSDS entities: organizations, services, locations, and service_at_location",
        "hsds_version": "3.1.1",
    }


@router.get("/{taxonomy_id}")
async def get_taxonomy(
    taxonomy_id: UUID,
) -> dict:
    """
    Get a specific taxonomy by ID (not yet implemented).

    This endpoint is part of HSDS v3.1.1 specification but taxonomy
    models are not yet implemented in this system.
    """
    return {
        "message": "Taxonomy endpoints are not yet implemented",
        "status": "not_implemented",
        "requested_id": str(taxonomy_id),
        "note": "This system currently focuses on core HSDS entities: organizations, services, locations, and service_at_location",
        "hsds_version": "3.1.1",
    }
