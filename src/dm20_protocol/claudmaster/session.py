"""
Session management for Claudmaster AI DM system.
"""

from datetime import datetime
from typing import Any
from shortuuid import random
from pydantic import BaseModel, Field

from .config import ClaudmasterConfig


class ClaudmasterSession(BaseModel):
    """Tracks a single Claudmaster AI DM session.

    A session represents one continuous gameplay period with the AI DM,
    including conversation history, turn tracking, and agent state management.
    """

    session_id: str = Field(
        default_factory=lambda: random(length=8),
        description="Unique session identifier"
    )
    campaign_id: str = Field(
        description="ID of the linked campaign"
    )
    config: ClaudmasterConfig = Field(
        default_factory=ClaudmasterConfig,
        description="Configuration for this session"
    )
    started_at: datetime = Field(
        default_factory=datetime.now,
        description="Session start timestamp"
    )
    turn_count: int = Field(
        default=0,
        ge=0,
        description="Current turn number in the session"
    )
    conversation_history: list[dict[str, str]] = Field(
        default_factory=list,
        description="List of {role, content} message dicts"
    )
    active_agents: dict[str, str] = Field(
        default_factory=dict,
        description="Map of agent_name to status (idle, working, completed, error)"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary session metadata"
    )

    def add_message(self, role: str, content: str) -> None:
        """Append a message to the conversation history.

        Args:
            role: The role of the message sender (e.g., 'user', 'assistant', 'system')
            content: The message content
        """
        self.conversation_history.append({
            "role": role,
            "content": content
        })

    def increment_turn(self) -> int:
        """Increment the turn counter and return the new count.

        Returns:
            The updated turn count
        """
        self.turn_count += 1
        return self.turn_count

    def set_agent_status(self, agent_name: str, status: str) -> None:
        """Update the status of a specific agent.

        Args:
            agent_name: The name of the agent (e.g., 'narrator', 'archivist')
            status: The new status (e.g., 'idle', 'working', 'completed', 'error')
        """
        self.active_agents[agent_name] = status

    def get_context(self, max_messages: int = 20) -> dict[str, Any]:
        """Get recent conversation context for agents.

        Retrieves the most recent messages from the conversation history
        along with current session state for agent consumption.

        Args:
            max_messages: Maximum number of recent messages to include

        Returns:
            Dict containing session context with keys:
                - session_id: Session identifier
                - campaign_id: Campaign identifier
                - turn_count: Current turn number
                - recent_messages: List of recent conversation messages
                - agent_statuses: Current status of all agents
                - config: Session configuration
        """
        recent_messages = self.conversation_history[-max_messages:] if max_messages > 0 else []

        return {
            "session_id": self.session_id,
            "campaign_id": self.campaign_id,
            "turn_count": self.turn_count,
            "recent_messages": recent_messages,
            "agent_statuses": dict(self.active_agents),
            "config": self.config.model_dump()
        }


__all__ = ["ClaudmasterSession"]
