"""Fargate worker for on-demand submarine LLM extraction.

Consumes SubmarineStagingMessages from the submarine-extraction queue
when the batch threshold is not met (<100 records). Calls Bedrock
Converse API directly, builds JobResult, and sends to reconciler.

This is the on-demand fallback path — batch inference (50% cheaper)
is used when >=100 records are available.
"""

import os
import sys

import structlog

from app.llm.queue.submarine_batch import route_submarine_success

logger = structlog.get_logger(__name__)


def process_submarine_extraction(data: dict) -> dict | None:
    """Process a submarine staging message for on-demand LLM extraction.

    Args:
        data: SubmarineStagingMessage dict from the extraction queue.

    Returns:
        Result dict or None.
    """
    from app.llm.providers.bedrock import (
        build_messages_api_request,
        parse_messages_api_response,
    )
    from app.submarine.extractor import SubmarineExtractor
    from app.submarine.models import SubmarineJob, SubmarineResult, SubmarineStatus
    from app.submarine.result_builder import SubmarineResultBuilder

    job_id = data.get("job_id", "unknown")
    location_id = data.get("location_id", "")
    prompt = data.get("prompt", [])
    missing_fields = data.get("missing_fields", [])
    crawl_metadata = data.get("crawl_metadata", {})
    submarine_job_data = data.get("submarine_job", {})

    logger.info(
        "submarine_extraction_started",
        job_id=job_id,
        location_id=location_id,
        missing_fields=missing_fields,
    )

    model_id = os.environ.get(
        "BEDROCK_MODEL_ID", "us.anthropic.claude-haiku-4-5-20251001-v1:0"
    )

    try:
        import boto3

        region = os.environ.get("AWS_DEFAULT_REGION")
        kwargs = {"region_name": region} if region else {}
        bedrock = boto3.client("bedrock-runtime", **kwargs)

        # Build and call Bedrock Converse API
        request_body = build_messages_api_request(
            prompt=prompt,
            temperature=0.1,
            max_tokens=2048,
        )
        response = bedrock.converse(**request_body, modelId=model_id)

        # Parse response
        llm_response = parse_messages_api_response(
            response=response,
            model_id=model_id,
        )
    except Exception as e:
        logger.error(
            "submarine_extraction_llm_failed",
            job_id=job_id,
            error=str(e),
            exc_info=True,
        )
        from app.llm.queue.submarine_batch import _update_location_status

        _update_location_status(location_id, SubmarineStatus.ERROR)
        return None

    # Extract structured fields
    extracted = SubmarineExtractor.parse_response(
        llm_response.text or "", missing_fields
    )

    # Build result
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

    builder = SubmarineResultBuilder()
    job_result = builder.build(job, result)

    if job_result is None:
        from app.llm.queue.submarine_batch import _update_location_status

        _update_location_status(location_id, status)
        return None

    from app.llm.queue.submarine_batch import _update_location_status

    _update_location_status(location_id, status)

    logger.info(
        "submarine_extraction_completed",
        job_id=job_id,
        location_id=location_id,
        status=status.value,
        fields_extracted=list(extracted.keys()),
    )

    return job_result.model_dump(mode="json")


def main() -> int:
    """Main entry point for submarine extraction Fargate worker."""
    from app.pipeline.worker import PipelineWorker

    try:
        queue_url = os.environ.get("SUBMARINE_EXTRACTION_QUEUE_URL")
        if not queue_url:
            logger.error("SUBMARINE_EXTRACTION_QUEUE_URL is required")
            return 1

        next_queue_url = os.environ.get("RECONCILER_QUEUE_URL")
        if not next_queue_url:
            logger.error("RECONCILER_QUEUE_URL is required")
            return 1

        worker = PipelineWorker(
            queue_url=queue_url,
            process_fn=process_submarine_extraction,
            service_name="submarine-extraction",
            next_queue_url=next_queue_url,
            visibility_timeout=600,
        )
        worker.run()
        return 0

    except KeyboardInterrupt:
        logger.info("submarine_extraction_worker_interrupted")
        return 0
    except Exception:
        logger.exception("submarine_extraction_worker_startup_failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
