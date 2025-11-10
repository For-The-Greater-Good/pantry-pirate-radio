"""
HAARRRvest Publisher Service

This service monitors recorder outputs and publishes them to the HAARRRvest repository.
It creates date-based branches and handles the entire publishing pipeline.
"""

import os
import time
import logging
import subprocess  # nosec B404
import json
import uuid
import re
import signal
import atexit
import gzip
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
import shutil


logger = logging.getLogger(__name__)


class HAARRRvestPublisher:
    def __init__(
        self,
        output_dir: str = "/app/outputs",
        data_repo_path: str = "/data-repo",
        data_repo_url: Optional[str] = None,
        check_interval: int = 21600,  # 6 hours
        days_to_sync: int = 7,
        error_retry_delay: int = 60,  # 1 minute
    ):
        self.output_dir = Path(output_dir)
        self.data_repo_path = Path(data_repo_path)
        # Use HTTPS URL with token for better security
        default_url = "https://github.com/For-The-Greater-Good/HAARRRvest.git"
        self.data_repo_url = data_repo_url or os.getenv("DATA_REPO_URL", default_url)
        self.data_repo_token = os.getenv("DATA_REPO_TOKEN")
        self.check_interval = check_interval
        self.days_to_sync = days_to_sync
        self.error_retry_delay = error_retry_delay
        self.git_user_email = os.getenv(
            "GIT_USER_EMAIL", "pantry-pirate-radio@example.com"
        )
        self.git_user_name = os.getenv("GIT_USER_NAME", "Pantry Pirate Radio Publisher")
        self.processed_files: Set[str] = set()
        self._load_processed_files()

        # Track last cleanup times
        self.last_weekly_cleanup = datetime.now()
        self.last_monthly_cleanup = datetime.now()

        # Check if push is enabled via environment
        self.push_enabled = (
            os.getenv("PUBLISHER_PUSH_ENABLED", "false").lower() == "true"
        )

        # Log push permission status
        if self.push_enabled:
            logger.warning(
                "⚠️  PUBLISHER PUSH ENABLED - This instance WILL push to remote repository!"
            )
        else:
            logger.info(
                "✅ Publisher running in READ-ONLY mode - no remote pushes will occur"
            )

    def _safe_log(self, level, message):
        """Safely log a message, checking if logger handlers are still open."""
        # Check if logger handlers are still open before logging
        # This prevents "I/O operation on closed file" errors during test teardown
        if logger.handlers and all(
            not getattr(h.stream, "closed", False)
            for h in logger.handlers
            if hasattr(h, "stream")
        ):
            if level == "info":
                logger.info(message)
            elif level == "warning":
                logger.warning(message)
            elif level == "error":
                logger.error(message)
            elif level == "debug":
                logger.debug(message)

    def _load_processed_files(self):
        """Load list of already processed files."""
        state_file = self.output_dir / ".haarrrvest_publisher_state.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                    self.processed_files = set(data.get("processed_files", []))
            except Exception as e:
                logger.error(f"Failed to load state: {e}")

    def _save_processed_files(self):
        """Save list of processed files atomically."""
        state_file = self.output_dir / ".haarrrvest_publisher_state.json"
        temp_file = state_file.with_suffix(".tmp")

        try:
            # Write to temporary file first
            with open(temp_file, "w") as f:
                json.dump(
                    {
                        "processed_files": list(self.processed_files),
                        "last_updated": datetime.now().isoformat(),
                    },
                    f,
                    indent=2,
                )

            # Atomically move temp file to final location
            temp_file.replace(state_file)

        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            # Clean up temp file if it exists
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception as cleanup_error:
                    logger.debug(f"Failed to clean up temp file: {cleanup_error}")

    def _run_command(
        self, cmd: List[str], cwd: Optional[Path] = None
    ) -> Tuple[int, str, str]:
        """Run a command and return exit code, stdout, stderr."""
        logger.debug(f"Running command: {' '.join(cmd)}")
        result = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True
        )  # nosec B603
        return result.returncode, result.stdout, result.stderr

    def _get_authenticated_url(self):
        """Get repository URL with authentication if token is available."""
        if self.data_repo_token and self.data_repo_url.startswith("https://"):
            # Insert token into HTTPS URL
            parts = self.data_repo_url.replace("https://", "").split("/", 1)
            return f"https://{self.data_repo_token}@{parts[0]}/{parts[1]}"
        return self.data_repo_url

    def _get_content_store_stats(self):
        """Get current content store statistics for integrity checking."""
        try:
            from app.content_store.config import get_content_store

            content_store = get_content_store()
            if content_store:
                stats = content_store.get_statistics()
                # Handle Mock objects in tests by ensuring we have a proper dict
                if hasattr(stats, "get") and callable(stats.get):
                    return stats
                # If it's not a dict-like object, return None to avoid errors
                return None
        except Exception as e:
            logger.debug(f"Could not get content store statistics: {e}")
        return None

    def _verify_content_store_integrity(self, before_stats, after_stats):
        """Verify content store wasn't damaged by git operations."""
        if before_stats and after_stats:
            before_count = before_stats.get("total_content", 0)
            after_count = after_stats.get("total_content", 0)

            if after_count < before_count * 0.95:  # 5% tolerance for edge cases
                raise Exception(
                    f"CRITICAL: Content store data loss detected during git operations! "
                    f"Before: {before_count}, After: {after_count}"
                )
            elif before_count > 0:  # Only log if we had data to begin with
                logger.info(
                    f"Content store integrity verified: {after_count} items preserved"
                )

    def _safe_git_stash_with_content_store_protection(self):
        """Stash changes while protecting content store data."""

        # First, commit any content store changes immediately to protect them
        content_store_path = self.data_repo_path / "content_store"
        if content_store_path.exists():
            logger.info("Protecting content store: committing changes before stash")
            self._run_command(["git", "add", "content_store/"], cwd=self.data_repo_path)

            # Check if there are actually changes to commit
            code, out, err = self._run_command(
                ["git", "diff", "--cached", "--name-only"], cwd=self.data_repo_path
            )
            if out.strip():
                # Commit content store changes with a clear message
                commit_msg = f"Auto-commit content store updates - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                self._run_command(
                    ["git", "commit", "-m", commit_msg], cwd=self.data_repo_path
                )
                logger.info("Content store changes committed successfully")

        # Now check for any remaining non-content-store changes to stash
        code, out, err = self._run_command(
            ["git", "status", "--porcelain"], cwd=self.data_repo_path
        )
        if out.strip():
            # Only stash non-content-store files using pathspec exclusion
            logger.info("Stashing non-content-store changes")
            self._run_command(
                [
                    "git",
                    "stash",
                    "push",
                    "-m",
                    "Publisher auto-stash (excluding content_store)",
                    "--",
                    ".",
                    ":(exclude)content_store",
                ],
                cwd=self.data_repo_path,
            )
        else:
            logger.info("No additional changes to stash after content store commit")

    def _get_repository_size(self) -> Dict[str, float]:
        """Get repository size information in MB."""
        sizes = {}

        # Get .git folder size
        git_path = self.data_repo_path / ".git"
        if git_path.exists():
            git_size = sum(f.stat().st_size for f in git_path.rglob("*") if f.is_file())
            sizes["git_mb"] = git_size / (1024 * 1024)

        # Get total repository size
        total_size = sum(
            f.stat().st_size for f in self.data_repo_path.rglob("*") if f.is_file()
        )
        sizes["total_mb"] = total_size / (1024 * 1024)

        # Get data folder size (excluding .git)
        data_size = total_size - (sizes.get("git_mb", 0) * 1024 * 1024)
        sizes["data_mb"] = data_size / (1024 * 1024)

        return sizes

    def _check_and_cleanup_repository(self) -> None:
        """Check repository size and cleanup if needed."""
        sizes = self._get_repository_size()

        logger.info(
            f"Repository sizes - Total: {sizes['total_mb']:.1f}MB, "
            f".git: {sizes.get('git_mb', 0):.1f}MB, "
            f"Data: {sizes['data_mb']:.1f}MB"
        )

        # Alert if .git is too large
        git_size_mb = sizes.get("git_mb", 0)
        if git_size_mb > 7500000:  # 75GB threshold
            logger.warning(
                f"⚠️ .git folder is {git_size_mb:.1f}MB - exceeds 30GB threshold!"
            )
            self._perform_deep_cleanup()
        elif git_size_mb > 20000:  # 20GB warning
            logger.warning(
                f"⚠️ .git folder is {git_size_mb:.1f}MB - approaching size limit"
            )

    def _perform_deep_cleanup(self) -> None:
        """Perform deep cleanup of git repository."""
        logger.info("Performing deep repository cleanup...")

        # Get initial size for comparison
        initial_sizes = self._get_repository_size()

        # First try aggressive gc
        logger.info("Running aggressive git gc...")
        code, out, err = self._run_command(
            ["git", "gc", "--aggressive", "--prune=all"], cwd=self.data_repo_path
        )

        # Repack with optimal settings
        logger.info("Repacking repository...")
        code, out, err = self._run_command(
            ["git", "repack", "-a", "-d", "-f", "--depth=250", "--window=250"],
            cwd=self.data_repo_path,
        )

        # Clean up reflog
        logger.info("Cleaning reflog...")
        self._run_command(
            ["git", "reflog", "expire", "--all", "--expire=now"],
            cwd=self.data_repo_path,
        )

        # Final gc
        self._run_command(["git", "gc", "--prune=now"], cwd=self.data_repo_path)

        # Check size after cleanup
        new_sizes = self._get_repository_size()
        logger.info(
            f"After cleanup - .git: {new_sizes.get('git_mb', 0):.1f}MB "
            f"(reduced by {initial_sizes.get('git_mb', 0) - new_sizes.get('git_mb', 0):.1f}MB)"
        )

    def _maintain_shallow_clone(self) -> None:
        """Maintain shallow clone to limit history."""
        logger.info("Maintaining shallow clone depth...")

        # Fetch with limited depth to prevent history growth
        code, out, err = self._run_command(
            ["git", "fetch", "--depth=1", "origin", "main"], cwd=self.data_repo_path
        )

        if code == 0:
            logger.info("Shallow fetch successful")
        else:
            logger.error(f"Shallow fetch failed: {err}")
            raise Exception(f"Cannot fetch from origin: {err}")

    def _setup_git_repo(self):
        """Clone or update the HAARRRvest repository with content store protection."""
        # Check if path exists AND is a git repository
        is_git_repo = (self.data_repo_path / ".git").exists()

        if not self.data_repo_path.exists() or not is_git_repo:
            if self.data_repo_path.exists() and not is_git_repo:
                # Directory exists but is not a git repo - clean contents instead of removing
                logger.warning(
                    f"Directory {self.data_repo_path} exists but is not a git repository, cleaning contents"
                )
                # Clean directory contents but not the directory itself (it's a volume mount)
                # IMPORTANT: Preserve content_store directory if it exists
                for item in self.data_repo_path.iterdir():
                    # Skip content_store directory to preserve deduplication data
                    if item.name == "content_store":
                        logger.info("Preserving content_store directory during cleanup")
                        continue

                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

            logger.info(f"Cloning HAARRRvest repository to {self.data_repo_path}")
            self.data_repo_path.parent.mkdir(parents=True, exist_ok=True)

            # Use authenticated URL for cloning
            clone_url = self._get_authenticated_url()
            # Shallow clone to save space and time
            code, out, err = self._run_command(
                ["git", "clone", "--depth", "1", clone_url, str(self.data_repo_path)]
            )
            if code != 0:
                raise Exception(f"Failed to clone repository: {err}")

            # Set remote URL without token for security
            if self.data_repo_token:
                self._run_command(
                    ["git", "remote", "set-url", "origin", self.data_repo_url],
                    cwd=self.data_repo_path,
                )
            # Configure git user
            self._run_command(
                ["git", "config", "user.email", self.git_user_email],
                cwd=self.data_repo_path,
            )
            self._run_command(
                ["git", "config", "user.name", self.git_user_name],
                cwd=self.data_repo_path,
            )
        else:
            logger.info("Updating HAARRRvest repository")

            # Configure git user
            self._run_command(
                ["git", "config", "user.email", self.git_user_email],
                cwd=self.data_repo_path,
            )
            self._run_command(
                ["git", "config", "user.name", self.git_user_name],
                cwd=self.data_repo_path,
            )

            # NEW: Get content store stats BEFORE any git operations
            initial_content_stats = self._get_content_store_stats()
            if initial_content_stats:
                logger.info(
                    f"Content store before git operations: {initial_content_stats['total_content']} items"
                )

            # Check if we have uncommitted changes and handle them safely
            code, out, err = self._run_command(
                ["git", "status", "--porcelain"], cwd=self.data_repo_path
            )
            if out.strip():
                logger.warning("Repository has uncommitted changes")
                # Use protected stash operation
                self._safe_git_stash_with_content_store_protection()

            # Ensure we're on main branch
            code, out, err = self._run_command(
                ["git", "checkout", "main"], cwd=self.data_repo_path
            )
            if code != 0:
                logger.error(f"Failed to checkout main: {err}")
                raise Exception(f"Cannot switch to main branch: {err}")

            # Maintain shallow clone
            self._maintain_shallow_clone()

            # Check repository size and cleanup if needed
            self._check_and_cleanup_repository()

            # Check if we're behind origin/main
            code, out, err = self._run_command(
                ["git", "rev-list", "--count", "HEAD..origin/main"],
                cwd=self.data_repo_path,
            )
            behind_count = int(out.strip()) if out.strip().isdigit() else 0

            if behind_count > 0:
                logger.info(
                    f"Local repository is {behind_count} commits behind origin/main, pulling updates"
                )
                # Pull with depth to maintain shallow clone
                code, out, err = self._run_command(
                    ["git", "pull", "--depth", "1", "origin", "main"],
                    cwd=self.data_repo_path,
                )
                if code != 0:
                    logger.error(f"Failed to pull: {err}")
                    raise Exception(f"Cannot pull from origin: {err}")
            else:
                logger.info("Repository is up to date with origin/main")

            # NEW: Verify content store integrity after git operations
            final_content_stats = self._get_content_store_stats()
            if final_content_stats:
                logger.info(
                    f"Content store after git operations: {final_content_stats['total_content']} items"
                )
            self._verify_content_store_integrity(
                initial_content_stats, final_content_stats
            )

    def _create_branch_name(self) -> str:
        """Create a validated branch name based on current date."""
        branch_name = f"data-update-{datetime.now().strftime('%Y-%m-%d')}"

        # Validate branch name - only allow alphanumeric, hyphens, underscores, and slashes
        if not re.match(r"^[a-zA-Z0-9_/\-]+$", branch_name):
            raise ValueError(f"Invalid branch name: {branch_name}")

        return branch_name

    def _find_new_files(self) -> List[Path]:
        """Find new files in the outputs directory."""
        new_files = []

        # Check daily directories
        daily_dir = self.output_dir / "daily"
        if daily_dir.exists():
            cutoff_date = datetime.now() - timedelta(days=self.days_to_sync)

            for date_dir in sorted(daily_dir.iterdir()):
                if not date_dir.is_dir():
                    continue

                try:
                    dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                    if dir_date < cutoff_date:
                        continue
                except ValueError:
                    continue

                # Check all JSON files in this date directory
                for json_file in date_dir.rglob("*.json"):
                    file_key = str(json_file.relative_to(self.output_dir))
                    if file_key not in self.processed_files:
                        new_files.append(json_file)

        # Check latest directory
        latest_dir = self.output_dir / "latest"
        if latest_dir.exists():
            for json_file in latest_dir.glob("*.json"):
                file_key = f"latest/{json_file.name}"
                if file_key not in self.processed_files:
                    new_files.append(json_file)

        return new_files

    def _sync_files_to_repo(self, files: List[Path]):
        """Sync files to the HAARRRvest repository structure with path validation."""
        logger.info(f"Syncing {len(files)} files to HAARRRvest")

        for file_path in files:
            # Validate file path is within output directory
            try:
                file_path = file_path.resolve()
                output_dir_resolved = self.output_dir.resolve()

                # Ensure file is within output directory
                if not str(file_path).startswith(str(output_dir_resolved)):
                    logger.error(f"File path {file_path} is outside output directory")
                    continue

            except Exception as e:
                logger.error(f"Invalid file path {file_path}: {e}")
                continue

            # Determine target path in HAARRRvest
            relative_path = file_path.relative_to(self.output_dir)
            target_path = self.data_repo_path / relative_path

            # Create target directory
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Copy file
            shutil.copy2(file_path, target_path)
            logger.debug(f"Copied {file_path} to {target_path}")

            # Mark as processed and save state immediately
            file_key = str(relative_path)
            self.processed_files.add(file_key)
            self._save_processed_files()  # Save after each file to handle partial failures

    def _sync_content_store(self):
        """Sync content store to HAARRRvest repository if configured."""
        try:
            from app.content_store.config import get_content_store

            content_store = get_content_store()

            if not content_store:
                logger.debug("Content store not configured, skipping sync")
                return

            logger.info("Syncing content store to HAARRRvest")

            # Get content store path - use the actual content_store_path from ContentStore
            content_store_path = content_store.content_store_path
            if not content_store_path.exists():
                logger.warning("Content store path does not exist, skipping sync")
                return

            # Target path in HAARRRvest - use underscore to match repository convention
            target_path = self.data_repo_path / "content_store"

            # Create target directory
            target_path.parent.mkdir(parents=True, exist_ok=True)

            # Sync content store directory
            # Use rsync-like behavior: copy new/updated files, preserve existing
            if target_path.exists():
                # Update existing content store
                logger.debug("Updating existing content store in repository")
                # Copy only new or updated files
                for item in content_store_path.rglob("*"):
                    if item.is_file():
                        relative = item.relative_to(content_store_path)
                        target_file = target_path / relative

                        # Only copy if file doesn't exist or is newer
                        if (
                            not target_file.exists()
                            or item.stat().st_mtime > target_file.stat().st_mtime
                        ):
                            target_file.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(item, target_file)
                            logger.debug(f"Updated {relative}")
            else:
                # Initial sync - copy entire directory
                logger.debug("Initial content store sync to repository")
                shutil.copytree(content_store_path, target_path)

            # Update content store statistics
            stats = content_store.get_statistics()
            logger.info(
                f"Content store synced: {stats['total_content']} items, "
                f"{stats['processed_content']} processed"
            )

        except Exception as e:
            logger.error(f"Failed to sync content store: {e}")
            # Don't fail the entire pipeline if content store sync fails

    def _update_repository_metadata(self):
        """Update README and statistics in the repository."""
        # Generate statistics
        stats = self._generate_statistics()

        # Update README - preserve existing content, only update harvester section
        readme_path = self.data_repo_path / "README.md"

        # Harvester-generated section content with confidence metrics
        confidence_section = ""
        if "confidence_metrics" in stats:
            cm = stats["confidence_metrics"]
            confidence_section = f"""
## Data Quality Metrics

- **Average Confidence Score**: {cm.get('average_confidence', 0)}/100
- **High Confidence Locations**: {cm.get('high_confidence_count', 0)} (80-100 score)
- **Medium Confidence Locations**: {cm.get('medium_confidence_count', 0)} (50-79 score)
- **Low Confidence Locations**: {cm.get('low_confidence_count', 0)} (<50 score)
- **Verification Status**:
  - Verified: {cm.get('verified_count', 0)}
  - Needs Review: {cm.get('needs_review_count', 0)}
  - Rejected: {cm.get('rejected_count', 0)} (excluded from exports)
"""

        harvester_section = f"""<!-- HARVESTER AUTO-GENERATED SECTION START -->
## Last Update

- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Total Records**: {stats['total_records']}
- **Data Sources**: {stats['sources']}
- **Date Range**: {stats['date_range']}
{confidence_section}
## Data Structure

- `daily/` - Historical data organized by date
- `latest/` - Most recent data for each scraper
- `sql_dumps/` - PostgreSQL dumps for fast initialization
- `sqlite/` - SQLite database exports for Datasette
- `content_store/` - Content deduplication store (if configured)
- `data/` - Location data with confidence scores for mapping

## Usage

This data follows the OpenReferral Human Services Data Specification (HSDS).
All location data includes confidence scores and validation status to help identify data quality.

For more information, visit the [Pantry Pirate Radio project](https://github.com/For-The-Greater-Good/pantry-pirate-radio).
<!-- HARVESTER AUTO-GENERATED SECTION END -->"""

        # Read existing README if it exists
        if readme_path.exists():
            with open(readme_path) as f:
                existing_content = f.read()

            # Look for harvester section markers
            start_marker = "<!-- HARVESTER AUTO-GENERATED SECTION START -->"
            end_marker = "<!-- HARVESTER AUTO-GENERATED SECTION END -->"

            start_idx = existing_content.find(start_marker)
            end_idx = existing_content.find(end_marker)

            if start_idx != -1 and end_idx != -1:
                # Replace existing harvester section
                end_idx += len(end_marker)
                new_content = (
                    existing_content[:start_idx]
                    + harvester_section
                    + existing_content[end_idx:]
                )
            else:
                # Add harvester section at the top (after title if present)
                lines = existing_content.split("\n")
                if lines and lines[0].startswith("# "):
                    # Insert after title
                    new_content = (
                        lines[0]
                        + "\n\n"
                        + harvester_section
                        + "\n\n"
                        + "\n".join(lines[1:])
                    )
                else:
                    # Insert at the beginning
                    new_content = harvester_section + "\n\n" + existing_content
        else:
            # Create new README with default title and harvester section
            new_content = f"""# HAARRRvest - Food Resource Data

This repository contains food resource data collected by Pantry Pirate Radio.

{harvester_section}
"""

        with open(readme_path, "w") as f:
            f.write(new_content)

        # Update STATS.md
        stats_path = self.data_repo_path / "STATS.md"
        with open(stats_path, "w") as f:
            f.write("# Data Statistics\n\n")
            f.write(
                f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            )
            f.write("## Summary\n\n")
            for key, value in stats.items():
                f.write(f"- **{key.replace('_', ' ').title()}**: {value}\n")

    def _generate_statistics(self) -> Dict[str, Any]:
        """Generate statistics about the data."""
        stats: Dict[str, Any] = {
            "total_records": 0,
            "sources": 0,
            "date_range": "N/A",
        }

        # Count files and sources
        daily_dir = self.data_repo_path / "daily"
        if daily_dir.exists():
            dates = []
            sources = set()

            for date_dir in daily_dir.iterdir():
                if date_dir.is_dir():
                    dates.append(date_dir.name)
                    scrapers_dir = date_dir / "scrapers"
                    if scrapers_dir.exists():
                        for scraper_dir in scrapers_dir.iterdir():
                            if scraper_dir.is_dir():
                                sources.add(scraper_dir.name)
                                json_files = list(scraper_dir.glob("*.json"))
                                stats["total_records"] = stats["total_records"] + len(
                                    json_files
                                )

            if dates:
                stats["date_range"] = f"{min(dates)} to {max(dates)}"
            stats["sources"] = len(sources)

        # Add content store statistics if available
        try:
            from app.content_store.config import get_content_store

            content_store = get_content_store()
            if content_store:
                cs_stats = content_store.get_statistics()
                stats["content_store_total"] = cs_stats["total_content"]
                stats["content_store_processed"] = cs_stats["processed_content"]
                stats["content_store_pending"] = cs_stats["pending_content"]
        except Exception as e:
            logger.debug(f"Could not get content store statistics: {e}")

        # Add confidence metrics from database
        try:
            import psycopg2

            # Get database connection info from environment
            db_host = os.getenv("POSTGRES_HOST", "db")
            db_port = os.getenv("POSTGRES_PORT", "5432")
            db_user = os.getenv("POSTGRES_USER", "pantry_pirate_radio")
            db_name = os.getenv("POSTGRES_DB", "pantry_pirate_radio")
            db_password = os.getenv("POSTGRES_PASSWORD")

            conn_string = (
                f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            )
            conn = psycopg2.connect(conn_string)

            with conn.cursor() as cursor:
                # Get confidence score statistics
                cursor.execute(
                    """
                    SELECT
                        AVG(confidence_score) as avg_confidence,
                        COUNT(*) FILTER (WHERE confidence_score >= 80) as high_confidence,
                        COUNT(*) FILTER (WHERE confidence_score >= 50 AND confidence_score < 80) as medium_confidence,
                        COUNT(*) FILTER (WHERE confidence_score < 50) as low_confidence,
                        COUNT(*) FILTER (WHERE validation_status = 'verified') as verified,
                        COUNT(*) FILTER (WHERE validation_status = 'needs_review') as needs_review,
                        COUNT(*) FILTER (WHERE validation_status = 'rejected') as rejected,
                        COUNT(*) as total_locations
                    FROM location
                    WHERE is_canonical = true
                """
                )

                result = cursor.fetchone()
                if result:
                    stats["confidence_metrics"] = {
                        "average_confidence": round(result[0], 1) if result[0] else 0,
                        "high_confidence_count": result[1] or 0,
                        "medium_confidence_count": result[2] or 0,
                        "low_confidence_count": result[3] or 0,
                        "verified_count": result[4] or 0,
                        "needs_review_count": result[5] or 0,
                        "rejected_count": result[6] or 0,
                        "total_validated_locations": result[7] or 0,
                    }

            conn.close()
        except Exception as e:
            logger.debug(f"Could not get confidence metrics from database: {e}")

        return stats

    def _create_and_merge_branch(self, branch_name: str):
        """Create a branch, commit changes, and merge to main."""
        logger.info(f"Creating branch: {branch_name}")

        # First ensure we're on main and up to date
        self._run_command(["git", "checkout", "main"], cwd=self.data_repo_path)

        # Check if branch already exists locally
        code, out, err = self._run_command(
            ["git", "rev-parse", "--verify", branch_name], cwd=self.data_repo_path
        )
        if code == 0:
            logger.warning(f"Branch {branch_name} already exists locally, deleting it")
            self._run_command(
                ["git", "branch", "-D", branch_name], cwd=self.data_repo_path
            )

        # Check if branch exists on remote
        code, out, err = self._run_command(
            ["git", "ls-remote", "--heads", "origin", branch_name],
            cwd=self.data_repo_path,
        )
        if out.strip():
            logger.warning(f"Branch {branch_name} exists on remote, using unique name")
            # Use UUID to ensure uniqueness and avoid race conditions
            unique_suffix = str(uuid.uuid4())[:8]
            branch_name = f"{branch_name}-{unique_suffix}"
            logger.info(f"New branch name: {branch_name}")

        # Create and checkout new branch from main
        code, out, err = self._run_command(
            ["git", "checkout", "-b", branch_name], cwd=self.data_repo_path
        )
        if code != 0:
            raise Exception(f"Failed to create branch {branch_name}: {err}")

        # Add all changes
        self._run_command(["git", "add", "-A"], cwd=self.data_repo_path)

        # Check if there are changes to commit
        code, out, err = self._run_command(
            ["git", "status", "--porcelain"], cwd=self.data_repo_path
        )
        if not out.strip():
            logger.info("No changes to commit")
            self._run_command(["git", "checkout", "main"], cwd=self.data_repo_path)
            self._run_command(
                ["git", "branch", "-d", branch_name], cwd=self.data_repo_path
            )
            return

        # Commit changes
        commit_message = (
            f"Data update for {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}"
        )
        self._run_command(
            ["git", "commit", "-m", commit_message], cwd=self.data_repo_path
        )

        # Switch back to main and merge
        self._run_command(["git", "checkout", "main"], cwd=self.data_repo_path)
        self._run_command(
            ["git", "merge", "--no-ff", branch_name, "-m", f"Merge {branch_name}"],
            cwd=self.data_repo_path,
        )

        # Delete the branch
        self._run_command(["git", "branch", "-d", branch_name], cwd=self.data_repo_path)

        # Push to remote
        if self.push_enabled:
            logger.info("Pushing to remote repository")

            # Use authenticated URL for push if token is available
            if self.data_repo_token:
                push_url = self._get_authenticated_url()
                code, out, err = self._run_command(
                    ["git", "push", push_url, "main"], cwd=self.data_repo_path
                )
            else:
                code, out, err = self._run_command(
                    ["git", "push", "origin", "main"], cwd=self.data_repo_path
                )

            if code != 0:
                logger.error(f"Failed to push: {err}")
                raise Exception(f"Git push failed: {err}")
            else:
                # Run git gc to clean up repository after push
                logger.info("Running git gc to optimize repository...")
                gc_code, gc_out, gc_err = self._run_command(
                    ["git", "gc", "--aggressive", "--prune=now"],
                    cwd=self.data_repo_path,
                )
                if gc_code == 0:
                    logger.info("Git gc completed successfully")
                else:
                    logger.warning(f"Git gc failed (non-critical): {gc_err}")
        else:
            logger.warning(
                "PUSH DISABLED - Changes committed locally but NOT pushed to remote"
            )
            logger.info(
                "To enable pushing, set PUBLISHER_PUSH_ENABLED=true in environment"
            )

    def _export_to_sqlite(self):
        """Export PostgreSQL data to SQLite for Datasette."""
        logger.info("Exporting database to SQLite")

        try:
            # Create sqlite directory in repo
            sqlite_dir = self.data_repo_path / "sqlite"
            sqlite_dir.mkdir(exist_ok=True)

            sqlite_path = sqlite_dir / "pantry_pirate_radio.sqlite"

            # Use the datasette exporter instead of db-to-sqlite
            code, out, err = self._run_command(
                ["python", "-m", "app.datasette.exporter", "--output", str(sqlite_path)]
            )

            if code == 0:
                logger.info(f"Successfully exported to {sqlite_path}")

                # Create metadata.json for Datasette
                metadata = {
                    "title": "Pantry Pirate Radio - Food Resource Data",
                    "description": "Food resource data following OpenReferral HSDS specification",
                    "databases": {
                        "pantry_pirate_radio": {
                            "tables": {
                                "organization": {
                                    "description": "Organizations providing food resources"
                                },
                                "location": {
                                    "description": "Physical locations of food resources"
                                },
                                "service": {
                                    "description": "Services offered by organizations"
                                },
                            }
                        }
                    },
                }

                metadata_path = sqlite_dir / "metadata.json"
                with open(metadata_path, "w") as f:
                    json.dump(metadata, f, indent=2)

            else:
                logger.error(f"SQLite export failed: {err}")
                raise Exception(f"Failed to export SQLite database: {err}")

        except Exception as e:
            logger.error(f"SQLite export error: {e}")
            raise Exception(f"Failed to export SQLite database: {e}")

    def _export_to_sql_dump(self):
        """Export PostgreSQL database to compressed SQL dump for fast initialization."""
        self._safe_log("info", "Creating compressed PostgreSQL SQL dump")

        try:
            # Create sql_dumps directory in repo
            sql_dumps_dir = self.data_repo_path / "sql_dumps"
            sql_dumps_dir.mkdir(parents=True, exist_ok=True)

            # Get database connection info from environment
            db_host = os.getenv("POSTGRES_HOST", "db")
            db_port = os.getenv("POSTGRES_PORT", "5432")
            db_user = os.getenv("POSTGRES_USER", "pantry_pirate_radio")
            db_name = os.getenv("POSTGRES_DB", "pantry_pirate_radio")
            db_password = os.getenv("POSTGRES_PASSWORD")

            # Safety check: Get current database record count
            env = os.environ.copy()
            env["PGPASSWORD"] = db_password
            check_cmd = [
                "psql",
                "-h",
                db_host,
                "-p",
                db_port,
                "-U",
                db_user,
                "-d",
                db_name,
                "-t",
                "-c",
                "SELECT COUNT(*) FROM organization;",
            ]
            result = subprocess.run(
                check_cmd, env=env, capture_output=True, text=True
            )  # nosec B603 - Safe hardcoded command

            if result.returncode != 0:
                self._safe_log(
                    "error", f"Failed to check database record count: {result.stderr}"
                )
                raise Exception("Cannot verify database state before dump")

            current_count = int(result.stdout.strip())
            self._safe_log(
                "info", f"Current database has {current_count} organizations"
            )

            # Load or initialize ratchet file
            ratchet_file = sql_dumps_dir / ".record_count_ratchet"
            max_known_count = 0

            if ratchet_file.exists():
                try:
                    ratchet_data = json.loads(ratchet_file.read_text())
                    max_known_count = ratchet_data.get("max_record_count", 0)
                    self._safe_log(
                        "info", f"Previous maximum record count: {max_known_count}"
                    )
                except Exception as e:
                    logger.warning(f"Could not read ratchet file: {e}")

            # Check against ratcheting threshold
            allow_empty_dump = (
                os.getenv("ALLOW_EMPTY_SQL_DUMP", "false").lower() == "true"
            )
            allow_percentage = float(
                os.getenv("SQL_DUMP_RATCHET_PERCENTAGE", "0.9")
            )  # Default 90%

            if max_known_count > 0:
                # We have a previous high water mark
                threshold = int(max_known_count * allow_percentage)
                if current_count < threshold and not allow_empty_dump:
                    self._safe_log(
                        "error", f"Database has only {current_count} records"
                    )
                    self._safe_log(
                        "error",
                        f"This is below {allow_percentage*100}% of maximum known count ({max_known_count})",
                    )
                    self._safe_log("error", f"Threshold: {threshold} records")
                    self._safe_log(
                        "error", "Refusing to create SQL dump to prevent data loss"
                    )
                    self._safe_log(
                        "error", "To override, set ALLOW_EMPTY_SQL_DUMP=true"
                    )
                    raise Exception(
                        f"Database record count {current_count} below ratchet threshold {threshold} (90% of {max_known_count})"
                    )
            else:
                # First dump or no ratchet file - use minimum threshold
                min_record_threshold = int(os.getenv("SQL_DUMP_MIN_RECORDS", "100"))
                if current_count < min_record_threshold and not allow_empty_dump:
                    # Check if we have existing dumps (legacy check)
                    existing_dumps = list(
                        sql_dumps_dir.glob("pantry_pirate_radio_*.sql")
                    )
                    if existing_dumps:
                        self._safe_log(
                            "error",
                            f"Database has only {current_count} records (minimum: {min_record_threshold})",
                        )
                        self._safe_log(
                            "error", "Refusing to create SQL dump to prevent data loss"
                        )
                        self._safe_log(
                            "error", "To override, set ALLOW_EMPTY_SQL_DUMP=true"
                        )
                        raise Exception(
                            f"Database record count {current_count} below minimum threshold {min_record_threshold}"
                        )
                    else:
                        # First dump ever, allow it
                        self._safe_log(
                            "warning",
                            f"Creating initial dump with {current_count} records",
                        )

            # Update ratchet if current count is higher
            if current_count > max_known_count:
                self._safe_log(
                    "info", f"New record count high water mark: {current_count}"
                )
                ratchet_data = {
                    "max_record_count": current_count,
                    "updated_at": datetime.now().isoformat(),
                    "updated_by": "haarrrvest_publisher",
                }
                ratchet_file.write_text(json.dumps(ratchet_data, indent=2))

            # Generate filename with timestamp for compressed dumps
            dump_filename = f"pantry_pirate_radio_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.sql.gz"
            dump_path = sql_dumps_dir / dump_filename

            # Create a compressed SQL dump using gzip for better storage efficiency
            # SQL dumps compress very well (typically 10-20% of original size)
            self._safe_log(
                "info",
                f"Running pg_dump with gzip compression to create {dump_filename}",
            )
            env = os.environ.copy()
            env["PGPASSWORD"] = db_password

            # Create temporary uncompressed dump first
            temp_dump_path = dump_path.with_suffix("")  # Remove .gz for temp file
            dump_cmd = [
                "pg_dump",
                "-h",
                db_host,
                "-p",
                db_port,
                "-U",
                db_user,
                "-d",
                db_name,
                "--no-owner",
                "--no-privileges",
                "--if-exists",
                "--clean",
            ]

            with open(temp_dump_path, "w") as dump_file:
                result = subprocess.run(  # nosec B603 - Safe hardcoded command
                    dump_cmd,
                    env=env,
                    stdout=dump_file,
                    stderr=subprocess.PIPE,
                    text=True,
                )

            if result.returncode == 0:
                # Compress the dump file
                self._safe_log("info", "Compressing SQL dump...")
                with open(temp_dump_path, "rb") as f_in:
                    with gzip.open(dump_path, "wb", compresslevel=9) as f_out:
                        shutil.copyfileobj(f_in, f_out)

                # Remove temporary uncompressed file
                temp_dump_path.unlink()

                # Get compressed file size
                compressed_size_mb = dump_path.stat().st_size / (1024 * 1024)
                # Estimate original size (gzip typically achieves 10-20% of original for SQL)
                estimated_original_mb = compressed_size_mb * 7  # Rough estimate
                compression_ratio = (
                    1 - compressed_size_mb / estimated_original_mb
                ) * 100

                self._safe_log(
                    "info",
                    f"Successfully created compressed SQL dump: {dump_filename} "
                    f"({compressed_size_mb:.1f} MB, ~{compression_ratio:.0f}% compression)",
                )

                # Create a latest symlink for easy access
                latest_link = sql_dumps_dir / "latest.sql.gz"
                # Remove old uncompressed symlink if it exists
                old_link = sql_dumps_dir / "latest.sql"
                if old_link.exists():
                    old_link.unlink()
                if latest_link.exists():
                    latest_link.unlink()
                latest_link.symlink_to(dump_filename)
                self._safe_log("info", "Updated latest.sql.gz symlink")

                # Keep only recent dumps (reduced from 24 to 3 hours to save storage)
                self._cleanup_old_dumps(sql_dumps_dir, keep_hours=3)

            else:
                self._safe_log("error", f"pg_dump failed: {result.stderr}")
                raise Exception(f"Failed to create SQL dump: {result.stderr}")

        except Exception as e:
            self._safe_log("error", f"SQL dump export error: {e}")
            # Don't fail the entire pipeline if SQL dump fails
            self._safe_log("warning", "Continuing without SQL dump")

    def _cleanup_old_dumps(self, sql_dumps_dir: Path, keep_hours: int = 3):
        """Remove SQL dumps older than keep_hours, but always keep the latest dump."""
        cutoff_time = datetime.now() - timedelta(hours=keep_hours)

        # Find all SQL dump files (both compressed and uncompressed)
        dump_files = list(sql_dumps_dir.glob("pantry_pirate_radio_*.sql")) + list(
            sql_dumps_dir.glob("pantry_pirate_radio_*.sql.gz")
        )

        # Skip symlinks
        dump_files = [f for f in dump_files if not f.is_symlink()]

        if not dump_files:
            return

        # Sort files by modification time to identify the latest
        dump_files_with_time = []
        for dump_file in dump_files:
            # Extract timestamp from filename
            match = re.match(
                r"pantry_pirate_radio_(\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})\.sql(?:\.gz)?",
                dump_file.name,
            )
            if match:
                try:
                    file_time = datetime.strptime(match.group(1), "%Y-%m-%d_%H-%M-%S")
                    dump_files_with_time.append((dump_file, file_time))
                except ValueError:
                    self._safe_log(
                        "warning",
                        f"Could not parse timestamp from filename: {dump_file.name}",
                    )

        if not dump_files_with_time:
            return

        # Sort by timestamp (newest first)
        dump_files_with_time.sort(key=lambda x: x[1], reverse=True)

        # Always keep the latest file
        latest_file = dump_files_with_time[0][0]
        self._safe_log("debug", f"Keeping latest dump: {latest_file.name}")

        # Remove old files (skip the first one which is the latest)
        for dump_file, file_time in dump_files_with_time[1:]:
            if file_time < cutoff_time:
                self._safe_log("info", f"Removing old SQL dump: {dump_file.name}")
                dump_file.unlink()
            else:
                self._safe_log("debug", f"Keeping recent dump: {dump_file.name}")

    def _sync_database_from_haarrrvest(self):
        """Sync database with recent HAARRRvest data using replay tool.

        NOTE: This method is no longer called during normal operation.
        Database synchronization is now handled by the db-init service
        during container startup. This method is kept for manual/testing purposes.
        """
        from app.replay.replay import replay_file
        from datetime import datetime, timedelta

        daily_dir = self.data_repo_path / "daily"
        if not daily_dir.exists():
            logger.info(
                "No daily directory found in HAARRRvest, skipping database sync"
            )
            return

        logger.info("Finding the 90 most recent days for each scraper")

        # Track all dates for each scraper
        scraper_dates = {}

        try:
            # First pass: collect all dates for each scraper
            for date_dir in daily_dir.iterdir():
                if not date_dir.is_dir():
                    continue

                try:
                    dir_date = datetime.strptime(date_dir.name, "%Y-%m-%d")
                except ValueError:
                    continue

                scrapers_dir = date_dir / "scrapers"
                if not scrapers_dir.exists():
                    continue

                # Check which scrapers have data on this date
                for scraper_dir in scrapers_dir.iterdir():
                    if not scraper_dir.is_dir():
                        continue

                    scraper_name = scraper_dir.name
                    json_files = list(scraper_dir.glob("*.json"))

                    if json_files:  # Only count dates with actual JSON files
                        if scraper_name not in scraper_dates:
                            scraper_dates[scraper_name] = []
                        scraper_dates[scraper_name].append(dir_date)

            # Second pass: process the 90 most recent days for each scraper
            success_count = 0
            error_count = 0
            files_processed = 0

            for scraper_name, dates in scraper_dates.items():
                # Sort dates descending and take the 90 most recent
                recent_dates = sorted(dates, reverse=True)[:90]

                if recent_dates:
                    oldest_date = min(recent_dates)
                    newest_date = max(recent_dates)
                    logger.info(
                        f"Processing {scraper_name}: {len(recent_dates)} days from {oldest_date.strftime('%Y-%m-%d')} to {newest_date.strftime('%Y-%m-%d')}"
                    )

                # Process files from these recent dates
                for date in recent_dates:
                    date_str = date.strftime("%Y-%m-%d")
                    scraper_dir = daily_dir / date_str / "scrapers" / scraper_name

                    if not scraper_dir.exists():
                        continue

                    # Process all JSON files for this scraper on this date
                    json_files = sorted(scraper_dir.glob("*.json"))
                    for json_file in json_files:
                        try:
                            result = replay_file(str(json_file))
                            if result:
                                success_count += 1
                            files_processed += 1
                        except Exception as e:
                            logger.error(f"Failed to process {json_file}: {e}")
                            error_count += 1
                            files_processed += 1

            logger.info(
                f"Database sync completed: processed {files_processed} files from {len(scraper_dates)} scrapers"
            )
            logger.info(
                f"Results: {success_count} successful jobs, {error_count} errors"
            )

        except Exception as e:
            logger.error(f"Database sync failed: {e}")
            # Don't raise the exception as this shouldn't block the publishing pipeline

    def _run_location_export(self):
        """Run aggregated location export for map data."""
        logger.info("Running aggregated location export for map data")

        try:
            # Use the new aggregated exporter that groups nearby locations
            from app.haarrrvest_publisher.export_map_data_aggregated import (
                AggregatedMapDataExporter,
            )

            start_time = time.time()
            exporter = AggregatedMapDataExporter(self.data_repo_path)
            success = exporter.export()
            elapsed = time.time() - start_time

            if success:
                logger.info(
                    f"Location export completed successfully in {elapsed:.2f} seconds"
                )
            else:
                # Fall back to the old method if available
                logger.warning("Optimized export failed, trying legacy export script")
                export_script = self.data_repo_path / "scripts" / "export-locations.py"

                if export_script.exists():
                    code, out, err = self._run_command(
                        ["python3", str(export_script)], cwd=self.data_repo_path
                    )
                    if code == 0:
                        logger.info("Legacy location export completed")
                    else:
                        logger.error(f"Legacy location export also failed: {err}")
                else:
                    logger.error("No fallback export script available")

        except ImportError as e:
            logger.error(f"Could not import AggregatedMapDataExporter: {e}")
            # Fall back to old method
            export_script = self.data_repo_path / "scripts" / "export-locations.py"
            if export_script.exists():
                logger.info("Using legacy export script")
                code, out, err = self._run_command(
                    ["python3", str(export_script)], cwd=self.data_repo_path
                )
                if code == 0:
                    logger.info("Legacy location export completed")
                else:
                    logger.error(f"Legacy location export failed: {err}")
        except Exception as e:
            logger.error(f"Location export error: {e}")

    def _run_database_operations(self):
        """Run database rebuild and SQLite export."""
        logger.info("Running database operations")

        # Run the existing scripts if they're available
        scripts_dir = Path("/app/scripts")

        # Database rebuild
        rebuild_script = scripts_dir / "rebuild-database.sh"
        if rebuild_script.exists():
            logger.info("Rebuilding database from JSON files")
            code, out, err = self._run_command(["bash", str(rebuild_script)])
            if code != 0:
                logger.error(f"Database rebuild failed: {err}")

        # SQL dump export for fast initialization
        self._export_to_sql_dump()

        # SQLite export - use our own method
        self._export_to_sqlite()

        # Run HAARRRvest's location export script for map data
        self._run_location_export()

    def _check_for_changes(self) -> bool:
        """Check if there are any changes that need publishing."""
        # Always run the pipeline to ensure SQL dumps are current
        # This ensures we capture database state on every run
        has_changes = False

        # Check for new JSON files
        new_files = self._find_new_files()
        if new_files:
            logger.info(f"Found {len(new_files)} new JSON files")
            has_changes = True

        # Always create SQL dumps to capture current database state
        logger.info("Will create SQL dump to capture current database state")
        has_changes = True

        # Check content store for changes
        try:
            from app.content_store.config import get_content_store

            content_store = get_content_store()
            if content_store:
                logger.info("Content store configured, will sync")
                has_changes = True
        except Exception as e:
            logger.debug(f"Content store check skipped: {e}")

        return has_changes

    def _perform_periodic_maintenance(self) -> None:
        """Perform weekly and monthly maintenance tasks."""
        now = datetime.now()

        # Weekly cleanup (every 7 days)
        if (now - self.last_weekly_cleanup).days >= 7:
            logger.info("Performing weekly maintenance...")
            try:
                # Remove old branches
                code, out, err = self._run_command(
                    ["git", "branch", "-v"], cwd=self.data_repo_path
                )
                if code == 0 and out:
                    for line in out.strip().split("\n"):
                        if "data-update-" in line and not line.startswith("*"):
                            branch = line.split()[0]
                            logger.info(f"Removing old branch: {branch}")
                            self._run_command(
                                ["git", "branch", "-D", branch], cwd=self.data_repo_path
                            )

                # Run deep cleanup
                self._perform_deep_cleanup()
                self.last_weekly_cleanup = now
                logger.info("Weekly maintenance completed")
            except Exception as e:
                logger.error(f"Weekly maintenance failed: {e}")

        # Monthly cleanup (every 30 days) - more aggressive
        if (now - self.last_monthly_cleanup).days >= 30:
            logger.info("Performing monthly deep maintenance...")
            try:
                # Consider re-cloning if repository is too large
                sizes = self._get_repository_size()
                if sizes.get("git_mb", 0) > 60000:  # 60GB threshold for re-clone
                    logger.warning(
                        "Repository exceeds 60GB, considering fresh clone..."
                    )
                    self._perform_fresh_clone()
                else:
                    # Just do extra aggressive cleanup
                    self._perform_deep_cleanup()

                self.last_monthly_cleanup = now
                logger.info("Monthly maintenance completed")
            except Exception as e:
                logger.error(f"Monthly maintenance failed: {e}")

    def _perform_fresh_clone(self) -> None:
        """Perform a fresh shallow clone to reset repository size."""
        logger.warning("Performing fresh clone to reset repository size...")

        # Backup content store if it exists
        content_store_backup = None
        content_store_path = self.data_repo_path / "content_store"
        if content_store_path.exists():
            logger.info("Backing up content store...")
            # Use a more secure temporary directory
            import tempfile

            temp_dir = tempfile.mkdtemp(prefix="content_store_backup_")
            content_store_backup = Path(temp_dir) / "content_store"
            if content_store_backup.exists():
                shutil.rmtree(content_store_backup)
            shutil.copytree(content_store_path, content_store_backup)

        # Remove old repository (except the directory itself - it's a volume mount)
        logger.info("Removing old repository files...")
        for item in self.data_repo_path.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Clone fresh with shallow depth
        logger.info("Cloning fresh repository with shallow depth...")
        clone_url = self._get_authenticated_url()
        code, out, err = self._run_command(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "--single-branch",
                "--branch",
                "main",
                clone_url,
                ".",
            ],
            cwd=self.data_repo_path,
        )

        if code != 0:
            raise Exception(f"Fresh clone failed: {err}")

        # Restore content store if we backed it up
        if content_store_backup and content_store_backup.exists():
            logger.info("Restoring content store...")
            shutil.copytree(content_store_backup, content_store_path)
            # Clean up the temporary directory (parent of content_store_backup)
            shutil.rmtree(content_store_backup.parent)

        # Configure git
        self._run_command(
            ["git", "config", "user.email", self.git_user_email],
            cwd=self.data_repo_path,
        )
        self._run_command(
            ["git", "config", "user.name", self.git_user_name], cwd=self.data_repo_path
        )

        logger.info("Fresh clone completed successfully")

    def process_once(self):
        """Run the publishing pipeline once."""
        logger.info("Starting HAARRRvest publishing pipeline")

        # Perform periodic maintenance first
        self._perform_periodic_maintenance()

        try:
            # Setup repository
            self._setup_git_repo()

            # Check if there are any changes to publish
            if not self._check_for_changes():
                logger.info("No changes to publish")
                return

            # Find new files
            new_files = self._find_new_files()

            # Create branch
            branch_name = self._create_branch_name()

            # Sync files if any
            if new_files:
                logger.info(f"Syncing {len(new_files)} new files")
                self._sync_files_to_repo(new_files)

            # Sync content store if configured
            self._sync_content_store()

            # Update metadata
            self._update_repository_metadata()

            # Run database operations (includes SQL dump)
            try:
                self._run_database_operations()
            except Exception as e:
                if "below safety threshold" in str(e):
                    logger.error("Skipping commit due to SQL dump safety check failure")
                    logger.error("Database appears to be empty or corrupted")
                    return
                raise

            # Commit and merge
            self._create_and_merge_branch(branch_name)

            # Save state
            self._save_processed_files()

            logger.info("Publishing pipeline completed successfully")

        except Exception as e:
            logger.error(f"Publishing pipeline failed: {e}", exc_info=True)
            raise

    def _shutdown_handler(self, signum=None, frame=None):
        """Handle shutdown by creating a final SQL dump."""
        _ = signum, frame  # Signal handler parameters, not used but required

        # Skip SQL dump only in integration tests to avoid logging errors
        # Allow it in unit tests that specifically test the shutdown handler
        if (
            os.getenv("TESTING") == "true"
            and os.getenv("SKIP_SHUTDOWN_SQL_DUMP") == "true"
        ):
            self._safe_log("debug", "Skipping SQL dump in integration test environment")
            return

        self._safe_log("info", "Received shutdown signal, creating final SQL dump...")
        try:
            # Create a final SQL dump before shutdown
            self._export_to_sql_dump()
            self._safe_log("info", "Final SQL dump created successfully")
        except Exception as e:
            self._safe_log("error", f"Failed to create final SQL dump: {e}")

    def run(self):
        """Run the service continuously."""
        logger.info(
            f"Starting HAARRRvest publisher service (check interval: {self.check_interval}s)"
        )

        # Register shutdown handlers
        signal.signal(signal.SIGTERM, self._shutdown_handler)
        signal.signal(signal.SIGINT, self._shutdown_handler)
        atexit.register(self._shutdown_handler)

        # Setup repository first (needed for db-init to work)
        try:
            logger.info("Setting up HAARRRvest repository...")
            self._setup_git_repo()
            logger.info("HAARRRvest repository ready")
        except Exception as e:
            logger.error(f"Failed to setup repository: {e}", exc_info=True)
            # Exit with error so container restarts
            raise

        # Run once on startup
        self.process_once()

        # Then run periodically
        while True:
            try:
                time.sleep(self.check_interval)
                self.process_once()
            except KeyboardInterrupt:
                logger.info("Shutting down HAARRRvest publisher service")
                break
            except Exception as e:
                logger.error(f"Error in publishing loop: {e}", exc_info=True)
                time.sleep(self.error_retry_delay)


def main():
    """Main entry point for the service."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

    publisher = HAARRRvestPublisher(
        output_dir=os.getenv("OUTPUT_DIR", "/app/outputs"),
        data_repo_path=os.getenv("DATA_REPO_PATH", "/data-repo"),
        data_repo_url=os.getenv("DATA_REPO_URL"),
        error_retry_delay=int(os.getenv("ERROR_RETRY_DELAY", "60")),
        check_interval=int(os.getenv("PUBLISHER_CHECK_INTERVAL", "43200")),
        days_to_sync=int(os.getenv("DAYS_TO_SYNC", "7")),
    )

    publisher.run()


if __name__ == "__main__":
    main()
