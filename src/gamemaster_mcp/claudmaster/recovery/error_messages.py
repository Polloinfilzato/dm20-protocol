"""
User-friendly error message formatter for the Claudmaster AI DM system.

Converts technical exceptions into immersive, in-character messages
that maintain the game atmosphere while informing the player.
"""

from __future__ import annotations

import logging
from typing import Any

from gamemaster_mcp.claudmaster.exceptions import (
    AgentError,
    ClaudmasterError,
    ClaudmasterTimeoutError,
    RecoveryError,
    RollbackError,
    SessionError,
    StateError,
)

logger = logging.getLogger("gamemaster-mcp")


class ErrorMessageFormatter:
    """Formats errors into user-friendly, in-character messages.

    Converts technical exceptions into immersive messages that fit
    the D&D atmosphere while still providing useful information.
    """

    def format_error(self, error: Exception, context: dict[str, Any] | None = None) -> str:
        """Format an error into a user-friendly message.

        Args:
            error: The exception to format
            context: Optional additional context for the error

        Returns:
            Formatted error message suitable for display to the player
        """
        context = context or {}

        # Match specific error types
        if isinstance(error, ClaudmasterTimeoutError):
            return self._format_timeout_error(error, context)
        elif isinstance(error, AgentError):
            return self._format_agent_error(error, context)
        elif isinstance(error, StateError):
            return self._format_state_error(error, context)
        elif isinstance(error, SessionError):
            return self._format_session_error(error, context)
        elif isinstance(error, RollbackError):
            return self._format_rollback_error(error, context)
        elif isinstance(error, RecoveryError):
            return self._format_recovery_error(error, context)
        elif isinstance(error, ClaudmasterError):
            return self._format_generic_claudmaster_error(error, context)
        else:
            return self._format_unknown_error(error, context)

    def suggest_recovery_action(self, error: Exception) -> str:
        """Suggest a recovery action for the error.

        Args:
            error: The exception to analyze

        Returns:
            Suggested action the user can take
        """
        if isinstance(error, ClaudmasterTimeoutError):
            return (
                "The mystical connection seems slow. You might:\n"
                "- Wait a moment and try again\n"
                "- Save your progress and restart if the issue persists"
            )
        elif isinstance(error, AgentError):
            if error.recoverable:
                return (
                    "This disruption should be temporary. You might:\n"
                    "- Try your action again\n"
                    "- Rephrase your request in simpler terms"
                )
            else:
                return (
                    "This issue requires attention beyond our realm. You should:\n"
                    "- Save your progress immediately\n"
                    "- Report this issue to the realm keepers"
                )
        elif isinstance(error, StateError):
            return (
                "The fabric of our reality needs mending. You should:\n"
                "- Save immediately if possible\n"
                "- Consider loading from a previous save point"
            )
        elif isinstance(error, SessionError):
            return (
                "Our connection to this adventure is troubled. You might:\n"
                "- Try starting a new session\n"
                "- Check if previous sessions can be resumed"
            )
        elif isinstance(error, RollbackError):
            return (
                "Time magic has failed us. You should:\n"
                "- Continue from current state if possible\n"
                "- Load from a saved session"
            )
        else:
            return (
                "The arcane forces are disrupted. You might:\n"
                "- Save your progress\n"
                "- Try again in a moment\n"
                "- Seek guidance from the realm keepers if this continues"
            )

    def _format_timeout_error(
        self, error: ClaudmasterTimeoutError, context: dict[str, Any]
    ) -> str:
        """Format a timeout error."""
        return (
            f"*The DM's voice fades momentarily*\n\n"
            f"Apologies, brave adventurer. The arcane connection seems... delayed. "
            f"My communion with the realm's deeper knowledge timed out after "
            f"{error.timeout_seconds} seconds.\n\n"
            f"*The operation '{error.operation}' could not complete in time*"
        )

    def _format_agent_error(self, error: AgentError, context: dict[str, Any]) -> str:
        """Format an agent error."""
        agent_descriptions = {
            "narrator": "the storyteller",
            "archivist": "the keeper of rules and state",
            "module_keeper": "the loremaster",
            "consistency": "the guardian of truth",
        }

        agent_desc = agent_descriptions.get(
            error.agent_name.lower(), f"agent {error.agent_name}"
        )

        if error.recoverable:
            return (
                f"*A shimmer in the air as {agent_desc} falters*\n\n"
                f"One moment, adventurer - {agent_desc} seems momentarily "
                f"distracted. Fear not, this should pass quickly.\n\n"
                f"*{error.agent_name} encountered a recoverable issue*"
            )
        else:
            return (
                f"*{agent_desc.title()} struggles visibly*\n\n"
                f"I must confess, {agent_desc} has encountered a problem "
                f"beyond my ability to mend. We may need to pause our adventure.\n\n"
                f"*{error.agent_name} encountered an unrecoverable error*"
            )

    def _format_state_error(self, error: StateError, context: dict[str, Any]) -> str:
        """Format a state error."""
        return (
            "*The DM frowns, consulting notes that seem to shift and blur*\n\n"
            "Something is amiss with the very fabric of our story. The threads "
            "of reality seem... tangled. I fear we may need to step back to an "
            "earlier moment in our tale.\n\n"
            "*Game state inconsistency detected*"
        )

    def _format_session_error(self, error: SessionError, context: dict[str, Any]) -> str:
        """Format a session error."""
        return (
            "*The DM's connection to the campaign world flickers*\n\n"
            "Our session seems troubled, adventurer. The magical bond that "
            "ties us to this adventure is strained. We may need to establish "
            "a new connection.\n\n"
            "*Session management issue encountered*"
        )

    def _format_rollback_error(self, error: RollbackError, context: dict[str, Any]) -> str:
        """Format a rollback error."""
        return (
            "*The DM attempts to turn back the pages, but they stick*\n\n"
            "I attempted to restore an earlier moment in our tale, but the "
            "magic of time refuses to cooperate. The past seems... inaccessible.\n\n"
            "*Failed to restore from snapshot*"
        )

    def _format_recovery_error(self, error: RecoveryError, context: dict[str, Any]) -> str:
        """Format a recovery error."""
        return (
            "*The DM's efforts to mend the situation seem to falter*\n\n"
            "My attempts to restore balance have themselves encountered difficulty. "
            "This is... unusual. We may need to take more drastic measures.\n\n"
            "*Recovery mechanism failure*"
        )

    def _format_generic_claudmaster_error(
        self, error: ClaudmasterError, context: dict[str, Any]
    ) -> str:
        """Format a generic Claudmaster error."""
        return (
            "*The DM pauses, troubled*\n\n"
            "Something unexpected has occurred in the realm of our adventure. "
            "While I work to understand the issue, you may wish to save your progress.\n\n"
            f"*{type(error).__name__}: {str(error)}*"
        )

    def _format_unknown_error(self, error: Exception, context: dict[str, Any]) -> str:
        """Format an unknown error type."""
        return (
            "*The DM looks confused, consulting mysterious scrolls*\n\n"
            "An unforeseen disturbance has rippled through our adventure. "
            "The nature of this disruption is... unclear. Let us proceed carefully.\n\n"
            f"*Unexpected error: {type(error).__name__}*"
        )

    def format_degradation_notice(
        self, level: str, reason: str, available_actions: list[str]
    ) -> str:
        """Format a notice about system degradation.

        Args:
            level: The degradation level
            reason: Why degradation occurred
            available_actions: List of actions still available

        Returns:
            Formatted degradation notice
        """
        action_list = "\n".join(f"- {action}" for action in available_actions)

        return (
            "*The DM's presence seems diminished*\n\n"
            f"I must inform you that my abilities have been... curtailed. "
            f"The realm is now in '{level}' mode. I can still assist with:\n\n"
            f"{action_list}\n\n"
            f"*Reason: {reason}*"
        )

    def format_crash_recovery_notice(
        self, session_id: str, turn_count: int, timestamp: str
    ) -> str:
        """Format a notice about crash recovery.

        Args:
            session_id: ID of the recovered session
            turn_count: Turn number when crash occurred
            timestamp: When the session was last active

        Returns:
            Formatted crash recovery notice
        """
        return (
            "*The mists part, revealing a familiar scene*\n\n"
            f"Welcome back, adventurer! It seems our previous connection to the "
            f"realm was... interrupted unexpectedly. I have woven the threads of "
            f"time to restore our tale to turn {turn_count}.\n\n"
            f"*Recovered session {session_id} from {timestamp}*\n\n"
            f"Shall we continue where we left off?"
        )


__all__ = ["ErrorMessageFormatter"]
