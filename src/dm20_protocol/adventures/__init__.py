"""
Adventure module integration for dm20-protocol.

Provides data models, index caching, and discovery tools for D&D 5e
adventures sourced from the 5etools GitHub mirror.
"""

from .models import AdventureIndexEntry, AdventureSearchResult, StorylineGroup

__all__ = [
    "AdventureIndexEntry",
    "AdventureSearchResult",
    "StorylineGroup",
]
