#!/usr/bin/env python3
"""
Standalone test runner for bouy tests.

This script runs the bouy tests in complete isolation from the main test suite,
preventing any app dependencies from being loaded.
"""

import subprocess
import sys
import os
from pathlib import Path

def main():
    """Run bouy tests in isolation."""
    # Get the project root and test directory
    project_root = Path(__file__).parent
    test_dir = project_root / "tests" / "bouy_tests"
    
    # Set environment variables to prevent loading app code
    env = os.environ.copy()
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env["PYTEST_CURRENT_TEST_DIR"] = str(test_dir)
    
    # Build pytest command
    cmd = [
        sys.executable,
        "-m", "pytest",
        "-v",
        "--tb=short",
        "-p", "no:cacheprovider",
        "-p", "no:warnings",
        "-p", "no:cov",
        "--rootdir", str(test_dir),
        "--confcutdir", str(test_dir),
        "-c", str(test_dir / "pytest.ini"),  # Explicitly use bouy_tests pytest.ini
    ]
    
    # Add test files or additional arguments
    if len(sys.argv) > 1:
        # Convert relative test names to full paths
        for arg in sys.argv[1:]:
            if arg.startswith("test_bouy") and ".py" in arg:
                # Handle test_file.py or test_file.py::test_function format
                parts = arg.split("::", 1)
                test_file = test_dir / parts[0]
                if len(parts) > 1:
                    cmd.append(f"{test_file}::{parts[1]}")
                else:
                    cmd.append(str(test_file))
            else:
                cmd.append(arg)
    else:
        # Run all tests in the directory
        cmd.append(str(test_dir))
    
    # Run pytest from project root to avoid path issues
    result = subprocess.run(cmd, env=env, cwd=str(project_root))
    
    # Exit with the same code as pytest
    sys.exit(result.returncode)

if __name__ == "__main__":
    main()