"""
Claudmaster: Multi-agent AI Game Master system.

This package implements a multi-agent architecture for D&D game mastering,
inspired by research showing that specialized agents outperform single-agent systems
for complex narrative and game management tasks.

The system consists of four specialized agents:
- Narrator: Handles descriptions, NPC dialogue, and atmosphere
- Archivist: Manages game state, rules, and combat mechanics
- Module Keeper: Provides RAG access to adventure modules and lore
- Consistency: Tracks facts and prevents contradictions

Public API exports the base Agent class and related types.
"""

from .base import Agent, AgentRequest, AgentResponse, AgentRole
from .module_indexer import ChunkConfig, IndexingResult, ModuleIndexer
from .orchestrator import (
    IntentType,
    PlayerIntent,
    WeightedPattern,
    DEFAULT_INTENT_PATTERNS,
    OrchestratorResponse,
    TurnResult,
    OrchestratorError,
    AgentTimeoutError,
    AgentExecutionError,
    IntentClassificationError,
    Orchestrator,
)
from .agents.archivist import (
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
from .action_interpreter import (
    ActionInterpreter,
    ActionIntent,
    ParsedAction,
    AmbiguityType,
    Ambiguity,
    ValidationResult,
    InterpretationResult,
    ClarificationRequest,
)
from .combat_narrator import (
    CombatNarrator,
    DamageSeverity,
    SpellInfo,
    SpellEffect,
    DramaticMoment,
    DescriptionTracker,
)
from .atmosphere import (
    AtmosphereManager,
    Tone,
    Pacing,
    SceneType,
    TensionState,
    SceneContext,
)
from .companions import (
    CombatStyle,
    CompanionArchetype,
    PersonalityTraits,
    CompanionProfile,
    CompanionManager,
    ARCHETYPE_TEMPLATES,
)

__all__ = [
    "Agent",
    "AgentRequest",
    "AgentResponse",
    "AgentRole",
    "ChunkConfig",
    "IndexingResult",
    "ModuleIndexer",
    "IntentType",
    "PlayerIntent",
    "WeightedPattern",
    "DEFAULT_INTENT_PATTERNS",
    "OrchestratorResponse",
    "TurnResult",
    "OrchestratorError",
    "AgentTimeoutError",
    "AgentExecutionError",
    "IntentClassificationError",
    "Orchestrator",
    # Archivist Agent (Issue #43)
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
    # Action Interpreter (Issue #44)
    "ActionInterpreter",
    "ActionIntent",
    "ParsedAction",
    "AmbiguityType",
    "Ambiguity",
    "ValidationResult",
    "InterpretationResult",
    "ClarificationRequest",
    # Combat Narrator (Issue #45)
    "CombatNarrator",
    "DamageSeverity",
    "SpellInfo",
    "SpellEffect",
    "DramaticMoment",
    "DescriptionTracker",
    # Atmosphere Manager (Issue #46)
    "AtmosphereManager",
    "Tone",
    "Pacing",
    "SceneType",
    "TensionState",
    "SceneContext",
    # Companion System (Issue #55)
    "CombatStyle",
    "CompanionArchetype",
    "PersonalityTraits",
    "CompanionProfile",
    "CompanionManager",
    "ARCHETYPE_TEMPLATES",
]
