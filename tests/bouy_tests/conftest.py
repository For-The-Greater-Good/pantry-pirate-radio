"""
Isolated conftest for bouy tests.

This conftest ensures that no parent conftest files are loaded,
preventing any app dependencies from being imported.
"""

import sys
import os

# Override pytest_plugins to prevent loading parent fixtures
pytest_plugins = []

def pytest_configure(config):
    """Configure pytest to skip loading parent conftest files."""
    # Prevent pytest from searching parent directories
    config.option.confcutdir = os.path.dirname(__file__)
    
    # Ensure we don't accidentally import app modules
    # by removing the project root from sys.path if it's there
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    if project_root in sys.path:
        sys.path.remove(project_root)