#!/usr/bin/env python3
"""Claude authentication manager for container-based setup."""

import asyncio
import json
import os
import subprocess  # nosec B404
import sys
from pathlib import Path
from typing import Dict, Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.llm.providers.claude import ClaudeProvider, ClaudeConfig

# Add project root to Python path if running outside container
if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

try:
    from app.core.logging import get_logger
    from app.llm.providers.claude import ClaudeProvider, ClaudeConfig
except ImportError:
    # Fallback for minimal functionality outside container
    import logging

    logging.basicConfig(level=logging.INFO)

    class MockLogger:
        def bind(self, **kwargs):
            return logging.getLogger("claude_auth_manager")

    def get_logger():
        return MockLogger()

    # Import will fail - we'll handle this in the class
    ClaudeProvider = None  # type: ignore[assignment,misc]
    ClaudeConfig = None  # type: ignore[assignment,misc]

logger = get_logger().bind(module="claude_auth_manager")


class ClaudeAuthManager:
    """Manages Claude authentication within the container."""

    def __init__(self):
        self.config: Optional["ClaudeConfig"] = None
        self.provider: Optional["ClaudeProvider"] = None

        if ClaudeProvider is None or ClaudeConfig is None:
            # Running outside container without full dependencies
            self.config = None
            self.provider = None
        else:
            self.config = ClaudeConfig()
            self.provider = ClaudeProvider(self.config)

    async def check_status(self) -> Dict[str, Any]:
        """Check current authentication status."""
        if self.provider is None:
            return {
                "provider": "claude",
                "status": "unhealthy",
                "authenticated": False,
                "error": "Dependencies not available (running outside container)",
                "message": "Please run inside container",
            }
        return await self.provider.health_check()

    def setup_interactive(self) -> int:
        """Run interactive Claude setup."""
        print("🔧 Starting Claude authentication setup...")
        print("📋 This will guide you through authenticating with your Claude account.")
        print("")

        try:
            # Run claude setup interactively
            result = subprocess.run(  # nosec B603 B607  # noqa: S603 S607
                ["claude"],
                stdin=sys.stdin,
                stdout=sys.stdout,
                stderr=sys.stderr,
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": os.environ.get("HOME", "/root"),
                },
            )

            if result.returncode == 0:
                print("\n✅ Authentication setup completed!")
                return 0
            else:
                print(f"\n❌ Setup failed with code {result.returncode}")
                return result.returncode

        except KeyboardInterrupt:
            print("\n❌ Setup cancelled by user")
            return 1
        except Exception as e:
            print(f"\n❌ Setup failed: {e}")
            return 1

    def check_config_files(self) -> Dict[str, Any]:
        """Check Claude configuration files."""
        home = os.environ.get("HOME", "/root")
        claude_config_dir = os.path.join(home, ".config", "claude")

        config_info = {
            "home_directory": home,
            "config_directory": claude_config_dir,
            "config_exists": os.path.exists(claude_config_dir),
            "files": [],
        }

        if os.path.exists(claude_config_dir):
            try:
                files = os.listdir(claude_config_dir)
                config_info["files"] = files
            except Exception as e:
                config_info["error"] = str(e)

        return config_info

    async def test_simple_request(self) -> Dict[str, Any]:
        """Test a simple Claude request."""
        try:
            # Try a simple request
            process = await asyncio.create_subprocess_exec(  # noqa: S603 S607
                "claude",
                "-p",
                "--output-format",
                "json",
                "Say hello",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env={
                    "PATH": "/usr/local/bin:/usr/bin:/bin",
                    "HOME": os.environ.get("HOME", "/root"),
                },
            )

            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30)

            result = {
                "return_code": process.returncode,
                "stdout": stdout.decode("utf-8"),
                "stderr": stderr.decode("utf-8"),
            }

            if process.returncode == 0:
                try:
                    # Try to parse JSON response
                    stdout_str = result["stdout"]
                    if isinstance(stdout_str, str):
                        data = json.loads(stdout_str)
                        result["parsed_response"] = data
                        result["success"] = not data.get("is_error", False)
                    else:
                        result["success"] = True
                except json.JSONDecodeError:
                    result["success"] = True  # Non-JSON response but successful
            else:
                result["success"] = False

            return result

        except asyncio.TimeoutError:
            return {"success": False, "error": "Request timed out"}
        except Exception as e:
            return {"success": False, "error": str(e)}


async def main():
    """Main CLI interface for Claude authentication management."""
    import argparse

    parser = argparse.ArgumentParser(description="Claude Authentication Manager")
    parser.add_argument(
        "command", choices=["status", "setup", "test", "config"], help="Command to run"
    )
    parser.add_argument(
        "--json", action="store_true", help="Output results in JSON format"
    )

    args = parser.parse_args()

    manager = ClaudeAuthManager()

    if args.command == "status":
        status = await manager.check_status()
        if args.json:
            print(json.dumps(status, indent=2))
        else:
            print("🔍 Claude Authentication Status:")
            print(f"   Provider: {status['provider']}")
            print(f"   Status: {status['status']}")
            print(f"   Authenticated: {status['authenticated']}")
            print(f"   Model: {status['model']}")
            print(f"   Message: {status['message']}")

            if status["authenticated"]:
                print("\n✅ Claude is ready!")
            else:
                print("\n❌ Authentication required!")
                print("   Run: python -m app.claude_auth_manager setup")

        return 0 if status["authenticated"] else 1

    elif args.command == "setup":
        if args.json:
            print(
                '{"error": "Setup cannot be run in JSON mode (requires interactive input)"}'
            )
            return 1

        return manager.setup_interactive()

    elif args.command == "test":
        result = await manager.test_simple_request()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("🧪 Testing Claude Request:")
            print(f"   Success: {result['success']}")
            print(f"   Return Code: {result.get('return_code', 'N/A')}")
            if result.get("error"):
                print(f"   Error: {result['error']}")
            elif result.get("parsed_response"):
                response = result["parsed_response"]
                print(f"   Response: {response.get('result', 'No result')[:100]}...")

        return 0 if result["success"] else 1

    elif args.command == "config":
        config = manager.check_config_files()
        if args.json:
            print(json.dumps(config, indent=2))
        else:
            print("📁 Claude Configuration:")
            print(f"   Home: {config['home_directory']}")
            print(f"   Config Dir: {config['config_directory']}")
            print(f"   Config Exists: {config['config_exists']}")
            if config["files"]:
                print(f"   Files: {', '.join(config['files'])}")

        return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
