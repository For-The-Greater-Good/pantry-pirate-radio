"""Main entry point for validator service."""

import argparse
import logging
import os
import signal
import sys
from typing import Dict, Any, NoReturn

from app.validator.worker import ValidatorWorker
from app.validator.config import get_validator_config, is_validator_enabled


def parse_args(args: list[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args: Optional list of arguments for testing

    Returns:
        Parsed arguments namespace
    """
    parser = argparse.ArgumentParser(
        description="Validator service for processing job validation",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )

    # Worker configuration
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="Number of workers to spawn",
    )
    parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Maximum number of jobs to process per worker",
    )

    # Execution modes
    parser.add_argument(
        "--burst",
        action="store_true",
        help="Run in burst mode (process all jobs then exit)",
    )
    parser.add_argument(
        "--with-scheduler",
        action="store_true",
        help="Enable job scheduling capabilities",
    )

    # Logging
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose/debug logging",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress non-error output",
    )

    # Service control
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="Check configuration and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Setup but don't start processing",
    )

    return parser.parse_args(args or [])


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """Set up logging configuration.

    Args:
        verbose: Enable debug logging
        quiet: Suppress non-error output
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Configure logging format
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logging.basicConfig(
        level=level,
        format=log_format,
        datefmt=date_format,
        handlers=[
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Adjust third-party loggers
    logging.getLogger("rq").setLevel(logging.WARNING if not verbose else logging.DEBUG)
    logging.getLogger("redis").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.debug(f"Logging configured: level={logging.getLevelName(level)}")


def check_configuration() -> bool:
    """Check and display configuration.

    Returns:
        True if configuration is valid
    """
    logger = logging.getLogger(__name__)

    try:
        config = get_validator_config()
        enabled = is_validator_enabled()

        logger.info("Validator Configuration:")
        logger.info(f"  Enabled: {enabled}")

        if enabled:
            logger.info(f"  Queue: {config.queue_name}")
            logger.info(f"  Redis TTL: {config.redis_ttl}s")
            logger.info(f"  Confidence Threshold: {config.confidence_threshold}")
            logger.info(f"  Max Retries: {config.max_retries}")
            logger.info(f"  Timeout: {config.timeout}s")
            logger.info(f"  Log Data Flow: {config.log_data_flow}")

            # Check Redis connectivity
            try:
                from app.validator.queues import get_redis_connection

                conn = get_redis_connection()
                conn.ping()
                logger.info("  Redis: Connected")
            except Exception as e:
                logger.error(f"  Redis: Failed - {e}")
                return False
        else:
            logger.info("  Validator is disabled in configuration")

        return True

    except Exception as e:
        logger.error(f"Configuration check failed: {e}")
        return False


def setup_signal_handlers() -> Dict[str, Any]:
    """Setup signal handlers for graceful shutdown.

    Returns:
        Dictionary containing handler references
    """
    handlers = {}

    def shutdown_handler(signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger = logging.getLogger(__name__)
        logger.info(f"Received signal {signum}, shutting down gracefully")
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    handlers["shutdown_handler"] = shutdown_handler

    return handlers


def run_workers(args: argparse.Namespace) -> None:
    """Run validator workers.

    Args:
        args: Parsed command line arguments
    """
    logger = logging.getLogger(__name__)

    # Check if validator is enabled
    if not is_validator_enabled():
        logger.error("Validator is disabled in configuration")
        sys.exit(1)

    # Get worker configuration
    from app.validator.config import get_worker_config

    worker_config = get_worker_config()

    # Override with command line arguments
    if args.max_jobs:
        worker_config["max_jobs_per_worker"] = args.max_jobs
    if args.burst:
        worker_config["burst_mode"] = True

    logger.info(f"Starting {args.workers} validator worker(s)")

    # For now, run a single worker (multi-worker support can be added later)
    if args.workers > 1:
        logger.warning(
            "Multi-worker support not yet implemented, starting single worker"
        )

    try:
        worker = ValidatorWorker(config=worker_config)

        if args.dry_run:
            logger.info("Dry run mode: setting up worker without processing")
            worker.setup()
            status = worker.get_status()
            logger.info(f"Worker status: {status}")
            worker.teardown()
        else:
            worker.setup()
            worker.work(
                burst=args.burst,
                with_scheduler=args.with_scheduler,
                max_jobs=args.max_jobs,
            )

    except KeyboardInterrupt:
        logger.info("Validator service interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Validator service failed: {e}", exc_info=True)
        sys.exit(1)


def main() -> NoReturn:
    """Main entry point for validator service.

    Parses arguments, configures logging, and starts workers.
    """
    # Parse arguments
    args = parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    # Setup signal handlers
    setup_signal_handlers()

    logger = logging.getLogger(__name__)
    logger.info("Validator service starting")

    # Check configuration if requested
    if args.check_config:
        if check_configuration():
            logger.info("Configuration check passed")
            sys.exit(0)
        else:
            logger.error("Configuration check failed")
            sys.exit(1)

    # Run workers
    run_workers(args)

    # Should not reach here
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        logging.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
