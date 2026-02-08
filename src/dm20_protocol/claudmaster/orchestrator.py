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

from dm20_protocol.models import Campaign, GameState
from .base import Agent, AgentResponse, AgentRole
from .config import ClaudmasterConfig
from .session import ClaudmasterSession

logger = logging.getLogger("dm20-protocol")


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


class WeightedPattern(BaseModel):
    """A phrase pattern with associated weight for intent classification."""
    phrase: str = Field(description="Multi-word phrase to match (lowercased)")
    weight: float = Field(ge=0.0, le=1.0, description="Confidence contribution (0.0-1.0)")


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
# Default Intent Patterns (weighted, multi-word phrases first)
# ============================================================================

DEFAULT_INTENT_PATTERNS: dict[IntentType, list[WeightedPattern]] = {
    IntentType.COMBAT: [
        # Multi-word D&D combat phrases (high weight)
        WeightedPattern(phrase="roll initiative", weight=1.0),
        WeightedPattern(phrase="cast fireball", weight=1.0),
        WeightedPattern(phrase="cast spell", weight=0.9),
        WeightedPattern(phrase="cast eldritch blast", weight=1.0),
        WeightedPattern(phrase="cast magic missile", weight=1.0),
        WeightedPattern(phrase="cast healing word", weight=0.8),
        WeightedPattern(phrase="sneak attack", weight=1.0),
        WeightedPattern(phrase="opportunity attack", weight=1.0),
        # Single combat keywords (medium weight)
        WeightedPattern(phrase="attack", weight=0.8),
        WeightedPattern(phrase="fight", weight=0.8),
        WeightedPattern(phrase="strike", weight=0.7),
        WeightedPattern(phrase="rage", weight=0.8),
        WeightedPattern(phrase="smite", weight=0.9),
        WeightedPattern(phrase="shoot", weight=0.7),
        WeightedPattern(phrase="stab", weight=0.8),
        WeightedPattern(phrase="punch", weight=0.7),
        WeightedPattern(phrase="kick", weight=0.6),
        WeightedPattern(phrase="grapple", weight=0.8),
        WeightedPattern(phrase="shove", weight=0.6),
        WeightedPattern(phrase="dodge", weight=0.7),
        WeightedPattern(phrase="disengage", weight=0.7),
        WeightedPattern(phrase="fireball", weight=0.9),
        # Ambiguous words (low weight — can appear in non-combat contexts)
        WeightedPattern(phrase="cast", weight=0.4),
        WeightedPattern(phrase="spell", weight=0.5),
        WeightedPattern(phrase="initiative", weight=0.6),
    ],
    IntentType.EXPLORATION: [
        # Multi-word exploration phrases (high weight)
        WeightedPattern(phrase="perception check", weight=1.0),
        WeightedPattern(phrase="cast my eyes", weight=0.8),
        WeightedPattern(phrase="look around", weight=0.9),
        WeightedPattern(phrase="search for traps", weight=1.0),
        WeightedPattern(phrase="search for", weight=0.8),
        # Single exploration keywords (medium weight)
        WeightedPattern(phrase="look", weight=0.7),
        WeightedPattern(phrase="examine", weight=0.8),
        WeightedPattern(phrase="search", weight=0.7),
        WeightedPattern(phrase="investigate", weight=0.8),
        WeightedPattern(phrase="inspect", weight=0.8),
        WeightedPattern(phrase="peek", weight=0.7),
        WeightedPattern(phrase="listen", weight=0.7),
        WeightedPattern(phrase="smell", weight=0.6),
        WeightedPattern(phrase="touch", weight=0.5),
        WeightedPattern(phrase="taste", weight=0.5),
        WeightedPattern(phrase="explore", weight=0.8),
        WeightedPattern(phrase="scout", weight=0.8),
    ],
    IntentType.ROLEPLAY: [
        # Multi-word roleplay phrases
        WeightedPattern(phrase="introduce myself", weight=0.9),
        WeightedPattern(phrase="talk to", weight=0.8),
        WeightedPattern(phrase="speak with", weight=0.8),
        WeightedPattern(phrase="try to persuade", weight=1.0),
        WeightedPattern(phrase="try to intimidate", weight=1.0),
        # Single roleplay keywords
        WeightedPattern(phrase="persuade", weight=0.8),
        WeightedPattern(phrase="intimidate", weight=0.8),
        WeightedPattern(phrase="deception", weight=0.8),
        WeightedPattern(phrase="insight", weight=0.7),
        WeightedPattern(phrase="talk", weight=0.6),
        WeightedPattern(phrase="speak", weight=0.6),
        WeightedPattern(phrase="say", weight=0.5),
        WeightedPattern(phrase="ask", weight=0.5),
        WeightedPattern(phrase="tell", weight=0.5),
        WeightedPattern(phrase="chat", weight=0.6),
        WeightedPattern(phrase="converse", weight=0.7),
        WeightedPattern(phrase="greet", weight=0.6),
        WeightedPattern(phrase="convince", weight=0.8),
        WeightedPattern(phrase="lie", weight=0.6),
        WeightedPattern(phrase="bargain", weight=0.7),
    ],
    IntentType.QUESTION: [
        # Multi-word question starters
        WeightedPattern(phrase="can i", weight=0.7),
        WeightedPattern(phrase="could i", weight=0.7),
        WeightedPattern(phrase="would i", weight=0.7),
        WeightedPattern(phrase="should i", weight=0.7),
        WeightedPattern(phrase="is there", weight=0.7),
        WeightedPattern(phrase="are there", weight=0.7),
        WeightedPattern(phrase="do you", weight=0.6),
        # Single question keywords
        WeightedPattern(phrase="does", weight=0.5),
        WeightedPattern(phrase="what", weight=0.6),
        WeightedPattern(phrase="where", weight=0.6),
        WeightedPattern(phrase="when", weight=0.5),
        WeightedPattern(phrase="who", weight=0.6),
        WeightedPattern(phrase="why", weight=0.5),
        WeightedPattern(phrase="how", weight=0.5),
    ],
    IntentType.SYSTEM: [
        # Multi-word system phrases (high weight)
        WeightedPattern(phrase="character sheet", weight=1.0),
        WeightedPattern(phrase="long rest", weight=1.0),
        WeightedPattern(phrase="short rest", weight=1.0),
        WeightedPattern(phrase="save game", weight=1.0),
        WeightedPattern(phrase="load game", weight=1.0),
        WeightedPattern(phrase="level up", weight=1.0),
        # Single system keywords (medium weight)
        WeightedPattern(phrase="inventory", weight=0.8),
        WeightedPattern(phrase="quit", weight=0.9),
        WeightedPattern(phrase="exit", weight=0.9),
        WeightedPattern(phrase="help", weight=0.7),
        WeightedPattern(phrase="status", weight=0.7),
        WeightedPattern(phrase="stats", weight=0.8),
        WeightedPattern(phrase="rest", weight=0.6),
        WeightedPattern(phrase="show", weight=0.5),
        WeightedPattern(phrase="check", weight=0.4),
    ],
    IntentType.ACTION: [
        # General action phrases (low weight, catch-all category)
        WeightedPattern(phrase="i try to", weight=0.5),
        WeightedPattern(phrase="i attempt to", weight=0.5),
        WeightedPattern(phrase="i want to", weight=0.4),
        WeightedPattern(phrase="open", weight=0.4),
        WeightedPattern(phrase="close", weight=0.4),
        WeightedPattern(phrase="use", weight=0.4),
        WeightedPattern(phrase="take", weight=0.4),
        WeightedPattern(phrase="drop", weight=0.4),
        WeightedPattern(phrase="move", weight=0.4),
        WeightedPattern(phrase="go", weight=0.3),
        WeightedPattern(phrase="run", weight=0.4),
        WeightedPattern(phrase="jump", weight=0.5),
        WeightedPattern(phrase="climb", weight=0.5),
        WeightedPattern(phrase="swim", weight=0.5),
    ],
}


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

    def _get_intent_patterns(self) -> dict[IntentType, list[WeightedPattern]]:
        """
        Build the intent patterns dict by merging defaults with config overrides.

        Config overrides in ``self.config.intent_weight_overrides`` use
        string keys (e.g. ``{"combat": {"attack": 0.9}}``).  For each
        override entry the matching default pattern weight is replaced,
        or a new pattern is appended.

        Returns:
            Merged intent pattern mapping.
        """
        import copy
        patterns = copy.deepcopy(DEFAULT_INTENT_PATTERNS)

        for intent_key, phrase_overrides in self.config.intent_weight_overrides.items():
            try:
                intent_type = IntentType(intent_key)
            except ValueError:
                logger.warning(f"Unknown intent type in overrides: {intent_key}")
                continue

            existing = patterns.setdefault(intent_type, [])
            existing_phrases = {p.phrase: p for p in existing}

            for phrase, weight in phrase_overrides.items():
                phrase_lower = phrase.lower()
                if phrase_lower in existing_phrases:
                    existing_phrases[phrase_lower].weight = weight
                else:
                    existing.append(WeightedPattern(phrase=phrase_lower, weight=weight))

        return patterns

    def classify_intent(self, player_input: str) -> PlayerIntent:
        """
        Classify player input into an intent type using weighted pattern scoring.

        For each IntentType, patterns are matched against the input and their
        weights are accumulated.  The intent with the highest total score wins.
        If the gap between the top two scores is below ``ambiguity_threshold``,
        the result is flagged as ambiguous via metadata.

        Args:
            player_input: Raw text from the player

        Returns:
            Classified PlayerIntent with confidence score and scoring metadata

        Raises:
            IntentClassificationError: If classification fails
        """
        if not player_input or not player_input.strip():
            raise IntentClassificationError(player_input, "Empty input")

        input_lower = player_input.lower().strip()

        intent_patterns = self._get_intent_patterns()
        ambiguity_threshold = self.config.ambiguity_threshold

        # Step A: Score accumulation — match patterns and accumulate weights
        scores: dict[IntentType, float] = {}
        best_weights: dict[IntentType, float] = {}
        all_matched: dict[IntentType, list[str]] = {}

        for intent_type, patterns in intent_patterns.items():
            sorted_patterns = sorted(patterns, key=lambda p: len(p.phrase), reverse=True)
            total = 0.0
            best = 0.0
            matched: list[str] = []
            for p in sorted_patterns:
                if p.phrase in input_lower:
                    total += p.weight
                    best = max(best, p.weight)
                    matched.append(p.phrase)
            if total > 0:
                scores[intent_type] = total
                best_weights[intent_type] = best
                all_matched[intent_type] = matched

        # Step B: No matches → fallback to ACTION
        if not scores:
            logger.debug(f"No pattern match for input '{player_input}', defaulting to ACTION")
            return PlayerIntent(
                intent_type=IntentType.ACTION,
                confidence=self.config.fallback_confidence,
                raw_input=player_input,
                metadata={"fallback": True},
            )

        # Step C: Find winner and runner-up, check ambiguity
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        winner_type, winner_score = ranked[0]
        runner_up_type, runner_up_score = ranked[1] if len(ranked) > 1 else (None, 0.0)

        score_gap = winner_score - runner_up_score
        metadata: dict[str, Any] = {
            "matched_patterns": all_matched.get(winner_type, []),
            "scores": {k.value: v for k, v in scores.items()},
        }
        if runner_up_type is not None and score_gap < ambiguity_threshold:
            metadata["ambiguous"] = True
            metadata["alternative_intent"] = runner_up_type.value
            metadata["score_gap"] = score_gap

        # Step D: Return intent — confidence = best individual weight of winner
        return PlayerIntent(
            intent_type=winner_type,
            confidence=min(best_weights[winner_type], 1.0),
            raw_input=player_input,
            metadata=metadata,
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

        if intent.metadata.get("ambiguous"):
            logger.warning(
                f"Ambiguous intent: {intent.intent_type} vs "
                f"{intent.metadata.get('alternative_intent')}"
            )

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
    "WeightedPattern",
    "DEFAULT_INTENT_PATTERNS",
    "OrchestratorResponse",
    "TurnResult",
    "OrchestratorError",
    "AgentTimeoutError",
    "AgentExecutionError",
    "IntentClassificationError",
    "Orchestrator",
]
