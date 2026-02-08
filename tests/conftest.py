"""
Pytest configuration and fixtures for dm20-protocol tests.
"""

import sys
from pathlib import Path

# Add src directory to Python path to allow importing dm20_protocol
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))
