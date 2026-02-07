"""
Data models for the consistency tracking system.

This module defines the Fact model and related enums for tracking narrative
facts throughout a campaign. Facts are categorized by type (event, location,
NPC, etc.) and can be linked together to represent relationships.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class FactCategory(str, Enum):
    """Categories for classifying narrative facts."""
    EVENT = "event"
    LOCATION = "location"
    NPC = "npc"
    ITEM = "item"
    QUEST = "quest"
    WORLD = "world"


class Fact(BaseModel):
    """
    A single narrative fact established during gameplay.

    Facts represent important information that should remain consistent
    throughout the campaign, such as events that occurred, NPC details,
    item descriptions, or world lore.

    Attributes:
        id: Unique identifier for the fact
        category: Type of fact (event, location, NPC, etc.)
        content: The actual fact description
        session_number: Session when this fact was established
        timestamp: When this fact was created
        relevance_score: How relevant/important this fact is (0.0-1.0+)
        related_facts: IDs of facts related to this one
        tags: Searchable tags for categorization
        source: Who or what established this fact (e.g., "Narrator", "Player action")
    """
    id: str = Field(default="", description="Unique identifier, auto-generated if empty")
    category: FactCategory = Field(description="Category of this fact")
    content: str = Field(description="The actual fact content")
    session_number: int = Field(ge=1, description="Session number when fact was established")
    timestamp: datetime = Field(default_factory=datetime.now, description="When fact was created")
    relevance_score: float = Field(default=1.0, ge=0.0, description="Relevance/importance score")
    related_facts: list[str] = Field(default_factory=list, description="IDs of related facts")
    tags: list[str] = Field(default_factory=list, description="Searchable tags")
    source: Optional[str] = Field(default=None, description="Source that established this fact")


class KnowledgeSource(str, Enum):
    """Sources from which an NPC can acquire knowledge."""
    WITNESSED = "witnessed"
    TOLD_BY_PLAYER = "told_by_player"
    TOLD_BY_NPC = "told_by_npc"
    COMMON_KNOWLEDGE = "common_knowledge"
    PROFESSION = "profession"
    RUMOR = "rumor"


class KnowledgeEntry(BaseModel):
    """
    A record of an NPC's knowledge of a specific fact.

    Tracks how and when an NPC learned a fact, with confidence level
    indicating certainty (1.0 = certain, 0.5 = rumor).

    Attributes:
        fact_id: ID of the fact this NPC knows
        source: How the NPC acquired this knowledge
        acquired_session: Session number when knowledge was acquired
        acquired_timestamp: When the knowledge was acquired
        confidence: Certainty level (0.0-1.0+)
        source_entity: Who told them (for TOLD_BY_PLAYER/NPC sources)
    """
    fact_id: str = Field(description="ID of the fact known by the NPC")
    source: KnowledgeSource = Field(description="How the knowledge was acquired")
    acquired_session: int = Field(ge=1, description="Session when knowledge was acquired")
    acquired_timestamp: datetime = Field(default_factory=datetime.now, description="When knowledge was acquired")
    confidence: float = Field(default=1.0, ge=0.0, description="Confidence level (1.0=certain, 0.5=rumor)")
    source_entity: Optional[str] = Field(default=None, description="Who told them (if applicable)")


class PlayerInteraction(BaseModel):
    """
    A record of an interaction between players and an NPC.

    Tracks the type and details of interactions to help generate
    contextual NPC dialogue.

    Attributes:
        session_number: Session when the interaction occurred
        timestamp: When the interaction occurred
        interaction_type: Type of interaction (e.g., "conversation", "combat", "trade")
        summary: Brief description of what happened
        player_characters: Names of player characters involved
        location: Where the interaction took place
    """
    session_number: int = Field(ge=1, description="Session when interaction occurred")
    timestamp: datetime = Field(default_factory=datetime.now, description="When the interaction occurred")
    interaction_type: str = Field(description="Type of interaction (conversation, combat, trade, etc.)")
    summary: str = Field(description="Brief description of the interaction")
    player_characters: list[str] = Field(default_factory=list, description="Player characters involved")
    location: str = Field(default="", description="Where the interaction took place")


__all__ = [
    "Fact",
    "FactCategory",
    "KnowledgeSource",
    "KnowledgeEntry",
    "PlayerInteraction",
]
