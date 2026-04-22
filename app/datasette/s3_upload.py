"""S3 upload for SQLite exports.

Uploads exported SQLite databases to S3 with dated and latest copies
for public consumption. Used by the AWS publisher task definition.
"""

import os
import time
from datetime import UTC, datetime
from pathlib import Path

import boto3
import structlog

logger = structlog.get_logger(__name__)


def _today_str() -> str:
    """Return today's date as YYYY-MM-DD string (UTC)."""
    return datetime.now(tz=UTC).strftime("%Y-%m-%d")


def _invalidate_cloudfront(distribution_id: str, paths: list[str]) -> None:
    """Best-effort CloudFront invalidation — logs but never raises.

    CloudFront caches S3 exports at the edge, so a fresh S3 upload is
    invisible to downstream consumers (e.g. Plentiful) until the TTL
    expires or we explicitly invalidate. The publisher calls this
    after the `latest/` copy lands, on a fail-soft basis — an
    invalidation error should not fail the upload, since the data is
    already correctly on S3.

    Args:
        distribution_id: CloudFront distribution ID (e.g. "EMV63Z4Q8NEBE").
        paths: Absolute paths to invalidate, each starting with "/".
    """
    if not distribution_id:
        logger.info("cloudfront_invalidation_skipped_no_distribution")
        return

    client = boto3.client("cloudfront")
    try:
        resp = client.create_invalidation(
            DistributionId=distribution_id,
            InvalidationBatch={
                "Paths": {"Quantity": len(paths), "Items": paths},
                "CallerReference": f"publisher-{int(time.time())}",
            },
        )
        logger.info(
            "cloudfront_invalidation_created",
            distribution_id=distribution_id,
            invalidation_id=resp["Invalidation"]["Id"],
            paths=paths,
        )
    except Exception as e:
        logger.warning(
            "cloudfront_invalidation_failed",
            distribution_id=distribution_id,
            error=str(e),
            paths=paths,
        )


def upload_to_s3(
    local_path: str,
    bucket: str,
    prefix: str = "sqlite-exports",
) -> None:
    """Upload SQLite file to S3 with dated and latest copies.

    Creates two copies in the bucket:
    - {prefix}/{date}/pantry_pirate_radio.sqlite (dated archive)
    - {prefix}/latest/pantry_pirate_radio.sqlite (always current)

    After the uploads complete, issues a CloudFront invalidation for
    the `latest/` paths if EXPORT_CLOUDFRONT_DISTRIBUTION_ID is set
    in the environment. Invalidation is best-effort — errors are
    logged but don't fail the run.

    Args:
        local_path: Path to the local SQLite file
        bucket: S3 bucket name
        prefix: S3 key prefix (default: sqlite-exports)
    """
    client = boto3.client("s3")
    filename = Path(local_path).name
    date_str = _today_str()

    dated_key = f"{prefix}/{date_str}/{filename}"
    latest_key = f"{prefix}/latest/{filename}"

    logger.info("uploading_sqlite_to_s3", bucket=bucket, dated_key=dated_key)
    client.upload_file(local_path, bucket, dated_key)

    logger.info("uploading_sqlite_latest", bucket=bucket, latest_key=latest_key)
    client.upload_file(local_path, bucket, latest_key)

    logger.info("s3_upload_complete", bucket=bucket, prefix=prefix)

    distribution_id = os.environ.get("EXPORT_CLOUDFRONT_DISTRIBUTION_ID", "")
    _invalidate_cloudfront(
        distribution_id,
        [f"/{latest_key}", f"/{prefix}/latest/*"],
    )


def build_database_url_from_env() -> str:
    """Build PostgreSQL DATABASE_URL from component environment variables.

    Reads DATABASE_HOST, DATABASE_NAME, DATABASE_USER, DATABASE_PASSWORD,
    and optionally DATABASE_PORT from environment variables.

    Returns:
        PostgreSQL connection string

    Raises:
        ValueError: If required environment variables are missing
    """
    host = os.environ.get("DATABASE_HOST")
    if not host:
        raise ValueError("DATABASE_HOST environment variable is required")

    name = os.environ.get("DATABASE_NAME", "pantry_pirate_radio")
    user = os.environ.get("DATABASE_USER", "pantry_pirate")
    password = os.environ.get("DATABASE_PASSWORD", "")
    port = os.environ.get("DATABASE_PORT", "5432")

    from urllib.parse import quote_plus

    return f"postgresql://{user}:{quote_plus(password)}@{host}:{port}/{name}"
