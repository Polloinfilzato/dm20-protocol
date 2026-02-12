"""
Bilingual terminology resolution system for D&D terms (IT ↔ EN).

Provides O(1) lookup for Italian/English D&D terms with accent normalization
and code-switching support.
"""

from .models import TermEntry
from .resolver import TermResolver
from .style import StyleTracker

__all__ = ["TermEntry", "TermResolver", "StyleTracker"]
