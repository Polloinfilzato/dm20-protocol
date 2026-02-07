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
- NPCKnowledgeTracker: Tracks what each NPC knows
- KnowledgeSource: How NPCs acquire knowledge
- KnowledgeEntry: Record of NPC knowledge of a fact
- PlayerInteraction: Record of player-NPC interactions
- ContradictionDetector: Detects contradictions between statements and facts
- Contradiction: Record of a detected contradiction
- ContradictionType: Type of contradiction (temporal, spatial, etc.)
- ContradictionSeverity: Severity level (minor, moderate, major, critical)
- ResolutionStrategy: Strategy for resolving contradictions
- ResolutionSuggestion: Suggested resolution with confidence level
"""

from .contradiction import ContradictionDetector
from .fact_database import FactDatabase
from .models import (
    Contradiction,
    ContradictionSeverity,
    ContradictionType,
    Fact,
    FactCategory,
    KnowledgeEntry,
    KnowledgeSource,
    PlayerInteraction,
    ResolutionStrategy,
    ResolutionSuggestion,
)
from .npc_knowledge import NPCKnowledgeTracker

__all__ = [
    "Fact",
    "FactCategory",
    "FactDatabase",
    "KnowledgeEntry",
    "KnowledgeSource",
    "NPCKnowledgeTracker",
    "PlayerInteraction",
    "ContradictionDetector",
    "Contradiction",
    "ContradictionType",
    "ContradictionSeverity",
    "ResolutionStrategy",
    "ResolutionSuggestion",
]
