"""
Combat mechanics package for dm20-protocol.

Provides the Active Effects engine, SRD condition definitions,
concentration tracking, stat computation utilities, encounter building,
XP budget calculation, and difficulty classification for D&D 5e combat.
"""

# Active Effects engine
from .effects import EffectsEngine, SRD_CONDITIONS

# Concentration tracking
from .concentration import ConcentrationTracker

__all__ = [
    "EffectsEngine",
    "SRD_CONDITIONS",
    "ConcentrationTracker",
]

# Encounter builder (may be added by parallel agent)
try:
    from .encounter_builder import (
        EncounterSuggestion,
        MonsterGroup,
        EncounterComposition,
        calculate_xp_budget,
        build_encounter,
        get_xp_thresholds,
        get_encounter_multiplier,
        classify_difficulty,
        XP_THRESHOLDS,
        CR_TO_XP,
        ENCOUNTER_MULTIPLIERS,
    )

    __all__ += [
        "EncounterSuggestion",
        "MonsterGroup",
        "EncounterComposition",
        "calculate_xp_budget",
        "build_encounter",
        "get_xp_thresholds",
        "get_encounter_multiplier",
        "classify_difficulty",
        "XP_THRESHOLDS",
        "CR_TO_XP",
        "ENCOUNTER_MULTIPLIERS",
    ]
except ImportError:
    pass

# Combat action pipeline
try:
    from .pipeline import (
        CombatResult,
        SpellSaveResult,
        resolve_attack,
        resolve_save_spell,
    )

    __all__ += [
        "CombatResult",
        "SpellSaveResult",
        "resolve_attack",
        "resolve_save_spell",
    ]
except ImportError:
    pass

# Positioning and AoE engine
try:
    from .positioning import (
        Position,
        Proximity,
        AoEShape,
        Sphere,
        Cube,
        Cone,
        Line,
        Cylinder,
        distance,
        calculate_aoe_targets,
        set_positions,
        move_participant,
        proximity_from_distance,
    )

    __all__ += [
        "Position",
        "Proximity",
        "AoEShape",
        "Sphere",
        "Cube",
        "Cone",
        "Line",
        "Cylinder",
        "distance",
        "calculate_aoe_targets",
        "set_positions",
        "move_participant",
        "proximity_from_distance",
    ]
except ImportError:
    pass
