"""
PDF Library System for gamemaster-mcp.

This module provides functionality for managing a shared library of PDF and Markdown
rulebooks that can be used across all campaigns.

The library system:
- Indexes PDFs and extracts table of contents
- Extracts content on-demand to CustomSource JSON format
- Loads extracted content through existing CustomSource infrastructure
"""

from .manager import LibraryManager
from .models import LibrarySource, IndexEntry, TOCEntry, ContentSummary

__all__ = [
    "LibraryManager",
    "LibrarySource",
    "IndexEntry",
    "TOCEntry",
    "ContentSummary",
]
