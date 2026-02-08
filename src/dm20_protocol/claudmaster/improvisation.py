"""
Improvisation Level System for Claudmaster AI DM.

This module defines the improvisation levels that control how closely the AI DM
adheres to published adventure module content. Levels range from strict module
adherence (verbatim text only) to complete creative freedom.

The system provides constraint templates that are injected into agent prompts
to enforce the selected improvisation level.
"""

from enum import Enum


class ImprovisationLevel(str, Enum):
    """
    Improvisation levels controlling module adherence vs creative freedom.

    Levels determine how strictly the AI DM follows published adventure module
    content, ranging from verbatim recitation to complete improvisation.
    """
    NONE = "none"       # 100% module adherence, verbatim text only
    LOW = "low"         # 90% adherence, minor flavor additions
    MEDIUM = "medium"   # 70% adherence, moderate improvisation
    HIGH = "high"       # 40% adherence, significant creative freedom
    FULL = "full"       # 0% adherence, complete improvisation


# Module adherence percentages for each improvisation level
ADHERENCE_PERCENTAGES: dict[ImprovisationLevel, int] = {
    ImprovisationLevel.NONE: 100,
    ImprovisationLevel.LOW: 90,
    ImprovisationLevel.MEDIUM: 70,
    ImprovisationLevel.HIGH: 40,
    ImprovisationLevel.FULL: 0,
}


# Detailed prompt constraint templates for each level
PROMPT_CONSTRAINTS: dict[ImprovisationLevel, str] = {
    ImprovisationLevel.NONE: (
        "You MUST read module content exactly as written. Do not add, modify, "
        "or embellish any text. Read-aloud boxes verbatim. NPC dialogue exactly "
        "as printed. No creative additions whatsoever. If the module provides "
        "specific descriptions, encounters, or dialogue, use them word-for-word."
    ),
    ImprovisationLevel.LOW: (
        "Follow module content closely. You may add minor descriptive flourishes "
        "(sensory details, brief atmosphere) but the plot, encounters, NPC dialogue, "
        "and key descriptions must remain faithful to the module text. Think of "
        "yourself as a narrator adding small touches of color, not rewriting the story."
    ),
    ImprovisationLevel.MEDIUM: (
        "Use the module as your primary guide. You may expand descriptions, add "
        "minor NPCs for flavor, and adapt dialogue to feel more natural. Core plot "
        "points, major encounters, and key NPCs must stay true to the module. You "
        "have freedom to embellish and enhance, but the adventure's structure remains."
    ),
    ImprovisationLevel.HIGH: (
        "The module provides a framework. You may create side content, modify "
        "encounters for dramatic effect, adapt the plot to player choices, and add "
        "original NPCs and locations. Only major plot milestones must remain intact. "
        "Feel free to improvise significantly while honoring the module's core narrative."
    ),
    ImprovisationLevel.FULL: (
        "The module is optional inspiration only. You have complete creative freedom. "
        "Create new content, modify anything, and let the story evolve organically "
        "based on player actions. The published module serves as a starting point, "
        "not a constraint. Improvise freely and prioritize player engagement over adherence."
    ),
}


def get_adherence_percentage(level: ImprovisationLevel) -> int:
    """
    Get the module adherence percentage for a given improvisation level.

    Args:
        level: The improvisation level to query

    Returns:
        Adherence percentage (0-100) indicating how closely to follow module content

    Example:
        >>> get_adherence_percentage(ImprovisationLevel.MEDIUM)
        70
    """
    return ADHERENCE_PERCENTAGES[level]


def get_constraints(level: ImprovisationLevel) -> str:
    """
    Get the prompt constraint text for a given improvisation level.

    This text should be injected into agent prompts to enforce the selected
    improvisation level during gameplay.

    Args:
        level: The improvisation level to query

    Returns:
        Detailed constraint text describing how to handle module content

    Example:
        >>> constraints = get_constraints(ImprovisationLevel.LOW)
        >>> "Follow module content closely" in constraints
        True
    """
    return PROMPT_CONSTRAINTS[level]


def validate_level_transition(
    current: ImprovisationLevel,
    target: ImprovisationLevel,
    allow_large_jumps: bool = True
) -> tuple[bool, str]:
    """
    Validate whether a level transition is allowed during an active session.

    By default, any transition is allowed. If large jumps are disabled,
    transitions can only move one level at a time.

    Args:
        current: Current improvisation level
        target: Desired improvisation level
        allow_large_jumps: Whether to allow non-adjacent level changes

    Returns:
        Tuple of (is_valid, error_message). If valid, error_message is empty.

    Example:
        >>> validate_level_transition(ImprovisationLevel.NONE, ImprovisationLevel.FULL, False)
        (False, "Cannot jump from NONE to FULL. Transition one level at a time.")
    """
    if allow_large_jumps:
        return (True, "")

    # Define level ordering
    level_order = [
        ImprovisationLevel.NONE,
        ImprovisationLevel.LOW,
        ImprovisationLevel.MEDIUM,
        ImprovisationLevel.HIGH,
        ImprovisationLevel.FULL,
    ]

    current_idx = level_order.index(current)
    target_idx = level_order.index(target)
    distance = abs(target_idx - current_idx)

    if distance <= 1:
        return (True, "")

    return (
        False,
        f"Cannot jump from {current.value.upper()} to {target.value.upper()}. "
        f"Transition one level at a time."
    )


__all__ = [
    "ImprovisationLevel",
    "ADHERENCE_PERCENTAGES",
    "PROMPT_CONSTRAINTS",
    "get_adherence_percentage",
    "get_constraints",
    "validate_level_transition",
]
