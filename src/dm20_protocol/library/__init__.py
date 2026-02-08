"""
PDF Library System for gamemaster-mcp.

This module provides functionality for managing a shared library of PDF and Markdown
rulebooks that can be used across all campaigns.

The library system:
- Indexes PDFs and extracts table of contents
- Extracts content on-demand to CustomSource JSON format
- Loads extracted content through existing CustomSource infrastructure
- Manages per-campaign bindings to enable/disable library content
"""

from .manager import LibraryManager
from .models import LibrarySource, IndexEntry, TOCEntry, ContentSummary, ContentType
from .extractors import TOCExtractor, ContentExtractor, ExtractedContent
from .bindings import SourceBinding, LibraryBindings
from .search import LibrarySearch, SearchResult

__all__ = [
    "LibraryManager",
    "LibrarySource",
    "IndexEntry",
    "TOCEntry",
    "ContentSummary",
    "ContentType",
    "TOCExtractor",
    "ContentExtractor",
    "ExtractedContent",
    "SourceBinding",
    "LibraryBindings",
    "LibrarySearch",
    "SearchResult",
]
