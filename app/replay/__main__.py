"""CLI interface for replay functionality."""

import argparse
import logging
import os
import sys
from pathlib import Path

from app.replay.replay import DEFAULT_OUTPUT_DIR, replay_directory, replay_file

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def main() -> int:
    """Main entry point for the replay CLI."""
    parser = argparse.ArgumentParser(
        description="Replay recorded JSON files to recreate database records"
    )

    # File/directory options (mutually exclusive)
    source_group = parser.add_mutually_exclusive_group(required=True)
    source_group.add_argument(
        "--file", "-f", help="Path to a single JSON file to replay"
    )
    source_group.add_argument(
        "--directory", "-d", help="Directory containing JSON files to replay"
    )
    source_group.add_argument(
        "--use-default-output-dir",
        action="store_true",
        help="Use the default output directory from OUTPUT_DIR environment variable",
    )

    # Processing options
    parser.add_argument(
        "--pattern",
        "-p",
        default="*.json",
        help="File pattern to match when processing a directory (default: *.json)",
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Perform a dry run without actually processing files",
    )
    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip validation service and route directly to reconciler (legacy behavior)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    try:
        if args.file:
            # Process single file
            file_path = Path(args.file)
            if not file_path.exists():
                logger.error(f"File not found: {args.file}")
                return 1

            logger.info(f"Replaying single file: {args.file}")
            if args.dry_run:
                logger.info("DRY RUN MODE - No actual processing will occur")
            if args.skip_validation:
                logger.info("SKIP VALIDATION - Routing directly to reconciler")

            success = replay_file(
                str(file_path),
                dry_run=args.dry_run,
                skip_validation=args.skip_validation,
            )
            if success:
                logger.info("File processed successfully")
                return 0
            else:
                logger.error("File processing failed")
                return 1

        elif args.directory:
            # Process directory
            dir_path = Path(args.directory)
            if not dir_path.exists():
                logger.error(f"Directory not found: {args.directory}")
                return 1

            logger.info(f"Replaying files from directory: {args.directory}")
            logger.info(f"Using pattern: {args.pattern}")
            if args.dry_run:
                logger.info("DRY RUN MODE - No actual processing will occur")
            if args.skip_validation:
                logger.info("SKIP VALIDATION - Routing directly to reconciler")

            stats = replay_directory(
                str(dir_path),
                pattern=args.pattern,
                dry_run=args.dry_run,
                skip_validation=args.skip_validation,
            )

            # Log summary
            logger.info("Replay complete:")
            logger.info(f"  Total files: {stats['total_files']}")
            logger.info(f"  Successful: {stats['successful']}")
            logger.info(f"  Failed: {stats['failed']}")

            # Return non-zero if any files failed
            return 0 if stats["failed"] == 0 else 1

        else:  # --use-default-output-dir
            # Use default output directory
            output_dir = os.environ.get("OUTPUT_DIR", DEFAULT_OUTPUT_DIR)
            dir_path = Path(output_dir)

            if not dir_path.exists():
                logger.error(f"Default output directory not found: {output_dir}")
                logger.info(
                    "Set OUTPUT_DIR environment variable or use --directory option"
                )
                return 1

            logger.info(f"Replaying files from default output directory: {output_dir}")
            logger.info(f"Using pattern: {args.pattern}")
            if args.dry_run:
                logger.info("DRY RUN MODE - No actual processing will occur")
            if args.skip_validation:
                logger.info("SKIP VALIDATION - Routing directly to reconciler")

            stats = replay_directory(
                str(dir_path),
                pattern=args.pattern,
                dry_run=args.dry_run,
                skip_validation=args.skip_validation,
            )

            # Log summary
            logger.info("Replay complete:")
            logger.info(f"  Total files: {stats['total_files']}")
            logger.info(f"  Successful: {stats['successful']}")
            logger.info(f"  Failed: {stats['failed']}")

            # Return non-zero if any files failed
            return 0 if stats["failed"] == 0 else 1

    except KeyboardInterrupt:
        logger.info("Replay interrupted by user")
        return 130
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
