"""Browser-based page fetcher using crawl4ai with stealth mode.

Provides a fallback for scrapers when sites block httpx requests (403)
or require JavaScript rendering. Uses the same stealth configuration
proven in the submarine crawler.

Usage in scrapers:
    from app.scraper.browser_fetcher import fetch_with_browser_fallback

    html = await fetch_with_browser_fallback(url, client)
"""

import structlog

logger = structlog.get_logger(__name__)


async def fetch_html_with_browser(url: str, timeout: int = 30) -> str | None:
    """Fetch rendered HTML from a URL using crawl4ai stealth browser.

    Args:
        url: URL to fetch.
        timeout: Page load timeout in seconds.

    Returns:
        Rendered HTML string, or None if crawl4ai is not installed
        or the fetch fails.
    """
    try:
        from crawl4ai import (
            AsyncWebCrawler,
            BrowserConfig,
            CacheMode,
            CrawlerRunConfig,
        )
    except ImportError:
        logger.warning(
            "crawl4ai_not_installed",
            url=url,
            msg="Cannot use browser fallback — crawl4ai not installed",
        )
        return None

    browser_config = BrowserConfig(
        headless=True,
        verbose=False,
        enable_stealth=True,
        text_mode=True,
        light_mode=True,
        viewport_width=1366,
        viewport_height=768,
        extra_args=[
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-blink-features=AutomationControlled",
        ],
    )
    run_config = CrawlerRunConfig(
        page_timeout=timeout * 1000,
        cache_mode=CacheMode.BYPASS,
        wait_until="load",
        delay_before_return_html=1.0,
        remove_overlay_elements=True,
        override_navigator=True,
    )

    try:
        async with AsyncWebCrawler(config=browser_config) as crawler:
            result = await crawler.arun(url=url, config=run_config)

            if not result.success:
                logger.warning(
                    "browser_fetch_failed",
                    url=url,
                    error=result.error_message,
                )
                return None

            return result.html

    except Exception as e:
        logger.error(
            "browser_fetch_error",
            url=url,
            error=str(e),
            error_type=type(e).__name__,
        )
        return None


async def fetch_with_browser_fallback(
    url: str,
    client=None,
    headers: dict | None = None,
    timeout: int = 30,
) -> str | None:
    """Try httpx first, fall back to crawl4ai browser on 403.

    Args:
        url: URL to fetch.
        client: httpx.AsyncClient instance (if None, goes straight to browser).
        headers: Optional headers for the httpx request.
        timeout: Timeout in seconds.

    Returns:
        HTML string, or None if both methods fail.
    """
    import httpx

    if client is not None:
        try:
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                logger.info("httpx_403_trying_browser", url=url)
            else:
                raise

    return await fetch_html_with_browser(url, timeout=timeout)
