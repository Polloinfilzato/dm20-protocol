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
from .tactics import (
    TacticalPriority,
    Combatant,
    TacticalDecision,
    BattlefieldState,
    TacticsEngine,
)
from .companion_dialogue import (
    DialogueTrigger,
    EmotionalState,
    DialogueContext,
    CompanionDialogue,
    CompanionDialogueEngine,
    DIALOGUE_TEMPLATES,
    REACTION_PROBABILITY,
)
from .improvisation import (
    ImprovisationLevel,
    ADHERENCE_PERCENTAGES,
    PROMPT_CONSTRAINTS,
    get_adherence_percentage,
    get_constraints,
    validate_level_transition,
)
from .element_locks import (
    ElementCategory,
    ElementLock,
    LockConfiguration,
    CATEGORY_HIERARCHY,
)
from .pc_tracking import (
    PCState,
    MultiPlayerConfig,
    PCRegistry,
    PCIdentifier,
)
from .guidance import (
    GuidanceType,
    ParsedGuidance,
    CompanionGuidance,
    GuidanceParser,
    GuidanceManager,
    ACKNOWLEDGMENTS,
)
from .config import ClaudmasterConfig
from .consistency import (
    GameTime,
    LocationState,
    LocationStateManager,
    StateChange,
    StateChangeType,
    TimelineEvent,
    TimelineTracker,
    TimeUnit,
)
from .fidelity import (
    NarrationContext,
    Deviation,
    EnforcementResult,
    FidelityWarning,
    FidelityAuditEntry,
    DeviationDetector,
    FidelityWarningSystem,
    ForcedTextInjector,
    FidelityAuditLog,
    NarratorLockEnforcer,
    get_applicable_locks,
)
from .content_tagging import (
    ContentOrigin,
    ContentTag,
    TaggedSegment,
    TaggedNarrative,
    TaggedFact,
    ContentTagger,
    TaggedContentStore,
    SessionNotesFormatter,
)
from .turn_manager import (
    TurnPhase,
    TurnDistribution,
    TurnRecord,
    ActionResult,
    SimultaneousAction,
    TurnState,
    TurnManager,
)
from .private_info import (
    InfoVisibility,
    PrivateInfo,
    PrivateMessage,
    HiddenRoll,
    SecretKnowledge,
    PrivateInfoManager,
)
from .tools.session_tools import (
    CampaignSummary,
    ModuleSummary,
    GameStateSummary,
    CharacterSummary,
    SessionState,
    SessionManager,
    start_claudmaster_session,
)
from .split_party import (
    PartyGroup,
    SplitEvent,
    ReunificationEvent,
    MessageResult,
    SplitProposal,
    SplitPartyManager,
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
    # AI Combat Tactics (Issue #56)
    "TacticalPriority",
    "Combatant",
    "TacticalDecision",
    "BattlefieldState",
    "TacticsEngine",
    # Companion Dialogue (Issue #57)
    "DialogueTrigger",
    "EmotionalState",
    "DialogueContext",
    "CompanionDialogue",
    "CompanionDialogueEngine",
    "DIALOGUE_TEMPLATES",
    "REACTION_PROBABILITY",
    # Improvisation System (Issue #51)
    "ImprovisationLevel",
    "ADHERENCE_PERCENTAGES",
    "PROMPT_CONSTRAINTS",
    "get_adherence_percentage",
    "get_constraints",
    "validate_level_transition",
    # Locked/Flexible Elements (Issue #52)
    "ElementCategory",
    "ElementLock",
    "LockConfiguration",
    "CATEGORY_HIERARCHY",
    # Multi-PC Tracking (Issue #59)
    "PCState",
    "MultiPlayerConfig",
    "PCRegistry",
    "PCIdentifier",
    # Player Guidance System (Issue #58)
    "GuidanceType",
    "ParsedGuidance",
    "CompanionGuidance",
    "GuidanceParser",
    "GuidanceManager",
    "ACKNOWLEDGMENTS",
    # Timeline and Location State (Issue #50)
    "GameTime",
    "TimeUnit",
    "TimelineEvent",
    "TimelineTracker",
    "StateChangeType",
    "StateChange",
    "LocationState",
    "LocationStateManager",
    # Config
    "ClaudmasterConfig",
    # Module Fidelity Enforcement (Issue #53)
    "NarrationContext",
    "Deviation",
    "EnforcementResult",
    "FidelityWarning",
    "FidelityAuditEntry",
    "DeviationDetector",
    "FidelityWarningSystem",
    "ForcedTextInjector",
    "FidelityAuditLog",
    "NarratorLockEnforcer",
    "get_applicable_locks",
    # Canonical vs Improvised Tagging (Issue #54)
    "ContentOrigin",
    "ContentTag",
    "TaggedSegment",
    "TaggedNarrative",
    "TaggedFact",
    "ContentTagger",
    "TaggedContentStore",
    "SessionNotesFormatter",
    # Turn Distribution and Management (Issue #60)
    "TurnPhase",
    "TurnDistribution",
    "TurnRecord",
    "ActionResult",
    "SimultaneousAction",
    "TurnState",
    "TurnManager",
    # Player-Specific Information (Issue #62)
    "InfoVisibility",
    "PrivateInfo",
    "PrivateMessage",
    "HiddenRoll",
    "SecretKnowledge",
    "PrivateInfoManager",
    # Session MCP Tools (Issue #63)
    "CampaignSummary",
    "ModuleSummary",
    "GameStateSummary",
    "CharacterSummary",
    "SessionState",
    "SessionManager",
    "start_claudmaster_session",
    # Split Party Handling (Issue #61)
    "PartyGroup",
    "SplitEvent",
    "ReunificationEvent",
    "MessageResult",
    "SplitProposal",
    "SplitPartyManager",
]
