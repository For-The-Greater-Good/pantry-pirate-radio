"""Submarine-specific helpers for the batch inference pipeline.

Used by batcher.py and batch_result_processor.py when source="submarine".
Keeps submarine logic isolated so the main Lambda handlers stay under 600 lines.
"""

import json
import os
import structlog
from datetime import UTC, datetime
from typing import Any

from app.llm.providers.bedrock import build_messages_api_request
from app.pipeline.sqs_sender import send_to_sqs
from app.submarine.extractor import EXTRACTION_SYSTEM_PROMPT, SubmarineExtractor
from app.submarine.models import SubmarineJob, SubmarineResult, SubmarineStatus
from app.submarine.result_builder import SubmarineResultBuilder

logger = structlog.get_logger(__name__)


def get_submarine_batcher_config() -> dict[str, str]:
    """Return queue URLs and config for submarine batch path."""
    return {
        "staging_queue_url": os.environ.get("SUBMARINE_STAGING_QUEUE_URL", ""),
        "on_demand_queue_url": os.environ.get("SUBMARINE_EXTRACTION_QUEUE_URL", ""),
        "job_name_prefix": "ppr-sub-batch",
    }


def extract_submarine_record(record: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Extract job_id and Bedrock model input from a SubmarineStagingMessage.

    Returns:
        (job_id, messages_api_request_body)
    """
    job_id = record.get("job_id", "")
    prompt = record.get("prompt", [])

    # Build Bedrock Converse API request from the pre-built prompt
    messages_body = build_messages_api_request(
        prompt=prompt,
        temperature=0.1,  # Low temp for factual extraction
        max_tokens=2048,
    )
    return job_id, messages_body


def requeue_submarine_on_demand(
    record: dict[str, Any],
    extraction_queue_url: str,
) -> None:
    """Re-enqueue a submarine staging message for on-demand extraction."""
    job_id = record.get("job_id", "")
    send_to_sqs(
        queue_url=extraction_queue_url,
        message_body=record,
        message_group_id="submarine",
        deduplication_id=job_id,
        source="batcher-lambda",
    )


def route_submarine_success(
    record_id: str,
    output: dict[str, Any],
    original_record: dict[str, Any],
    model_id: str,
    reconciler_queue_url: str,
) -> None:
    """Route a successful submarine batch result to the reconciler.

    Parses the Bedrock output, extracts fields using SubmarineExtractor,
    builds a JobResult via SubmarineResultBuilder, and sends to reconciler.
    Submarine bypasses the validator (Constitution v1.5.1).
    """
    from app.llm.providers.bedrock import parse_messages_api_response

    # Parse Bedrock response
    llm_response = parse_messages_api_response(
        response=output,
        model_id=model_id,
    )

    missing_fields = original_record.get("missing_fields", [])
    crawl_metadata = original_record.get("crawl_metadata", {})
    submarine_job_data = original_record.get("submarine_job", {})

    # Extract structured fields from the LLM text output
    extracted = SubmarineExtractor.parse_response(
        llm_response.text or "", missing_fields
    )

    # Reconstruct SubmarineJob and SubmarineResult
    job = SubmarineJob.model_validate(submarine_job_data)

    status = (
        SubmarineStatus.SUCCESS
        if len(extracted) == len(missing_fields)
        else SubmarineStatus.PARTIAL
    )
    if not extracted:
        status = SubmarineStatus.NO_DATA

    result = SubmarineResult(
        job_id=job.id,
        location_id=job.location_id,
        status=status,
        extracted_fields=extracted,
        crawl_metadata=crawl_metadata,
    )

    # Build JobResult for the reconciler
    builder = SubmarineResultBuilder()
    job_result = builder.build(job, result)

    if job_result is None:
        logger.info(
            "submarine_batch_no_useful_data",
            record_id=record_id,
            location_id=job.location_id,
        )
        _update_location_status(job.location_id, status)
        return

    send_to_sqs(
        queue_url=reconciler_queue_url,
        message_body=job_result.model_dump(mode="json"),
        message_group_id="submarine",
        deduplication_id=record_id,
        source="submarine-batch-result-processor",
    )

    _update_location_status(job.location_id, status)

    logger.info(
        "submarine_batch_result_routed",
        record_id=record_id,
        location_id=job.location_id,
        status=status.value,
        fields_extracted=list(extracted.keys()),
    )


def _update_location_status(location_id: str, status: SubmarineStatus | str) -> None:
    """Update submarine tracking columns on the location record."""
    try:
        from sqlalchemy import create_engine, text
        from sqlalchemy.orm import sessionmaker

        from app.core.config import settings

        db_url = os.environ.get("DATABASE_URL", "") or settings.DATABASE_URL
        engine = create_engine(db_url)
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
                    "status": str(status.value if hasattr(status, "value") else status),
                    "id": location_id,
                },
            )
            session.commit()
    except Exception as e:
        logger.error(
            "submarine_batch_status_update_failed",
            location_id=location_id,
            status=str(status),
            error=str(e),
        )
