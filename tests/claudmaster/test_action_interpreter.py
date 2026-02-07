"""
Tests for the ActionInterpreter module.

Tests cover:
- Intent classification for all major ActionIntent categories
- Compound action parsing
- OOC detection
- Ambiguity detection
- Validation (combat action outside combat, etc.)
- Clarification request generation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

# Configure pytest to use anyio with asyncio backend only
pytestmark = pytest.mark.anyio

# Configure anyio to use only asyncio backend
@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

from gamemaster_mcp.models import GameState, Character, CharacterClass, Race, AbilityScore
from gamemaster_mcp.claudmaster.action_interpreter import (
    ActionInterpreter,
    ActionIntent,
    ParsedAction,
    AmbiguityType,
    Ambiguity,
    ValidationResult,
    InterpretationResult,
    ClarificationRequest,
)
from gamemaster_mcp.claudmaster.agents.archivist import (
    ArchivistAgent,
    CharacterStats,
    HPStatus,
)
from gamemaster_mcp.models import GameState, Character, CharacterClass, Race, AbilityScore
from gamemaster_mcp.claudmaster.action_interpreter import (
    ActionInterpreter,
    ActionIntent,
    ParsedAction,
    AmbiguityType,
    Ambiguity,
    ValidationResult,
    InterpretationResult,
    ClarificationRequest,
)
from gamemaster_mcp.claudmaster.agents.archivist import (
    ArchivistAgent,
    CharacterStats,
    HPStatus,
)


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def mock_llm():
    """Create a mock LLMClient."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value="Mock LLM response")
    return llm


@pytest.fixture
def mock_archivist():
    """Create a mock ArchivistAgent."""
    archivist = AsyncMock(spec=ArchivistAgent)

    # Mock get_character_stats
    stats = CharacterStats(
        name="Gandalf",
        race="Human",
        character_class="Wizard",
        level=5,
        ability_scores={"strength": 10, "dexterity": 14, "intelligence": 18},
        hp_current=30,
        hp_max=30,
        armor_class=12,
        proficiency_bonus=3
    )
    archivist.get_character_stats = AsyncMock(return_value=stats)

    # Mock get_character_hp
    hp_status = HPStatus(
        name="Gandalf",
        hp_current=30,
        hp_max=30,
        hp_temp=0,
        is_conscious=True,
        percentage=100.0
    )
    archivist.get_character_hp = AsyncMock(return_value=hp_status)

    return archivist


@pytest.fixture
def game_state_combat():
    """Create a GameState in combat."""
    return GameState(
        campaign_name="Test Campaign",
        in_combat=True,
        current_turn="Gandalf",
        current_location="Dark Cave",
        initiative_order=[
            {"name": "Gandalf", "initiative": 15},
            {"name": "Goblin", "initiative": 10}
        ]
    )


@pytest.fixture
def game_state_exploration():
    """Create a GameState in exploration mode."""
    return GameState(
        campaign_name="Test Campaign",
        in_combat=False,
        current_location="Forest Path"
    )


@pytest.fixture
def action_interpreter(mock_archivist, mock_llm):
    """Create an ActionInterpreter instance."""
    return ActionInterpreter(archivist=mock_archivist, llm=mock_llm)


# ============================================================================
# Test Intent Classification
# ============================================================================


async def test_classify_combat_attack(action_interpreter, game_state_combat):
    """Test classification of combat attack actions."""
    result = await action_interpreter.interpret(
        "I attack the goblin with my sword",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.COMBAT_ATTACK
    assert action.actor == "Gandalf"
    assert action.confidence >= 0.5



async def test_classify_combat_spell(action_interpreter, game_state_combat):
    """Test classification of combat spell actions."""
    result = await action_interpreter.interpret(
        "I cast fireball at the enemies",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.COMBAT_SPELL
    assert action.method == "fireball"
    assert action.confidence >= 0.5



async def test_classify_combat_defensive(action_interpreter, game_state_combat):
    """Test classification of defensive combat actions."""
    result = await action_interpreter.interpret(
        "I dodge",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.COMBAT_DEFENSIVE
    assert action.confidence >= 0.5



async def test_classify_exploration_search(action_interpreter, game_state_exploration):
    """Test classification of exploration search actions."""
    result = await action_interpreter.interpret(
        "I search for traps",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.EXPLORATION_SEARCH
    assert action.confidence >= 0.5



async def test_classify_exploration_movement(action_interpreter, game_state_exploration):
    """Test classification of exploration movement actions."""
    result = await action_interpreter.interpret(
        "I walk to the north door",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.EXPLORATION_MOVEMENT
    assert action.confidence >= 0.5



async def test_classify_exploration_interact(action_interpreter, game_state_exploration):
    """Test classification of exploration interaction actions."""
    result = await action_interpreter.interpret(
        "I open the chest",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.EXPLORATION_INTERACT
    assert action.confidence >= 0.5



async def test_classify_social_dialogue(action_interpreter, game_state_exploration):
    """Test classification of social dialogue actions."""
    result = await action_interpreter.interpret(
        "I talk to the innkeeper",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.SOCIAL_DIALOGUE
    assert action.confidence >= 0.5



async def test_classify_social_persuade(action_interpreter, game_state_exploration):
    """Test classification of persuasion actions."""
    result = await action_interpreter.interpret(
        "I try to persuade the guard",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.SOCIAL_PERSUADE
    assert action.confidence >= 0.5



async def test_classify_social_intimidate(action_interpreter, game_state_exploration):
    """Test classification of intimidation actions."""
    result = await action_interpreter.interpret(
        "I intimidate the bandit",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.SOCIAL_INTIMIDATE
    assert action.confidence >= 0.5



async def test_classify_item_use(action_interpreter, game_state_exploration):
    """Test classification of item use actions."""
    result = await action_interpreter.interpret(
        "I drink a healing potion",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.ITEM_USE
    assert action.confidence >= 0.5



async def test_classify_rest_short(action_interpreter, game_state_exploration):
    """Test classification of short rest actions."""
    result = await action_interpreter.interpret(
        "I take a short rest",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.REST_SHORT
    assert action.confidence >= 0.5



async def test_classify_rest_long(action_interpreter, game_state_exploration):
    """Test classification of long rest actions."""
    result = await action_interpreter.interpret(
        "I sleep for the night",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    action = result.actions[0]
    assert action.intent == ActionIntent.REST_LONG
    assert action.confidence >= 0.5


# ============================================================================
# Test Compound Actions
# ============================================================================


async def test_compound_action_and(action_interpreter, game_state_combat):
    """Test parsing compound actions with 'and'."""
    result = await action_interpreter.interpret(
        "I move to the goblin and attack",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 2
    assert result.actions[0].intent == ActionIntent.COMBAT_MOVEMENT
    assert result.actions[1].intent == ActionIntent.COMBAT_ATTACK



async def test_compound_action_then(action_interpreter, game_state_combat):
    """Test parsing compound actions with 'then'."""
    result = await action_interpreter.interpret(
        "I dodge then move to cover",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 2
    assert result.actions[0].intent == ActionIntent.COMBAT_DEFENSIVE
    assert result.actions[1].intent == ActionIntent.COMBAT_MOVEMENT



async def test_compound_action_while(action_interpreter, game_state_exploration):
    """Test parsing compound actions with 'while'."""
    result = await action_interpreter.interpret(
        "I search the room while checking for traps",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 2
    # Both should be search actions
    assert all(a.intent == ActionIntent.EXPLORATION_SEARCH for a in result.actions)


# ============================================================================
# Test OOC Detection
# ============================================================================


async def test_ooc_detection_ooc_prefix(action_interpreter, game_state_exploration):
    """Test OOC detection with 'ooc' prefix."""
    result = await action_interpreter.interpret(
        "OOC: can we take a break?",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    assert result.actions[0].intent == ActionIntent.META_OOC
    assert result.actions[0].confidence == 1.0



async def test_ooc_detection_parentheses(action_interpreter, game_state_exploration):
    """Test OOC detection with parentheses."""
    result = await action_interpreter.interpret(
        "(quick question about the rules)",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    assert result.actions[0].intent == ActionIntent.META_OOC



async def test_meta_question_detection(action_interpreter, game_state_exploration):
    """Test meta question detection."""
    result = await action_interpreter.interpret(
        "How do spell slots work?",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    assert result.actions[0].intent == ActionIntent.META_QUESTION
    assert result.actions[0].confidence >= 0.8


# ============================================================================
# Test Target Extraction
# ============================================================================


async def test_extract_targets_the(action_interpreter, game_state_combat):
    """Test target extraction with 'the' pattern."""
    result = await action_interpreter.interpret(
        "I attack the orc",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    assert "orc" in result.actions[0].targets[0]



async def test_extract_targets_at(action_interpreter, game_state_combat):
    """Test target extraction with 'at' pattern."""
    result = await action_interpreter.interpret(
        "I shoot at the goblin",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    assert "goblin" in result.actions[0].targets[0]


# ============================================================================
# Test Method Extraction
# ============================================================================


async def test_extract_method_spell(action_interpreter, game_state_combat):
    """Test spell method extraction."""
    result = await action_interpreter.interpret(
        "I cast magic missile at the enemy",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    assert result.actions[0].method == "magic missile"



async def test_extract_method_weapon(action_interpreter, game_state_combat):
    """Test weapon method extraction."""
    result = await action_interpreter.interpret(
        "I attack with my dagger",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    assert result.actions[0].method == "dagger"


# ============================================================================
# Test Modifier Extraction
# ============================================================================


async def test_extract_modifier_stealth(action_interpreter, game_state_exploration):
    """Test stealth modifier extraction."""
    result = await action_interpreter.interpret(
        "I move stealthily to the door",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    assert "stealth" in result.actions[0].modifiers



async def test_extract_modifier_advantage(action_interpreter, game_state_combat):
    """Test advantage modifier extraction."""
    result = await action_interpreter.interpret(
        "I attack with advantage",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    assert "advantage" in result.actions[0].modifiers


# ============================================================================
# Test Validation
# ============================================================================


async def test_validate_combat_action_in_combat(action_interpreter, game_state_combat):
    """Test validation of combat action during combat (should be valid)."""
    action = ParsedAction(
        intent=ActionIntent.COMBAT_ATTACK,
        actor="Gandalf",
        targets=["goblin"],
        raw_input="I attack the goblin",
        confidence=0.9
    )

    result = await action_interpreter.validate(action, game_state_combat)

    assert result.is_valid is True
    assert len(result.issues) == 0



async def test_validate_combat_action_outside_combat(action_interpreter, game_state_exploration):
    """Test validation of combat action outside combat (should warn)."""
    action = ParsedAction(
        intent=ActionIntent.COMBAT_ATTACK,
        actor="Gandalf",
        targets=["goblin"],
        raw_input="I attack the goblin",
        confidence=0.9
    )

    result = await action_interpreter.validate(action, game_state_exploration)

    assert result.is_valid is False
    assert len(result.issues) > 0
    assert "combat is not active" in result.issues[0].lower()
    assert result.can_attempt_with_penalty is True



async def test_validate_missing_target(action_interpreter, game_state_combat):
    """Test validation of action missing required target."""
    action = ParsedAction(
        intent=ActionIntent.COMBAT_ATTACK,
        actor="Gandalf",
        targets=[],  # No target
        raw_input="I attack",
        confidence=0.8
    )

    result = await action_interpreter.validate(action, game_state_combat)

    assert result.is_valid is False
    assert len(result.issues) > 0
    assert "requires a target" in result.issues[0].lower()



async def test_validate_invalid_character(action_interpreter, game_state_combat):
    """Test validation with invalid character name."""
    # Configure mock to raise KeyError for invalid character
    action_interpreter.archivist.get_character_stats = AsyncMock(
        side_effect=KeyError("Character not found")
    )

    action = ParsedAction(
        intent=ActionIntent.COMBAT_ATTACK,
        actor="InvalidCharacter",
        targets=["goblin"],
        raw_input="I attack the goblin",
        confidence=0.9
    )

    result = await action_interpreter.validate(action, game_state_combat)

    assert result.is_valid is False
    assert any("not found" in issue.lower() for issue in result.issues)


# ============================================================================
# Test Ambiguity Detection
# ============================================================================


async def test_ambiguity_detection_low_confidence(action_interpreter, game_state_exploration):
    """Test that low confidence actions are flagged as ambiguous."""
    # Use a very vague input that won't match many keywords
    result = await action_interpreter.interpret(
        "I do something",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 1
    # Should have low confidence
    assert result.actions[0].confidence < 0.5
    # Should be flagged as needing clarification
    assert result.requires_clarification is True
    assert len(result.ambiguities) > 0


# ============================================================================
# Test Clarification Requests
# ============================================================================


async def test_clarification_request_target(action_interpreter):
    """Test clarification request for target ambiguity."""
    ambiguity = Ambiguity(
        type=AmbiguityType.TARGET,
        options=["goblin", "orc"],
        context_hint="Multiple enemies in range"
    )

    clarification = await action_interpreter.request_clarification(
        ambiguity,
        "I attack"
    )

    assert clarification.question == "Who or what do you want to target?"
    assert "goblin" in clarification.options
    assert "orc" in clarification.options
    assert clarification.original_input == "I attack"



async def test_clarification_request_method(action_interpreter):
    """Test clarification request for method ambiguity."""
    ambiguity = Ambiguity(
        type=AmbiguityType.METHOD,
        options=["sword", "dagger"],
        context_hint="Multiple weapons equipped"
    )

    clarification = await action_interpreter.request_clarification(
        ambiguity,
        "I attack the goblin"
    )

    assert clarification.question == "How do you want to do this?"
    assert "sword" in clarification.options
    assert "dagger" in clarification.options



async def test_clarification_request_intent(action_interpreter):
    """Test clarification request for intent ambiguity."""
    ambiguity = Ambiguity(
        type=AmbiguityType.INTENT,
        options=["attack", "investigate"],
        context_hint="Action unclear"
    )

    clarification = await action_interpreter.request_clarification(
        ambiguity,
        "I approach the figure"
    )

    assert clarification.question == "What exactly do you want to do?"


# ============================================================================
# Test Edge Cases
# ============================================================================


async def test_empty_input(action_interpreter, game_state_exploration):
    """Test handling of empty input."""
    result = await action_interpreter.interpret(
        "",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 0
    assert result.requires_clarification is True
    assert result.clarification_prompt is not None



async def test_whitespace_only_input(action_interpreter, game_state_exploration):
    """Test handling of whitespace-only input."""
    result = await action_interpreter.interpret(
        "   ",
        "Gandalf",
        game_state_exploration
    )

    assert len(result.actions) == 0
    assert result.requires_clarification is True



async def test_complex_compound_action(action_interpreter, game_state_combat):
    """Test complex compound action with multiple separators."""
    result = await action_interpreter.interpret(
        "I move to the goblin and attack with my sword then dodge",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 3
    assert result.actions[0].intent == ActionIntent.COMBAT_MOVEMENT
    assert result.actions[1].intent == ActionIntent.COMBAT_ATTACK
    assert result.actions[2].intent == ActionIntent.COMBAT_DEFENSIVE


# ============================================================================
# Test Integration
# ============================================================================


async def test_full_workflow_interpret_and_validate(action_interpreter, game_state_combat):
    """Test full workflow: interpret then validate."""
    # Interpret
    result = await action_interpreter.interpret(
        "I attack the orc with my sword",
        "Gandalf",
        game_state_combat
    )

    assert len(result.actions) == 1
    action = result.actions[0]

    # Validate
    validation = await action_interpreter.validate(action, game_state_combat)

    assert validation.is_valid is True
    assert validation.action == action



async def test_full_workflow_with_ambiguity(action_interpreter, game_state_exploration):
    """Test full workflow with ambiguity detection and clarification."""
    # Interpret with vague input
    result = await action_interpreter.interpret(
        "I do a thing",
        "Gandalf",
        game_state_exploration
    )

    # Should detect ambiguity
    if result.requires_clarification and result.ambiguities:
        # Request clarification
        clarification = await action_interpreter.request_clarification(
            result.ambiguities[0],
            "I do a thing"
        )

        assert clarification.question is not None
        assert len(clarification.options) > 0
        assert clarification.original_input == "I do a thing"
