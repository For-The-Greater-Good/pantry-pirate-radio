#!/usr/bin/env python3
"""Backfill missing service_at_location linkages for orphaned schedules.

This script repairs schedules that have service_id set but service_at_location_id as NULL,
preventing them from being linked to physical locations. The issue affects 100% of schedules
(4,136 out of 4,137) due to a reconciler logic gap.

Root Cause:
    The reconciler's top-level schedule processing path (job_processor.py:1446-1544) creates
    schedules with service_id but doesn't auto-infer service_at_location_id when the LLM
    doesn't provide it explicitly. This results in all schedules being orphaned.

Repair Strategy:
    Phase 1: Link to Existing SAL (Easy Wins)
        - Find services with exactly 1 service_at_location record
        - Link all orphaned schedules for that service to the existing SAL
        - Expected: ~50% of schedules (~500-600)

    Phase 2: Create Missing SAL (Safe Auto-Fix)
        - Find services with 0 SAL records where organization has exactly 1 location
        - Create service_at_location record linking service to that location
        - Link all schedules for that service to the new SAL
        - Expected: ~25% of schedules (~250-300)

    Phase 3: Heuristic Matching (Requires Analysis)
        - Multi-location organizations requiring intelligent matching
        - Use service name, location name, and metadata for matching
        - Expected: ~15% of schedules (~150-200)

Usage:
    python3 scripts/backfill_service_at_location.py                  # Dry run (preview changes)
    python3 scripts/backfill_service_at_location.py --execute        # Actually update database
    python3 scripts/backfill_service_at_location.py --limit 50       # Process only 50 schedules
    python3 scripts/backfill_service_at_location.py --batch-size 10  # Process in batches of 10
    python3 scripts/backfill_service_at_location.py --phase 1        # Run only Phase 1 (easy wins)
    python3 scripts/backfill_service_at_location.py --phase 2        # Run Phase 1 and 2
    python3 scripts/backfill_service_at_location.py --phase 3        # Run all phases (default)

Examples:
    # Quick test: Preview first 10 schedules in Phase 1 only
    python3 scripts/backfill_service_at_location.py --phase 1 --limit 10

    # Safe production run: Execute Phase 1 and 2 only (no heuristics)
    python3 scripts/backfill_service_at_location.py --execute --phase 2

    # Full repair: Execute all phases with progress tracking
    python3 scripts/backfill_service_at_location.py --execute --phase 3 --batch-size 100
"""

import argparse
import asyncio
import logging
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, List, Tuple

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from sqlalchemy import select, and_, func, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.database.models import (
    ScheduleModel,
    ServiceModel,
    ServiceAtLocationModel,
    LocationModel,
    OrganizationModel,
)


class ServiceAtLocationBackfiller:
    """Backfills missing service_at_location linkages for orphaned schedules."""

    def __init__(
        self,
        session: AsyncSession,
        dry_run: bool = True,
        max_phase: int = 3,
    ):
        """Initialize the backfiller.

        Args:
            session: Database session
            dry_run: If True, don't actually update the database
            max_phase: Maximum phase to execute (1, 2, or 3)
        """
        self.session = session
        self.dry_run = dry_run
        self.max_phase = max_phase

        # Statistics tracking
        self.stats = {
            # Overall counts
            "total_schedules_processed": 0,
            "total_schedules_fixed": 0,
            "total_sal_created": 0,
            # Phase 1: Link to existing SAL
            "phase1_candidates": 0,
            "phase1_linked": 0,
            # Phase 2: Create SAL for single-location orgs
            "phase2_candidates": 0,
            "phase2_sal_created": 0,
            "phase2_linked": 0,
            # Phase 3: Heuristic matching
            "phase3_candidates": 0,
            "phase3_linked": 0,
            # Failures and skips
            "skipped_no_service": 0,
            "skipped_already_linked": 0,
            "skipped_no_strategy": 0,
            "manual_review_needed": 0,
            "errors": 0,
        }

        # Manual review cases
        self.manual_review_cases: List[Dict] = []

        # Setup logging
        self.logger = logging.getLogger(__name__)

    async def get_orphaned_schedules(
        self, limit: Optional[int] = None
    ) -> List[ScheduleModel]:
        """Query schedules with service_id but NULL service_at_location_id.

        Args:
            limit: Optional limit on number of records to fetch

        Returns:
            List of orphaned schedule records
        """
        self.logger.info("Querying orphaned schedules...")

        query = select(ScheduleModel).where(
            and_(
                ScheduleModel.service_id.isnot(None),
                ScheduleModel.service_at_location_id.is_(None),
                ScheduleModel.closes_at.isnot(None),  # Only schedules with actual times
            )
        )

        if limit:
            query = query.limit(limit)

        result = await self.session.execute(query)
        schedules = result.scalars().all()

        self.logger.info(f"Found {len(schedules)} orphaned schedules")
        return schedules

    async def get_service_details(
        self, service_id: str
    ) -> Tuple[ServiceModel, List[ServiceAtLocationModel], List[LocationModel], OrganizationModel]:
        """Get service details including SAL records, locations, and organization.

        Args:
            service_id: Service UUID

        Returns:
            Tuple of (service, sal_records, locations, organization)
        """
        # Get service
        service_result = await self.session.execute(
            select(ServiceModel).where(ServiceModel.id == service_id)
        )
        service = service_result.scalar_one_or_none()

        if not service:
            return None, [], [], None

        # Get organization
        org_result = await self.session.execute(
            select(OrganizationModel).where(
                OrganizationModel.id == service.organization_id
            )
        )
        organization = org_result.scalar_one_or_none()

        # Get service_at_location records for this service
        sal_result = await self.session.execute(
            select(ServiceAtLocationModel).where(
                ServiceAtLocationModel.service_id == service_id
            )
        )
        sal_records = sal_result.scalars().all()

        # Get all locations for this organization
        if organization:
            loc_result = await self.session.execute(
                select(LocationModel).where(
                    LocationModel.organization_id == organization.id
                )
            )
            locations = loc_result.scalars().all()
        else:
            locations = []

        return service, sal_records, locations, organization

    async def create_service_at_location(
        self,
        service_id: str,
        location_id: str,
        description: str = "Auto-generated by backfill script",
    ) -> Optional[str]:
        """Create a new service_at_location record.

        Args:
            service_id: Service UUID
            location_id: Location UUID
            description: Description for the SAL record

        Returns:
            New service_at_location ID if created, None on error
        """
        try:
            sal_id = str(uuid.uuid4())
            new_sal = ServiceAtLocationModel(
                id=sal_id,
                service_id=service_id,
                location_id=location_id,
                description=description,
            )

            if not self.dry_run:
                self.session.add(new_sal)
                await self.session.flush()
                self.logger.info(f"✅ Created service_at_location: {sal_id}")
            else:
                self.logger.info(
                    f"🔍 Would create service_at_location: {sal_id} "
                    f"(service={service_id[:8]}, location={location_id[:8]})"
                )

            self.stats["total_sal_created"] += 1
            return sal_id

        except Exception as e:
            self.logger.error(f"❌ Failed to create service_at_location: {e}")
            self.stats["errors"] += 1
            return None

    async def link_schedule_to_sal(
        self, schedule: ScheduleModel, sal_id: str, strategy: str
    ) -> bool:
        """Link a schedule to a service_at_location record.

        Args:
            schedule: Schedule model to update
            sal_id: service_at_location ID to link to
            strategy: Description of the linking strategy used

        Returns:
            True if linked successfully, False otherwise
        """
        try:
            if not self.dry_run:
                schedule.service_at_location_id = sal_id
                await self.session.flush()
                self.logger.info(
                    f"✅ Linked schedule {schedule.id[:8]} to SAL {sal_id[:8]} "
                    f"(strategy: {strategy})"
                )
            else:
                self.logger.info(
                    f"🔍 Would link schedule {schedule.id[:8]} to SAL {sal_id[:8]} "
                    f"(strategy: {strategy})"
                )

            self.stats["total_schedules_fixed"] += 1
            return True

        except Exception as e:
            self.logger.error(f"❌ Failed to link schedule: {e}")
            self.stats["errors"] += 1
            return False

    async def process_schedule_phase1(
        self, schedule: ScheduleModel, service: ServiceModel, sal_records: List
    ) -> bool:
        """Phase 1: Link to existing SAL if service has exactly 1 SAL record.

        Args:
            schedule: Schedule to process
            service: Service model
            sal_records: List of service_at_location records for this service

        Returns:
            True if schedule was linked, False otherwise
        """
        if len(sal_records) != 1:
            return False

        self.stats["phase1_candidates"] += 1
        sal_id = sal_records[0].id

        success = await self.link_schedule_to_sal(
            schedule, sal_id, "phase1_single_sal"
        )
        if success:
            self.stats["phase1_linked"] += 1
        return success

    async def process_schedule_phase2(
        self,
        schedule: ScheduleModel,
        service: ServiceModel,
        sal_records: List,
        locations: List,
        organization: OrganizationModel,
    ) -> bool:
        """Phase 2: Create SAL for single-location orgs with no SAL records.

        Args:
            schedule: Schedule to process
            service: Service model
            sal_records: List of service_at_location records (should be empty)
            locations: List of locations for this organization
            organization: Organization model

        Returns:
            True if schedule was linked, False otherwise
        """
        # Only applies if service has 0 SAL records and org has exactly 1 location
        if len(sal_records) != 0 or len(locations) != 1:
            return False

        self.stats["phase2_candidates"] += 1

        location = locations[0]
        org_name = organization.name if organization else "Unknown"
        location_name = location.name if location.name else f"Location {location.id[:8]}"

        self.logger.info(
            f"📍 Phase 2: Creating SAL for single-location org '{org_name}' → '{location_name}'"
        )

        # Create service_at_location record
        sal_id = await self.create_service_at_location(
            service_id=service.id,
            location_id=location.id,
            description=f"Auto-generated for single-location organization: {org_name}",
        )

        if not sal_id:
            return False

        self.stats["phase2_sal_created"] += 1

        # Link schedule to new SAL
        success = await self.link_schedule_to_sal(
            schedule, sal_id, "phase2_single_location_org"
        )
        if success:
            self.stats["phase2_linked"] += 1
        return success

    async def process_schedule_phase3(
        self,
        schedule: ScheduleModel,
        service: ServiceModel,
        sal_records: List,
        locations: List,
        organization: OrganizationModel,
    ) -> bool:
        """Phase 3: Heuristic matching for multi-location organizations.

        Args:
            schedule: Schedule to process
            service: Service model
            sal_records: List of service_at_location records
            locations: List of locations for this organization
            organization: Organization model

        Returns:
            True if schedule was linked, False otherwise
        """
        # Only for complex cases: no SAL records and multiple locations
        if len(sal_records) != 0 or len(locations) <= 1:
            return False

        self.stats["phase3_candidates"] += 1

        org_name = organization.name if organization else "Unknown"
        service_name = service.name if service.name else "Unknown Service"

        self.logger.info(
            f"🔍 Phase 3: Multi-location org '{org_name}' with {len(locations)} locations"
        )

        # Heuristic 1: Service name contains location name
        for location in locations:
            location_name = location.name or ""
            if location_name and location_name.lower() in service_name.lower():
                self.logger.info(
                    f"✨ Heuristic match: Service '{service_name}' contains location '{location_name}'"
                )

                # Create SAL and link
                sal_id = await self.create_service_at_location(
                    service_id=service.id,
                    location_id=location.id,
                    description=f"Auto-generated via name matching heuristic: '{service_name}' → '{location_name}'",
                )

                if sal_id:
                    success = await self.link_schedule_to_sal(
                        schedule, sal_id, "phase3_name_matching"
                    )
                    if success:
                        self.stats["phase3_linked"] += 1
                    return success

        # Heuristic 2: If all services use the same location, assume this one does too
        # (This would require analyzing other services in the org - not implemented)

        # No heuristic matched - flag for manual review
        self.logger.warning(
            f"⚠️  Manual review needed: Service '{service_name}' in org '{org_name}' "
            f"with {len(locations)} locations"
        )

        self.manual_review_cases.append(
            {
                "schedule_id": str(schedule.id),
                "service_id": str(service.id),
                "service_name": service_name,
                "organization_id": str(organization.id) if organization else None,
                "organization_name": org_name,
                "location_count": len(locations),
                "location_names": [
                    loc.name or f"Location {loc.id[:8]}" for loc in locations
                ],
            }
        )

        self.stats["manual_review_needed"] += 1
        return False

    async def process_schedule(self, schedule: ScheduleModel) -> bool:
        """Process a single orphaned schedule through all applicable phases.

        Args:
            schedule: Schedule model to process

        Returns:
            True if schedule was fixed, False otherwise
        """
        self.stats["total_schedules_processed"] += 1

        # Validate schedule
        if not schedule.service_id:
            self.logger.warning(
                f"⚠️  Schedule {schedule.id[:8]} has no service_id, skipping"
            )
            self.stats["skipped_no_service"] += 1
            return False

        if schedule.service_at_location_id:
            self.logger.debug(
                f"Schedule {schedule.id[:8]} already has service_at_location_id, skipping"
            )
            self.stats["skipped_already_linked"] += 1
            return False

        # Get service details
        service, sal_records, locations, organization = await self.get_service_details(
            schedule.service_id
        )

        if not service:
            self.logger.error(
                f"❌ Service {schedule.service_id[:8]} not found for schedule {schedule.id[:8]}"
            )
            self.stats["errors"] += 1
            return False

        service_name = service.name if service.name else f"Service {service.id[:8]}"
        org_name = organization.name if organization else "Unknown Org"

        self.logger.info(f"\n{'='*60}")
        self.logger.info(f"Processing Schedule: {schedule.id[:8]}")
        self.logger.info(f"Service: {service_name}")
        self.logger.info(f"Organization: {org_name}")
        self.logger.info(
            f"Hours: {schedule.opens_at} - {schedule.closes_at} ({schedule.byday or 'daily'})"
        )
        self.logger.info(
            f"Current state: {len(sal_records)} SAL records, {len(locations)} locations"
        )

        # Try Phase 1: Link to existing SAL
        if self.max_phase >= 1:
            if await self.process_schedule_phase1(schedule, service, sal_records):
                return True

        # Try Phase 2: Create SAL for single-location orgs
        if self.max_phase >= 2:
            if await self.process_schedule_phase2(
                schedule, service, sal_records, locations, organization
            ):
                return True

        # Try Phase 3: Heuristic matching
        if self.max_phase >= 3:
            if await self.process_schedule_phase3(
                schedule, service, sal_records, locations, organization
            ):
                return True

        # No strategy worked
        self.logger.warning(f"⚠️  No strategy available for schedule {schedule.id[:8]}")
        self.stats["skipped_no_strategy"] += 1
        return False

    async def backfill_batch(
        self, batch_size: int = 50, limit: Optional[int] = None
    ) -> Dict[str, int]:
        """Backfill service_at_location links in batches.

        Args:
            batch_size: Number of records to process in each batch
            limit: Optional total limit on records to process

        Returns:
            Statistics dictionary
        """
        # Get orphaned schedules
        schedules = await self.get_orphaned_schedules(limit)

        if not schedules:
            self.logger.info("No orphaned schedules found")
            return self.stats

        # Process in batches
        total_schedules = len(schedules)
        for i in range(0, total_schedules, batch_size):
            batch = schedules[i : i + batch_size]
            batch_num = (i // batch_size) + 1
            total_batches = (total_schedules + batch_size - 1) // batch_size

            self.logger.info(
                f"\n{'='*60}\n"
                f"Processing batch {batch_num}/{total_batches} "
                f"(schedules {i+1}-{min(i+batch_size, total_schedules)} of {total_schedules})\n"
                f"{'='*60}"
            )

            for schedule in batch:
                try:
                    await self.process_schedule(schedule)
                except Exception as e:
                    self.logger.error(
                        f"Error processing schedule {schedule.id}: {e}", exc_info=True
                    )
                    self.stats["errors"] += 1

            # Commit after each batch
            if not self.dry_run:
                try:
                    await self.session.commit()
                    self.logger.info(f"✅ Committed batch {batch_num}")
                except Exception as e:
                    self.logger.error(f"❌ Batch commit failed: {e}")
                    await self.session.rollback()
                    self.stats["errors"] += 1

        return self.stats

    def print_summary(self):
        """Print a summary of the backfill operation."""
        self.logger.info("\n" + "=" * 70)
        self.logger.info("BACKFILL SUMMARY")
        self.logger.info("=" * 70)
        self.logger.info(f"Mode: {'🔍 DRY RUN' if self.dry_run else '✅ LIVE UPDATE'}")
        self.logger.info(f"Max Phase: {self.max_phase}")
        self.logger.info("")
        self.logger.info("OVERALL RESULTS:")
        self.logger.info(f"  Total schedules processed: {self.stats['total_schedules_processed']}")
        self.logger.info(
            f"  Total schedules fixed: {self.stats['total_schedules_fixed']} "
            f"({100*self.stats['total_schedules_fixed']/max(self.stats['total_schedules_processed'],1):.1f}%)"
        )
        self.logger.info(f"  Total SAL records created: {self.stats['total_sal_created']}")
        self.logger.info("")
        self.logger.info("PHASE 1 (Link to Existing SAL):")
        self.logger.info(f"  Candidates: {self.stats['phase1_candidates']}")
        self.logger.info(f"  Linked: {self.stats['phase1_linked']}")
        self.logger.info("")
        self.logger.info("PHASE 2 (Create SAL for Single-Location Orgs):")
        self.logger.info(f"  Candidates: {self.stats['phase2_candidates']}")
        self.logger.info(f"  SAL records created: {self.stats['phase2_sal_created']}")
        self.logger.info(f"  Linked: {self.stats['phase2_linked']}")
        self.logger.info("")
        self.logger.info("PHASE 3 (Heuristic Matching):")
        self.logger.info(f"  Candidates: {self.stats['phase3_candidates']}")
        self.logger.info(f"  Linked: {self.stats['phase3_linked']}")
        self.logger.info("")
        self.logger.info("SKIPPED/FAILED:")
        self.logger.info(f"  Already linked: {self.stats['skipped_already_linked']}")
        self.logger.info(f"  No service found: {self.stats['skipped_no_service']}")
        self.logger.info(f"  No strategy available: {self.stats['skipped_no_strategy']}")
        self.logger.info(f"  Manual review needed: {self.stats['manual_review_needed']}")
        self.logger.info(f"  Errors: {self.stats['errors']}")
        self.logger.info("=" * 70)

        # Print manual review cases if any
        if self.manual_review_cases:
            self.logger.info("\n" + "=" * 70)
            self.logger.info(f"MANUAL REVIEW NEEDED ({len(self.manual_review_cases)} cases)")
            self.logger.info("=" * 70)
            for i, case in enumerate(self.manual_review_cases[:10], 1):
                self.logger.info(f"\n{i}. {case['organization_name']}")
                self.logger.info(f"   Service: {case['service_name']}")
                self.logger.info(f"   Locations ({case['location_count']}): {', '.join(case['location_names'])}")
                self.logger.info(f"   Schedule ID: {case['schedule_id']}")
            if len(self.manual_review_cases) > 10:
                self.logger.info(f"\n... and {len(self.manual_review_cases) - 10} more")
            self.logger.info("=" * 70)


async def main():
    """Main function to run the backfill process."""
    parser = argparse.ArgumentParser(
        description="Backfill missing service_at_location linkages for orphaned schedules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually update the database (default is dry-run)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="Limit number of schedules to process",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Number of schedules to process per batch (default: 50)",
    )
    parser.add_argument(
        "--phase",
        type=int,
        choices=[1, 2, 3],
        default=3,
        help="Maximum phase to execute (1=easy wins only, 2=include SAL creation, 3=all phases including heuristics)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )

    args = parser.parse_args()

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger = logging.getLogger(__name__)

    # Print configuration
    logger.info("=" * 70)
    logger.info("SERVICE_AT_LOCATION BACKFILL SCRIPT")
    logger.info("=" * 70)
    logger.info(f"Mode: {'LIVE UPDATE ✅' if args.execute else 'DRY RUN 🔍'}")
    logger.info(f"Max Phase: {args.phase}")
    logger.info(f"Batch Size: {args.batch_size}")
    if args.limit:
        logger.info(f"Limit: {args.limit} schedules")
    logger.info(f"Database: {settings.DATABASE_URL.split('@')[1] if '@' in settings.DATABASE_URL else 'unknown'}")
    logger.info("=" * 70)

    if args.execute:
        logger.warning("⚠️  LIVE UPDATE MODE - Database will be modified!")
        logger.warning("⚠️  Press Ctrl+C within 5 seconds to cancel...")
        await asyncio.sleep(5)

    # Create async engine and session
    # Convert psycopg2 URL to asyncpg for async support
    db_url = settings.DATABASE_URL
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://")
    elif db_url.startswith("postgresql+psycopg2://"):
        db_url = db_url.replace("postgresql+psycopg2://", "postgresql+asyncpg://")

    engine = create_async_engine(db_url, echo=False, pool_pre_ping=True)
    async_session_maker = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    async with async_session_maker() as session:
        # Create backfiller
        backfiller = ServiceAtLocationBackfiller(
            session=session,
            dry_run=not args.execute,
            max_phase=args.phase,
        )

        # Run backfill
        try:
            start_time = datetime.now()
            logger.info(f"\nStarting backfill at {start_time.strftime('%Y-%m-%d %H:%M:%S')}\n")

            stats = await backfiller.backfill_batch(
                batch_size=args.batch_size, limit=args.limit
            )

            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()

            logger.info(f"\nCompleted at {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"Duration: {duration:.1f} seconds")

            # Print summary
            backfiller.print_summary()

            # Suggest next steps
            if args.execute:
                logger.info("\n✅ Backfill complete! Check HAARRRvest export to verify schedule linkage.")
            else:
                logger.info("\n🔍 Dry run complete. Run with --execute to apply changes.")
                if stats['phase1_candidates'] > 0:
                    logger.info(f"   Recommended: Start with Phase 1 only (--phase 1 --execute)")
                    logger.info(f"   This will safely link {stats['phase1_candidates']} schedules to existing SAL records.")

        except KeyboardInterrupt:
            logger.warning("\n⚠️  Interrupted by user")
            await session.rollback()
        except Exception as e:
            logger.error(f"\n❌ Backfill failed: {e}", exc_info=True)
            await session.rollback()
            sys.exit(1)
        finally:
            await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
