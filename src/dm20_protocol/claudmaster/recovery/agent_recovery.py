"""
Agent failure recovery manager for the Claudmaster AI DM system.

Implements retry, fallback, and degradation strategies for handling
agent execution failures.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any

from dm20_protocol.claudmaster.base import AgentResponse, AgentRole
from dm20_protocol.claudmaster.exceptions import AgentError, RecoveryError
from dm20_protocol.claudmaster.recovery import RecoveryResult

if TYPE_CHECKING:
    from dm20_protocol.claudmaster.base import Agent
    from dm20_protocol.claudmaster.orchestrator import Orchestrator

logger = logging.getLogger("dm20-protocol")


class AgentRecoveryManager:
    """Manages agent failure recovery with multiple strategies.

    This manager tracks agent failures and applies recovery strategies
    in the following order:
    1. Retry with exponential backoff
    2. Fallback to alternative agent
    3. Graceful degradation
    4. User intervention

    Attributes:
        orchestrator: Reference to the orchestrator managing agents
        max_retries: Maximum number of retry attempts per agent
        retry_delays: List of delay seconds for exponential backoff
        failure_counts: Tracking of failures per agent name
    """

    def __init__(self, orchestrator: Orchestrator, max_retries: int = 3):
        """Initialize the recovery manager.

        Args:
            orchestrator: Reference to the orchestrator managing agents
            max_retries: Maximum number of retry attempts per agent
        """
        self.orchestrator = orchestrator
        self.max_retries = max_retries
        self.retry_delays = [1.0, 2.0, 4.0]  # Exponential backoff: 1s, 2s, 4s
        self.failure_counts: dict[str, int] = {}

    async def handle_agent_failure(
        self,
        agent: Agent,
        error: Exception,
        context: dict[str, Any],
    ) -> RecoveryResult:
        """Handle an agent failure with appropriate recovery strategy.

        Attempts recovery strategies in order:
        1. Retry with exponential backoff
        2. Fallback to alternative agent
        3. Request graceful degradation
        4. Request user intervention

        Args:
            agent: The agent that failed
            error: The exception that was raised
            context: The execution context for the agent

        Returns:
            RecoveryResult describing the outcome
        """
        agent_name = agent.name
        self.failure_counts[agent_name] = self.failure_counts.get(agent_name, 0) + 1

        logger.warning(
            f"Agent {agent_name} failed (attempt {self.failure_counts[agent_name]}): {error}"
        )

        # Classify error recoverability
        recoverable = self._is_recoverable(error)
        if not recoverable:
            return RecoveryResult(
                success=False,
                strategy_used="user_intervention",
                message=f"Agent {agent_name} encountered unrecoverable error: {error}",
            )

        # Strategy 1: Retry with backoff
        if self.failure_counts[agent_name] <= self.max_retries:
            logger.info(f"Attempting retry for agent {agent_name}")
            response = await self.retry_with_backoff(agent, context)
            if response is not None:
                self.reset_failure_count(agent_name)
                return RecoveryResult(
                    success=True,
                    strategy_used="retry",
                    message=f"Agent {agent_name} recovered after retry",
                    response=response,
                )

        # Strategy 2: Fallback agent
        fallback = self.get_fallback_agent(agent)
        if fallback is not None:
            logger.info(f"Attempting fallback from {agent_name} to {fallback.name}")
            try:
                response = await fallback.run(context)
                self.reset_failure_count(agent_name)
                return RecoveryResult(
                    success=True,
                    strategy_used="fallback",
                    message=f"Recovered using fallback agent {fallback.name}",
                    response=response,
                )
            except Exception as fallback_error:
                logger.error(f"Fallback agent {fallback.name} also failed: {fallback_error}")

        # Strategy 3: Request degradation
        logger.warning(f"Agent {agent_name} exhausted recovery options, requesting degradation")
        return RecoveryResult(
            success=False,
            strategy_used="degradation",
            message=f"Agent {agent_name} unavailable, system degradation required",
        )

    async def retry_with_backoff(
        self,
        agent: Agent,
        context: dict[str, Any],
    ) -> AgentResponse | None:
        """Retry agent execution with exponential backoff.

        Args:
            agent: The agent to retry
            context: The execution context for the agent

        Returns:
            AgentResponse if successful, None if all retries failed
        """
        agent_name = agent.name
        attempt = self.failure_counts.get(agent_name, 0)

        if attempt > len(self.retry_delays):
            logger.warning(f"Agent {agent_name} exceeded maximum retries")
            return None

        # Wait with exponential backoff
        delay = self.retry_delays[min(attempt - 1, len(self.retry_delays) - 1)]
        logger.info(f"Retrying agent {agent_name} after {delay}s delay")
        await asyncio.sleep(delay)

        try:
            response = await agent.run(context)
            logger.info(f"Agent {agent_name} retry succeeded")
            return response
        except Exception as e:
            logger.error(f"Agent {agent_name} retry failed: {e}")
            return None

    def get_fallback_agent(self, failed_agent: Agent) -> Agent | None:
        """Get a fallback agent for the failed agent.

        Fallback mapping:
        - NARRATOR: No fallback (primary narrative voice)
        - ARCHIVIST: No fallback (state management is critical)
        - MODULE_KEEPER: Could fall back to Narrator for basic responses
        - CONSISTENCY: Could fall back to Archivist for fact checking

        Args:
            failed_agent: The agent that failed

        Returns:
            Fallback agent if available, None otherwise
        """
        role = failed_agent.role

        if role == AgentRole.MODULE_KEEPER:
            # MODULE_KEEPER can fall back to NARRATOR for basic narrative
            for agent in self.orchestrator.agents.values():
                if agent.role == AgentRole.NARRATOR and agent.name != failed_agent.name:
                    return agent

        elif role == AgentRole.CONSISTENCY:
            # CONSISTENCY can fall back to ARCHIVIST for state tracking
            for agent in self.orchestrator.agents.values():
                if agent.role == AgentRole.ARCHIVIST and agent.name != failed_agent.name:
                    return agent

        # No fallback for NARRATOR or ARCHIVIST
        return None

    def reset_failure_count(self, agent_name: str) -> None:
        """Reset failure count for an agent after successful recovery.

        Args:
            agent_name: Name of the agent to reset
        """
        if agent_name in self.failure_counts:
            logger.info(f"Resetting failure count for agent {agent_name}")
            del self.failure_counts[agent_name]

    def _is_recoverable(self, error: Exception) -> bool:
        """Determine if an error is recoverable.

        Args:
            error: The exception to classify

        Returns:
            True if the error might be recoverable, False otherwise
        """
        # AgentError with recoverable=False
        if isinstance(error, AgentError) and not error.recoverable:
            return False

        # Timeout errors are typically recoverable (might be temporary)
        if isinstance(error, asyncio.TimeoutError):
            return True

        # Network/API errors are typically recoverable
        error_type = type(error).__name__
        recoverable_patterns = ["Timeout", "Connection", "Network", "API", "Rate"]
        if any(pattern in error_type for pattern in recoverable_patterns):
            return True

        # Most other errors are worth attempting recovery
        return True


__all__ = ["AgentRecoveryManager"]
