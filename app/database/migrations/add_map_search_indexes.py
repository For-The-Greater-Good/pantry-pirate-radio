#!/usr/bin/env python3
"""
Migration script to add map search performance indexes.
Run this to add indexes to an existing database for improved search performance.
"""

import asyncio
import logging
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


INDEX_QUERIES = [
    # Geographic indexes
    """CREATE INDEX IF NOT EXISTS idx_location_lat_lng
       ON location(latitude, longitude)
       WHERE latitude IS NOT NULL AND longitude IS NOT NULL""",
    """CREATE INDEX IF NOT EXISTS idx_location_geo_confidence
       ON location(latitude, longitude, confidence_score)
       WHERE latitude IS NOT NULL AND longitude IS NOT NULL""",
    # Address indexes
    "CREATE INDEX IF NOT EXISTS idx_address_state ON address(state_province)",
    "CREATE INDEX IF NOT EXISTS idx_address_city ON address(LOWER(city))",
    "CREATE INDEX IF NOT EXISTS idx_address_address1_lower ON address(LOWER(address_1))",
    # Location indexes
    "CREATE INDEX IF NOT EXISTS idx_location_confidence ON location(confidence_score)",
    "CREATE INDEX IF NOT EXISTS idx_location_validation ON location(validation_status)",
    "CREATE INDEX IF NOT EXISTS idx_location_canonical ON location(is_canonical) WHERE is_canonical = true",
    "CREATE INDEX IF NOT EXISTS idx_location_name_lower ON location(LOWER(name))",
    "CREATE INDEX IF NOT EXISTS idx_location_description_lower ON location(LOWER(description))",
    # Organization indexes
    "CREATE INDEX IF NOT EXISTS idx_organization_name_lower ON organization(LOWER(name))",
    "CREATE INDEX IF NOT EXISTS idx_organization_description_lower ON organization(LOWER(description))",
    # Service and language indexes
    "CREATE INDEX IF NOT EXISTS idx_service_name_lower ON service(LOWER(name))",
    "CREATE INDEX IF NOT EXISTS idx_language_name_lower ON language(LOWER(name))",
    "CREATE INDEX IF NOT EXISTS idx_language_location ON language(location_id) WHERE location_id IS NOT NULL",
    # Schedule indexes
    "CREATE INDEX IF NOT EXISTS idx_schedule_byday ON schedule(byday)",
    "CREATE INDEX IF NOT EXISTS idx_schedule_times ON schedule(opens_at, closes_at)",
    # Relationship indexes
    "CREATE INDEX IF NOT EXISTS idx_service_at_location_location ON service_at_location(location_id)",
    "CREATE INDEX IF NOT EXISTS idx_service_at_location_service ON service_at_location(service_id)",
    "CREATE INDEX IF NOT EXISTS idx_location_source_location ON location_source(location_id)",
    "CREATE INDEX IF NOT EXISTS idx_location_source_scraper ON location_source(scraper_id)",
    "CREATE INDEX IF NOT EXISTS idx_location_source_count ON location_source(location_id, scraper_id)",
    # Phone indexes
    "CREATE INDEX IF NOT EXISTS idx_phone_location ON phone(location_id) WHERE location_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_phone_organization ON phone(organization_id) WHERE organization_id IS NOT NULL",
]

ANALYZE_QUERIES = [
    "ANALYZE location",
    "ANALYZE organization",
    "ANALYZE address",
    "ANALYZE service",
    "ANALYZE service_at_location",
    "ANALYZE location_source",
    "ANALYZE language",
    "ANALYZE schedule",
    "ANALYZE phone",
]


async def create_indexes(database_url: str):
    """Create all map search indexes."""

    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session() as session:
        try:
            logger.info(f"Starting index creation at {datetime.now()}")

            # Create indexes
            for i, query in enumerate(INDEX_QUERIES, 1):
                try:
                    logger.info(
                        f"Creating index {i}/{len(INDEX_QUERIES)}: {query[:60]}..."
                    )
                    await session.execute(text(query))
                    await session.commit()
                except Exception as e:
                    logger.error(f"Failed to create index: {e}")
                    await session.rollback()

            # Analyze tables
            logger.info("Analyzing tables to update statistics...")
            for query in ANALYZE_QUERIES:
                try:
                    await session.execute(text(query))
                    await session.commit()
                except Exception as e:
                    logger.error(f"Failed to analyze table: {e}")
                    await session.rollback()

            logger.info(f"Index creation completed at {datetime.now()}")

            # Verify indexes were created
            result = await session.execute(
                text(
                    """
                SELECT indexname, tablename
                FROM pg_indexes
                WHERE schemaname = 'public'
                AND indexname LIKE 'idx_%'
                ORDER BY tablename, indexname
            """
                )
            )

            indexes = result.fetchall()
            logger.info(f"\nCreated {len(indexes)} indexes:")
            for idx in indexes:
                logger.info(f"  - {idx.tablename}: {idx.indexname}")

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            raise
        finally:
            await engine.dispose()


async def main():
    """Main migration function."""

    # Get database URL from environment
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        logger.error("DATABASE_URL environment variable not set")
        return

    # Convert to async URL if needed
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://")

    await create_indexes(database_url)


if __name__ == "__main__":
    asyncio.run(main())
