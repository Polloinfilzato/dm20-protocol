"""Claudmaster agent implementations."""

from .narrator import NarratorAgent, NarrativeStyle, LLMClient
from .archivist import (
    ArchivistAgent,
    HPStatus,
    CharacterStats,
    InventoryItem,
    Inventory,
    Condition,
    InitiativeEntry,
    CombatState,
    AvailableAction,
    RuleResult,
    QueryResult,
    QueryType,
    StateCache,
)
from .module_keeper import (
    ModuleKeeperAgent,
    NPCKnowledge,
    LocationDescription,
    EncounterTrigger,
    PlotContext,
)

__all__ = [
    "NarratorAgent",
    "NarrativeStyle",
    "LLMClient",
    # Archivist Agent exports
    "ArchivistAgent",
    "HPStatus",
    "CharacterStats",
    "InventoryItem",
    "Inventory",
    "Condition",
    "InitiativeEntry",
    "CombatState",
    "AvailableAction",
    "RuleResult",
    "QueryResult",
    "QueryType",
    "StateCache",
    # Module Keeper Agent exports
    "ModuleKeeperAgent",
    "NPCKnowledge",
    "LocationDescription",
    "EncounterTrigger",
    "PlotContext",
]
