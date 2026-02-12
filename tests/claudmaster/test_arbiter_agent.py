"""
Unit tests for ArbiterAgent mechanical resolution capabilities.

Tests the Arbiter agent with rules adjudication, dice roll interpretation,
and state change proposals. All tests use mocked LLM clients.
"""

import json
import pytest
from typing import Any

from dm20_protocol.models import (
    Campaign,
    Character,
    CharacterClass,
    Race,
    AbilityScore,
    GameState,
)
from dm20_protocol.claudmaster.agents.arbiter import (
    ArbiterAgent,
    MechanicalResolution,
    DiceRollResult,
    StateChange,
    ActionType,
)
from dm20_protocol.claudmaster.base import AgentRole


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """LLM client that returns canned JSON responses and records calls."""

    def __init__(self, response: dict[str, Any] | None = None) -> None:
        self.response = response or {
            "success": True,
            "dice_rolls": [
                {
                    "description": "Attack roll",
                    "notation": "1d20+5",
                    "result": 18,
                    "success": True,
                    "dc": 13,
                }
            ],
            "state_changes": [
                {
                    "target": "Goblin",
                    "change_type": "hp",
                    "description": "Goblin takes 8 slashing damage",
                    "value": -8,
                }
            ],
            "rules_applied": ["PHB p.194: Attack action"],
            "narrative_hooks": ["Your blade strikes true, cutting into the goblin's shoulder."],
            "reasoning": "Player makes melee attack. Roll 1d20+5 vs AC 13. Hit! Roll 1d8+3 for 8 damage.",
        }
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return json.dumps(self.response)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_character() -> Character:
    """Create a mock character for testing."""
    return Character(
        name="Thorin",
        race=Race(name="Dwarf", size="Medium"),
        character_class=CharacterClass(name="Fighter", level=3),
        abilities={
            "strength": AbilityScore(score=16),
            "dexterity": AbilityScore(score=12),
            "constitution": AbilityScore(score=14),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=13),
            "charisma": AbilityScore(score=8),
        },
        hit_points_max=28,
        hit_points_current=28,
        armor_class=16,
        proficiency_bonus=2,
    )


@pytest.fixture
def mock_campaign(mock_character: Character) -> Campaign:
    """Create a mock campaign for testing."""
    campaign = Campaign(
        name="Test Campaign",
        description="A test campaign for Arbiter testing",
        setting="Forgotten Realms",
        characters={"char1": mock_character},
        game_state=GameState(campaign_name="Test Campaign", in_combat=False),
    )
    return campaign


@pytest.fixture
def mock_llm() -> MockLLM:
    """Create a mock LLM with default response."""
    return MockLLM()


@pytest.fixture
def arbiter(mock_llm: MockLLM, mock_campaign: Campaign) -> ArbiterAgent:
    """Create an Arbiter agent with mock dependencies."""
    return ArbiterAgent(llm=mock_llm, campaign=mock_campaign)


# ---------------------------------------------------------------------------
# Initialization Tests
# ---------------------------------------------------------------------------

class TestArbiterInitialization:
    """Tests for Arbiter agent initialization."""

    def test_initialization(self, mock_llm: MockLLM, mock_campaign: Campaign) -> None:
        """Test that Arbiter initializes with correct name and role."""
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)
        assert arbiter.name == "arbiter"
        assert arbiter.role == AgentRole.ARBITER
        assert arbiter.llm is mock_llm
        assert arbiter.campaign is mock_campaign

    def test_custom_max_tokens(self, mock_llm: MockLLM, mock_campaign: Campaign) -> None:
        """Test that custom max_tokens is stored."""
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign, max_tokens=2048)
        assert arbiter.max_tokens == 2048


# ---------------------------------------------------------------------------
# Reason Phase Tests
# ---------------------------------------------------------------------------

class TestReasonPhase:
    """Tests for the Arbiter's reasoning/pattern matching phase."""

    @pytest.mark.anyio
    async def test_reason_attack_action(self, arbiter: ArbiterAgent) -> None:
        """Test that attack actions are correctly identified."""
        context = {"player_action": "I attack the goblin with my sword"}
        reasoning = await arbiter.reason(context)
        assert ActionType.ATTACK in reasoning
        assert "attack" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_spell_casting(self, arbiter: ArbiterAgent) -> None:
        """Test that spell casting is correctly identified."""
        context = {"player_action": "I cast Fireball at the enemies"}
        reasoning = await arbiter.reason(context)
        assert ActionType.SPELL in reasoning
        assert "spell" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_skill_check(self, arbiter: ArbiterAgent) -> None:
        """Test that skill checks are correctly identified."""
        context = {"player_action": "I sneak past the guards"}
        reasoning = await arbiter.reason(context)
        assert ActionType.SKILL_CHECK in reasoning
        assert "skill check" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_saving_throw(self, arbiter: ArbiterAgent) -> None:
        """Test that saving throws are correctly identified."""
        context = {"player_action": "I try to save against the poison"}
        reasoning = await arbiter.reason(context)
        assert ActionType.SAVING_THROW in reasoning
        assert "saving throw" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_ability_check(self, arbiter: ArbiterAgent) -> None:
        """Test that general ability checks are correctly identified."""
        context = {"player_action": "I attempt a strength check to break the door"}
        reasoning = await arbiter.reason(context)
        assert ActionType.ABILITY_CHECK in reasoning
        assert "ability check" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_movement(self, arbiter: ArbiterAgent) -> None:
        """Test that movement actions are correctly identified."""
        context = {"player_action": "I run towards the exit"}
        reasoning = await arbiter.reason(context)
        assert ActionType.MOVEMENT in reasoning
        assert "moving" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_interaction(self, arbiter: ArbiterAgent) -> None:
        """Test that object interactions are correctly identified."""
        context = {"player_action": "I pull the lever"}
        reasoning = await arbiter.reason(context)
        assert ActionType.INTERACTION in reasoning
        assert "interact" in reasoning.lower()

    @pytest.mark.anyio
    async def test_reason_ambiguous_action(self, arbiter: ArbiterAgent) -> None:
        """Test handling of ambiguous/creative actions."""
        context = {"player_action": "I use my wit to charm the dragon"}
        reasoning = await arbiter.reason(context)
        assert ActionType.UNKNOWN in reasoning or ActionType.SKILL_CHECK in reasoning


# ---------------------------------------------------------------------------
# Act Phase Tests
# ---------------------------------------------------------------------------

class TestActPhase:
    """Tests for the Arbiter's action execution with LLM calls."""

    @pytest.mark.anyio
    async def test_act_calls_llm(self, arbiter: ArbiterAgent, mock_llm: MockLLM) -> None:
        """Test that act phase calls the LLM."""
        reasoning = f"action_type:{ActionType.ATTACK}|Player making attack"
        result = await arbiter.act(reasoning)
        assert len(mock_llm.calls) == 1
        assert isinstance(result, MechanicalResolution)

    @pytest.mark.anyio
    async def test_act_parses_successful_resolution(self, arbiter: ArbiterAgent) -> None:
        """Test that successful resolutions are parsed correctly."""
        reasoning = f"action_type:{ActionType.ATTACK}|Player making attack"
        result = await arbiter.act(reasoning)
        assert isinstance(result, MechanicalResolution)
        assert result.success is True
        assert len(result.dice_rolls) > 0
        assert len(result.state_changes) > 0
        assert len(result.narrative_hooks) > 0

    @pytest.mark.anyio
    async def test_act_handles_failed_resolution(self, mock_campaign: Campaign) -> None:
        """Test handling of failed action resolution."""
        mock_llm = MockLLM(response={
            "success": False,
            "dice_rolls": [
                {
                    "description": "Attack roll",
                    "notation": "1d20+5",
                    "result": 8,
                    "success": False,
                    "dc": 15,
                }
            ],
            "state_changes": [],
            "rules_applied": ["PHB p.194: Attack action"],
            "narrative_hooks": ["Your attack misses the target."],
            "reasoning": "Attack roll of 8 does not meet AC 15.",
        })
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        reasoning = f"action_type:{ActionType.ATTACK}|Player making attack"
        result = await arbiter.act(reasoning)
        assert isinstance(result, MechanicalResolution)
        assert result.success is False
        assert len(result.dice_rolls) > 0

    @pytest.mark.anyio
    async def test_act_handles_malformed_json(self, mock_campaign: Campaign) -> None:
        """Test graceful handling of malformed LLM response."""
        mock_llm = MockLLM(response={"invalid": "response"})  # Missing required fields
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        reasoning = f"action_type:{ActionType.ATTACK}|Player making attack"
        result = await arbiter.act(reasoning)
        # Should return fallback resolution
        assert isinstance(result, MechanicalResolution)
        assert result.success is False
        assert "error" in result.reasoning.lower() or "Error" in result.reasoning

    @pytest.mark.anyio
    async def test_act_strips_markdown_fences(self, mock_campaign: Campaign) -> None:
        """Test that markdown code fences are stripped from JSON response."""
        response_with_fence = {
            "success": True,
            "dice_rolls": [],
            "state_changes": [],
            "rules_applied": [],
            "narrative_hooks": ["Action resolved."],
            "reasoning": "Test reasoning.",
        }

        # Simulate LLM returning JSON wrapped in markdown
        class MockLLMWithFence:
            async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
                return f"```json\n{json.dumps(response_with_fence)}\n```"

        arbiter = ArbiterAgent(llm=MockLLMWithFence(), campaign=mock_campaign)
        reasoning = f"action_type:{ActionType.ATTACK}|Test"
        result = await arbiter.act(reasoning)
        assert isinstance(result, MechanicalResolution)
        assert result.success is True


# ---------------------------------------------------------------------------
# Observe Phase Tests
# ---------------------------------------------------------------------------

class TestObservePhase:
    """Tests for the Arbiter's observation phase."""

    @pytest.mark.anyio
    async def test_observe_extracts_success(self, arbiter: ArbiterAgent) -> None:
        """Test that observe extracts success status."""
        resolution = MechanicalResolution(
            success=True,
            dice_rolls=[],
            state_changes=[],
            rules_applied=[],
            narrative_hooks=[],
            reasoning="Test",
        )
        observations = await arbiter.observe(resolution)
        assert observations["success"] is True

    @pytest.mark.anyio
    async def test_observe_extracts_state_changes(self, arbiter: ArbiterAgent) -> None:
        """Test that observe extracts state changes."""
        resolution = MechanicalResolution(
            success=True,
            dice_rolls=[],
            state_changes=[
                StateChange(
                    target="Goblin",
                    change_type="hp",
                    description="Takes 10 damage",
                    value=-10,
                )
            ],
            rules_applied=[],
            narrative_hooks=[],
            reasoning="Test",
        )
        observations = await arbiter.observe(resolution)
        assert "state_changes" in observations
        assert len(observations["state_changes"]) == 1
        assert observations["state_changes"][0]["target"] == "Goblin"
        assert observations["state_changes"][0]["value"] == -10

    @pytest.mark.anyio
    async def test_observe_extracts_narrative_hooks(self, arbiter: ArbiterAgent) -> None:
        """Test that observe extracts narrative hooks for Narrator."""
        resolution = MechanicalResolution(
            success=True,
            dice_rolls=[],
            state_changes=[],
            rules_applied=[],
            narrative_hooks=["Your attack strikes true!", "The enemy staggers."],
            reasoning="Test",
        )
        observations = await arbiter.observe(resolution)
        assert "narrative_hooks" in observations
        assert len(observations["narrative_hooks"]) == 2

    @pytest.mark.anyio
    async def test_observe_extracts_dice_rolls(self, arbiter: ArbiterAgent) -> None:
        """Test that observe extracts dice roll summaries."""
        resolution = MechanicalResolution(
            success=True,
            dice_rolls=[
                DiceRollResult(
                    description="Attack roll",
                    notation="1d20+5",
                    result=18,
                    success=True,
                    dc=15,
                )
            ],
            state_changes=[],
            rules_applied=[],
            narrative_hooks=[],
            reasoning="Test",
        )
        observations = await arbiter.observe(resolution)
        assert "dice_rolls" in observations
        assert len(observations["dice_rolls"]) == 1
        assert observations["dice_rolls"][0]["result"] == 18

    @pytest.mark.anyio
    async def test_observe_handles_unexpected_type(self, arbiter: ArbiterAgent) -> None:
        """Test handling of unexpected result type."""
        observations = await arbiter.observe("not a resolution")
        assert observations["success"] is False
        assert "error" in observations


# ---------------------------------------------------------------------------
# Full ReAct Cycle Tests
# ---------------------------------------------------------------------------

class TestFullReActCycle:
    """Tests for the complete ReAct cycle: reason -> act -> observe."""

    @pytest.mark.anyio
    async def test_full_cycle_attack_action(self, arbiter: ArbiterAgent) -> None:
        """Test complete ReAct cycle for an attack action."""
        context = {"player_action": "I attack the goblin with my longsword"}
        response = await arbiter.run(context)

        assert response.agent_name == "arbiter"
        assert response.agent_role == AgentRole.ARBITER
        assert ActionType.ATTACK in response.reasoning
        assert isinstance(response.action_result, MechanicalResolution)
        assert response.observations["success"] is True

    @pytest.mark.anyio
    async def test_full_cycle_spell_casting(self, arbiter: ArbiterAgent, mock_campaign: Campaign) -> None:
        """Test complete ReAct cycle for spell casting."""
        mock_llm = MockLLM(response={
            "success": True,
            "dice_rolls": [
                {
                    "description": "Spell attack roll",
                    "notation": "1d20+6",
                    "result": 19,
                    "success": True,
                    "dc": None,
                }
            ],
            "state_changes": [
                {
                    "target": "Wizard",
                    "change_type": "spell_slot",
                    "description": "Expend 1st level spell slot",
                    "value": -1,
                }
            ],
            "rules_applied": ["PHB p.201: Spell attack"],
            "narrative_hooks": ["Magical energy crackles from your fingertips."],
            "reasoning": "Spell attack roll hits. Expend spell slot.",
        })
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        context = {"player_action": "I cast Magic Missile at the orc"}
        response = await arbiter.run(context)

        assert ActionType.SPELL in response.reasoning
        assert isinstance(response.action_result, MechanicalResolution)
        assert response.observations["success"] is True

    @pytest.mark.anyio
    async def test_full_cycle_skill_check(self, arbiter: ArbiterAgent, mock_campaign: Campaign) -> None:
        """Test complete ReAct cycle for skill check."""
        mock_llm = MockLLM(response={
            "success": True,
            "dice_rolls": [
                {
                    "description": "Stealth check",
                    "notation": "1d20+4",
                    "result": 17,
                    "success": True,
                    "dc": 15,
                }
            ],
            "state_changes": [],
            "rules_applied": ["PHB p.177: Stealth"],
            "narrative_hooks": ["You melt into the shadows, unnoticed."],
            "reasoning": "Stealth check vs DC 15. Roll of 17 succeeds.",
        })
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        context = {"player_action": "I sneak past the guard"}
        response = await arbiter.run(context)

        assert ActionType.SKILL_CHECK in response.reasoning
        assert response.observations["success"] is True
        assert response.observations["num_dice_rolls"] == 1


# ---------------------------------------------------------------------------
# State Change Proposal Tests
# ---------------------------------------------------------------------------

class TestStateChangeProposals:
    """Tests for state change proposal structure and validation."""

    @pytest.mark.anyio
    async def test_hp_change_proposal(self, arbiter: ArbiterAgent, mock_campaign: Campaign) -> None:
        """Test HP change proposals are correctly structured."""
        mock_llm = MockLLM(response={
            "success": True,
            "dice_rolls": [],
            "state_changes": [
                {
                    "target": "Thorin",
                    "change_type": "hp",
                    "description": "Takes 15 bludgeoning damage",
                    "value": -15,
                }
            ],
            "rules_applied": [],
            "narrative_hooks": [],
            "reasoning": "Damage applied.",
        })
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        reasoning = f"action_type:{ActionType.ATTACK}|Test"
        result = await arbiter.act(reasoning)
        assert len(result.state_changes) == 1
        assert result.state_changes[0].change_type == "hp"
        assert result.state_changes[0].value == -15

    @pytest.mark.anyio
    async def test_condition_change_proposal(self, arbiter: ArbiterAgent, mock_campaign: Campaign) -> None:
        """Test condition addition proposals are correctly structured."""
        mock_llm = MockLLM(response={
            "success": False,
            "dice_rolls": [
                {
                    "description": "Constitution saving throw",
                    "notation": "1d20+2",
                    "result": 9,
                    "success": False,
                    "dc": 12,
                }
            ],
            "state_changes": [
                {
                    "target": "Thorin",
                    "change_type": "condition",
                    "description": "Poisoned condition applied",
                    "value": "poisoned",
                }
            ],
            "rules_applied": ["PHB p.292: Poisoned condition"],
            "narrative_hooks": ["The poison courses through your veins."],
            "reasoning": "Failed save vs poison. Apply poisoned condition.",
        })
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        reasoning = f"action_type:{ActionType.SAVING_THROW}|Test"
        result = await arbiter.act(reasoning)
        assert len(result.state_changes) == 1
        assert result.state_changes[0].change_type == "condition"
        assert result.state_changes[0].value == "poisoned"

    @pytest.mark.anyio
    async def test_multiple_state_changes(self, arbiter: ArbiterAgent, mock_campaign: Campaign) -> None:
        """Test multiple simultaneous state changes."""
        mock_llm = MockLLM(response={
            "success": True,
            "dice_rolls": [],
            "state_changes": [
                {
                    "target": "Thorin",
                    "change_type": "hp",
                    "description": "Takes 8 fire damage",
                    "value": -8,
                },
                {
                    "target": "Thorin",
                    "change_type": "condition",
                    "description": "Catches fire",
                    "value": "burning",
                },
            ],
            "rules_applied": [],
            "narrative_hooks": ["Flames engulf you!"],
            "reasoning": "Fire damage and burning condition applied.",
        })
        arbiter = ArbiterAgent(llm=mock_llm, campaign=mock_campaign)

        reasoning = f"action_type:{ActionType.SPELL}|Test"
        result = await arbiter.act(reasoning)
        assert len(result.state_changes) == 2


# ---------------------------------------------------------------------------
# Narrative Hook Tests
# ---------------------------------------------------------------------------

class TestNarrativeHooks:
    """Tests for narrative hook generation for Narrator consumption."""

    @pytest.mark.anyio
    async def test_narrative_hooks_generated(self, arbiter: ArbiterAgent) -> None:
        """Test that narrative hooks are generated."""
        reasoning = f"action_type:{ActionType.ATTACK}|Test"
        result = await arbiter.act(reasoning)
        assert len(result.narrative_hooks) > 0

    @pytest.mark.anyio
    async def test_narrative_hooks_format(self, arbiter: ArbiterAgent) -> None:
        """Test that narrative hooks are brief sentences."""
        reasoning = f"action_type:{ActionType.ATTACK}|Test"
        result = await arbiter.act(reasoning)
        for hook in result.narrative_hooks:
            assert isinstance(hook, str)
            assert len(hook) > 0


# ---------------------------------------------------------------------------
# Context Building Tests
# ---------------------------------------------------------------------------

class TestContextBuilding:
    """Tests for prompt context building from campaign state."""

    def test_get_character_context(self, arbiter: ArbiterAgent) -> None:
        """Test character context extraction."""
        context = arbiter._get_character_context()
        assert "Thorin" in context
        assert "Fighter" in context
        assert "strength" in context.lower() or "Strength" in context

    def test_get_game_state_context(self, arbiter: ArbiterAgent) -> None:
        """Test game state context extraction."""
        context = arbiter._get_game_state_context()
        assert "Combat" in context or "combat" in context

    def test_get_rules_context_attack(self, arbiter: ArbiterAgent) -> None:
        """Test rules context for attack actions."""
        context = arbiter._get_rules_context(ActionType.ATTACK)
        assert "1d20" in context
        assert "AC" in context or "armor class" in context.lower()

    def test_get_rules_context_spell(self, arbiter: ArbiterAgent) -> None:
        """Test rules context for spell actions."""
        context = arbiter._get_rules_context(ActionType.SPELL)
        assert "spell" in context.lower()
        assert "DC" in context or "save" in context.lower()

    def test_get_rules_context_skill_check(self, arbiter: ArbiterAgent) -> None:
        """Test rules context for skill checks."""
        context = arbiter._get_rules_context(ActionType.SKILL_CHECK)
        assert "1d20" in context
        assert "DC" in context


# ---------------------------------------------------------------------------
# Pydantic Model Tests
# ---------------------------------------------------------------------------

class TestPydanticModels:
    """Tests for Pydantic model structure and validation."""

    def test_dice_roll_result_model(self) -> None:
        """Test DiceRollResult model."""
        roll = DiceRollResult(
            description="Attack roll",
            notation="1d20+5",
            result=18,
            success=True,
            dc=15,
        )
        assert roll.description == "Attack roll"
        assert roll.result == 18
        assert roll.success is True

    def test_state_change_model(self) -> None:
        """Test StateChange model."""
        change = StateChange(
            target="Goblin",
            change_type="hp",
            description="Takes damage",
            value=-10,
        )
        assert change.target == "Goblin"
        assert change.value == -10

    def test_mechanical_resolution_model(self) -> None:
        """Test MechanicalResolution model."""
        resolution = MechanicalResolution(
            success=True,
            dice_rolls=[],
            state_changes=[],
            rules_applied=["PHB p.194"],
            narrative_hooks=["Test hook"],
            reasoning="Test reasoning",
        )
        assert resolution.success is True
        assert len(resolution.narrative_hooks) == 1
