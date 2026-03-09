"""Pytest configuration for CDK tests."""

import sys
from pathlib import Path

# Add stacks directory to path for imports
infra_dir = Path(__file__).parent.parent
sys.path.insert(0, str(infra_dir))
