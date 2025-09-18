"""Tests for taxonomy API endpoints."""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from fastapi import Request

from app.api.v1.taxonomies import list_taxonomies, get_taxonomy


class TestTaxonomiesAPI:
    """Test cases for taxonomy API endpoints."""

    @pytest.mark.asyncio
    async def test_list_taxonomies(self):
        """Test list taxonomies endpoint returns not implemented message."""
        # Create mock request
        mock_request = MagicMock(spec=Request)

        # Call the endpoint
        result = await list_taxonomies(
            request=mock_request, page=1, per_page=25, search=None
        )

        assert result["status"] == "not_implemented"
        assert result["message"] == "Taxonomy endpoints are not yet implemented"
        assert result["hsds_version"] == "3.1.1"

    @pytest.mark.asyncio
    async def test_list_taxonomies_with_params(self):
        """Test list taxonomies endpoint with query parameters."""
        # Create mock request
        mock_request = MagicMock(spec=Request)

        # Call the endpoint with parameters
        result = await list_taxonomies(
            request=mock_request, page=2, per_page=50, search="food"
        )

        assert result["status"] == "not_implemented"
        assert result["message"] == "Taxonomy endpoints are not yet implemented"

    @pytest.mark.asyncio
    async def test_get_taxonomy(self):
        """Test get specific taxonomy endpoint returns not implemented message."""
        taxonomy_id = uuid4()

        # Call the endpoint
        result = await get_taxonomy(taxonomy_id=taxonomy_id)

        assert result["status"] == "not_implemented"
        assert result["message"] == "Taxonomy endpoints are not yet implemented"
        assert result["requested_id"] == str(taxonomy_id)
        assert result["hsds_version"] == "3.1.1"
