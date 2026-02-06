"""
Orchestrator for the Claudmaster multi-agent AI DM system.

The Orchestrator is the central coordination engine that:
1. Classifies player intent from raw input
2. Routes requests to the appropriate agents
3. Manages agent execution with timeouts
4. Aggregates responses into coherent narrative
5. Tracks turn state and session lifecycle

This implements the main game loop: player input -> intent -> agents -> response.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from gamemaster_mcp.models import Campaign, GameState
from .base import Agent, AgentResponse, AgentRole
from .config import ClaudmasterConfig
from .session import ClaudmasterSession

logger = logging.getLogger("gamemaster-mcp")


# ============================================================================
# Protocol Types
# ============================================================================

class IntentType(str, Enum):
    """Classification of player input intent."""
    ACTION = "action"
    QUESTION = "question"
    ROLEPLAY = "roleplay"
    COMBAT = "combat"
    EXPLORATION = "exploration"
    SYSTEM = "system"


class PlayerIntent(BaseModel):
    """Classified player intent with confidence score."""
    intent_type: IntentType = Field(description="The classified type of player intent")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence score for this classification")
    raw_input: str = Field(description="The original player input text")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional intent metadata (keywords, context clues, etc.)"
    )


class OrchestratorResponse(BaseModel):
    """Aggregated response from all agents."""
    narrative: str = Field(description="The primary narrative text presented to the player")
    state_changes: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of game state changes (e.g., HP updates, inventory changes)"
    )
    agent_responses: list[AgentResponse] = Field(
        default_factory=list,
        description="Raw responses from all agents that contributed"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional response metadata"
    )


class TurnResult(BaseModel):
    """Result of a complete turn execution."""
    turn_number: int = Field(description="The turn number in the session")
    player_input: str = Field(description="The original player input for this turn")
    intent: PlayerIntent = Field(description="The classified player intent")
    response: OrchestratorResponse = Field(description="The orchestrated response")
    timestamp: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when the turn completed"
    )


# ============================================================================
# Error Hierarchy
# ============================================================================

class OrchestratorError(Exception):
    """Base exception for orchestrator errors."""
    pass


class AgentTimeoutError(OrchestratorError):
    """Raised when an agent exceeds its timeout."""
    def __init__(self, agent_name: str, timeout: float):
        self.agent_name = agent_name
        self.timeout = timeout
        super().__init__(f"Agent '{agent_name}' exceeded timeout of {timeout}s")


class AgentExecutionError(OrchestratorError):
    """Raised when an agent execution fails."""
    def __init__(self, agent_name: str, original_error: Exception):
        self.agent_name = agent_name
        self.original_error = original_error
        super().__init__(f"Agent '{agent_name}' execution failed: {original_error}")


class IntentClassificationError(OrchestratorError):
    """Raised when intent classification fails."""
    def __init__(self, player_input: str, reason: str):
        self.player_input = player_input
        self.reason = reason
        super().__init__(f"Failed to classify intent for '{player_input}': {reason}")


# ============================================================================
# Orchestrator
# ============================================================================

class Orchestrator:
    """
    Central orchestration engine for the Claudmaster multi-agent AI DM.

    The Orchestrator manages the complete game loop:
    1. Receives player input
    2. Classifies intent (exploration, combat, roleplay, etc.)
    3. Routes to appropriate agents
    4. Executes agents asynchronously with timeout handling
    5. Aggregates responses into coherent narrative
    6. Updates game state and session tracking

    Attributes:
        campaign: The active D&D campaign
        config: Configuration for LLM, agents, and game behavior
        agents: Registry of available agents by name
        session: Current gameplay session (None when not in session)
    """

    def __init__(self, campaign: Campaign, config: ClaudmasterConfig) -> None:
        """
        Initialize the Orchestrator.

        Args:
            campaign: The active D&D campaign to manage
            config: Configuration settings for the AI DM
        """
        self.campaign = campaign
        self.config = config
        self.agents: dict[str, Agent] = {}
        self.session: ClaudmasterSession | None = None

        logger.info(f"Orchestrator initialized for campaign '{campaign.name}'")

    def register_agent(self, name: str, agent: Agent) -> None:
        """
        Register an agent with the orchestrator.

        Args:
            name: Unique name for this agent (e.g., "narrator", "archivist")
            agent: The agent instance to register
        """
        self.agents[name] = agent
        logger.info(f"Registered agent: {name} (role: {agent.role})")

    def unregister_agent(self, name: str) -> None:
        """
        Remove an agent from the orchestrator.

        Args:
            name: Name of the agent to remove

        Raises:
            KeyError: If agent name is not registered
        """
        if name not in self.agents:
            raise KeyError(f"Agent '{name}' is not registered")

        removed_agent = self.agents.pop(name)
        logger.info(f"Unregistered agent: {name} (role: {removed_agent.role})")

    def start_session(self) -> ClaudmasterSession:
        """
        Start a new gameplay session.

        Returns:
            The newly created session

        Raises:
            OrchestratorError: If a session is already active
        """
        if self.session is not None:
            raise OrchestratorError("Session already active. End current session first.")

        self.session = ClaudmasterSession(
            campaign_id=self.campaign.id,
            config=self.config
        )

        # Register all active agents in session
        for agent_name, agent in self.agents.items():
            self.session.set_agent_status(agent_name, "idle")

        logger.info(f"Started session {self.session.session_id} for campaign {self.campaign.name}")
        return self.session

    def end_session(self) -> None:
        """
        End the current gameplay session.

        Raises:
            OrchestratorError: If no session is active
        """
        if self.session is None:
            raise OrchestratorError("No active session to end")

        session_id = self.session.session_id
        turn_count = self.session.turn_count

        self.session = None

        logger.info(f"Ended session {session_id} after {turn_count} turns")

    def classify_intent(self, player_input: str) -> PlayerIntent:
        """
        Classify player input into an intent type using pattern matching.

        This is a simple keyword-based classifier. For production use,
        consider replacing with an LLM-based classifier for better accuracy.

        Args:
            player_input: Raw text from the player

        Returns:
            Classified PlayerIntent with confidence score

        Raises:
            IntentClassificationError: If classification fails
        """
        if not player_input or not player_input.strip():
            raise IntentClassificationError(player_input, "Empty input")

        input_lower = player_input.lower().strip()

        # TODO(human): Define the keyword-to-intent mapping strategy
        # Consider: should keywords be exact match, substring, or regex?
        # Should confidence be binary or weighted by match specificity?
        # Current implementation uses simple substring matching with fixed confidence.
        # Longer patterns are checked first to avoid premature matches.

        intent_patterns: dict[IntentType, list[str]] = {
            IntentType.COMBAT: [
                "roll initiative", "cast spell", "attack", "fight", "strike",
                "rage", "smite", "shoot", "stab", "punch", "kick", "grapple",
                "shove", "initiative", "dodge", "disengage", "cast", "fireball",
                "spell"
            ],
            IntentType.SYSTEM: [
                "character sheet", "long rest", "short rest", "save game",
                "load game", "level up", "inventory", "quit", "exit", "help",
                "status", "stats", "rest", "show", "check"
            ],
            IntentType.EXPLORATION: [
                "perception check", "look", "examine", "search", "investigate",
                "inspect", "peek", "listen", "smell", "touch", "taste",
                "explore", "scout"
            ],
            IntentType.ROLEPLAY: [
                "persuade", "intimidate", "deception", "insight", "talk",
                "speak", "say", "ask", "tell", "chat", "converse",
                "greet", "introduce", "convince", "lie", "bargain"
            ],
            IntentType.QUESTION: [
                "can i", "could i", "would i", "should i", "is there",
                "are there", "do you", "does", "what", "where", "when",
                "who", "why", "how"
            ]
        }

        # Sort keywords by length (longest first) to match specific patterns before generic ones
        for intent_type, keywords in intent_patterns.items():
            sorted_keywords = sorted(keywords, key=len, reverse=True)
            for keyword in sorted_keywords:
                if keyword in input_lower:
                    return PlayerIntent(
                        intent_type=intent_type,
                        confidence=0.8,  # High confidence for keyword match
                        raw_input=player_input,
                        metadata={"matched_keyword": keyword}
                    )

        # Default fallback: classify as ACTION with medium confidence
        logger.debug(f"No pattern match for input '{player_input}', defaulting to ACTION")
        return PlayerIntent(
            intent_type=IntentType.ACTION,
            confidence=0.5,  # Medium confidence for default
            raw_input=player_input,
            metadata={"fallback": True}
        )

    def _get_agents_for_intent(self, intent: PlayerIntent) -> list[Agent]:
        """
        Determine which agents should handle this intent.

        Routing logic:
        - NARRATOR: Always included (provides narrative)
        - ARCHIVIST: Combat, system actions (tracks state, rules)
        - MODULE_KEEPER: Exploration, questions (provides lore, details)
        - CONSISTENCY: Complex roleplay or multi-turn actions (fact checking)

        Args:
            intent: The classified player intent

        Returns:
            List of agents to execute for this intent
        """
        selected_agents: list[Agent] = []

        # Narrator always participates (primary narrative voice)
        narrator = next((a for a in self.agents.values() if a.role == AgentRole.NARRATOR), None)
        if narrator:
            selected_agents.append(narrator)

        # Route based on intent type
        if intent.intent_type == IntentType.COMBAT:
            # Combat needs Archivist for rules and state tracking
            archivist = next((a for a in self.agents.values() if a.role == AgentRole.ARCHIVIST), None)
            if archivist:
                selected_agents.append(archivist)

        elif intent.intent_type == IntentType.EXPLORATION:
            # Exploration benefits from Module Keeper for location details
            module_keeper = next((a for a in self.agents.values() if a.role == AgentRole.MODULE_KEEPER), None)
            if module_keeper:
                selected_agents.append(module_keeper)

        elif intent.intent_type == IntentType.QUESTION:
            # Questions may need Module Keeper for lore lookup
            module_keeper = next((a for a in self.agents.values() if a.role == AgentRole.MODULE_KEEPER), None)
            if module_keeper:
                selected_agents.append(module_keeper)

        elif intent.intent_type == IntentType.ROLEPLAY:
            # Roleplay benefits from Consistency for fact tracking
            consistency = next((a for a in self.agents.values() if a.role == AgentRole.CONSISTENCY), None)
            if consistency:
                selected_agents.append(consistency)

        elif intent.intent_type == IntentType.SYSTEM:
            # System commands need Archivist for state management
            archivist = next((a for a in self.agents.values() if a.role == AgentRole.ARCHIVIST), None)
            if archivist:
                selected_agents.append(archivist)

        # ACTION type gets just Narrator (default handling)

        logger.debug(
            f"Routed intent {intent.intent_type} to agents: "
            f"{[a.name for a in selected_agents]}"
        )

        return selected_agents

    async def process_player_input(self, player_input: str) -> OrchestratorResponse:
        """
        Process player input through the full agent pipeline.

        This is the main orchestration method:
        1. Classify the player's intent
        2. Route to appropriate agents
        3. Execute agents asynchronously with timeout
        4. Aggregate responses into coherent output
        5. Update session state

        Args:
            player_input: Raw text input from the player

        Returns:
            Aggregated orchestrator response

        Raises:
            OrchestratorError: If no session is active
            IntentClassificationError: If intent classification fails
            AgentTimeoutError: If an agent exceeds timeout
            AgentExecutionError: If agent execution fails
        """
        if self.session is None:
            raise OrchestratorError("No active session. Call start_session() first.")

        # Step 1: Classify intent
        logger.info(f"Processing player input: '{player_input}'")
        intent = self.classify_intent(player_input)
        logger.info(f"Classified intent: {intent.intent_type} (confidence: {intent.confidence:.2f})")

        # Add to conversation history
        self.session.add_message("user", player_input)

        # Step 2: Route to agents
        agents_to_run = self._get_agents_for_intent(intent)

        if not agents_to_run:
            logger.warning("No agents available to process input")
            return OrchestratorResponse(
                narrative="(No agents available to process this request)",
                metadata={"error": "no_agents"}
            )

        # Step 3: Execute agents with timeout
        context = self.session.get_context()
        context["player_input"] = player_input
        context["intent"] = intent.model_dump()
        context["game_state"] = self.campaign.game_state.model_dump()

        agent_responses: list[AgentResponse] = []

        for agent in agents_to_run:
            self.session.set_agent_status(agent.name, "working")
            try:
                # Execute agent with timeout
                response = await asyncio.wait_for(
                    agent.run(context),
                    timeout=self.config.agent_timeout
                )
                agent_responses.append(response)
                self.session.set_agent_status(agent.name, "completed")
                logger.info(f"Agent {agent.name} completed successfully")

            except asyncio.TimeoutError:
                self.session.set_agent_status(agent.name, "error")
                error = AgentTimeoutError(agent.name, self.config.agent_timeout)
                logger.error(str(error))
                raise error

            except Exception as e:
                self.session.set_agent_status(agent.name, "error")
                error = AgentExecutionError(agent.name, e)
                logger.error(str(error))
                raise error

        # Step 4: Aggregate responses
        orchestrator_response = self._aggregate_responses(agent_responses)

        # Step 5: Update session
        self.session.add_message("assistant", orchestrator_response.narrative)

        return orchestrator_response

    async def execute_turn(self) -> TurnResult:
        """
        Execute a complete turn with turn tracking.

        This wraps process_player_input with turn counter management
        and creates a complete TurnResult record.

        Note: This method expects player input to already be in the session's
        conversation history. For direct player input, use process_player_input().

        Returns:
            Complete turn result with all metadata

        Raises:
            OrchestratorError: If no session is active
            OrchestratorError: If no recent player input found
        """
        if self.session is None:
            raise OrchestratorError("No active session. Call start_session() first.")

        # Get most recent player input from conversation history
        recent_messages = [
            msg for msg in self.session.conversation_history
            if msg.get("role") == "user"
        ]

        if not recent_messages:
            raise OrchestratorError("No player input found in session history")

        player_input = recent_messages[-1]["content"]

        # Increment turn counter
        turn_number = self.session.increment_turn()
        logger.info(f"Executing turn {turn_number}")

        # Classify intent
        intent = self.classify_intent(player_input)

        # Process input (this will add to conversation history again, but that's OK)
        response = await self.process_player_input(player_input)

        # Create turn result
        turn_result = TurnResult(
            turn_number=turn_number,
            player_input=player_input,
            intent=intent,
            response=response,
            timestamp=datetime.now()
        )

        logger.info(f"Turn {turn_number} completed")
        return turn_result

    def _aggregate_responses(self, responses: list[AgentResponse]) -> OrchestratorResponse:
        """
        Aggregate multiple agent responses into a single coherent response.

        Aggregation strategy:
        - Narrator response becomes primary narrative
        - Other agents contribute to state_changes and metadata
        - All raw agent responses are preserved for debugging

        Args:
            responses: List of agent responses to aggregate

        Returns:
            Aggregated orchestrator response
        """
        if not responses:
            return OrchestratorResponse(
                narrative="(No agent responses to aggregate)",
                metadata={"error": "no_responses"}
            )

        # Find narrator response (primary narrative)
        narrator_response = next(
            (r for r in responses if r.agent_role == AgentRole.NARRATOR),
            None
        )

        if narrator_response and isinstance(narrator_response.action_result, str):
            primary_narrative = narrator_response.action_result
        else:
            # Fallback: use first response or generic message
            primary_narrative = "(Orchestrator: No narrative available)"
            if responses and isinstance(responses[0].action_result, str):
                primary_narrative = responses[0].action_result

        # Collect state changes from all agents
        state_changes: list[dict[str, Any]] = []
        for response in responses:
            if response.agent_role == AgentRole.ARCHIVIST:
                # Archivist manages state, extract changes from observations
                if "state_changes" in response.observations:
                    changes = response.observations["state_changes"]
                    if isinstance(changes, list):
                        state_changes.extend(changes)
                    elif isinstance(changes, dict):
                        state_changes.append(changes)

        # Aggregate metadata
        metadata: dict[str, Any] = {
            "agent_count": len(responses),
            "agents_used": [r.agent_name for r in responses],
            "roles_used": [r.agent_role.value for r in responses]
        }

        return OrchestratorResponse(
            narrative=primary_narrative,
            state_changes=state_changes,
            agent_responses=responses,
            metadata=metadata
        )


__all__ = [
    "IntentType",
    "PlayerIntent",
    "OrchestratorResponse",
    "TurnResult",
    "OrchestratorError",
    "AgentTimeoutError",
    "AgentExecutionError",
    "IntentClassificationError",
    "Orchestrator",
]
