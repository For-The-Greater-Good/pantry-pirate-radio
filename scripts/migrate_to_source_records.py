#!/usr/bin/env python
"""
Migration script to populate source-specific tables from version history.

This script reads the version history for locations, organizations, and services,
and creates source-specific records for each unique scraper_id found in the version data.
It then updates the canonical records to be merged views of the source records.

Usage:
    python scripts/migrate_to_source_records.py
"""

import argparse
import json
import logging
import sys
from typing import Any, Dict, List, Optional, Set

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.reconciler.merge_strategy import MergeStrategy


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def migrate_locations(db: Session, dry_run: bool = False) -> None:
    """Migrate location records to the new source-specific model.

    Args:
        db: Database session
        dry_run: If True, don't commit changes
    """
    logger.info("Migrating location records...")

    # Get all canonical locations
    query = text(
        """
    SELECT id, name, description, latitude, longitude
    FROM location
    WHERE is_canonical = TRUE OR is_canonical IS NULL
    """
    )

    locations = db.execute(query).fetchall()
    logger.info(f"Found {len(locations)} canonical locations to migrate")

    # For each location, get its version history
    for location in locations:
        location_id = location[0]

        # Get version history for this location
        version_query = text(
            """
        SELECT version_num, data
        FROM record_version
        WHERE record_id = :record_id AND record_type = 'location'
        ORDER BY version_num
        """
        )

        versions = db.execute(version_query, {"record_id": location_id}).fetchall()

        if not versions:
            logger.warning(f"No version history found for location {location_id}")
            continue

        # Extract unique scraper_ids from version history
        scraper_ids: Set[str] = set()
        for version in versions:
            data = json.loads(version[1])
            scraper_id = data.get("scraper_id", "unknown")
            scraper_ids.add(scraper_id)

        logger.info(
            f"Location {location_id} has {len(scraper_ids)} unique scrapers: {scraper_ids}"
        )

        # Create source records for each scraper
        for scraper_id in scraper_ids:
            # Find the latest version for this scraper
            latest_data = None
            for version in reversed(versions):
                data = json.loads(version[1])
                if data.get("scraper_id") == scraper_id:
                    latest_data = data
                    break

            if not latest_data:
                continue

            # Create source record
            if not dry_run:
                source_query = text(
                    """
                INSERT INTO location_source (
                    id,
                    location_id,
                    scraper_id,
                    name,
                    description,
                    latitude,
                    longitude,
                    location_type
                ) VALUES (
                    :id,
                    :location_id,
                    :scraper_id,
                    :name,
                    :description,
                    :latitude,
                    :longitude,
                    'physical'
                )
                ON CONFLICT (location_id, scraper_id) DO UPDATE SET
                    name = :name,
                    description = :description,
                    latitude = :latitude,
                    longitude = :longitude,
                    updated_at = NOW()
                """
                )

                db.execute(
                    source_query,
                    {
                        "id": f"{location_id}_{scraper_id}",
                        "location_id": location_id,
                        "scraper_id": scraper_id,
                        "name": latest_data.get("name", ""),
                        "description": latest_data.get("description", ""),
                        "latitude": latest_data.get("latitude", 0),
                        "longitude": latest_data.get("longitude", 0),
                    },
                )

        # Update canonical record
        if not dry_run:
            # Ensure is_canonical is set
            update_query = text(
                """
            UPDATE location
            SET is_canonical = TRUE
            WHERE id = :id
            """
            )

            db.execute(update_query, {"id": location_id})

            # Merge source records
            merge_strategy = MergeStrategy(db)
            merge_strategy.merge_location(location_id)

    if not dry_run:
        db.commit()
        logger.info("Location migration completed and committed")
    else:
        logger.info("Dry run completed, no changes committed")


def migrate_organizations(db: Session, dry_run: bool = False) -> None:
    """Migrate organization records to the new source-specific model.

    Args:
        db: Database session
        dry_run: If True, don't commit changes
    """
    logger.info("Migrating organization records...")

    # Get all organizations
    query = text(
        """
    SELECT id, name, description, website, email, year_incorporated, legal_status, tax_status, tax_id, uri
    FROM organization
    """
    )

    organizations = db.execute(query).fetchall()
    logger.info(f"Found {len(organizations)} organizations to migrate")

    # For each organization, get its version history
    for organization in organizations:
        organization_id = organization[0]

        # Get version history for this organization
        version_query = text(
            """
        SELECT version_num, data
        FROM record_version
        WHERE record_id = :record_id AND record_type = 'organization'
        ORDER BY version_num
        """
        )

        versions = db.execute(version_query, {"record_id": organization_id}).fetchall()

        if not versions:
            logger.warning(
                f"No version history found for organization {organization_id}"
            )
            continue

        # Extract unique scraper_ids from version history
        scraper_ids: Set[str] = set()
        for version in versions:
            data = json.loads(version[1])
            scraper_id = data.get("scraper_id", "unknown")
            scraper_ids.add(scraper_id)

        logger.info(
            f"Organization {organization_id} has {len(scraper_ids)} unique scrapers: {scraper_ids}"
        )

        # Create source records for each scraper
        for scraper_id in scraper_ids:
            # Find the latest version for this scraper
            latest_data = None
            for version in reversed(versions):
                data = json.loads(version[1])
                if data.get("scraper_id") == scraper_id:
                    latest_data = data
                    break

            if not latest_data:
                continue

            # Create source record
            if not dry_run:
                source_query = text(
                    """
                INSERT INTO organization_source (
                    id,
                    organization_id,
                    scraper_id,
                    name,
                    description,
                    website,
                    email,
                    year_incorporated,
                    legal_status,
                    tax_status,
                    tax_id,
                    uri
                ) VALUES (
                    :id,
                    :organization_id,
                    :scraper_id,
                    :name,
                    :description,
                    :website,
                    :email,
                    :year_incorporated,
                    :legal_status,
                    :tax_status,
                    :tax_id,
                    :uri
                )
                ON CONFLICT (organization_id, scraper_id) DO UPDATE SET
                    name = :name,
                    description = :description,
                    website = :website,
                    email = :email,
                    year_incorporated = :year_incorporated,
                    legal_status = :legal_status,
                    tax_status = :tax_status,
                    tax_id = :tax_id,
                    uri = :uri,
                    updated_at = NOW()
                """
                )

                db.execute(
                    source_query,
                    {
                        "id": f"{organization_id}_{scraper_id}",
                        "organization_id": organization_id,
                        "scraper_id": scraper_id,
                        "name": latest_data.get("name", ""),
                        "description": latest_data.get("description", ""),
                        "website": latest_data.get("website"),
                        "email": latest_data.get("email"),
                        "year_incorporated": latest_data.get("year_incorporated"),
                        "legal_status": latest_data.get("legal_status"),
                        "tax_status": latest_data.get("tax_status"),
                        "tax_id": latest_data.get("tax_id"),
                        "uri": latest_data.get("uri"),
                    },
                )

        # Merge source records
        if not dry_run and len(scraper_ids) > 0:
            merge_strategy = MergeStrategy(db)
            merge_strategy.merge_organization(organization_id)

    if not dry_run:
        db.commit()
        logger.info("Organization migration completed and committed")
    else:
        logger.info("Dry run completed, no changes committed")


def migrate_services(db: Session, dry_run: bool = False) -> None:
    """Migrate service records to the new source-specific model.

    Args:
        db: Database session
        dry_run: If True, don't commit changes
    """
    logger.info("Migrating service records...")

    # Get all services
    query = text(
        """
    SELECT id, name, description, organization_id, status
    FROM service
    """
    )

    services = db.execute(query).fetchall()
    logger.info(f"Found {len(services)} services to migrate")

    # For each service, get its version history
    for service in services:
        service_id = service[0]

        # Get version history for this service
        version_query = text(
            """
        SELECT version_num, data
        FROM record_version
        WHERE record_id = :record_id AND record_type = 'service'
        ORDER BY version_num
        """
        )

        versions = db.execute(version_query, {"record_id": service_id}).fetchall()

        if not versions:
            logger.warning(f"No version history found for service {service_id}")
            continue

        # Extract unique scraper_ids from version history
        scraper_ids: Set[str] = set()
        for version in versions:
            data = json.loads(version[1])
            scraper_id = data.get("scraper_id", "unknown")
            scraper_ids.add(scraper_id)

        logger.info(
            f"Service {service_id} has {len(scraper_ids)} unique scrapers: {scraper_ids}"
        )

        # Create source records for each scraper
        for scraper_id in scraper_ids:
            # Find the latest version for this scraper
            latest_data = None
            for version in reversed(versions):
                data = json.loads(version[1])
                if data.get("scraper_id") == scraper_id:
                    latest_data = data
                    break

            if not latest_data:
                continue

            # Create source record
            if not dry_run:
                source_query = text(
                    """
                INSERT INTO service_source (
                    id,
                    service_id,
                    scraper_id,
                    name,
                    description,
                    organization_id,
                    status
                ) VALUES (
                    :id,
                    :service_id,
                    :scraper_id,
                    :name,
                    :description,
                    :organization_id,
                    :status
                )
                ON CONFLICT (service_id, scraper_id) DO UPDATE SET
                    name = :name,
                    description = :description,
                    organization_id = :organization_id,
                    status = :status,
                    updated_at = NOW()
                """
                )

                db.execute(
                    source_query,
                    {
                        "id": f"{service_id}_{scraper_id}",
                        "service_id": service_id,
                        "scraper_id": scraper_id,
                        "name": latest_data.get("name", ""),
                        "description": latest_data.get("description", ""),
                        "organization_id": latest_data.get("organization_id"),
                        "status": latest_data.get("status", "active"),
                    },
                )

        # Merge source records
        if not dry_run and len(scraper_ids) > 0:
            merge_strategy = MergeStrategy(db)
            merge_strategy.merge_service(service_id)

    if not dry_run:
        db.commit()
        logger.info("Service migration completed and committed")
    else:
        logger.info("Dry run completed, no changes committed")


def main() -> None:
    """Run the migration script."""
    parser = argparse.ArgumentParser(description="Migrate to source-specific records")
    parser.add_argument("--dry-run", action="store_true", help="Don't commit changes")
    parser.add_argument(
        "--entity",
        choices=["location", "organization", "service", "all"],
        default="all",
        help="Entity type to migrate",
    )
    args = parser.parse_args()

    # Connect to database
    engine = create_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)

    with Session() as db:
        if args.entity in ["location", "all"]:
            migrate_locations(db, args.dry_run)

        if args.entity in ["organization", "all"]:
            migrate_organizations(db, args.dry_run)

        if args.entity in ["service", "all"]:
            migrate_services(db, args.dry_run)


if __name__ == "__main__":
    main()
