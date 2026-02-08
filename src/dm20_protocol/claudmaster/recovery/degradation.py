"""
Graceful degradation manager for the Claudmaster AI DM system.

Manages system degradation levels when components fail, ensuring the system
remains functional with reduced capabilities rather than complete failure.
"""

from __future__ import annotations

import logging
from enum import Enum

logger = logging.getLogger("dm20-protocol")


class DegradationLevel(str, Enum):
    """System degradation levels from full functionality to emergency mode."""

    FULL = "full"  # All features available
    REDUCED = "reduced"  # Core gameplay only, no advanced features
    MINIMAL = "minimal"  # Basic interaction and saving
    EMERGENCY = "emergency"  # Save and exit only


class DegradationManager:
    """Manages graceful degradation of system capabilities.

    Tracks the current degradation level and provides information about
    available actions at each level. Ensures degradation only moves downward
    (more restricted) unless components recover.

    Attributes:
        current_level: Current degradation level
        degradation_reasons: List of reasons for current degradation
    """

    def __init__(self):
        """Initialize the degradation manager at FULL level."""
        self.current_level = DegradationLevel.FULL
        self.degradation_reasons: list[str] = []

    def degrade_to(self, level: DegradationLevel, reason: str) -> bool:
        """Degrade system to a lower level of functionality.

        Degradation can only move downward (more restricted). To restore
        functionality, use upgrade_to() after confirming components are healthy.

        Args:
            level: Target degradation level
            reason: Explanation for why degradation is needed

        Returns:
            True if degradation was applied, False if already at that level or lower
        """
        # Get ordinal values for comparison
        level_order = [
            DegradationLevel.FULL,
            DegradationLevel.REDUCED,
            DegradationLevel.MINIMAL,
            DegradationLevel.EMERGENCY,
        ]
        current_idx = level_order.index(self.current_level)
        target_idx = level_order.index(level)

        # Only allow downward degradation
        if target_idx <= current_idx:
            logger.info(f"Already at {self.current_level}, not degrading to {level}")
            return False

        logger.warning(f"Degrading system from {self.current_level} to {level}: {reason}")
        self.current_level = level
        self.degradation_reasons.append(reason)
        return True

    def upgrade_to(self, level: DegradationLevel) -> bool:
        """Upgrade system to a higher level of functionality.

        Should only be called after confirming that components have recovered.

        Args:
            level: Target level to upgrade to

        Returns:
            True if upgrade was successful, False if already at that level or higher
        """
        level_order = [
            DegradationLevel.FULL,
            DegradationLevel.REDUCED,
            DegradationLevel.MINIMAL,
            DegradationLevel.EMERGENCY,
        ]
        current_idx = level_order.index(self.current_level)
        target_idx = level_order.index(level)

        # Only allow upward upgrades
        if target_idx >= current_idx:
            logger.info(f"Already at {self.current_level}, not upgrading to {level}")
            return False

        logger.info(f"Upgrading system from {self.current_level} to {level}")
        self.current_level = level
        # Clear some degradation reasons on upgrade
        if self.degradation_reasons:
            self.degradation_reasons.pop()
        return True

    def get_available_actions(self) -> list[str]:
        """Get list of available actions at current degradation level.

        Returns:
            List of action types available at current level
        """
        if self.current_level == DegradationLevel.FULL:
            return [
                "exploration",
                "combat",
                "roleplay",
                "system",
                "advanced_narrative",
                "npc_dialogue",
                "module_queries",
                "fact_checking",
            ]
        elif self.current_level == DegradationLevel.REDUCED:
            return [
                "exploration",
                "combat",
                "roleplay",
                "basic_narrative",
                "simple_npc",
            ]
        elif self.current_level == DegradationLevel.MINIMAL:
            return [
                "basic_actions",
                "simple_responses",
                "save_session",
            ]
        else:  # EMERGENCY
            return [
                "save_session",
                "exit_session",
            ]

    def notify_user(self) -> str:
        """Generate user-friendly notification about degradation.

        Returns:
            In-character message explaining the degradation
        """
        if self.current_level == DegradationLevel.FULL:
            return ""

        messages = {
            DegradationLevel.REDUCED: (
                "*The DM pauses briefly, consulting notes*\n\n"
                "I apologize, adventurer. My arcane connection to the deeper lore "
                "seems... unstable. We can continue our adventure, but some of the "
                "finer details may elude me for now. The core of our tale remains strong."
            ),
            DegradationLevel.MINIMAL: (
                "*The DM's voice wavers*\n\n"
                "Forgive me, brave one. The magical threads that weave our story "
                "are fraying. I can still respond to your basic actions, and we can "
                "save your progress, but the rich tapestry of our adventure must pause "
                "until the connection strengthens."
            ),
            DegradationLevel.EMERGENCY: (
                "*The DM's form flickers*\n\n"
                "I'm afraid our connection to the realm is failing critically. "
                "I can only help you save your progress and prepare for departure. "
                "Fear not - your journey will be preserved, ready to continue when "
                "the connection is restored."
            ),
        }

        message = messages.get(self.current_level, "System degraded")
        if self.degradation_reasons:
            message += f"\n\n*Technical note: {self.degradation_reasons[-1]}*"
        return message

    def can_upgrade(self) -> bool:
        """Check if system can be upgraded from current level.

        Returns:
            True if not at FULL level, False if already at FULL
        """
        return self.current_level != DegradationLevel.FULL

    def is_action_allowed(self, action_type: str) -> bool:
        """Check if a specific action type is allowed at current level.

        Args:
            action_type: The action type to check

        Returns:
            True if action is allowed, False otherwise
        """
        return action_type in self.get_available_actions()


__all__ = [
    "DegradationLevel",
    "DegradationManager",
]
