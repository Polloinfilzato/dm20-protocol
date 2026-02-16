"""
Unit tests for the PlayerCharacterAgent.

Tests cover:
- Agent initialization with character and personality
- Information barrier: restricted context building
- Reason phase: personality-influenced reasoning
- Act phase: LLM-driven decision making
- Observe phase: action extraction for orchestrator
- Fallback behavior when LLM fails
- Full ReAct cycle
- Integration with Orchestrator companion methods
"""

import asyncio
import json
import pytest
from typing import Any
from unittest.mock import AsyncMock

from dm20_protocol.models import (
    Character, CharacterClass, Race, AbilityScore
)
from dm20_protocol.claudmaster.base import AgentRole
from dm20_protocol.claudmaster.agents.player_character import (
    PlayerCharacterAgent,
    PCContext,
    PCDecision,
)
from dm20_protocol.claudmaster.companions import (
    CompanionArchetype,
    CombatStyle,
    PersonalityTraits,
)


# ── Backend fixture ───────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def sample_character() -> Character:
    """Create a sample fighter character."""
    return Character(
        name="Tormund",
        player_name="AI",
        character_class=CharacterClass(name="Fighter", level=5),
        race=Race(name="Human"),
        background="Soldier",
        alignment="Neutral Good",
        abilities={
            "strength": AbilityScore(score=18),
            "dexterity": AbilityScore(score=14),
            "constitution": AbilityScore(score=16),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=12),
            "charisma": AbilityScore(score=8),
        },
        bio="A gruff but loyal warrior who protects his companions.",
        description="Tall, scarred, wearing battered plate armor.",
    )


@pytest.fixture
def mock_llm() -> AsyncMock:
    """Create a mock LLM client that returns valid JSON."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=json.dumps({
        "action": "Raises shield and moves to protect the party.",
        "reasoning": "Enemies approaching — must defend allies.",
        "dialogue": "Stay behind me!",
        "target": "nearest goblin",
    }))
    return llm


@pytest.fixture
def tank_agent(sample_character: Character, mock_llm: AsyncMock) -> PlayerCharacterAgent:
    """Create a tank archetype PC agent."""
    return PlayerCharacterAgent(
        character=sample_character,
        llm=mock_llm,
        archetype=CompanionArchetype.TANK,
    )


@pytest.fixture
def healer_character() -> Character:
    """Create a sample cleric character."""
    return Character(
        name="Lyra",
        player_name="AI",
        character_class=CharacterClass(name="Cleric", level=5),
        race=Race(name="Half-Elf"),
        background="Acolyte",
        alignment="Lawful Good",
        abilities={
            "strength": AbilityScore(score=10),
            "dexterity": AbilityScore(score=12),
            "constitution": AbilityScore(score=14),
            "intelligence": AbilityScore(score=13),
            "wisdom": AbilityScore(score=18),
            "charisma": AbilityScore(score=15),
        },
        bio="A compassionate healer devoted to protecting the innocent.",
    )


# ── Initialization Tests ─────────────────────────────────────────────

class TestInitialization:
    """Tests for PlayerCharacterAgent initialization."""

    def test_agent_name_from_character(self, tank_agent: PlayerCharacterAgent) -> None:
        """Agent name is derived from character name."""
        assert tank_agent.name == "pc_agent_tormund"

    def test_agent_role(self, tank_agent: PlayerCharacterAgent) -> None:
        """Agent has PLAYER_CHARACTER role."""
        assert tank_agent.role == AgentRole.PLAYER_CHARACTER

    def test_archetype_applied(self, tank_agent: PlayerCharacterAgent) -> None:
        """Tank archetype is applied correctly."""
        assert tank_agent.archetype == CompanionArchetype.TANK

    def test_default_personality_from_archetype(self, tank_agent: PlayerCharacterAgent) -> None:
        """Default personality comes from archetype template."""
        # Tank template: bravery=80, aggression=40, caution=30
        assert tank_agent.personality.bravery == 80
        assert tank_agent.personality.caution == 30

    def test_custom_personality_overrides_template(
        self, sample_character: Character, mock_llm: AsyncMock
    ) -> None:
        """Custom personality overrides archetype defaults."""
        custom = PersonalityTraits(bravery=20, aggression=10, caution=90)
        agent = PlayerCharacterAgent(
            character=sample_character,
            llm=mock_llm,
            archetype=CompanionArchetype.TANK,
            personality=custom,
        )
        assert agent.personality.bravery == 20
        assert agent.personality.caution == 90

    def test_combat_style_from_archetype(self, tank_agent: PlayerCharacterAgent) -> None:
        """Combat style defaults from archetype template."""
        assert tank_agent.combat_style == CombatStyle.DEFENSIVE

    def test_name_with_spaces(self, mock_llm: AsyncMock) -> None:
        """Character names with spaces are handled in agent name."""
        char = Character(
            name="Sir Galahad",
            character_class=CharacterClass(name="Paladin", level=3),
            race=Race(name="Human"),
        )
        agent = PlayerCharacterAgent(character=char, llm=mock_llm)
        assert agent.name == "pc_agent_sir_galahad"


# ── Information Barrier Tests ─────────────────────────────────────────

class TestInformationBarrier:
    """Tests that the AI PC only sees restricted public context."""

    def test_restricted_context_has_character_sheet(self, tank_agent: PlayerCharacterAgent) -> None:
        """PC context includes full character sheet."""
        ctx = tank_agent.build_restricted_context({})
        assert "name" in ctx.character_sheet
        assert ctx.character_sheet["name"] == "Tormund"

    def test_restricted_context_excludes_id(self, tank_agent: PlayerCharacterAgent) -> None:
        """Character ID is excluded from context (internal detail)."""
        ctx = tank_agent.build_restricted_context({})
        assert "id" not in ctx.character_sheet

    def test_party_members_basic_info_only(
        self, tank_agent: PlayerCharacterAgent, healer_character: Character
    ) -> None:
        """Party member info only includes name, race, class — no stats."""
        ctx = tank_agent.build_restricted_context(
            {}, party_characters=[tank_agent.character, healer_character]
        )
        assert len(ctx.party_members) == 1  # Excludes self
        assert ctx.party_members[0]["name"] == "Lyra"
        assert ctx.party_members[0]["class"] == "Cleric"
        # No detailed stats
        assert "abilities" not in ctx.party_members[0]
        assert "hit_points" not in ctx.party_members[0]

    def test_no_secret_fields_in_context(self, tank_agent: PlayerCharacterAgent) -> None:
        """Full context secrets are NOT passed to PC context."""
        full_context = {
            "adventure_secrets": "The BBEG is hiding in room 5",
            "npc_bios": {"villain": "Secretly a lich"},
            "module_content": "Chapter 3: The Final Battle",
            "dm_notes": "TPK planned if they go left",
            "game_state": {"notes": "Party exploring cave", "in_combat": False},
        }
        ctx = tank_agent.build_restricted_context(full_context)

        # These should NOT appear anywhere in the context
        ctx_str = str(ctx.model_dump())
        assert "BBEG" not in ctx_str
        assert "lich" not in ctx_str
        assert "TPK" not in ctx_str

    def test_visible_environment_from_conversation(self, tank_agent: PlayerCharacterAgent) -> None:
        """Visible environment comes from last assistant message."""
        ctx = tank_agent.build_restricted_context({
            "conversation_history": [
                {"role": "user", "content": "I look around the room"},
                {"role": "assistant", "content": "The cavern is dimly lit by phosphorescent moss."},
            ],
        })
        assert "phosphorescent moss" in ctx.visible_environment

    def test_player_suggestion_passed_through(self, tank_agent: PlayerCharacterAgent) -> None:
        """Human player suggestions are available to the AI PC."""
        ctx = tank_agent.build_restricted_context({
            "player_suggestion": "Tormund, protect the healer!",
        })
        assert ctx.player_suggestion == "Tormund, protect the healer!"


# ── Reason Phase Tests ────────────────────────────────────────────────

class TestReasonPhase:
    """Tests for the reason() method."""

    @pytest.mark.anyio
    async def test_reason_includes_character_info(self, tank_agent: PlayerCharacterAgent) -> None:
        """Reasoning includes character name, class, and level."""
        result = await tank_agent.reason({"pc_context": PCContext().model_dump()})
        assert "Tormund" in result
        assert "Fighter" in result

    @pytest.mark.anyio
    async def test_reason_includes_personality_traits(self, tank_agent: PlayerCharacterAgent) -> None:
        """Reasoning reflects personality traits."""
        result = await tank_agent.reason({"pc_context": PCContext().model_dump()})
        assert "brave" in result.lower() or "brave_eager_to_act" in result

    @pytest.mark.anyio
    async def test_reason_includes_player_suggestion(self, tank_agent: PlayerCharacterAgent) -> None:
        """Reasoning includes human player's suggestion if provided."""
        ctx = PCContext(player_suggestion="Defend the entrance")
        result = await tank_agent.reason({"pc_context": ctx.model_dump()})
        assert "Defend the entrance" in result

    @pytest.mark.anyio
    async def test_reason_combat_flag(self, tank_agent: PlayerCharacterAgent) -> None:
        """Reasoning indicates combat state."""
        ctx = PCContext(in_combat=True)
        result = await tank_agent.reason({"pc_context": ctx.model_dump()})
        assert "in_combat:True" in result


# ── Act Phase Tests ───────────────────────────────────────────────────

class TestActPhase:
    """Tests for the act() method (LLM interaction)."""

    @pytest.mark.anyio
    async def test_act_returns_pc_decision(self, tank_agent: PlayerCharacterAgent) -> None:
        """Act returns a valid PCDecision."""
        result = await tank_agent.act("character:Tormund|class:Fighter|level:5")
        assert isinstance(result, PCDecision)
        assert "shield" in result.action.lower() or "protect" in result.action.lower()

    @pytest.mark.anyio
    async def test_act_calls_llm(self, tank_agent: PlayerCharacterAgent, mock_llm: AsyncMock) -> None:
        """Act calls the LLM with a prompt."""
        await tank_agent.act("character:Tormund|archetype:tank")
        mock_llm.generate.assert_called_once()

    @pytest.mark.anyio
    async def test_act_fallback_on_llm_error(
        self, sample_character: Character
    ) -> None:
        """Act returns fallback action if LLM fails."""
        error_llm = AsyncMock()
        error_llm.generate = AsyncMock(side_effect=RuntimeError("LLM down"))

        agent = PlayerCharacterAgent(
            character=sample_character,
            llm=error_llm,
            archetype=CompanionArchetype.TANK,
        )
        result = await agent.act("character:Tormund")
        assert isinstance(result, PCDecision)
        assert "defensive" in result.action.lower() or "shield" in result.action.lower()

    @pytest.mark.anyio
    async def test_act_handles_malformed_json(
        self, sample_character: Character
    ) -> None:
        """Act handles LLM returning non-JSON gracefully."""
        bad_llm = AsyncMock()
        bad_llm.generate = AsyncMock(return_value="I attack the goblin with my sword!")

        agent = PlayerCharacterAgent(
            character=sample_character,
            llm=bad_llm,
            archetype=CompanionArchetype.STRIKER,
        )
        result = await agent.act("character:Tormund")
        assert isinstance(result, PCDecision)
        assert "goblin" in result.action.lower() or len(result.action) > 0


# ── Observe Phase Tests ──────────────────────────────────────────────

class TestObservePhase:
    """Tests for the observe() method."""

    @pytest.mark.anyio
    async def test_observe_extracts_action(self, tank_agent: PlayerCharacterAgent) -> None:
        """Observe extracts action details from PCDecision."""
        decision = PCDecision(
            action="Charges at the goblin",
            reasoning="Must protect the healer",
            dialogue="For the party!",
            target="goblin",
        )
        obs = await tank_agent.observe(decision)
        assert obs["pc_name"] == "Tormund"
        assert obs["action"] == "Charges at the goblin"
        assert obs["dialogue"] == "For the party!"
        assert obs["target"] == "goblin"

    @pytest.mark.anyio
    async def test_observe_handles_non_decision(self, tank_agent: PlayerCharacterAgent) -> None:
        """Observe handles non-PCDecision results gracefully."""
        obs = await tank_agent.observe("I do something")
        assert obs["pc_name"] == "Tormund"
        assert "I do something" in obs["action"]


# ── Full ReAct Cycle Tests ───────────────────────────────────────────

class TestFullReActCycle:
    """Tests for the complete reason -> act -> observe cycle."""

    @pytest.mark.anyio
    async def test_full_run_cycle(self, tank_agent: PlayerCharacterAgent) -> None:
        """Full run() executes all three phases and returns AgentResponse."""
        context = {"pc_context": PCContext(in_combat=True).model_dump()}
        response = await tank_agent.run(context)

        assert response.agent_name == "pc_agent_tormund"
        assert response.agent_role == AgentRole.PLAYER_CHARACTER
        assert len(response.reasoning) > 0
        assert response.observations.get("pc_name") == "Tormund"
        assert response.observations.get("action") is not None


# ── PCContext Model Tests ─────────────────────────────────────────────

class TestPCContext:
    """Tests for the PCContext model."""

    def test_default_context(self) -> None:
        """Default PCContext has sensible empty defaults."""
        ctx = PCContext()
        assert ctx.character_sheet == {}
        assert ctx.party_members == []
        assert ctx.visible_environment == ""
        assert ctx.in_combat is False
        assert ctx.player_suggestion is None

    def test_context_with_data(self) -> None:
        """PCContext accepts and stores data correctly."""
        ctx = PCContext(
            character_sheet={"name": "Tormund", "level": 5},
            in_combat=True,
            player_suggestion="Help the wizard!",
        )
        assert ctx.character_sheet["name"] == "Tormund"
        assert ctx.in_combat is True
        assert ctx.player_suggestion == "Help the wizard!"


# ── Personality Description Tests ────────────────────────────────────

class TestPersonalityDescription:
    """Tests for personality-to-text conversion."""

    def test_brave_personality(self, sample_character: Character, mock_llm: AsyncMock) -> None:
        """High bravery produces 'brave' description."""
        agent = PlayerCharacterAgent(
            character=sample_character,
            llm=mock_llm,
            personality=PersonalityTraits(bravery=90),
        )
        desc = agent._describe_personality()
        assert "brave" in desc.lower()

    def test_cautious_personality(self, sample_character: Character, mock_llm: AsyncMock) -> None:
        """High caution produces 'careful' description."""
        agent = PlayerCharacterAgent(
            character=sample_character,
            llm=mock_llm,
            personality=PersonalityTraits(caution=80),
        )
        desc = agent._describe_personality()
        assert "careful" in desc.lower() or "methodical" in desc.lower()

    def test_balanced_personality(self, sample_character: Character, mock_llm: AsyncMock) -> None:
        """All-50 traits produce 'balanced' description."""
        agent = PlayerCharacterAgent(
            character=sample_character,
            llm=mock_llm,
            personality=PersonalityTraits(),
        )
        desc = agent._describe_personality()
        assert "balanced" in desc.lower()
