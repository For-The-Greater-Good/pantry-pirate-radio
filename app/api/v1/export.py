"""Export endpoints for locations."""

from typing import Dict, Any, List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/locations", tags=["export"])


class ExportResponse(BaseModel):
    """Export response model."""
    metadata: Dict[str, Any]
    locations: List[Dict[str, Any]]


@router.get("/export-working")
async def export_working():
    """Test export endpoint in separate file."""
    return {
        "metadata": {
            "test": "from separate file",
            "working": True
        },
        "locations": []
    }