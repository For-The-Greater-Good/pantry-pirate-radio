"""Tests for PTF partner sync router endpoint."""

import pytest
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.partners.ptf.router import ptf_sync


class TestPtfSyncRouter:
    """Test the PTF sync endpoint handler."""

    @pytest.fixture
    def mock_session(self):
        return MagicMock(spec=AsyncSession)

    @pytest.fixture
    def mock_request(self):
        req = MagicMock(spec=Request)
        req.headers = {}
        return req

    @pytest.fixture
    def sample_response(self):
        return {
            "meta": {
                "total_available": 1,
                "returned": 1,
                "cursor": None,
                "has_more": False,
                "generated_at": datetime(2026, 3, 7, tzinfo=UTC),
                "etag": "abc123",
                "data_version": "1.0",
            },
            "organizations": [
                {
                    "ppr_location_id": "loc-001",
                    "name": "Test Food Bank",
                    "latitude": 40.7128,
                    "longitude": -74.006,
                    "address_street_1": "123 Test St",
                    "address_street_2": "",
                    "city": "Newark",
                    "state": "NJ",
                    "zip_code": 7102,
                    "phone": 5551234567,
                    "website": "https://example.org",
                    "email": "info@example.com",
                    "additional_info": "Food distribution",
                    "schedule": "Monday: 9:00 AM - 5:00 PM",
                    "timezone": "America/New_York",
                    "hide": 0,
                    "boundless_id": None,
                    "data_sources": ["Capital Area Food Bank"],
                    "confidence_score": 85,
                    "updated_at": datetime(2026, 3, 6, 12, 0, tzinfo=UTC),
                }
            ],
        }

    @pytest.mark.asyncio
    async def test_returns_200_with_data(
        self, mock_request, mock_session, sample_response
    ):
        """Verify endpoint returns response with correct structure."""
        with patch("app.api.v1.partners.ptf.router.PtfSyncService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.sync = AsyncMock(return_value=sample_response)
            mock_svc_cls.return_value = mock_svc

            response = await ptf_sync(
                request=mock_request,
                cursor=None,
                page_size=1000,
                updated_since=None,
                session=mock_session,
            )

        assert response.status_code == 200
        assert "organizations" in response.body.decode()

    @pytest.mark.asyncio
    async def test_304_on_etag_match(self, mock_request, mock_session, sample_response):
        """Verify 304 returned when If-None-Match matches ETag."""
        mock_request.headers = {"if-none-match": "abc123"}

        with patch("app.api.v1.partners.ptf.router.PtfSyncService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.sync = AsyncMock(return_value=sample_response)
            mock_svc_cls.return_value = mock_svc

            response = await ptf_sync(
                request=mock_request,
                cursor=None,
                page_size=1000,
                updated_since=None,
                session=mock_session,
            )

        assert response.status_code == 304

    @pytest.mark.asyncio
    async def test_cache_headers_set(self, mock_request, mock_session, sample_response):
        """Verify Cache-Control and ETag headers are set."""
        with patch("app.api.v1.partners.ptf.router.PtfSyncService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.sync = AsyncMock(return_value=sample_response)
            mock_svc_cls.return_value = mock_svc

            response = await ptf_sync(
                request=mock_request,
                cursor=None,
                page_size=1000,
                updated_since=None,
                session=mock_session,
            )

        assert response.headers.get("etag") == "abc123"
        assert "private" in response.headers.get("cache-control", "")

    @pytest.mark.asyncio
    async def test_passes_params_to_service(
        self, mock_request, mock_session, sample_response
    ):
        """Verify cursor, page_size, updated_since are passed through."""
        updated = datetime(2026, 3, 1, tzinfo=UTC)

        with patch("app.api.v1.partners.ptf.router.PtfSyncService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.sync = AsyncMock(return_value=sample_response)
            mock_svc_cls.return_value = mock_svc

            await ptf_sync(
                request=mock_request,
                cursor="abc",
                page_size=500,
                updated_since=updated,
                session=mock_session,
            )

            mock_svc.sync.assert_called_once_with(
                page_size=500, cursor="abc", updated_since=updated
            )
