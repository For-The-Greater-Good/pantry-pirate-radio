"""Type stubs package."""

import os
import sys

# Add types directory to Python path for stub resolution
types_dir = os.path.dirname(os.path.abspath(__file__))
if types_dir not in sys.path:
    sys.path.insert(0, types_dir)
