"""Beacon configuration from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


@dataclass
class BeaconConfig:
    """Configuration for the beacon static site generator."""

    # Database
    db_host: str = field(default_factory=lambda: os.getenv("DATABASE_HOST", "localhost"))
    db_port: int = field(
        default_factory=lambda: int(os.getenv("DATABASE_PORT", "5432"))
    )
    db_user: str = field(default_factory=lambda: os.getenv("DATABASE_USER", "postgres"))
    db_password: str = field(
        default_factory=lambda: os.getenv("DATABASE_PASSWORD", "pirate")
    )
    db_name: str = field(
        default_factory=lambda: os.getenv("DATABASE_NAME", "pantry_pirate_radio")
    )
    db_secret_arn: str | None = field(
        default_factory=lambda: os.getenv("DATABASE_SECRET_ARN")
    )
    db_proxy_endpoint: str | None = field(
        default_factory=lambda: os.getenv("DATABASE_PROXY_ENDPOINT")
    )

    # Beacon
    base_url: str = field(
        default_factory=lambda: os.getenv(
            "BEACON_BASE_URL", "https://plentiful.org/providers"
        )
    )
    output_dir: str = field(
        default_factory=lambda: os.getenv("BEACON_OUTPUT_DIR", "./output")
    )
    s3_bucket: str | None = field(
        default_factory=lambda: os.getenv("BEACON_S3_BUCKET")
    )
    cloudfront_dist_id: str | None = field(
        default_factory=lambda: os.getenv("BEACON_CLOUDFRONT_DIST_ID")
    )
    analytics_endpoint: str | None = field(
        default_factory=lambda: os.getenv("BEACON_ANALYTICS_ENDPOINT")
    )

    # Quality gate
    min_confidence: int = 93

    @property
    def dsn(self) -> str:
        """PostgreSQL connection string."""
        host = self.db_proxy_endpoint or self.db_host
        return (
            f"postgresql://{self.db_user}:{self.db_password}"
            f"@{host}:{self.db_port}/{self.db_name}"
        )
