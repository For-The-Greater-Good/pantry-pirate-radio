#!/usr/bin/env python3
"""Fix state mismatches in existing location data.

This script:
1. Identifies locations with state/coordinate mismatches
2. Uses ZIP codes and city names to determine correct state
3. Updates the database with corrections
4. Logs all changes for audit
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from app.validator.reprocessor import NeedsReviewReprocessor
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import logging


async def main():
    """Main function to run state mismatch corrections."""

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('state_corrections.log')
        ]
    )

    logger = logging.getLogger(__name__)

    logger.info("=" * 60)
    logger.info("Starting state mismatch correction process")
    logger.info("=" * 60)

    # Create database connection
    # Convert DATABASE_URL to async format
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    elif db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")

    engine = create_async_engine(
        db_url,
        echo=False,
        pool_pre_ping=True
    )

    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with async_session() as session:
            # Create reprocessor
            reprocessor = NeedsReviewReprocessor(session)

            # Process in batches
            batch_size = 100
            total_processed = 0
            total_corrected = 0

            while True:
                logger.info(f"\nProcessing batch (up to {batch_size} locations)...")

                # Process batch
                stats = await reprocessor.reprocess_batch(limit=batch_size)

                if stats['total_processed'] == 0:
                    logger.info("No more locations to process")
                    break

                total_processed += stats['total_processed']
                total_corrected += stats['state_corrected']

                logger.info(
                    f"Batch complete: processed={stats['total_processed']}, "
                    f"corrected={stats['state_corrected']}, "
                    f"errors={stats['errors']}"
                )

                # Reset stats for next batch
                reprocessor.stats = {
                    "total_processed": 0,
                    "state_corrected": 0,
                    "coordinates_corrected": 0,
                    "status_updated": 0,
                    "errors": 0
                }

                # Optional: Add delay between batches to avoid overload
                await asyncio.sleep(1)

                # Optional: Limit total processing
                if total_processed >= 1000:
                    logger.info("Reached processing limit of 1000 locations")
                    break

            logger.info("\n" + "=" * 60)
            logger.info("State mismatch correction complete")
            logger.info(f"Total locations processed: {total_processed}")
            logger.info(f"Total states corrected: {total_corrected}")
            logger.info("=" * 60)

    except Exception as e:
        logger.error(f"Error during processing: {e}", exc_info=True)
        sys.exit(1)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())