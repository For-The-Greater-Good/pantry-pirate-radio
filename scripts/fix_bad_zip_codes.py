#!/usr/bin/env python3
"""
Script to fix bad zip codes (00000) in the database.
Sets them to NULL and lowers confidence scores for affected locations.
"""

import os
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_connection():
    """Get database connection from environment variables."""
    db_url = os.getenv("DATABASE_URL")

    # Convert SQLAlchemy URL format to psycopg2 format if needed
    if db_url and db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql://")

    if not db_url:
        # Build from individual components
        db_host = os.getenv("POSTGRES_HOST", "db")
        db_port = os.getenv("POSTGRES_PORT", "5432")
        db_user = os.getenv("POSTGRES_USER", "postgres")
        db_name = os.getenv("POSTGRES_DB", "pantry_pirate_radio")
        db_password = os.getenv("POSTGRES_PASSWORD", "pirate")
        db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"

    return psycopg2.connect(db_url)


def fix_bad_zip_codes():
    """Fix locations with 00000 zip codes."""
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)

    try:
        # First, find all affected locations
        logger.info("Finding locations with bad zip codes...")
        cursor.execute("""
            SELECT
                l.id as location_id,
                l.name,
                l.confidence_score,
                l.validation_status,
                a.id as address_id,
                a.postal_code,
                a.city,
                a.state_province
            FROM location l
            JOIN address a ON a.location_id = l.id
            WHERE a.postal_code IN ('00000', '0000', '000', '99999', '12345', '11111', '22222')
               OR (a.postal_code IS NOT NULL AND LENGTH(TRIM(a.postal_code)) < 5 AND LENGTH(TRIM(a.postal_code)) > 0)
        """)

        bad_locations = cursor.fetchall()
        logger.info(f"Found {len(bad_locations)} locations with bad zip codes")

        if not bad_locations:
            logger.info("No bad zip codes found!")
            return

        # Update each location
        fixed_count = 0
        for loc in bad_locations:
            location_id = loc['location_id']
            address_id = loc['address_id']
            current_score = loc['confidence_score'] or 50

            # Lower confidence score if it's high
            new_score = min(current_score, 30)  # Cap at 30 for bad zip codes

            # Update location confidence and validation status
            cursor.execute("""
                UPDATE location
                SET
                    confidence_score = %s,
                    validation_status = 'needs_review',
                    validation_notes = jsonb_set(
                        COALESCE(validation_notes, '{}'::jsonb),
                        '{rejection_reason}',
                        '"Invalid postal code (00000 or similar)"'::jsonb
                    ),
                    updated_at = NOW()
                WHERE id = %s
            """, (new_score, location_id))

            # Set postal code to empty string instead of NULL (due to NOT NULL constraint)
            # Empty string is better than invalid data like 00000
            cursor.execute("""
                UPDATE address
                SET
                    postal_code = '',
                    updated_at = NOW()
                WHERE id = %s
            """, (address_id,))

            fixed_count += 1

            logger.info(
                f"Fixed location {loc['name'] or 'unnamed'} "
                f"in {loc['city']}, {loc['state_province']} "
                f"(confidence: {current_score} -> {new_score})"
            )

        # Commit all changes
        conn.commit()
        logger.info(f"Successfully fixed {fixed_count} locations with bad zip codes")

        # Show summary
        cursor.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN postal_code IS NULL THEN 1 END) as null_zips,
                COUNT(CASE WHEN postal_code = '00000' THEN 1 END) as zero_zips
            FROM address
        """)
        summary = cursor.fetchone()
        logger.info(
            f"Summary - Total addresses: {summary['total']}, "
            f"NULL zips: {summary['null_zips']}, "
            f"00000 zips: {summary['zero_zips']}"
        )

    except Exception as e:
        logger.error(f"Error fixing bad zip codes: {e}")
        conn.rollback()
        raise
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    fix_bad_zip_codes()