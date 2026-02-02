"""
Content extractors for the PDF Library System.

This package contains extractors for:
- TOC (Table of Contents) extraction from PDFs
- Content extraction for specific content types (future)
"""

from .toc import TOCExtractor

__all__ = ["TOCExtractor"]
