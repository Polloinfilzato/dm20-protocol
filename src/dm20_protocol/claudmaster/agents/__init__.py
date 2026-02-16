"""Claudmaster agent implementations."""

from .narrator import (
    NarratorAgent,
    NarrativeStyle,
    LLMClient,
    VoiceProfile,
    DialogueLine,
    DialogueContext,
    Conversation,
)
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
# Module Keeper requires optional 'rag' dependencies (chromadb)
try:
    from .module_keeper import (
        ModuleKeeperAgent,
        NPCKnowledge,
        LocationDescription,
        EncounterTrigger,
        PlotContext,
    )
except ImportError:
    ModuleKeeperAgent = None  # type: ignore[assignment,misc]
    NPCKnowledge = None  # type: ignore[assignment,misc]
    LocationDescription = None  # type: ignore[assignment,misc]
    EncounterTrigger = None  # type: ignore[assignment,misc]
    PlotContext = None  # type: ignore[assignment,misc]

from .player_character import (
    PlayerCharacterAgent,
    PCContext,
    PCDecision,
)

__all__ = [
    "NarratorAgent",
    "NarrativeStyle",
    "LLMClient",
    "VoiceProfile",
    "DialogueLine",
    "DialogueContext",
    "Conversation",
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
    # Player Character Agent exports
    "PlayerCharacterAgent",
    "PCContext",
    "PCDecision",
]
