"""
Consistency tracking system for the Claudmaster AI DM.

This module provides tools for tracking and querying narrative facts
to maintain consistency throughout a campaign. The FactDatabase stores
established facts about events, NPCs, locations, items, and world lore,
enabling agents to reference past information and avoid contradictions.

Key components:
- Fact: Individual narrative fact with metadata
- FactCategory: Enumeration of fact types
- FactDatabase: Storage and querying interface
"""

from .fact_database import FactDatabase
from .models import Fact, FactCategory

__all__ = [
    "Fact",
    "FactCategory",
    "FactDatabase",
]
