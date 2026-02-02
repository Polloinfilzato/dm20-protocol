"""
Rulebook data sources.

This subpackage provides implementations for different rulebook sources:
- Custom: Local JSON/YAML files for homebrew content
- SRD: Official D&D 5e System Reference Document via 5e-srd-api (Task 13)
- Open5e: Extended OGL content (future)
"""

from .base import RulebookSourceBase, SearchResult, ContentCounts
from .custom import CustomSource, CustomSourceError

__all__ = [
    # Base
    "RulebookSourceBase",
    "SearchResult",
    "ContentCounts",
    # Custom source
    "CustomSource",
    "CustomSourceError",
]
