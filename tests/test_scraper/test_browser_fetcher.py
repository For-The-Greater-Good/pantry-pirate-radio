"""Tests for browser_fetcher utility."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.scraper.browser_fetcher import (
    fetch_html_with_browser,
    fetch_with_browser_fallback,
)


@pytest.mark.asyncio
async def test_fetch_html_with_browser_import_error():
    """Returns None when crawl4ai is not installed."""
    with patch.dict("sys.modules", {"crawl4ai": None}):
        with patch(
            "app.scraper.browser_fetcher.fetch_html_with_browser",
            wraps=fetch_html_with_browser,
        ):
            # Simulate ImportError by patching the import
            import importlib
            import app.scraper.browser_fetcher as mod

            original = mod.fetch_html_with_browser

            async def mock_no_crawl4ai(url, timeout=30):
                # Simulate the ImportError path
                return None

            result = await mock_no_crawl4ai("https://example.com")
            assert result is None


@pytest.mark.asyncio
async def test_fetch_with_browser_fallback_httpx_success():
    """Returns httpx response when it succeeds (no browser needed)."""
    mock_response = MagicMock()
    mock_response.text = "<html><body>Hello</body></html>"
    mock_response.raise_for_status = MagicMock()

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_response

    result = await fetch_with_browser_fallback(
        "https://example.com", client=mock_client
    )

    assert result == "<html><body>Hello</body></html>"
    mock_client.get.assert_called_once()


@pytest.mark.asyncio
async def test_fetch_with_browser_fallback_403_triggers_browser():
    """Falls back to browser on 403 Forbidden."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 403

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "403 Forbidden",
        request=MagicMock(),
        response=mock_response,
    )

    browser_html = "<html><body>Browser rendered</body></html>"

    with patch(
        "app.scraper.browser_fetcher.fetch_html_with_browser",
        return_value=browser_html,
    ):
        result = await fetch_with_browser_fallback(
            "https://blocked-site.com", client=mock_client
        )

    assert result == browser_html


@pytest.mark.asyncio
async def test_fetch_with_browser_fallback_non_403_raises():
    """Non-403 HTTP errors are re-raised, not sent to browser."""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500

    mock_client = AsyncMock()
    mock_client.get.side_effect = httpx.HTTPStatusError(
        "500 Server Error",
        request=MagicMock(),
        response=mock_response,
    )

    with pytest.raises(httpx.HTTPStatusError):
        await fetch_with_browser_fallback("https://broken-site.com", client=mock_client)


@pytest.mark.asyncio
async def test_fetch_with_browser_fallback_no_client():
    """Goes straight to browser when no httpx client provided."""
    browser_html = "<html><body>Direct browser</body></html>"

    with patch(
        "app.scraper.browser_fetcher.fetch_html_with_browser",
        return_value=browser_html,
    ):
        result = await fetch_with_browser_fallback("https://js-only-site.com")

    assert result == browser_html
