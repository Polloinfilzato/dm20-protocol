"""
Pytest configuration file for dm20-protocol tests.
"""

import sys
from pathlib import Path

# Add src directory to Python path for test imports
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))
