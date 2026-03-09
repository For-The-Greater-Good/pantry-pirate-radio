"""Map API module for serving location data to web interface."""

from fastapi import APIRouter

from app.api.v1.map.router import router as _main_router
from app.api.v1.map.geolocate import router as _geolocate_router
from app.api.v1.map.clusters import router as _clusters_router

# Create a combined router that includes both sub-routers
router = APIRouter()
router.include_router(_main_router)
router.include_router(_geolocate_router)
router.include_router(_clusters_router)

__all__ = ["router"]
