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


__all__ = [
    "Fact",
    "FactCategory",
]
