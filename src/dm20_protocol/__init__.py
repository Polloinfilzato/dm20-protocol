"""
D&D MCP Server - A comprehensive campaign management tool for D&D built with FastMCP 2.8.0+.
"""

from .main import mcp
from .models import *
from .storage import DnDStorage

try:
    from importlib.metadata import version as _get_version
    __version__ = _get_version("dm20-protocol")
except Exception:
    __version__ = "0.3.0"  # Fallback if metadata unavailable
__all__ = ["mcp", "DnDStorage"]
