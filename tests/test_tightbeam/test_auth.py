"""Tests for Tightbeam API key authentication."""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.tightbeam.auth import _parse_local_keys, require_api_key
from app.api.v1.tightbeam.models import CallerIdentity


class TestParseLocalKeys:
    """Test local API key parsing."""

    def test_empty_string(self):
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_API_KEYS = ""
            assert _parse_local_keys() == {}

    def test_single_key(self):
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_API_KEYS = "my-secret-key"
            keys = _parse_local_keys()
            assert "my-secret-key" in keys
            assert keys["my-secret-key"] == "default"

    def test_named_keys(self):
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_API_KEYS = "slackbot:key1,admin:key2"
            keys = _parse_local_keys()
            assert keys["key1"] == "slackbot"
            assert keys["key2"] == "admin"

    def test_mixed_format(self):
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_API_KEYS = "slackbot:key1,plain-key"
            keys = _parse_local_keys()
            assert keys["key1"] == "slackbot"
            assert keys["plain-key"] == "default"

    def test_whitespace_handling(self):
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_API_KEYS = " slackbot : key1 , admin : key2 "
            keys = _parse_local_keys()
            assert keys["key1"] == "slackbot"
            assert keys["key2"] == "admin"


class TestRequireApiKey:
    """Test the require_api_key dependency."""

    @pytest.fixture
    def mock_request(self):
        req = MagicMock()
        req.url.path = "/api/v1/tightbeam/search"
        req.client.host = "127.0.0.1"
        req.headers = {"user-agent": "TestAgent/1.0"}
        return req

    @pytest.mark.asyncio
    async def test_rejects_missing_key(self, mock_request):
        """Request without API key should be rejected."""
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_ENABLED = True
            mock_settings.TIGHTBEAM_API_KEYS = "slackbot:valid-key"

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
                with pytest.raises(HTTPException) as exc_info:
                    await require_api_key(mock_request, api_key=None)
                assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_rejects_invalid_key(self, mock_request):
        """Request with wrong API key should be rejected."""
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_ENABLED = True
            mock_settings.TIGHTBEAM_API_KEYS = "slackbot:valid-key"

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
                with pytest.raises(HTTPException) as exc_info:
                    await require_api_key(mock_request, api_key="wrong-key")
                assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_accepts_valid_key(self, mock_request):
        """Request with valid API key should succeed."""
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_ENABLED = True
            mock_settings.TIGHTBEAM_API_KEYS = "slackbot:valid-key"

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
                identity = await require_api_key(mock_request, api_key="valid-key")

                assert isinstance(identity, CallerIdentity)
                assert identity.api_key_name == "slackbot"
                assert identity.source_ip == "127.0.0.1"
                assert identity.user_agent == "TestAgent/1.0"

    @pytest.mark.asyncio
    async def test_disabled_returns_404(self, mock_request):
        """When TIGHTBEAM_ENABLED is False, return 404."""
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_ENABLED = False

            with pytest.raises(HTTPException) as exc_info:
                await require_api_key(mock_request, api_key="any-key")
            assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_aws_mode_extracts_key_id(self, mock_request):
        """In AWS mode, extract key ID from API Gateway headers."""
        mock_request.headers = {
            "x-api-key-id": "apigw-key-abc123",
            "x-api-key-name": "slackbot",
            "x-forwarded-for": "203.0.113.1",
            "user-agent": "SlackBot/1.0",
        }

        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_ENABLED = True

            with patch.dict(os.environ, {"AWS_LAMBDA_FUNCTION_NAME": "my-lambda"}):
                identity = await require_api_key(mock_request, api_key=None)

                assert identity.api_key_id == "apigw-key-abc123"
                assert identity.source_ip == "203.0.113.1"

    @pytest.mark.asyncio
    async def test_api_key_id_truncated_locally(self, mock_request):
        """Local mode should truncate API key ID for security."""
        with patch("app.api.v1.tightbeam.auth.settings") as mock_settings:
            mock_settings.TIGHTBEAM_ENABLED = True
            mock_settings.TIGHTBEAM_API_KEYS = "slackbot:my-super-secret-key"

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("AWS_LAMBDA_FUNCTION_NAME", None)
                identity = await require_api_key(
                    mock_request, api_key="my-super-secret-key"
                )

                assert identity.api_key_id == "my-super..."
                assert "secret" not in identity.api_key_id
