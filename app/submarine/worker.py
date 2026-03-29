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

# Keywords that indicate food-related content. At least 2 distinct matches required.
_FOOD_KEYWORDS = [
    "food bank",
    "food pantry",
    "food distribution",
    "food assistance",
    "food shelf",
    "food closet",
    "food program",
    "food insecurity",
    "free food",
    "food box",
    "pantry",
    "grocery",
    "hunger",
    "feeding",
    "snap",
    "wic",
    "meal program",
]

_FOOD_RELEVANCE_THRESHOLD = 2


def _check_content_relevance(markdown: str) -> bool:
    """Check if crawled content is about a food bank or food assistance program.

    Performs a case-insensitive keyword scan. Requires at least 2 distinct
    keyword matches to pass — a single mention of "food" in a footer is
    not sufficient.
    """
    text_lower = markdown.lower()
    matches = sum(1 for kw in _FOOD_KEYWORDS if kw in text_lower)
    return matches >= _FOOD_RELEVANCE_THRESHOLD


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
        result, location_id, status = _process_job(job_data)
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

    # Update status AFTER successful forwarding to prevent data loss
    if result:
        _update_location_status(location_id, status)

    return result


def _process_job(
    job_data: dict[str, Any],
) -> tuple[dict[str, Any] | None, str, str]:
    """Inner processing logic, wrapped by process_submarine_job for error handling.

    Returns:
        Tuple of (result_dict, location_id, status). The caller is responsible
        for updating location status AFTER successful queue forwarding to avoid
        a data loss window where status is marked success but data never reaches
        the reconciler.
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

    if result.status == SubmarineStatus.STAGED:
        # Crawl succeeded, extraction staged for batch inference.
        # DB status updated to "staged" — the batch result processor
        # will update to success/error after extraction completes.
        _update_location_status(job.location_id, result.status)
        return None, job.location_id, result.status

    if result.status in (
        SubmarineStatus.NO_DATA,
        SubmarineStatus.ERROR,
        SubmarineStatus.BLOCKED,
    ):
        # Update status immediately — no forwarding needed for these statuses
        _update_location_status(job.location_id, result.status)
        logger.info(
            "submarine_job_no_useful_data",
            extra={
                "job_id": job.id,
                "location_id": job.location_id,
                "status": result.status,
                "error": result.error,
            },
        )
        return None, job.location_id, result.status

    # Build JobResult for the Reconciler
    builder = SubmarineResultBuilder()
    job_result = builder.build(job, result)

    if job_result is None:
        _update_location_status(job.location_id, result.status)
        return None, job.location_id, result.status

    logger.info(
        "submarine_job_completed",
        extra={
            "job_id": job.id,
            "location_id": job.location_id,
            "fields_extracted": list(result.extracted_fields.keys()),
            "pages_crawled": result.crawl_metadata.get("pages_crawled", 0),
        },
    )

    # Do NOT update status here — caller must do it after forwarding
    return job_result.model_dump(mode="json"), job.location_id, result.status


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

    # --- Content relevance gate ---
    if not _check_content_relevance(crawl_result.markdown):
        logger.info(
            "submarine_content_not_food_related",
            extra={
                "job_id": job.id,
                "location_id": job.location_id,
                "website_url": job.website_url,
            },
        )
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status=SubmarineStatus.NO_DATA,
            crawl_metadata={
                "url": job.website_url,
                "pages_crawled": crawl_result.pages_crawled,
                "rejection_reason": "content_not_food_related",
            },
        )

    crawl_metadata = {
        "url": job.website_url,
        "pages_crawled": crawl_result.pages_crawled,
        "links_followed": crawl_result.links_followed,
    }

    # --- AWS batch path: stage for batch inference (50% cheaper) ---
    if os.environ.get("QUEUE_BACKEND", "redis").lower() == "sqs":
        return _stage_for_batch_extraction(job, crawl_result, crawl_metadata)

    # --- Local/Redis path: extract inline ---
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
            crawl_metadata=crawl_metadata,
            error=f"LLM extraction failed: {e}",
        )

    if not extracted:
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status=SubmarineStatus.NO_DATA,
            crawl_metadata=crawl_metadata,
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
        crawl_metadata=crawl_metadata,
    )


def _stage_for_batch_extraction(
    job: SubmarineJob,
    crawl_result: Any,
    crawl_metadata: dict[str, Any],
) -> SubmarineResult:
    """Stage crawled content for batch inference instead of extracting inline.

    Builds the extraction prompt, creates a SubmarineStagingMessage, and
    enqueues it to the submarine-staging queue. Returns a STAGED result
    so the caller updates the DB accordingly.
    """
    from app.pipeline.sqs_sender import send_to_sqs
    from app.submarine.extractor import (
        EXTRACTION_SYSTEM_PROMPT,
        SubmarineExtractor,
    )
    from app.submarine.staging import SubmarineStagingMessage

    # Build the extraction prompt (same prompt the inline path would use)
    user_prompt = SubmarineExtractor.build_prompt(
        crawl_result.markdown, job.missing_fields
    )
    prompt = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    staging_msg = SubmarineStagingMessage(
        job_id=job.id,
        location_id=job.location_id,
        submarine_job=job.model_dump(mode="json"),
        prompt=prompt,
        missing_fields=job.missing_fields,
        crawl_metadata=crawl_metadata,
    )

    staging_queue_url = os.environ.get("SUBMARINE_STAGING_QUEUE_URL", "")
    if not staging_queue_url:
        logger.error("submarine_staging_queue_url_not_set", job_id=job.id)
        return SubmarineResult(
            job_id=job.id,
            location_id=job.location_id,
            status=SubmarineStatus.ERROR,
            crawl_metadata=crawl_metadata,
            error="SUBMARINE_STAGING_QUEUE_URL not set",
        )

    send_to_sqs(
        queue_url=staging_queue_url,
        message_body=staging_msg.model_dump(mode="json"),
        message_group_id="submarine",
        deduplication_id=job.id,
        source="submarine-crawler",
    )

    logger.info(
        "submarine_job_staged_for_batch",
        job_id=job.id,
        location_id=job.location_id,
        missing_fields=job.missing_fields,
        pages_crawled=crawl_metadata.get("pages_crawled", 0),
    )

    return SubmarineResult(
        job_id=job.id,
        location_id=job.location_id,
        status=SubmarineStatus.STAGED,
        crawl_metadata=crawl_metadata,
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
