"""Submarine worker — processes SubmarineJobs from the queue.

Crawls food bank websites, extracts missing data using LLM, and
sends enriched results back to the Reconciler queue.

Submarine results go directly to the Reconciler, bypassing the Validator.
This is intentional: submarine targets existing validated locations (coordinates
already verified) and only fills missing text fields (phone, hours, email,
description). These fields have no geographic validation requirements, and the
reconciler's update path handles merge logic. See constitution.md v1.5.0.
"""

import asyncio
import os
import structlog
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.llm.providers.factory import create_provider
from app.submarine.crawler import SubmarineCrawler
from app.submarine.extractor import ExtractionError, SubmarineExtractor
from app.submarine.models import SubmarineJob, SubmarineResult, SubmarineStatus
from app.submarine.rate_limiter import SubmarineRateLimiter
from app.submarine.result_builder import SubmarineResultBuilder

logger = structlog.get_logger(__name__)


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
    try:
        result = _process_job(job_data)
    except Exception as e:
        logger.error(
            "submarine_job_failed",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "job_data_keys": (
                    list(job_data.keys()) if isinstance(job_data, dict) else None
                ),
            },
        )
        raise

    # Forward to reconciler queue (local/Redis only).
    # On AWS, the PipelineWorker in fargate_worker.py handles forwarding automatically.
    if result and os.environ.get("QUEUE_BACKEND", "redis").lower() != "sqs":
        from app.llm.queue.queues import reconciler_queue

        reconciler_queue.enqueue_call(
            func="app.reconciler.job_processor.process_job_result",
            args=(result,),
            result_ttl=settings.REDIS_TTL_SECONDS,
            failure_ttl=settings.REDIS_TTL_SECONDS,
        )
        logger.info(
            "submarine_result_forwarded_to_reconciler",
            job_id=result.get("job_id", "unknown"),
        )

    return result


def _process_job(job_data: dict[str, Any]) -> dict[str, Any] | None:
    """Inner processing logic, wrapped by process_submarine_job for error handling."""
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
            status=SubmarineStatus.ERROR,
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
            status=SubmarineStatus.NO_DATA,
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
    try:
        extracted = await extractor.extract(
            markdown=crawl_result.markdown,
            missing_fields=job.missing_fields,
            provider=provider,
        )
    except ExtractionError as e:
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status=SubmarineStatus.ERROR,
            crawl_metadata={
                "url": job.website_url,
                "pages_crawled": crawl_result.pages_crawled,
                "links_followed": crawl_result.links_followed,
            },
            error=f"LLM extraction failed: {e}",
        )

    if not extracted:
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status=SubmarineStatus.NO_DATA,
            crawl_metadata={
                "url": job.website_url,
                "pages_crawled": crawl_result.pages_crawled,
                "links_followed": crawl_result.links_followed,
            },
        )

    status = (
        SubmarineStatus.SUCCESS
        if len(extracted) == len(job.missing_fields)
        else SubmarineStatus.PARTIAL
    )

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


def _get_engine():
    """Get or create the module-level SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_engine(settings.DATABASE_URL)
    return _engine


_engine = None


def _update_location_status(location_id: str, status: str) -> None:
    """Update submarine tracking columns on the location record."""
    try:
        engine = _get_engine()
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
        logger.error(
            "submarine_status_update_failed",
            extra={"location_id": location_id, "status": status, "error": str(e)},
        )
