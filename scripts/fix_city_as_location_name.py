#!/usr/bin/env python3
"""
Fix locations where the name is incorrectly set to the city name.

This script identifies locations where location.name equals address.city
and corrects them using the proper name from location_source records.
"""

import asyncio
import logging
import re
from collections import Counter
from typing import Optional

import asyncpg
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def extract_name_from_description(description: str) -> Optional[str]:
    """Extract the real name from a generated description."""
    if not description:
        return None
    
    # Look for "Food service location: [Real Name]" pattern
    match = re.search(r"Food service location:\s*(.+)", description)
    if match:
        return match.group(1).strip()
    
    # Look for other patterns like "Food service at X: Y"
    match = re.search(r"Food service at .+:\s*(.+)", description)
    if match:
        return match.group(1).strip()
    
    return None


def fix_location_names(db: Session, dry_run: bool = True) -> dict:
    """Fix locations where name equals city name.
    
    Args:
        db: Database session
        dry_run: If True, only report what would be changed without making changes
        
    Returns:
        Statistics about the fixes
    """
    stats = {
        "total_checked": 0,
        "city_as_name": 0,
        "fixed": 0,
        "skipped": 0,
        "errors": 0
    }
    
    # Find all locations where name equals city
    query = text("""
        SELECT DISTINCT l.id, l.name as location_name, l.description, 
               a.city, a.state_province
        FROM location l
        JOIN address a ON l.id = a.location_id
        WHERE l.name = a.city
        AND a.city IS NOT NULL
        ORDER BY a.state_province, a.city, l.id
    """)
    
    result = db.execute(query)
    locations_to_fix = result.fetchall()
    
    stats["total_checked"] = len(locations_to_fix)
    stats["city_as_name"] = len(locations_to_fix)
    
    logger.info(f"Found {stats['city_as_name']} locations with city as name")
    
    for row in locations_to_fix:
        location_id = row[0]
        current_name = row[1]
        description = row[2]
        city = row[3]
        state = row[4]
        
        # Get all location_source names for this location
        source_query = text("""
            SELECT scraper_id, name, updated_at
            FROM location_source
            WHERE location_id = :location_id
            AND name IS NOT NULL
            AND name != :city
            ORDER BY updated_at DESC
        """)
        
        source_result = db.execute(source_query, {
            "location_id": location_id,
            "city": city
        })
        source_names = source_result.fetchall()
        
        # Determine the best name to use
        best_name = None
        
        if source_names:
            # Count frequency of each name across scrapers
            name_counts = Counter([row[1] for row in source_names])
            
            # Filter out generic names
            filtered_names = {
                name: count for name, count in name_counts.items()
                if not re.match(r"^Location\s+\d+$", name)  # Skip "Location 1", etc.
            }
            
            if filtered_names:
                # Use the most common non-generic name
                best_name = max(filtered_names, key=filtered_names.get)
            elif source_names:
                # If all names are generic, use the most recent one
                best_name = source_names[0][1]
        
        # If no good source name, try extracting from description
        if not best_name:
            best_name = extract_name_from_description(description)
        
        # Apply the fix if we found a better name
        if best_name and best_name != current_name:
            logger.info(
                f"Location {location_id}: '{current_name}' ({city}, {state}) -> '{best_name}'"
            )
            
            if not dry_run:
                try:
                    # Update the location name
                    update_query = text("""
                        UPDATE location
                        SET name = :new_name,
                            updated_at = NOW()
                        WHERE id = :location_id
                    """)
                    
                    db.execute(update_query, {
                        "new_name": best_name,
                        "location_id": location_id
                    })
                    
                    # Clean up redundant description if it was generated
                    if description == f"Food service location: {best_name}":
                        # Clear the redundant description
                        desc_update_query = text("""
                            UPDATE location
                            SET description = NULL
                            WHERE id = :location_id
                        """)
                        db.execute(desc_update_query, {"location_id": location_id})
                        logger.debug(f"Cleared redundant description for {location_id}")
                    
                    stats["fixed"] += 1
                    
                except Exception as e:
                    logger.error(f"Error fixing location {location_id}: {e}")
                    stats["errors"] += 1
                    db.rollback()
                    continue
            else:
                stats["fixed"] += 1  # Count what would be fixed in dry run
        else:
            if not best_name:
                logger.debug(f"No better name found for location {location_id}: '{current_name}'")
            stats["skipped"] += 1
    
    if not dry_run:
        db.commit()
        logger.info("Changes committed to database")
    
    return stats


def main():
    """Main entry point."""
    import argparse
    import os
    
    parser = argparse.ArgumentParser(
        description="Fix locations where name equals city name"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually perform the fixes (default is dry run)"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Skip confirmation prompt (use with --execute)"
    )
    parser.add_argument(
        "--database-url",
        default=os.getenv("DATABASE_URL"),
        help="Database connection URL"
    )
    args = parser.parse_args()
    
    if not args.database_url:
        logger.error("DATABASE_URL environment variable or --database-url argument required")
        return 1
    
    # Create database connection
    engine = create_engine(args.database_url)
    
    with Session(engine) as db:
        # Run the fix
        dry_run = not args.execute
        
        if dry_run:
            logger.info("Running in DRY RUN mode - no changes will be made")
            logger.info("Use --execute flag to apply changes")
        else:
            logger.warning("Running in EXECUTE mode - changes WILL be made to the database")
            if not args.force:
                response = input("Are you sure you want to proceed? (yes/no): ")
                if response.lower() != "yes":
                    logger.info("Aborted by user")
                    return 0
            else:
                logger.info("Proceeding with --force flag")
        
        stats = fix_location_names(db, dry_run=dry_run)
        
        # Print summary
        logger.info("\n" + "="*50)
        logger.info("SUMMARY")
        logger.info("="*50)
        logger.info(f"Total locations checked: {stats['total_checked']}")
        logger.info(f"Locations with city as name: {stats['city_as_name']}")
        if dry_run:
            logger.info(f"Would fix: {stats['fixed']}")
        else:
            logger.info(f"Fixed: {stats['fixed']}")
        logger.info(f"Skipped (no better name): {stats['skipped']}")
        if stats['errors'] > 0:
            logger.error(f"Errors: {stats['errors']}")
        
        return 0 if stats['errors'] == 0 else 1


if __name__ == "__main__":
    exit(main())