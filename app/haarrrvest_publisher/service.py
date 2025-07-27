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
        data_repo_url: str = None,
        check_interval: int = 300,  # 5 minutes
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

    def _setup_git_repo(self):
        """Clone or update the HAARRRvest repository."""
        # Check if path exists AND is a git repository
        is_git_repo = (self.data_repo_path / ".git").exists()

        if not self.data_repo_path.exists() or not is_git_repo:
            if self.data_repo_path.exists() and not is_git_repo:
                # Directory exists but is not a git repo - clean contents instead of removing
                logger.warning(
                    f"Directory {self.data_repo_path} exists but is not a git repository, cleaning contents"
                )
                # Clean directory contents but not the directory itself (it's a volume mount)
                for item in self.data_repo_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()

            logger.info(f"Cloning HAARRRvest repository to {self.data_repo_path}")
            self.data_repo_path.parent.mkdir(parents=True, exist_ok=True)

            # Use authenticated URL for cloning
            clone_url = self._get_authenticated_url()
            code, out, err = self._run_command(
                ["git", "clone", clone_url, str(self.data_repo_path)]
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

            # First, check if we have uncommitted changes
            code, out, err = self._run_command(
                ["git", "status", "--porcelain"], cwd=self.data_repo_path
            )
            if out.strip():
                logger.warning("Repository has uncommitted changes, stashing them")
                self._run_command(
                    ["git", "stash", "push", "-m", "Publisher auto-stash"],
                    cwd=self.data_repo_path,
                )

            # Ensure we're on main branch
            code, out, err = self._run_command(
                ["git", "checkout", "main"], cwd=self.data_repo_path
            )
            if code != 0:
                logger.error(f"Failed to checkout main: {err}")
                raise Exception(f"Cannot switch to main branch: {err}")

            # Fetch latest changes
            code, out, err = self._run_command(
                ["git", "fetch", "origin"], cwd=self.data_repo_path
            )
            if code != 0:
                logger.error(f"Failed to fetch: {err}")
                raise Exception(f"Cannot fetch from origin: {err}")

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
                code, out, err = self._run_command(
                    ["git", "pull", "origin", "main"], cwd=self.data_repo_path
                )
                if code != 0:
                    logger.error(f"Failed to pull: {err}")
                    raise Exception(f"Cannot pull from origin: {err}")
            else:
                logger.info("Repository is up to date with origin/main")

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

            # Get content store path
            content_store_path = content_store.store_path / "content-store"
            if not content_store_path.exists():
                logger.warning("Content store path does not exist, skipping sync")
                return

            # Target path in HAARRRvest
            target_path = self.data_repo_path / "content_store" / "content-store"

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

        # Harvester-generated section content
        harvester_section = f"""<!-- HARVESTER AUTO-GENERATED SECTION START -->
## Last Update

- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S UTC')}
- **Total Records**: {stats['total_records']}
- **Data Sources**: {stats['sources']}
- **Date Range**: {stats['date_range']}

## Data Structure

- `daily/` - Historical data organized by date
- `latest/` - Most recent data for each scraper
- `sqlite/` - SQLite database exports for Datasette
- `content_store/` - Content deduplication store (if configured)

## Usage

This data follows the OpenReferral Human Services Data Specification (HSDS).

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

    def _sync_database_from_haarrrvest(self):
        """Sync database with recent HAARRRvest data using replay tool."""
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
        """Run HAARRRvest's location export script to generate map data."""
        export_script = self.data_repo_path / "scripts" / "export-locations.py"

        if not export_script.exists():
            logger.error(f"Location export script not found: {export_script}")
            return

        logger.info("Running location export for map data")

        # Run the export script
        code, out, err = self._run_command(
            ["python3", str(export_script)], cwd=self.data_repo_path
        )

        if code == 0:
            logger.info("Location export completed successfully")
            if out:
                logger.info(f"Export output:\n{out}")
        else:
            logger.error(f"Location export failed: {err}")

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

        # SQLite export - use our own method
        self._export_to_sqlite()

        # Run HAARRRvest's location export script for map data
        self._run_location_export()

    def process_once(self):
        """Run the publishing pipeline once."""
        logger.info("Starting HAARRRvest publishing pipeline")

        try:
            # Setup repository
            self._setup_git_repo()

            # Find new files
            new_files = self._find_new_files()
            if not new_files:
                logger.info("No new files to process")
                return

            logger.info(f"Found {len(new_files)} new files to process")

            # Sync database with existing HAARRRvest data first
            logger.info("Syncing database with HAARRRvest data")
            self._sync_database_from_haarrrvest()

            # Create branch
            branch_name = self._create_branch_name()

            # Sync files
            self._sync_files_to_repo(new_files)

            # Sync content store if configured
            self._sync_content_store()

            # Update metadata
            self._update_repository_metadata()

            # Run database operations
            self._run_database_operations()

            # Commit and merge
            self._create_and_merge_branch(branch_name)

            # Save state
            self._save_processed_files()

            logger.info("Publishing pipeline completed successfully")

        except Exception as e:
            logger.error(f"Publishing pipeline failed: {e}", exc_info=True)
            raise

    def run(self):
        """Run the service continuously."""
        logger.info(
            f"Starting HAARRRvest publisher service (check interval: {self.check_interval}s)"
        )

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
        check_interval=int(os.getenv("PUBLISHER_CHECK_INTERVAL", "300")),
        days_to_sync=int(os.getenv("DAYS_TO_SYNC", "7")),
    )

    publisher.run()


if __name__ == "__main__":
    main()
