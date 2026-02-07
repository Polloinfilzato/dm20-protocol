"""
Tests for action_tools module.

This module tests the player_action MCP tool and its supporting components.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from gamemaster_mcp.claudmaster.tools.action_tools import (
    DiceRoll,
    NPCResponse,
    StateChange,
    ActionType,
    ActionResponse,
    ActionProcessor,
    player_action,
)
from gamemaster_mcp.claudmaster.orchestrator import (
    IntentType,
    PlayerIntent,
    OrchestratorResponse,
)
from gamemaster_mcp.claudmaster.base import AgentResponse, AgentRole


# ============================================================================
# Model Tests
# ============================================================================

def test_dice_roll_creation():
    """Test DiceRoll model creation."""
    roll = DiceRoll(dice="1d20+5", result=18, purpose="attack roll")
    assert roll.dice == "1d20+5"
    assert roll.result == 18
    assert roll.purpose == "attack roll"


def test_dice_roll_serialization():
    """Test DiceRoll model serialization."""
    roll = DiceRoll(dice="2d6", result=7, purpose="damage roll")
    data = roll.model_dump()
    assert data == {
        "dice": "2d6",
        "result": 7,
        "purpose": "damage roll"
    }


def test_npc_response_creation():
    """Test NPCResponse model creation."""
    response = NPCResponse(
        npc_name="Guard Captain",
        dialogue="Who goes there?",
        reaction="suspicious",
        attitude_change="neutral -> hostile"
    )
    assert response.npc_name == "Guard Captain"
    assert response.dialogue == "Who goes there?"
    assert response.reaction == "suspicious"
    assert response.attitude_change == "neutral -> hostile"


def test_npc_response_optional_fields():
    """Test NPCResponse with only required fields."""
    response = NPCResponse(npc_name="Merchant")
    assert response.npc_name == "Merchant"
    assert response.dialogue is None
    assert response.reaction is None
    assert response.attitude_change is None


def test_state_change_creation():
    """Test StateChange model creation."""
    change = StateChange(
        entity="Thorin",
        field="hp",
        old_value="45",
        new_value="38"
    )
    assert change.entity == "Thorin"
    assert change.field == "hp"
    assert change.old_value == "45"
    assert change.new_value == "38"


def test_state_change_without_old_value():
    """Test StateChange without old_value."""
    change = StateChange(
        entity="Party",
        field="location",
        new_value="Goblin Cave"
    )
    assert change.entity == "Party"
    assert change.field == "location"
    assert change.old_value is None
    assert change.new_value == "Goblin Cave"


def test_action_type_enum_values():
    """Test ActionType enum contains expected values."""
    assert ActionType.COMBAT == "combat"
    assert ActionType.ROLEPLAY == "roleplay"
    assert ActionType.EXPLORATION == "exploration"
    assert ActionType.PUZZLE == "puzzle"
    assert ActionType.SKILL_CHECK == "skill_check"
    assert ActionType.REST == "rest"
    assert ActionType.INVENTORY == "inventory"
    assert ActionType.MIXED == "mixed"


def test_action_type_enum_membership():
    """Test ActionType enum membership checks."""
    assert "combat" in [at.value for at in ActionType]
    assert "invalid" not in [at.value for at in ActionType]


def test_action_response_minimal():
    """Test ActionResponse with minimal required fields."""
    response = ActionResponse(
        narrative="You swing your sword.",
        action_type=ActionType.COMBAT
    )
    assert response.narrative == "You swing your sword."
    assert response.action_type == ActionType.COMBAT
    assert response.state_changes == []
    assert response.dice_rolls == []
    assert response.npc_responses == []
    assert response.follow_up_options is None
    assert response.warnings == []
    assert response.character_name is None
    assert response.turn_number == 0


def test_action_response_complete():
    """Test ActionResponse with all fields populated."""
    response = ActionResponse(
        narrative="Your blade strikes true!",
        action_type=ActionType.COMBAT,
        state_changes=[
            StateChange(entity="Goblin", field="hp", old_value="12", new_value="0")
        ],
        dice_rolls=[
            DiceRoll(dice="1d20+5", result=18, purpose="attack roll"),
            DiceRoll(dice="1d8+3", result=7, purpose="damage roll")
        ],
        npc_responses=[
            NPCResponse(npc_name="Goblin", reaction="dying")
        ],
        follow_up_options=["Search the goblin", "Move forward", "Take a short rest"],
        warnings=["Low HP warning"],
        character_name="Aragorn",
        turn_number=5
    )
    assert response.narrative == "Your blade strikes true!"
    assert response.action_type == ActionType.COMBAT
    assert len(response.state_changes) == 1
    assert len(response.dice_rolls) == 2
    assert len(response.npc_responses) == 1
    assert len(response.follow_up_options) == 3
    assert response.warnings == ["Low HP warning"]
    assert response.character_name == "Aragorn"
    assert response.turn_number == 5


def test_action_response_serialization():
    """Test ActionResponse serialization to dict."""
    response = ActionResponse(
        narrative="Test narrative",
        action_type=ActionType.EXPLORATION,
        dice_rolls=[DiceRoll(dice="1d20", result=15, purpose="perception")]
    )
    data = response.model_dump()
    assert data["narrative"] == "Test narrative"
    assert data["action_type"] == "exploration"
    assert len(data["dice_rolls"]) == 1
    assert data["dice_rolls"][0]["dice"] == "1d20"


# ============================================================================
# ActionProcessor Tests
# ============================================================================

@pytest.fixture
def mock_session_manager():
    """Create a mock SessionManager."""
    manager = MagicMock()
    manager._active_sessions = {}
    return manager


@pytest.fixture
def mock_orchestrator():
    """Create a mock Orchestrator."""
    orchestrator = MagicMock()
    orchestrator.classify_intent = MagicMock()
    orchestrator.process_player_input = AsyncMock()
    return orchestrator


@pytest.fixture
def mock_session():
    """Create a mock ClaudmasterSession."""
    session = MagicMock()
    session.turn_count = 1
    session.metadata = {}
    return session


@pytest.fixture
def action_processor(mock_session_manager):
    """Create an ActionProcessor instance."""
    return ActionProcessor(mock_session_manager)


def test_action_processor_initialization(action_processor, mock_session_manager):
    """Test ActionProcessor initialization."""
    assert action_processor.session_manager is mock_session_manager


def test_get_active_session_found(action_processor, mock_session_manager, mock_orchestrator, mock_session):
    """Test _get_active_session with valid session_id."""
    session_id = "test123"
    mock_session_manager._active_sessions[session_id] = (mock_orchestrator, mock_session)

    orch, sess = action_processor._get_active_session(session_id)
    assert orch is mock_orchestrator
    assert sess is mock_session


def test_get_active_session_not_found(action_processor):
    """Test _get_active_session with invalid session_id."""
    with pytest.raises(ValueError, match="Session invalid123 not found"):
        action_processor._get_active_session("invalid123")


def test_map_intent_to_action_type_combat(action_processor):
    """Test intent mapping for COMBAT."""
    intent = PlayerIntent(
        intent_type=IntentType.COMBAT,
        confidence=0.9,
        raw_input="I attack"
    )
    action_type = action_processor._map_intent_to_action_type(intent)
    assert action_type == ActionType.COMBAT


def test_map_intent_to_action_type_roleplay(action_processor):
    """Test intent mapping for ROLEPLAY."""
    intent = PlayerIntent(
        intent_type=IntentType.ROLEPLAY,
        confidence=0.8,
        raw_input="I persuade the guard"
    )
    action_type = action_processor._map_intent_to_action_type(intent)
    assert action_type == ActionType.ROLEPLAY


def test_map_intent_to_action_type_exploration(action_processor):
    """Test intent mapping for EXPLORATION."""
    intent = PlayerIntent(
        intent_type=IntentType.EXPLORATION,
        confidence=0.85,
        raw_input="I search the room"
    )
    action_type = action_processor._map_intent_to_action_type(intent)
    assert action_type == ActionType.EXPLORATION


def test_map_intent_to_action_type_question(action_processor):
    """Test intent mapping for QUESTION."""
    intent = PlayerIntent(
        intent_type=IntentType.QUESTION,
        confidence=0.7,
        raw_input="What do I see?"
    )
    action_type = action_processor._map_intent_to_action_type(intent)
    assert action_type == ActionType.SKILL_CHECK


def test_map_intent_to_action_type_system(action_processor):
    """Test intent mapping for SYSTEM."""
    intent = PlayerIntent(
        intent_type=IntentType.SYSTEM,
        confidence=0.95,
        raw_input="show inventory"
    )
    action_type = action_processor._map_intent_to_action_type(intent)
    assert action_type == ActionType.INVENTORY


def test_map_intent_to_action_type_action(action_processor):
    """Test intent mapping for ACTION (fallback)."""
    intent = PlayerIntent(
        intent_type=IntentType.ACTION,
        confidence=0.6,
        raw_input="I do something"
    )
    action_type = action_processor._map_intent_to_action_type(intent)
    assert action_type == ActionType.MIXED


def test_extract_state_changes_empty(action_processor):
    """Test _extract_state_changes with no state changes."""
    orch_response = OrchestratorResponse(
        narrative="Nothing changes.",
        state_changes=[]
    )
    changes = action_processor._extract_state_changes(orch_response)
    assert changes == []


def test_extract_state_changes_valid(action_processor):
    """Test _extract_state_changes with valid state changes."""
    orch_response = OrchestratorResponse(
        narrative="You take damage.",
        state_changes=[
            {"entity": "Hero", "field": "hp", "old_value": "50", "new_value": "45"},
            {"entity": "Party", "field": "location", "new_value": "Cave"}
        ]
    )
    changes = action_processor._extract_state_changes(orch_response)
    assert len(changes) == 2
    assert changes[0].entity == "Hero"
    assert changes[0].field == "hp"
    assert changes[0].old_value == "50"
    assert changes[0].new_value == "45"
    assert changes[1].entity == "Party"
    assert changes[1].field == "location"


def test_extract_state_changes_invalid_dict(action_processor):
    """Test _extract_state_changes with invalid dict (missing required fields)."""
    orch_response = OrchestratorResponse(
        narrative="Test",
        state_changes=[
            {"invalid": "data"}  # Missing required fields
        ]
    )
    changes = action_processor._extract_state_changes(orch_response)
    # Should skip invalid entries
    assert len(changes) == 0


def test_extract_dice_rolls_from_observations(action_processor):
    """Test _extract_dice_rolls from agent observations."""
    agent_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="Rolling attack",
        action_result="Hit!",
        observations={
            "dice_rolls": [
                {"dice": "1d20+5", "result": 18, "purpose": "attack roll"}
            ]
        }
    )
    orch_response = OrchestratorResponse(
        narrative="You hit!",
        agent_responses=[agent_response]
    )
    rolls = action_processor._extract_dice_rolls(orch_response)
    assert len(rolls) == 1
    assert rolls[0].dice == "1d20+5"
    assert rolls[0].result == 18


def test_extract_dice_rolls_from_metadata(action_processor):
    """Test _extract_dice_rolls from agent metadata."""
    agent_response = AgentResponse(
        agent_name="archivist",
        agent_role=AgentRole.ARCHIVIST,
        reasoning="Combat tracking",
        action_result="Updated",
        metadata={
            "dice_rolls": [
                {"dice": "2d6", "result": 8, "purpose": "damage roll"}
            ]
        }
    )
    orch_response = OrchestratorResponse(
        narrative="Damage dealt!",
        agent_responses=[agent_response]
    )
    rolls = action_processor._extract_dice_rolls(orch_response)
    assert len(rolls) == 1
    assert rolls[0].dice == "2d6"


def test_extract_dice_rolls_empty(action_processor):
    """Test _extract_dice_rolls with no dice rolls."""
    agent_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="Just narrative",
        action_result="You look around."
    )
    orch_response = OrchestratorResponse(
        narrative="You look around.",
        agent_responses=[agent_response]
    )
    rolls = action_processor._extract_dice_rolls(orch_response)
    assert rolls == []


def test_extract_npc_responses_from_observations(action_processor):
    """Test _extract_npc_responses from agent observations."""
    agent_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="NPC interaction",
        action_result="Guard responds",
        observations={
            "npc_interactions": [
                {
                    "npc_name": "Guard",
                    "dialogue": "Halt!",
                    "reaction": "alert"
                }
            ]
        }
    )
    orch_response = OrchestratorResponse(
        narrative="The guard shouts.",
        agent_responses=[agent_response]
    )
    responses = action_processor._extract_npc_responses(orch_response)
    assert len(responses) == 1
    assert responses[0].npc_name == "Guard"
    assert responses[0].dialogue == "Halt!"


def test_extract_npc_responses_from_metadata(action_processor):
    """Test _extract_npc_responses from agent metadata."""
    agent_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="NPC reaction",
        action_result="Merchant responds",
        metadata={
            "npc_responses": [
                {
                    "npc_name": "Merchant",
                    "dialogue": "Good day!",
                    "reaction": "friendly"
                }
            ]
        }
    )
    orch_response = OrchestratorResponse(
        narrative="The merchant greets you.",
        agent_responses=[agent_response]
    )
    responses = action_processor._extract_npc_responses(orch_response)
    assert len(responses) == 1
    assert responses[0].npc_name == "Merchant"


def test_extract_npc_responses_empty(action_processor):
    """Test _extract_npc_responses with no NPC interactions."""
    agent_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="Solo action",
        action_result="You search."
    )
    orch_response = OrchestratorResponse(
        narrative="You search the room.",
        agent_responses=[agent_response]
    )
    responses = action_processor._extract_npc_responses(orch_response)
    assert responses == []


@pytest.mark.anyio
async def test_process_action_happy_path(action_processor, mock_session_manager, mock_orchestrator, mock_session):
    """Test process_action happy path."""
    session_id = "test123"
    mock_session_manager._active_sessions[session_id] = (mock_orchestrator, mock_session)

    # Mock intent classification
    intent = PlayerIntent(
        intent_type=IntentType.COMBAT,
        confidence=0.9,
        raw_input="I attack the orc"
    )
    mock_orchestrator.classify_intent.return_value = intent

    # Mock orchestrator response
    orch_response = OrchestratorResponse(
        narrative="You swing your sword and hit!",
        state_changes=[
            {"entity": "Orc", "field": "hp", "old_value": "15", "new_value": "8"}
        ]
    )
    mock_orchestrator.process_player_input.return_value = orch_response

    # Process action
    result = await action_processor.process_action(
        session_id=session_id,
        action="I attack the orc"
    )

    # Verify
    assert isinstance(result, ActionResponse)
    assert result.narrative == "You swing your sword and hit!"
    assert result.action_type == ActionType.COMBAT
    assert len(result.state_changes) == 1
    assert result.warnings == []


@pytest.mark.anyio
async def test_process_action_with_character_name(action_processor, mock_session_manager, mock_orchestrator, mock_session):
    """Test process_action with character_name."""
    session_id = "test123"
    mock_session_manager._active_sessions[session_id] = (mock_orchestrator, mock_session)

    intent = PlayerIntent(intent_type=IntentType.ROLEPLAY, confidence=0.8, raw_input="I talk")
    mock_orchestrator.classify_intent.return_value = intent
    mock_orchestrator.process_player_input.return_value = OrchestratorResponse(narrative="You talk.")

    result = await action_processor.process_action(
        session_id=session_id,
        action="I talk to the merchant",
        character_name="Gandalf"
    )

    assert result.character_name == "Gandalf"
    # Verify metadata was set and then cleaned up
    assert "acting_character" not in mock_session.metadata


@pytest.mark.anyio
async def test_process_action_with_context(action_processor, mock_session_manager, mock_orchestrator, mock_session):
    """Test process_action with context."""
    session_id = "test123"
    mock_session_manager._active_sessions[session_id] = (mock_orchestrator, mock_session)

    intent = PlayerIntent(intent_type=IntentType.EXPLORATION, confidence=0.85, raw_input="I search")
    mock_orchestrator.classify_intent.return_value = intent
    mock_orchestrator.process_player_input.return_value = OrchestratorResponse(narrative="You search carefully.")

    result = await action_processor.process_action(
        session_id=session_id,
        action="I search the room",
        context="Looking for traps"
    )

    assert result.action_type == ActionType.EXPLORATION
    # Verify metadata was cleaned up
    assert "action_context" not in mock_session.metadata


@pytest.mark.anyio
async def test_process_action_session_not_found(action_processor):
    """Test process_action with invalid session_id."""
    result = await action_processor.process_action(
        session_id="invalid123",
        action="I attack"
    )

    assert isinstance(result, ActionResponse)
    assert "Session invalid123 not found" in result.narrative
    assert len(result.warnings) == 1
    assert result.turn_number == 0


@pytest.mark.anyio
async def test_process_action_orchestrator_error(action_processor, mock_session_manager, mock_orchestrator, mock_session):
    """Test process_action when orchestrator raises an error."""
    session_id = "test123"
    mock_session_manager._active_sessions[session_id] = (mock_orchestrator, mock_session)

    # Make orchestrator raise an error
    mock_orchestrator.process_player_input.side_effect = RuntimeError("Orchestrator failed")

    result = await action_processor.process_action(
        session_id=session_id,
        action="I attack"
    )

    assert isinstance(result, ActionResponse)
    assert "I encountered an issue" in result.narrative
    assert "RuntimeError" in result.narrative
    assert len(result.warnings) == 1
    assert "RuntimeError" in result.warnings[0]


# ============================================================================
# MCP Tool Function Tests
# ============================================================================

@pytest.mark.anyio
async def test_player_action_tool_basic():
    """Test player_action MCP tool function basic usage."""
    with patch('gamemaster_mcp.claudmaster.tools.action_tools._session_manager') as mock_mgr:
        # Setup mocks
        mock_orchestrator = MagicMock()
        mock_session = MagicMock()
        mock_session.turn_count = 3
        mock_session.metadata = {}

        mock_mgr._active_sessions = {"session123": (mock_orchestrator, mock_session)}

        intent = PlayerIntent(intent_type=IntentType.COMBAT, confidence=0.9, raw_input="attack")
        mock_orchestrator.classify_intent.return_value = intent
        mock_orchestrator.process_player_input = AsyncMock(
            return_value=OrchestratorResponse(narrative="You attack!")
        )

        # Call tool
        result = await player_action(
            session_id="session123",
            action="I attack the goblin"
        )

        # Verify it returns a dict
        assert isinstance(result, dict)
        assert result["narrative"] == "You attack!"
        assert result["action_type"] == "combat"


@pytest.mark.anyio
async def test_player_action_tool_with_character_name():
    """Test player_action with character_name parameter."""
    with patch('gamemaster_mcp.claudmaster.tools.action_tools._session_manager') as mock_mgr:
        mock_orchestrator = MagicMock()
        mock_session = MagicMock()
        mock_session.turn_count = 1
        mock_session.metadata = {}

        mock_mgr._active_sessions = {"session456": (mock_orchestrator, mock_session)}

        intent = PlayerIntent(intent_type=IntentType.ROLEPLAY, confidence=0.8, raw_input="talk")
        mock_orchestrator.classify_intent.return_value = intent
        mock_orchestrator.process_player_input = AsyncMock(
            return_value=OrchestratorResponse(narrative="You speak.")
        )

        result = await player_action(
            session_id="session456",
            action="I speak to the wizard",
            character_name="Frodo"
        )

        assert result["character_name"] == "Frodo"


@pytest.mark.anyio
async def test_player_action_tool_with_context():
    """Test player_action with context parameter."""
    with patch('gamemaster_mcp.claudmaster.tools.action_tools._session_manager') as mock_mgr:
        mock_orchestrator = MagicMock()
        mock_session = MagicMock()
        mock_session.turn_count = 2
        mock_session.metadata = {}

        mock_mgr._active_sessions = {"session789": (mock_orchestrator, mock_session)}

        intent = PlayerIntent(intent_type=IntentType.EXPLORATION, confidence=0.85, raw_input="search")
        mock_orchestrator.classify_intent.return_value = intent
        mock_orchestrator.process_player_input = AsyncMock(
            return_value=OrchestratorResponse(narrative="You search stealthily.")
        )

        result = await player_action(
            session_id="session789",
            action="I search for traps",
            context="Being very careful"
        )

        assert "search" in result["narrative"].lower()


@pytest.mark.anyio
async def test_player_action_tool_invalid_session():
    """Test player_action with invalid session ID."""
    with patch('gamemaster_mcp.claudmaster.tools.action_tools._session_manager') as mock_mgr:
        mock_mgr._active_sessions = {}

        result = await player_action(
            session_id="nonexistent",
            action="I attack"
        )

        assert isinstance(result, dict)
        assert "not found" in result["narrative"]
        assert len(result["warnings"]) > 0


@pytest.mark.anyio
async def test_player_action_tool_with_all_response_fields():
    """Test player_action returning response with all fields populated."""
    with patch('gamemaster_mcp.claudmaster.tools.action_tools._session_manager') as mock_mgr:
        mock_orchestrator = MagicMock()
        mock_session = MagicMock()
        mock_session.turn_count = 5
        mock_session.metadata = {}

        mock_mgr._active_sessions = {"rich_session": (mock_orchestrator, mock_session)}

        intent = PlayerIntent(intent_type=IntentType.COMBAT, confidence=0.95, raw_input="attack")
        mock_orchestrator.classify_intent.return_value = intent

        # Create response with dice rolls and NPC responses
        agent_response = AgentResponse(
            agent_name="narrator",
            agent_role=AgentRole.NARRATOR,
            reasoning="Combat narration",
            action_result="Critical hit!",
            observations={
                "dice_rolls": [
                    {"dice": "1d20+5", "result": 20, "purpose": "attack roll"}
                ],
                "npc_interactions": [
                    {"npc_name": "Dragon", "reaction": "enraged"}
                ]
            }
        )

        orch_response = OrchestratorResponse(
            narrative="Critical hit!",
            state_changes=[
                {"entity": "Dragon", "field": "hp", "old_value": "200", "new_value": "180"}
            ],
            agent_responses=[agent_response],
            metadata={"follow_up_options": ["Attack again", "Dodge", "Cast spell"]}
        )

        mock_orchestrator.process_player_input = AsyncMock(return_value=orch_response)

        result = await player_action(
            session_id="rich_session",
            action="I attack with my legendary sword",
            character_name="Hero"
        )

        assert result["narrative"] == "Critical hit!"
        assert result["character_name"] == "Hero"
        assert result["turn_number"] == 5
        assert len(result["dice_rolls"]) == 1
        assert result["dice_rolls"][0]["result"] == 20
        assert len(result["npc_responses"]) == 1
        assert result["npc_responses"][0]["npc_name"] == "Dragon"
        assert len(result["state_changes"]) == 1
        assert result["follow_up_options"] == ["Attack again", "Dodge", "Cast spell"]
