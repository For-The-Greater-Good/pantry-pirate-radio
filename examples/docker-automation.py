#!/usr/bin/env python3
"""
Example of using bouy programmatically from another application.
Demonstrates how to control the Docker fleet with structured output.
"""

import subprocess
import json
import sys
from typing import Dict, List, Optional


class DockerFleetController:
    """Controller for managing Pantry Pirate Radio Docker services."""

    def __init__(self, script_path: str = "./bouy"):
        self.script_path = script_path

    def _run_command(
        self, args: List[str], capture_output: bool = True
    ) -> subprocess.CompletedProcess:
        """Run bouy command with given arguments."""
        cmd = [self.script_path, *args]

        return subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            check=False,  # Don't raise on non-zero exit
        )

    def get_service_status(self) -> Optional[List[Dict]]:
        """Get status of all services as JSON."""
        result = self._run_command(["--json", "ps"])

        if result.returncode != 0:
            print(f"Error getting service status: {result.stderr}", file=sys.stderr)
            return None

        # Parse JSON output line by line (each service is a separate JSON object)
        services = []
        for line in result.stdout.strip().split("\n"):
            if line:
                try:
                    services.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Error parsing JSON: {e}", file=sys.stderr)

        return services

    def start_services(
        self, services: Optional[List[str]] = None, mode: str = "dev"
    ) -> bool:
        """Start services with specified mode."""
        args = ["--programmatic", "--quiet", "up", f"--{mode}"]
        if services:
            args.extend(services)

        result = self._run_command(args, capture_output=False)
        return result.returncode == 0

    def stop_services(self) -> bool:
        """Stop all services."""
        result = self._run_command(
            ["--programmatic", "--quiet", "down"], capture_output=False
        )
        return result.returncode == 0

    def run_tests(self, test_type: str = "all") -> bool:
        """Run tests and return success status."""
        test_arg = f"--{test_type}" if test_type != "all" else ""
        args = ["--programmatic", "test"]
        if test_arg:
            args.append(test_arg)

        result = self._run_command(args, capture_output=False)
        return result.returncode == 0

    def run_scraper(self, scraper_name: str) -> Optional[str]:
        """Run a specific scraper and return its output."""
        result = self._run_command(
            ["--programmatic", "--quiet", "scraper", scraper_name]
        )

        if result.returncode != 0:
            print(f"Error running scraper: {result.stderr}", file=sys.stderr)
            return None

        return result.stdout

    def get_service_logs(self, service: str, tail: int = 100) -> Optional[str]:
        """Get logs for a specific service."""
        result = self._run_command(["--programmatic", "logs", service])

        if result.returncode != 0:
            print(f"Error getting logs: {result.stderr}", file=sys.stderr)
            return None

        return result.stdout


def main():
    """Example usage of the DockerFleetController."""
    controller = DockerFleetController()

    print("=== Docker Fleet Controller Example ===\n")

    # Check service status
    print("1. Checking service status...")
    services = controller.get_service_status()
    if services:
        running_services = [s for s in services if s.get("State") == "running"]
        print(f"   Found {len(running_services)} running services")
        for service in running_services[:3]:  # Show first 3
            print(f"   - {service.get('Service')}: {service.get('Status')}")

    # Start services if needed
    print("\n2. Ensuring services are running...")
    if controller.start_services(["app", "worker"], mode="dev"):
        print("   Services started successfully")
    else:
        print("   Failed to start services")

    # Run a quick test
    print("\n3. Running mypy type checks...")
    if controller.run_tests("mypy"):
        print("   Type checks passed!")
    else:
        print("   Type checks failed")

    # List scrapers
    print("\n4. Listing available scrapers...")
    scraper_list = controller.run_scraper("--list")
    if scraper_list:
        print("   Available scrapers:")
        for line in scraper_list.strip().split("\n")[:5]:  # Show first 5
            if line.strip() and not line.startswith("Available"):
                print(f"   - {line.strip()}")

    # Get logs sample
    print("\n5. Getting recent logs from app service...")
    logs = controller.get_service_logs("app", tail=5)
    if logs:
        log_lines = logs.strip().split("\n")[:3]  # Show first 3 lines
        print("   Recent logs:")
        for line in log_lines:
            print(f"   {line[:80]}...")  # Truncate long lines


if __name__ == "__main__":
    main()
