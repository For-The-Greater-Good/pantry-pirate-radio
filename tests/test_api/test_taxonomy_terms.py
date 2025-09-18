"""Tests for taxonomy terms API endpoints."""

import pytest
from uuid import uuid4
from unittest.mock import MagicMock
from fastapi import Request

from app.api.v1.taxonomy_terms import list_taxonomy_terms, get_taxonomy_term


class TestTaxonomyTermsAPI:
    """Test cases for taxonomy terms API endpoints."""

    @pytest.mark.asyncio
    async def test_list_taxonomy_terms(self):
        """Test list taxonomy terms endpoint returns not implemented message."""
        # Create mock request
        mock_request = MagicMock(spec=Request)

        # Call the endpoint
        result = await list_taxonomy_terms(
            request=mock_request, page=1, per_page=25, search=None, taxonomy_id=None
        )

        assert result["status"] == "not_implemented"
        assert result["message"] == "Taxonomy term endpoints are not yet implemented"
        assert result["hsds_version"] == "3.1.1"

    @pytest.mark.asyncio
    async def test_list_taxonomy_terms_with_params(self):
        """Test list taxonomy terms endpoint with query parameters."""
        taxonomy_id = uuid4()
        # Create mock request
        mock_request = MagicMock(spec=Request)

        # Call the endpoint with parameters
        result = await list_taxonomy_terms(
            request=mock_request,
            page=2,
            per_page=50,
            search="food",
            taxonomy_id=taxonomy_id,
        )

        assert result["status"] == "not_implemented"
        assert result["message"] == "Taxonomy term endpoints are not yet implemented"

    @pytest.mark.asyncio
    async def test_get_taxonomy_term(self):
        """Test get specific taxonomy term endpoint returns not implemented message."""
        term_id = uuid4()

        # Call the endpoint
        result = await get_taxonomy_term(taxonomy_term_id=term_id)

        assert result["status"] == "not_implemented"
        assert result["message"] == "Taxonomy term endpoints are not yet implemented"
        assert result["requested_id"] == str(term_id)
        assert result["hsds_version"] == "3.1.1"
