"""
Base agent class and core types for the Claudmaster multi-agent system.

This module implements the ReAct (Reason + Act) pattern for AI agents:
- Reason: Analyze context and decide what to do
- Act: Execute the decided action
- Observe: Process results and update internal state

The abstract Agent base class defines the interface that all specialized
agents (Narrator, Archivist, Module Keeper, Consistency) must implement.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class AgentRole(str, Enum):
    """Roles available in the Claudmaster multi-agent system."""
    NARRATOR = "narrator"
    ARCHIVIST = "archivist"
    MODULE_KEEPER = "module_keeper"
    CONSISTENCY = "consistency"
    ARBITER = "arbiter"
    PLAYER_CHARACTER = "player_character"


class AgentRequest(BaseModel):
    """Request structure for agent execution."""
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="Contextual information for the agent to process"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata about the request"
    )


class AgentResponse(BaseModel):
    """Response structure from agent execution."""
    agent_name: str = Field(description="Name of the agent that generated this response")
    agent_role: AgentRole = Field(description="Role of the agent that generated this response")
    reasoning: str = Field(description="The reasoning process of the agent")
    action_result: Any = Field(description="The result of the agent's action")
    observations: dict[str, Any] = Field(
        default_factory=dict,
        description="Observations made after the action"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Optional metadata about the response"
    )


class Agent(ABC):
    """
    Abstract base class for all Claudmaster agents implementing the ReAct pattern.

    The ReAct pattern consists of three phases:
    1. Reason: Analyze the context and decide what action to take
    2. Act: Execute the decided action
    3. Observe: Process the results and extract observations

    Subclasses must implement the three abstract methods: reason(), act(), and observe().
    The run() method orchestrates these three phases and returns an AgentResponse.

    Attributes:
        name: Human-readable name for this agent instance
        role: The role this agent plays in the multi-agent system
    """

    def __init__(self, name: str, role: AgentRole) -> None:
        """
        Initialize the agent.

        Args:
            name: Human-readable name for this agent instance
            role: The role this agent plays in the multi-agent system
        """
        self.name = name
        self.role = role

    @abstractmethod
    async def reason(self, context: dict[str, Any]) -> str:
        """
        Analyze the context and determine what action to take.

        This method should examine the provided context and decide on the most
        appropriate action based on the agent's role and capabilities.

        Args:
            context: Contextual information to base reasoning on

        Returns:
            A string describing the reasoning process and intended action
        """
        pass

    @abstractmethod
    async def act(self, reasoning: str) -> Any:
        """
        Execute the action decided during the reasoning phase.

        This method takes the reasoning output and performs the actual work,
        which could include LLM calls, database queries, computation, etc.

        Args:
            reasoning: The reasoning output from the reason() phase

        Returns:
            The result of the action, type depends on the specific agent
        """
        pass

    @abstractmethod
    async def observe(self, result: Any) -> dict[str, Any]:
        """
        Process the action result and extract observations.

        This method analyzes the result of the action and extracts relevant
        observations, updates internal state, or prepares data for other agents.

        Args:
            result: The result from the act() phase

        Returns:
            A dictionary of observations extracted from the result
        """
        pass

    async def run(self, context: dict[str, Any]) -> AgentResponse:
        """
        Execute the full ReAct cycle: Reason -> Act -> Observe.

        This is the main entry point for agent execution. It orchestrates
        the three phases of the ReAct pattern and returns a structured response.

        Args:
            context: Contextual information for the agent to process

        Returns:
            AgentResponse containing the complete result of the ReAct cycle
        """
        # Phase 1: Reason
        reasoning = await self.reason(context)

        # Phase 2: Act
        action_result = await self.act(reasoning)

        # Phase 3: Observe
        observations = await self.observe(action_result)

        # Return structured response
        return AgentResponse(
            agent_name=self.name,
            agent_role=self.role,
            reasoning=reasoning,
            action_result=action_result,
            observations=observations
        )


__all__ = [
    "Agent",
    "AgentRequest",
    "AgentResponse",
    "AgentRole",
]
