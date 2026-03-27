"""Submarine web crawler — crawls food bank websites for missing data.

Uses crawl4ai for LLM-ready markdown extraction from web pages.
Follows relevant links (Contact, Hours, About, Services) to find
phone numbers, hours, email addresses, and descriptions.
"""

import logging
import re
from dataclasses import dataclass, field

from app.submarine.rate_limiter import SubmarineRateLimiter

logger = logging.getLogger(__name__)

# Link text patterns that suggest pages with contact/hours/service info
RELEVANT_LINK_PATTERNS = re.compile(
    r"contact|hours|location|about|service|find\s+food|get\s+help|"
    r"program|pantry|distribution|schedule",
    re.IGNORECASE,
)

# Link text patterns to skip (not useful for our extraction)
SKIP_LINK_PATTERNS = re.compile(
    r"donat|volunt|blog|news|event|career|press|media|"
    r"privacy|terms|login|sign.?up|cart|shop|store",
    re.IGNORECASE,
)


@dataclass
class CrawlResult:
    """Result of crawling a website."""

    url: str
    markdown: str
    pages_crawled: int
    status: str  # 'success', 'partial', 'no_data', 'error'
    links_followed: list[str] = field(default_factory=list)
    error: str | None = None


class SubmarineCrawler:
    """Crawls food bank websites and returns LLM-ready markdown content.

    Strategy:
        1. Fetch the main page and extract markdown
        2. Identify relevant links (Contact, Hours, About, Services)
        3. Follow up to (max_pages - 1) relevant links
        4. Combine all page content into a single markdown document
    """

    def __init__(
        self,
        max_pages: int = 3,
        timeout: int = 30,
        rate_limiter: SubmarineRateLimiter | None = None,
    ):
        self.max_pages = max_pages
        self.timeout = timeout
        self.rate_limiter = rate_limiter or SubmarineRateLimiter()

    async def crawl(self, url: str) -> CrawlResult:
        """Crawl a website and return combined markdown content.

        Args:
            url: Starting URL to crawl.

        Returns:
            CrawlResult with combined markdown from all crawled pages.
        """
        try:
            from crawl4ai import (
                AsyncWebCrawler,
                BrowserConfig,
                CacheMode,
                CrawlerRunConfig,
            )
        except ImportError:
            logger.error("crawl4ai not installed — cannot crawl")
            return CrawlResult(
                url=url,
                markdown="",
                pages_crawled=0,
                status="error",
                error="crawl4ai not installed",
            )

        all_markdown: list[str] = []
        links_followed: list[str] = []
        pages_crawled = 0

        browser_config = BrowserConfig(
            headless=True,
            verbose=False,
            text_mode=True,  # Skip images — faster, less memory
            light_mode=True,  # Disable background features
            user_agent=self.rate_limiter.user_agent,
            extra_args=[
                "--no-sandbox",  # Required when running as root in Docker
                "--disable-dev-shm-usage",  # Avoid /dev/shm 64MB limit
                "--disable-gpu",  # No GPU in containers
            ],
        )
        run_config = CrawlerRunConfig(
            word_count_threshold=5,  # Low threshold to capture short contact blocks
            page_timeout=self.timeout * 1000,  # crawl4ai uses milliseconds
            cache_mode=CacheMode.BYPASS,  # Always fetch fresh
            remove_overlay_elements=True,  # Dismiss cookie banners
        )

        try:
            async with AsyncWebCrawler(config=browser_config) as crawler:
                # --- Page 1: Main page ---
                await self.rate_limiter.wait_and_record(url)
                result = await crawler.arun(url=url, config=run_config)

                if not result.success:
                    return CrawlResult(
                        url=url,
                        markdown="",
                        pages_crawled=0,
                        status="error",
                        error=result.error_message or "Crawl failed",
                    )

                # result.markdown is a MarkdownGenerationResult, not a string
                page_md = result.markdown.raw_markdown if result.markdown else ""
                all_markdown.append(f"# Page: {url}\n\n{page_md}")
                pages_crawled = 1

                # --- Extract and follow relevant links ---
                if pages_crawled < self.max_pages and result.links:
                    page_links = [
                        (link.get("href", ""), link.get("text", ""))
                        for link in result.links.get("internal", [])
                        if link.get("href")
                    ]
                    relevant = self._filter_relevant_links(page_links)

                    for link_url, _link_text in relevant:
                        if pages_crawled >= self.max_pages:
                            break

                        await self.rate_limiter.wait_and_record(link_url)
                        sub_result = await crawler.arun(url=link_url, config=run_config)

                        if sub_result.success and sub_result.markdown:
                            sub_md = sub_result.markdown.raw_markdown
                            if sub_md and sub_md.strip():
                                all_markdown.append(
                                    f"\n\n# Page: {link_url}\n\n{sub_md}"
                                )
                                links_followed.append(link_url)
                                pages_crawled += 1

        except Exception as e:
            error_msg = str(e)
            logger.warning(
                "submarine_crawl_error",
                extra={"url": url, "error": error_msg},
            )
            if pages_crawled > 0:
                return CrawlResult(
                    url=url,
                    markdown="\n".join(all_markdown),
                    pages_crawled=pages_crawled,
                    status="partial" if all_markdown else "error",
                    links_followed=links_followed,
                    error=error_msg,
                )
            return CrawlResult(
                url=url,
                markdown="",
                pages_crawled=0,
                status="error",
                error=error_msg,
            )

        combined = "\n".join(all_markdown)
        return CrawlResult(
            url=url,
            markdown=combined,
            pages_crawled=pages_crawled,
            status="success" if combined.strip() else "no_data",
            links_followed=links_followed,
        )

    @staticmethod
    def _filter_relevant_links(
        links: list[tuple[str, str]],
    ) -> list[tuple[str, str]]:
        """Filter links to only those likely to contain contact/hours info.

        Args:
            links: List of (url, text) tuples from the page.

        Returns:
            Filtered list of relevant (url, text) tuples.
        """
        relevant = []
        for url, text in links:
            combined = f"{url} {text}"
            if SKIP_LINK_PATTERNS.search(combined):
                continue
            if RELEVANT_LINK_PATTERNS.search(combined):
                relevant.append((url, text))
        return relevant
