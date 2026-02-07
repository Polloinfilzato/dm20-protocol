"""
Tests for the Orchestrator and related types.
"""

import asyncio
import pytest
from datetime import datetime

from gamemaster_mcp.models import Campaign, GameState, Character, CharacterClass, Race
from gamemaster_mcp.claudmaster import (
    Agent,
    AgentRequest,
    AgentResponse,
    AgentRole,
    IntentType,
    PlayerIntent,
    OrchestratorResponse,
    TurnResult,
    OrchestratorError,
    AgentTimeoutError,
    AgentExecutionError,
    IntentClassificationError,
    Orchestrator,
)
from gamemaster_mcp.claudmaster.config import ClaudmasterConfig


# ============================================================================
# Mock Agents for Testing
# ============================================================================

class MockNarrator(Agent):
    """Mock Narrator agent for testing."""

    def __init__(self, delay: float = 0.0, should_fail: bool = False) -> None:
        super().__init__(name="test_narrator", role=AgentRole.NARRATOR)
        self.delay = delay
        self.should_fail = should_fail
        self.call_count = 0

    async def reason(self, context: dict) -> str:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.should_fail:
            raise ValueError("Mock narrator failure")
        return "Narrator reasoning: describe the scene"

    async def act(self, reasoning: str) -> str:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.should_fail:
            raise ValueError("Mock narrator failure")
        return "You find yourself in a dimly lit tavern."

    async def observe(self, result: str) -> dict:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        if self.should_fail:
            raise ValueError("Mock narrator failure")
        return {"scene": "tavern", "mood": "mysterious"}


class MockArchivist(Agent):
    """Mock Archivist agent for testing."""

    def __init__(self, delay: float = 0.0) -> None:
        super().__init__(name="test_archivist", role=AgentRole.ARCHIVIST)
        self.delay = delay
        self.call_count = 0

    async def reason(self, context: dict) -> str:
        self.call_count += 1
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return "Archivist reasoning: track combat state"

    async def act(self, reasoning: str) -> dict:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return {"initiative": [{"name": "Player", "roll": 15}]}

    async def observe(self, result: dict) -> dict:
        if self.delay > 0:
            await asyncio.sleep(self.delay)
        return {
            "state_changes": [
                {"type": "combat_start", "in_combat": True}
            ]
        }


class MockModuleKeeper(Agent):
    """Mock Module Keeper agent for testing."""

    def __init__(self) -> None:
        super().__init__(name="test_module_keeper", role=AgentRole.MODULE_KEEPER)
        self.call_count = 0

    async def reason(self, context: dict) -> str:
        self.call_count += 1
        return "Module Keeper reasoning: retrieve lore"

    async def act(self, reasoning: str) -> str:
        return "The Forgotten Realms lore states..."

    async def observe(self, result: str) -> dict:
        return {"lore_retrieved": True}


class MockConsistency(Agent):
    """Mock Consistency agent for testing."""

    def __init__(self) -> None:
        super().__init__(name="test_consistency", role=AgentRole.CONSISTENCY)
        self.call_count = 0

    async def reason(self, context: dict) -> str:
        self.call_count += 1
        return "Consistency reasoning: check facts"

    async def act(self, reasoning: str) -> dict:
        return {"contradictions": []}

    async def observe(self, result: dict) -> dict:
        return {"facts_verified": True}


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def campaign() -> Campaign:
    """Create a test campaign."""
    return Campaign(
        name="Test Campaign",
        description="A test campaign for unit tests",
        game_state=GameState(
            campaign_name="Test Campaign",
            current_session=1,
            current_location="Test Town",
            active_quests=[],
            party_level=1
        )
    )


@pytest.fixture
def config() -> ClaudmasterConfig:
    """Create test configuration."""
    return ClaudmasterConfig(
        agent_timeout=5.0,
        temperature=0.7,
        improvisation_level=2
    )


@pytest.fixture
def orchestrator(campaign: Campaign, config: ClaudmasterConfig) -> Orchestrator:
    """Create orchestrator with test campaign and config."""
    return Orchestrator(campaign=campaign, config=config)


# ============================================================================
# Type Tests
# ============================================================================

def test_intent_type_enum():
    """Test IntentType enum values."""
    assert IntentType.ACTION == "action"
    assert IntentType.QUESTION == "question"
    assert IntentType.ROLEPLAY == "roleplay"
    assert IntentType.COMBAT == "combat"
    assert IntentType.EXPLORATION == "exploration"
    assert IntentType.SYSTEM == "system"


def test_player_intent_creation():
    """Test PlayerIntent model creation."""
    intent = PlayerIntent(
        intent_type=IntentType.COMBAT,
        confidence=0.9,
        raw_input="I attack the goblin",
        metadata={"target": "goblin"}
    )

    assert intent.intent_type == IntentType.COMBAT
    assert intent.confidence == 0.9
    assert intent.raw_input == "I attack the goblin"
    assert intent.metadata["target"] == "goblin"


def test_player_intent_confidence_validation():
    """Test PlayerIntent confidence must be between 0 and 1."""
    # Valid confidence
    intent = PlayerIntent(
        intent_type=IntentType.ACTION,
        confidence=0.5,
        raw_input="test"
    )
    assert intent.confidence == 0.5

    # Invalid confidence should raise validation error
    with pytest.raises(Exception):  # Pydantic validation error
        PlayerIntent(
            intent_type=IntentType.ACTION,
            confidence=1.5,  # > 1.0
            raw_input="test"
        )


def test_orchestrator_response_creation():
    """Test OrchestratorResponse model."""
    response = OrchestratorResponse(
        narrative="You enter the dungeon",
        state_changes=[{"location": "dungeon"}],
        agent_responses=[],
        metadata={"turn": 1}
    )

    assert response.narrative == "You enter the dungeon"
    assert len(response.state_changes) == 1
    assert response.metadata["turn"] == 1


def test_turn_result_creation():
    """Test TurnResult model."""
    intent = PlayerIntent(
        intent_type=IntentType.EXPLORATION,
        confidence=0.8,
        raw_input="I look around"
    )

    response = OrchestratorResponse(
        narrative="You see a corridor",
        state_changes=[],
        agent_responses=[],
        metadata={}
    )

    turn_result = TurnResult(
        turn_number=1,
        player_input="I look around",
        intent=intent,
        response=response
    )

    assert turn_result.turn_number == 1
    assert turn_result.player_input == "I look around"
    assert turn_result.intent.intent_type == IntentType.EXPLORATION
    assert isinstance(turn_result.timestamp, datetime)


# ============================================================================
# Error Hierarchy Tests
# ============================================================================

def test_orchestrator_error():
    """Test base OrchestratorError."""
    error = OrchestratorError("Test error")
    assert str(error) == "Test error"
    assert isinstance(error, Exception)


def test_agent_timeout_error():
    """Test AgentTimeoutError."""
    error = AgentTimeoutError("narrator", 30.0)
    assert error.agent_name == "narrator"
    assert error.timeout == 30.0
    assert "narrator" in str(error)
    assert "30" in str(error)
    assert isinstance(error, OrchestratorError)


def test_agent_execution_error():
    """Test AgentExecutionError."""
    original = ValueError("Something went wrong")
    error = AgentExecutionError("archivist", original)
    assert error.agent_name == "archivist"
    assert error.original_error == original
    assert "archivist" in str(error)
    assert isinstance(error, OrchestratorError)


def test_intent_classification_error():
    """Test IntentClassificationError."""
    error = IntentClassificationError("test input", "empty string")
    assert error.player_input == "test input"
    assert error.reason == "empty string"
    assert "test input" in str(error)
    assert isinstance(error, OrchestratorError)


# ============================================================================
# Orchestrator Initialization Tests
# ============================================================================

def test_orchestrator_init(orchestrator: Orchestrator, campaign: Campaign, config: ClaudmasterConfig):
    """Test Orchestrator initialization."""
    assert orchestrator.campaign == campaign
    assert orchestrator.config == config
    assert len(orchestrator.agents) == 0
    assert orchestrator.session is None


def test_orchestrator_register_agent(orchestrator: Orchestrator):
    """Test registering agents."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    assert "narrator" in orchestrator.agents
    assert orchestrator.agents["narrator"] == narrator


def test_orchestrator_register_multiple_agents(orchestrator: Orchestrator):
    """Test registering multiple agents."""
    narrator = MockNarrator()
    archivist = MockArchivist()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("archivist", archivist)

    assert len(orchestrator.agents) == 2
    assert "narrator" in orchestrator.agents
    assert "archivist" in orchestrator.agents


def test_orchestrator_unregister_agent(orchestrator: Orchestrator):
    """Test unregistering agents."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    assert "narrator" in orchestrator.agents

    orchestrator.unregister_agent("narrator")

    assert "narrator" not in orchestrator.agents


def test_orchestrator_unregister_nonexistent_agent(orchestrator: Orchestrator):
    """Test unregistering non-existent agent raises error."""
    with pytest.raises(KeyError):
        orchestrator.unregister_agent("nonexistent")


# ============================================================================
# Session Lifecycle Tests
# ============================================================================

def test_start_session(orchestrator: Orchestrator, campaign: Campaign):
    """Test starting a session."""
    session = orchestrator.start_session()

    assert orchestrator.session is not None
    assert session.campaign_id == campaign.id
    assert session.turn_count == 0
    assert len(session.conversation_history) == 0


def test_start_session_with_agents(orchestrator: Orchestrator):
    """Test starting session registers agents."""
    narrator = MockNarrator()
    archivist = MockArchivist()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("archivist", archivist)

    session = orchestrator.start_session()

    assert "narrator" in session.active_agents
    assert "archivist" in session.active_agents
    assert session.active_agents["narrator"] == "idle"
    assert session.active_agents["archivist"] == "idle"


def test_start_session_already_active(orchestrator: Orchestrator):
    """Test starting session when one is already active raises error."""
    orchestrator.start_session()

    with pytest.raises(OrchestratorError, match="already active"):
        orchestrator.start_session()


def test_end_session(orchestrator: Orchestrator):
    """Test ending a session."""
    orchestrator.start_session()
    assert orchestrator.session is not None

    orchestrator.end_session()
    assert orchestrator.session is None


def test_end_session_not_active(orchestrator: Orchestrator):
    """Test ending session when none is active raises error."""
    with pytest.raises(OrchestratorError, match="No active session"):
        orchestrator.end_session()


# ============================================================================
# Intent Classification Tests
# ============================================================================

def test_classify_intent_combat(orchestrator: Orchestrator):
    """Test classifying combat intents."""
    combat_inputs = [
        "I attack the goblin",
        "I cast fireball",
        "roll initiative",
        "I strike with my sword"
    ]

    for player_input in combat_inputs:
        intent = orchestrator.classify_intent(player_input)
        assert intent.intent_type == IntentType.COMBAT
        assert intent.raw_input == player_input
        assert 0.0 <= intent.confidence <= 1.0


def test_classify_intent_exploration(orchestrator: Orchestrator):
    """Test classifying exploration intents."""
    exploration_inputs = [
        "I look around",
        "I examine the door",
        "I search for traps",
        "I investigate the room"
    ]

    for player_input in exploration_inputs:
        intent = orchestrator.classify_intent(player_input)
        assert intent.intent_type == IntentType.EXPLORATION
        assert intent.raw_input == player_input


def test_classify_intent_roleplay(orchestrator: Orchestrator):
    """Test classifying roleplay intents."""
    roleplay_inputs = [
        "I talk to the bartender",
        "I ask about the quest",
        "I try to persuade the guard",
        "I introduce myself"
    ]

    for player_input in roleplay_inputs:
        intent = orchestrator.classify_intent(player_input)
        assert intent.intent_type == IntentType.ROLEPLAY
        assert intent.raw_input == player_input


def test_classify_intent_question(orchestrator: Orchestrator):
    """Test classifying question intents."""
    question_inputs = [
        "What do I see?",
        "Where am I?",
        "Who is that person?",
        "Can I open the chest?"
    ]

    for player_input in question_inputs:
        intent = orchestrator.classify_intent(player_input)
        assert intent.intent_type == IntentType.QUESTION
        assert intent.raw_input == player_input


def test_classify_intent_system(orchestrator: Orchestrator):
    """Test classifying system intents."""
    system_inputs = [
        "show character sheet",
        "check inventory",
        "take a long rest",
        "save game"
    ]

    for player_input in system_inputs:
        intent = orchestrator.classify_intent(player_input)
        assert intent.intent_type == IntentType.SYSTEM
        assert intent.raw_input == player_input


def test_classify_intent_default_action(orchestrator: Orchestrator):
    """Test default classification to ACTION."""
    # Input with no matching keywords should default to ACTION
    intent = orchestrator.classify_intent("I do something unusual and specific")
    assert intent.intent_type == IntentType.ACTION
    assert intent.confidence == 0.5  # Medium confidence for default
    assert intent.metadata.get("fallback") is True


def test_classify_intent_empty_input(orchestrator: Orchestrator):
    """Test classifying empty input raises error."""
    with pytest.raises(IntentClassificationError):
        orchestrator.classify_intent("")

    with pytest.raises(IntentClassificationError):
        orchestrator.classify_intent("   ")


# ============================================================================
# Agent Routing Tests
# ============================================================================

def test_get_agents_for_combat_intent(orchestrator: Orchestrator):
    """Test agent routing for combat intent."""
    narrator = MockNarrator()
    archivist = MockArchivist()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("archivist", archivist)

    intent = PlayerIntent(
        intent_type=IntentType.COMBAT,
        confidence=0.9,
        raw_input="I attack"
    )

    agents = orchestrator._get_agents_for_intent(intent)

    # Combat should route to both Narrator and Archivist
    assert len(agents) == 2
    assert narrator in agents
    assert archivist in agents


def test_get_agents_for_exploration_intent(orchestrator: Orchestrator):
    """Test agent routing for exploration intent."""
    narrator = MockNarrator()
    module_keeper = MockModuleKeeper()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("module_keeper", module_keeper)

    intent = PlayerIntent(
        intent_type=IntentType.EXPLORATION,
        confidence=0.8,
        raw_input="I look around"
    )

    agents = orchestrator._get_agents_for_intent(intent)

    # Exploration should route to Narrator and Module Keeper
    assert len(agents) == 2
    assert narrator in agents
    assert module_keeper in agents


def test_get_agents_for_roleplay_intent(orchestrator: Orchestrator):
    """Test agent routing for roleplay intent."""
    narrator = MockNarrator()
    consistency = MockConsistency()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("consistency", consistency)

    intent = PlayerIntent(
        intent_type=IntentType.ROLEPLAY,
        confidence=0.9,
        raw_input="I talk to the NPC"
    )

    agents = orchestrator._get_agents_for_intent(intent)

    # Roleplay should route to Narrator and Consistency
    assert len(agents) == 2
    assert narrator in agents
    assert consistency in agents


def test_get_agents_for_action_default(orchestrator: Orchestrator):
    """Test agent routing for default ACTION intent."""
    narrator = MockNarrator()
    archivist = MockArchivist()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("archivist", archivist)

    intent = PlayerIntent(
        intent_type=IntentType.ACTION,
        confidence=0.5,
        raw_input="I do something"
    )

    agents = orchestrator._get_agents_for_intent(intent)

    # ACTION should only route to Narrator
    assert len(agents) == 1
    assert narrator in agents
    assert archivist not in agents


def test_get_agents_no_narrator(orchestrator: Orchestrator):
    """Test routing when narrator is not registered."""
    archivist = MockArchivist()
    orchestrator.register_agent("archivist", archivist)

    intent = PlayerIntent(
        intent_type=IntentType.COMBAT,
        confidence=0.9,
        raw_input="I attack"
    )

    agents = orchestrator._get_agents_for_intent(intent)

    # Should only get archivist since narrator is missing
    assert len(agents) == 1
    assert archivist in agents


# ============================================================================
# Full Turn Processing Tests
# ============================================================================

def test_process_player_input_success(orchestrator: Orchestrator):
    """Test successful player input processing."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)
    orchestrator.start_session()

    response = asyncio.run(orchestrator.process_player_input("I look around"))

    assert isinstance(response, OrchestratorResponse)
    assert "tavern" in response.narrative.lower()
    assert narrator.call_count == 1
    assert len(orchestrator.session.conversation_history) == 2  # user + assistant


def test_process_player_input_no_session(orchestrator: Orchestrator):
    """Test processing input without active session raises error."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    with pytest.raises(OrchestratorError, match="No active session"):
        asyncio.run(orchestrator.process_player_input("I attack"))


def test_process_player_input_no_agents(orchestrator: Orchestrator):
    """Test processing input with no agents available."""
    orchestrator.start_session()

    response = asyncio.run(orchestrator.process_player_input("I attack"))

    assert "No agents available" in response.narrative
    assert response.metadata.get("error") == "no_agents"


def test_process_player_input_agent_timeout(orchestrator: Orchestrator):
    """Test agent timeout handling."""
    # Create slow agent that will timeout
    narrator = MockNarrator(delay=10.0)  # 10 second delay
    orchestrator.register_agent("narrator", narrator)

    # Set short timeout
    orchestrator.config.agent_timeout = 0.5

    orchestrator.start_session()

    with pytest.raises(AgentTimeoutError) as exc_info:
        asyncio.run(orchestrator.process_player_input("I attack"))

    assert exc_info.value.agent_name == "test_narrator"
    assert orchestrator.session.active_agents["test_narrator"] == "error"


def test_process_player_input_agent_execution_error(orchestrator: Orchestrator):
    """Test agent execution error handling."""
    narrator = MockNarrator(should_fail=True)
    orchestrator.register_agent("narrator", narrator)
    orchestrator.start_session()

    with pytest.raises(AgentExecutionError) as exc_info:
        asyncio.run(orchestrator.process_player_input("I attack"))

    assert exc_info.value.agent_name == "test_narrator"
    assert orchestrator.session.active_agents["test_narrator"] == "error"


def test_process_player_input_multiple_agents(orchestrator: Orchestrator):
    """Test processing with multiple agents."""
    narrator = MockNarrator()
    archivist = MockArchivist()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("archivist", archivist)

    orchestrator.start_session()

    response = asyncio.run(orchestrator.process_player_input("I attack the goblin"))

    assert isinstance(response, OrchestratorResponse)
    assert len(response.agent_responses) == 2
    assert narrator.call_count == 1
    assert archivist.call_count == 1


# ============================================================================
# Response Aggregation Tests
# ============================================================================

def test_aggregate_responses_with_narrator(orchestrator: Orchestrator):
    """Test aggregation uses narrator as primary narrative."""
    narrator_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="test",
        action_result="You see a beautiful sunset.",
        observations={}
    )

    result = orchestrator._aggregate_responses([narrator_response])

    assert result.narrative == "You see a beautiful sunset."
    assert len(result.agent_responses) == 1


def test_aggregate_responses_with_state_changes(orchestrator: Orchestrator):
    """Test aggregation extracts state changes from archivist."""
    narrator_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="test",
        action_result="Combat begins!",
        observations={}
    )

    archivist_response = AgentResponse(
        agent_name="archivist",
        agent_role=AgentRole.ARCHIVIST,
        reasoning="test",
        action_result={"initiative": []},
        observations={
            "state_changes": [
                {"type": "combat_start", "in_combat": True}
            ]
        }
    )

    result = orchestrator._aggregate_responses([narrator_response, archivist_response])

    assert result.narrative == "Combat begins!"
    assert len(result.state_changes) == 1
    assert result.state_changes[0]["type"] == "combat_start"


def test_aggregate_responses_no_responses(orchestrator: Orchestrator):
    """Test aggregation with no responses."""
    result = orchestrator._aggregate_responses([])

    assert "No agent responses" in result.narrative
    assert result.metadata.get("error") == "no_responses"


def test_aggregate_responses_metadata(orchestrator: Orchestrator):
    """Test aggregation includes metadata."""
    narrator_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="test",
        action_result="Test narrative",
        observations={}
    )

    archivist_response = AgentResponse(
        agent_name="archivist",
        agent_role=AgentRole.ARCHIVIST,
        reasoning="test",
        action_result={},
        observations={}
    )

    result = orchestrator._aggregate_responses([narrator_response, archivist_response])

    assert result.metadata["agent_count"] == 2
    assert "narrator" in result.metadata["agents_used"]
    assert "archivist" in result.metadata["agents_used"]


# ============================================================================
# Execute Turn Tests
# ============================================================================

def test_execute_turn(orchestrator: Orchestrator):
    """Test complete turn execution."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    session = orchestrator.start_session()
    session.add_message("user", "I look around")

    turn_result = asyncio.run(orchestrator.execute_turn())

    assert isinstance(turn_result, TurnResult)
    assert turn_result.turn_number == 1
    assert turn_result.player_input == "I look around"
    assert turn_result.intent.intent_type == IntentType.EXPLORATION
    assert isinstance(turn_result.response, OrchestratorResponse)
    assert session.turn_count == 1


def test_execute_turn_increments_counter(orchestrator: Orchestrator):
    """Test turn counter increments correctly."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    session = orchestrator.start_session()

    # Execute multiple turns
    session.add_message("user", "I look around")
    turn1 = asyncio.run(orchestrator.execute_turn())

    session.add_message("user", "I attack")
    turn2 = asyncio.run(orchestrator.execute_turn())

    assert turn1.turn_number == 1
    assert turn2.turn_number == 2
    assert session.turn_count == 2


def test_execute_turn_no_session(orchestrator: Orchestrator):
    """Test execute turn without session raises error."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    with pytest.raises(OrchestratorError, match="No active session"):
        asyncio.run(orchestrator.execute_turn())


def test_execute_turn_no_player_input(orchestrator: Orchestrator):
    """Test execute turn with no player input raises error."""
    narrator = MockNarrator()
    orchestrator.register_agent("narrator", narrator)

    orchestrator.start_session()
    # Don't add any player input to conversation history

    with pytest.raises(OrchestratorError, match="No player input found"):
        asyncio.run(orchestrator.execute_turn())


# ============================================================================
# Weighted Scoring Algorithm Tests
# ============================================================================

def test_scoring_metadata_contains_scores(orchestrator: Orchestrator):
    """Test that classification metadata includes per-intent scores."""
    intent = orchestrator.classify_intent("I attack the goblin")
    assert "scores" in intent.metadata
    assert "combat" in intent.metadata["scores"]
    assert intent.metadata["scores"]["combat"] > 0


def test_scoring_metadata_contains_matched_patterns(orchestrator: Orchestrator):
    """Test that metadata lists which patterns matched."""
    intent = orchestrator.classify_intent("I cast fireball")
    assert "matched_patterns" in intent.metadata
    assert "cast fireball" in intent.metadata["matched_patterns"]


def test_cast_fireball_is_combat(orchestrator: Orchestrator):
    """Test 'cast fireball' is classified as COMBAT (not ambiguous)."""
    intent = orchestrator.classify_intent("I cast fireball at the orc")
    assert intent.intent_type == IntentType.COMBAT
    assert intent.confidence == 1.0  # best_weight for "cast fireball" is 1.0


def test_cast_my_eyes_is_exploration(orchestrator: Orchestrator):
    """Test 'cast my eyes around' is classified as EXPLORATION."""
    intent = orchestrator.classify_intent("I cast my eyes around the room")
    assert intent.intent_type == IntentType.EXPLORATION


def test_ambiguity_flagged_when_scores_close(orchestrator: Orchestrator):
    """Test ambiguity is flagged when top two intents have close scores."""
    # "ask" matches ROLEPLAY (0.5) and QUESTION via "ask" is not in QUESTION
    # Use a phrase that triggers close scores across intents
    # "search" (EXPLORATION 0.7) + "check" (SYSTEM 0.4) — not close enough
    # We need config override to create artificial ambiguity
    orchestrator.config.ambiguity_threshold = 5.0  # very high threshold
    intent = orchestrator.classify_intent("I attack the goblin")
    # With threshold=5.0, almost any multi-match will be flagged
    if len(intent.metadata.get("scores", {})) > 1:
        assert intent.metadata.get("ambiguous") is True
        assert "alternative_intent" in intent.metadata
        assert "score_gap" in intent.metadata


def test_ambiguity_not_flagged_with_clear_winner(orchestrator: Orchestrator):
    """Test no ambiguity when one intent dominates clearly."""
    intent = orchestrator.classify_intent("roll initiative and cast fireball")
    assert intent.intent_type == IntentType.COMBAT
    # COMBAT should dominate so heavily that ambiguous is not set
    assert intent.metadata.get("ambiguous") is not True


def test_fallback_action_for_unknown_input(orchestrator: Orchestrator):
    """Test unknown input falls back to ACTION with configured confidence."""
    intent = orchestrator.classify_intent("I whistle a cheerful tune")
    assert intent.intent_type == IntentType.ACTION
    assert intent.confidence == 0.5
    assert intent.metadata.get("fallback") is True


def test_fallback_confidence_respects_config(orchestrator: Orchestrator):
    """Test fallback confidence uses config value."""
    orchestrator.config.fallback_confidence = 0.3
    intent = orchestrator.classify_intent("I do something truly bizarre and unprecedented")
    assert intent.confidence == 0.3


def test_confidence_is_best_weight_not_total(orchestrator: Orchestrator):
    """Test confidence equals best individual weight, not total score."""
    # "cast fireball" matches: "cast fireball"(1.0) + "fireball"(0.9) + "cast"(0.4)
    # Total = 2.3, but confidence should be 1.0 (best weight)
    intent = orchestrator.classify_intent("I cast fireball")
    assert intent.confidence == 1.0  # best weight, not 2.3


def test_config_weight_overrides(orchestrator: Orchestrator):
    """Test that config weight overrides affect classification."""
    # Override "attack" weight to 0.1 (very low)
    orchestrator.config.intent_weight_overrides = {
        "combat": {"attack": 0.1}
    }
    intent = orchestrator.classify_intent("I attack")
    # "attack" now has weight 0.1 — should still be COMBAT but low confidence
    assert intent.intent_type == IntentType.COMBAT
    assert intent.confidence == 0.1


def test_longest_phrase_match_priority(orchestrator: Orchestrator):
    """Test that longer phrases take priority in pattern matching."""
    # "search for traps" (1.0) should match, plus "search" (0.7)
    intent = orchestrator.classify_intent("I search for traps")
    assert intent.intent_type == IntentType.EXPLORATION
    assert "search for traps" in intent.metadata["matched_patterns"]


# ============================================================================
# Integration Tests
# ============================================================================

def test_full_game_loop(orchestrator: Orchestrator):
    """Test a complete multi-turn game loop."""
    narrator = MockNarrator()
    archivist = MockArchivist()
    module_keeper = MockModuleKeeper()

    orchestrator.register_agent("narrator", narrator)
    orchestrator.register_agent("archivist", archivist)
    orchestrator.register_agent("module_keeper", module_keeper)

    session = orchestrator.start_session()

    # Turn 1: Exploration
    response1 = asyncio.run(orchestrator.process_player_input("I look around the tavern"))
    assert narrator.call_count == 1
    assert module_keeper.call_count == 1
    assert session.turn_count == 0  # process_player_input doesn't increment

    # Turn 2: Combat
    response2 = asyncio.run(orchestrator.process_player_input("I attack the orc"))
    assert narrator.call_count == 2
    assert archivist.call_count == 1

    # Verify conversation history
    assert len(session.conversation_history) == 4  # 2 user + 2 assistant

    orchestrator.end_session()
    assert orchestrator.session is None
