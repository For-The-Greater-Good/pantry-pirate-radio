"""Submarine worker — processes SubmarineJobs from the queue.

Crawls food bank websites, extracts missing data using LLM, and
sends enriched results back to the Reconciler queue.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.llm.providers.factory import create_provider
from app.submarine.crawler import SubmarineCrawler
from app.submarine.extractor import SubmarineExtractor
from app.submarine.models import SubmarineJob, SubmarineResult
from app.submarine.rate_limiter import SubmarineRateLimiter
from app.submarine.result_builder import SubmarineResultBuilder

logger = logging.getLogger(__name__)


def process_submarine_job(job_data: dict[str, Any]) -> dict[str, Any] | None:
    """Process a submarine job from the queue.

    This is the RQ entry point. Deserializes the job, runs the async
    crawl/extract pipeline, updates the DB, and returns the result
    for forwarding to the Reconciler.

    Args:
        job_data: Serialized SubmarineJob dict from the queue.

    Returns:
        Serialized JobResult dict for the Reconciler queue, or None.
    """
    job = SubmarineJob.model_validate(job_data)
    logger.info(
        "submarine_job_started",
        extra={
            "job_id": job.id,
            "location_id": job.location_id,
            "website_url": job.website_url,
            "missing_fields": job.missing_fields,
            "attempt": job.attempt,
        },
    )

    result = asyncio.run(_process_async(job))

    # Update the location's submarine tracking columns
    _update_location_status(job.location_id, result.status)

    if result.status in ("no_data", "error", "blocked"):
        logger.info(
            "submarine_job_no_useful_data",
            extra={
                "job_id": job.id,
                "location_id": job.location_id,
                "status": result.status,
                "error": result.error,
            },
        )
        return None

    # Build JobResult for the Reconciler
    builder = SubmarineResultBuilder()
    job_result = builder.build(job, result)

    if job_result is None:
        return None

    logger.info(
        "submarine_job_completed",
        extra={
            "job_id": job.id,
            "location_id": job.location_id,
            "fields_extracted": list(result.extracted_fields.keys()),
            "pages_crawled": result.crawl_metadata.get("pages_crawled", 0),
        },
    )

    return job_result.model_dump(mode="json")


async def _process_async(job: SubmarineJob) -> SubmarineResult:
    """Async pipeline: crawl website, extract fields with LLM.

    Args:
        job: The SubmarineJob to process.

    Returns:
        SubmarineResult with extracted fields or error info.
    """
    rate_limiter = SubmarineRateLimiter(
        min_delay_seconds=settings.SUBMARINE_MIN_CRAWL_DELAY,
    )
    crawler = SubmarineCrawler(
        max_pages=settings.SUBMARINE_MAX_PAGES_PER_SITE,
        timeout=settings.SUBMARINE_CRAWL_TIMEOUT,
        rate_limiter=rate_limiter,
    )

    # --- Crawl ---
    crawl_result = await crawler.crawl(job.website_url)

    if crawl_result.status == "error":
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status="error",
            crawl_metadata={
                "url": job.website_url,
                "pages_crawled": crawl_result.pages_crawled,
            },
            error=crawl_result.error,
        )

    if not crawl_result.markdown.strip():
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status="no_data",
            crawl_metadata={
                "url": job.website_url,
                "pages_crawled": crawl_result.pages_crawled,
            },
        )

    # --- Extract with LLM ---
    provider = create_provider(
        provider_name=settings.LLM_PROVIDER,
        model_name=settings.LLM_MODEL_NAME,
        temperature=0.1,
        max_tokens=2048,
    )
    extractor = SubmarineExtractor()
    extracted = await extractor.extract(
        markdown=crawl_result.markdown,
        missing_fields=job.missing_fields,
        provider=provider,
    )

    if not extracted:
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status="no_data",
            crawl_metadata={
                "url": job.website_url,
                "pages_crawled": crawl_result.pages_crawled,
                "links_followed": crawl_result.links_followed,
            },
        )

    status = "success" if len(extracted) == len(job.missing_fields) else "partial"

    return SubmarineResult(
        job_id=job.id,
        location_id=job.location_id,
        status=status,
        extracted_fields=extracted,
        crawl_metadata={
            "url": job.website_url,
            "pages_crawled": crawl_result.pages_crawled,
            "links_followed": crawl_result.links_followed,
        },
    )


def _update_location_status(location_id: str, status: str) -> None:
    """Update submarine tracking columns on the location record."""
    try:
        engine = create_engine(settings.DATABASE_URL)
        session_factory = sessionmaker(bind=engine)
        with session_factory() as session:
            session.execute(
                text(
                    "UPDATE location SET "
                    "submarine_last_crawled_at = :now, "
                    "submarine_last_status = :status "
                    "WHERE id = :id"
                ),
                {
                    "now": datetime.now(UTC),
                    "status": status,
                    "id": location_id,
                },
            )
            session.commit()
    except Exception as e:
        logger.warning(
            "submarine_status_update_failed",
            extra={"location_id": location_id, "error": str(e)},
        )
