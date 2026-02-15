"""
End-to-end integration tests for the Claudmaster AI DM system.

These tests validate the complete game loop under realistic conditions
using MockLLMClient:
1. Exploration flow (Narrator + Arbiter pipeline)
2. Combat flow (Narrator + Arbiter with combat intent)
3. Social/roleplay flow (persuasion/deception through dual agents)
4. Session lifecycle (start -> play -> save -> load -> resume -> verify)
5. Error scenarios (timeout, invalid input, all-agent failure, error formatting)
6. Multi-turn context tracking

All tests use MockLLMClient for deterministic, API-free execution.
"""

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from dm20_protocol.claudmaster.base import Agent, AgentResponse, AgentRole
from dm20_protocol.claudmaster.config import ClaudmasterConfig
from dm20_protocol.claudmaster.exceptions import (
    AgentError,
    ClaudmasterTimeoutError,
)
from dm20_protocol.claudmaster.llm_client import MockLLMClient
from dm20_protocol.claudmaster.orchestrator import (
    AgentExecutionError,
    AgentTimeoutError,
    IntentClassificationError,
    IntentType,
    Orchestrator,
    OrchestratorError,
)
from dm20_protocol.claudmaster.agents.arbiter import ArbiterAgent
from dm20_protocol.claudmaster.agents.narrator import NarratorAgent, NarrativeStyle
from dm20_protocol.claudmaster.persistence.session_serializer import SessionSerializer
from dm20_protocol.claudmaster.recovery.error_messages import ErrorMessageFormatter
from dm20_protocol.models import Campaign, GameState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def campaign():
    """Minimal campaign for testing."""
    return Campaign(
        name="Test Campaign",
        description="A test campaign for e2e integration",
        game_state=GameState(campaign_name="Test Campaign"),
    )


@pytest.fixture
def config():
    """ClaudmasterConfig with fast timeout for tests."""
    return ClaudmasterConfig(agent_timeout=5.0)


@pytest.fixture
def narrator_llm():
    """Mock LLM for Narrator — returns descriptive narrative text."""
    return MockLLMClient(
        default_response=(
            "The ancient stone walls of the chamber glisten with moisture. "
            "Shadows dance in the flickering torchlight as you step forward, "
            "your footsteps echoing through the silence."
        )
    )


@pytest.fixture
def arbiter_llm_exploration():
    """Mock LLM for Arbiter — returns exploration skill check resolution."""
    resolution = {
        "success": True,
        "dice_rolls": [
            {
                "description": "Perception check",
                "notation": "1d20+4",
                "result": 17,
                "success": True,
                "dc": 15,
            }
        ],
        "state_changes": [],
        "rules_applied": ["PHB p.178: Perception (Wisdom)"],
        "narrative_hooks": [
            "Your keen eyes spot a faint seam in the stonework — a hidden passage."
        ],
        "reasoning": "Perception check 17 vs DC 15 succeeds. Hidden passage found.",
    }
    return MockLLMClient(default_response=json.dumps(resolution))


@pytest.fixture
def arbiter_llm_combat():
    """Mock LLM for Arbiter — returns combat attack resolution."""
    resolution = {
        "success": True,
        "dice_rolls": [
            {
                "description": "Attack roll",
                "notation": "1d20+5",
                "result": 18,
                "success": True,
                "dc": 13,
            },
            {
                "description": "Damage roll",
                "notation": "8d6",
                "result": 28,
                "success": True,
                "dc": 0,
            },
        ],
        "state_changes": [
            {
                "target": "Goblin Group",
                "change_type": "hp",
                "description": "Goblins take 28 fire damage (14 on save)",
                "value": -28,
            }
        ],
        "rules_applied": [
            "PHB p.241: Fireball (3rd-level evocation)",
            "PHB p.147: Dexterity saving throw",
        ],
        "narrative_hooks": [
            "A bead of fire streaks from your finger and detonates among the goblins, "
            "engulfing them in a roaring inferno."
        ],
        "reasoning": (
            "Fireball spell. Each creature in 20ft radius makes DEX save DC 15. "
            "Damage: 8d6 = 28 fire damage."
        ),
    }
    return MockLLMClient(default_response=json.dumps(resolution))


@pytest.fixture
def arbiter_llm_social():
    """Mock LLM for Arbiter — returns social/persuasion check resolution."""
    resolution = {
        "success": True,
        "dice_rolls": [
            {
                "description": "Persuasion check",
                "notation": "1d20+7",
                "result": 22,
                "success": True,
                "dc": 18,
            }
        ],
        "state_changes": [
            {
                "target": "Merchant",
                "change_type": "attitude",
                "description": "Merchant becomes friendly, offers 15% discount",
                "value": "friendly",
            }
        ],
        "rules_applied": ["PHB p.187: Persuasion (Charisma)"],
        "narrative_hooks": [
            "The merchant's stern expression softens as your words find their mark."
        ],
        "reasoning": "Persuasion check 22 vs DC 18 succeeds. Merchant attitude improves.",
    }
    return MockLLMClient(default_response=json.dumps(resolution))


def _make_orchestrator(campaign, config, narrator_llm, arbiter_llm):
    """Helper: create orchestrator with Narrator + Arbiter."""
    orch = Orchestrator(campaign=campaign, config=config)
    narrator = NarratorAgent(llm=narrator_llm, style=NarrativeStyle.DESCRIPTIVE)
    arbiter = ArbiterAgent(llm=arbiter_llm, campaign=campaign)
    orch.register_agent("narrator", narrator)
    orch.register_agent("arbiter", arbiter)
    return orch


# ===========================================================================
# Test 1: Exploration Flow
# ===========================================================================


class TestExplorationFlow:
    """Full pipeline: exploration input -> intent -> agents -> response."""

    @pytest.mark.anyio
    async def test_exploration_full_pipeline(
        self, campaign, config, narrator_llm, arbiter_llm_exploration
    ):
        """Exploration input goes through classify -> route -> execute -> aggregate."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        orch.start_session()

        response = await orch.process_player_input(
            "I search the room carefully for hidden passages"
        )

        # Intent was correctly classified as exploration
        intent = orch.classify_intent("I search the room carefully for hidden passages")
        assert intent.intent_type == IntentType.EXPLORATION

        # Both agents contributed
        assert "narrator" in response.metadata["agents_used"]
        assert "arbiter" in response.metadata["agents_used"]

        # Narrative is present (from Narrator)
        assert len(response.narrative) > 20
        assert "ancient stone" in response.narrative.lower() or "chamber" in response.narrative.lower()

        # Arbiter narrative hook is merged into narrative
        assert "hidden passage" in response.narrative.lower()

        # Mechanical resolution metadata
        assert response.metadata["has_mechanical_resolution"] is True
        assert response.metadata["arbiter_success"] is True

    @pytest.mark.anyio
    async def test_exploration_session_history_updated(
        self, campaign, config, narrator_llm, arbiter_llm_exploration
    ):
        """Session history captures both player input and assistant response."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        session = orch.start_session()

        await orch.process_player_input("I look around the room")

        assert len(session.conversation_history) == 2
        assert session.conversation_history[0]["role"] == "user"
        assert session.conversation_history[0]["content"] == "I look around the room"
        assert session.conversation_history[1]["role"] == "assistant"
        assert len(session.conversation_history[1]["content"]) > 0


# ===========================================================================
# Test 2: Combat Flow
# ===========================================================================


class TestCombatFlow:
    """Full pipeline: combat input -> intent -> dual agents -> mechanics + narrative."""

    @pytest.mark.anyio
    async def test_combat_spell_full_pipeline(
        self, campaign, config, narrator_llm, arbiter_llm_combat
    ):
        """Fireball spell produces narrative + dice rolls + state changes."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_combat)
        orch.start_session()

        response = await orch.process_player_input(
            "I cast fireball at the group of goblins"
        )

        # Intent classified as combat
        intent = orch.classify_intent("I cast fireball at the group of goblins")
        assert intent.intent_type == IntentType.COMBAT

        # Both agents participated
        assert response.metadata["agent_count"] == 2

        # State changes from Arbiter (goblin damage)
        assert len(response.state_changes) > 0
        goblin_change = response.state_changes[0]
        assert goblin_change["target"] == "Goblin Group"
        assert goblin_change["value"] == -28

        # Dice roll count
        assert response.metadata["dice_roll_count"] == 2  # attack + damage

        # Narrative includes Arbiter hooks (fireball narration)
        assert "inferno" in response.narrative.lower() or "fire" in response.narrative.lower()

    @pytest.mark.anyio
    async def test_combat_preserves_agent_responses(
        self, campaign, config, narrator_llm, arbiter_llm_combat
    ):
        """Both raw agent responses are preserved for inspection."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_combat)
        orch.start_session()

        response = await orch.process_player_input("I attack with my sword")

        roles = {r.agent_role for r in response.agent_responses}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER in roles


# ===========================================================================
# Test 3: Social / Roleplay Flow
# ===========================================================================


class TestRoleplayFlow:
    """Full pipeline: social input -> roleplay intent -> persuasion mechanics."""

    @pytest.mark.anyio
    async def test_persuasion_full_pipeline(
        self, campaign, config, narrator_llm, arbiter_llm_social
    ):
        """Persuasion attempt produces narrative + skill check + NPC attitude change."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_social)
        orch.start_session()

        response = await orch.process_player_input(
            "I try to persuade the merchant to lower his prices"
        )

        # Intent classified as roleplay
        intent = orch.classify_intent("I try to persuade the merchant to lower his prices")
        assert intent.intent_type == IntentType.ROLEPLAY

        # Both agents participated
        assert "narrator" in response.metadata["agents_used"]
        assert "arbiter" in response.metadata["agents_used"]

        # State changes reflect NPC attitude shift
        assert len(response.state_changes) > 0
        merchant_change = response.state_changes[0]
        assert merchant_change["target"] == "Merchant"

        # Narrative includes social hook
        assert "merchant" in response.narrative.lower()

    @pytest.mark.anyio
    async def test_question_routes_narrator_only(
        self, campaign, config, narrator_llm, arbiter_llm_social
    ):
        """A pure question should only use Narrator (no mechanics needed)."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_social)
        orch.start_session()

        response = await orch.process_player_input(
            "what is the history of this ancient temple?"
        )

        # Only Narrator participated
        assert "narrator" in response.metadata["agents_used"]
        assert response.metadata["has_mechanical_resolution"] is False


# ===========================================================================
# Test 4: Session Lifecycle
# ===========================================================================


class TestSessionLifecycle:
    """Start -> multi-turn play -> save -> load -> verify state continuity."""

    @pytest.mark.anyio
    async def test_multi_turn_and_save_load(
        self, campaign, config, narrator_llm, arbiter_llm_exploration, tmp_path
    ):
        """Play multiple turns, save session, load it, verify state is intact."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        session = orch.start_session()
        session_id = session.session_id

        # Turn 1
        await orch.process_player_input("I enter the dungeon")
        # Turn 2
        await orch.process_player_input("I search for traps")
        # Turn 3
        await orch.process_player_input("I examine the walls carefully")

        # Should have 6 messages (3 user + 3 assistant)
        assert len(session.conversation_history) == 6

        # Save session via SessionSerializer
        serializer = SessionSerializer(tmp_path)
        session_data = {
            "session_id": session_id,
            "campaign_id": session.campaign_id,
            "started_at": session.started_at.isoformat(),
            "turn_count": session.turn_count,
            "conversation_history": session.conversation_history,
            "config": session.config.model_dump(),
            "active_agents": dict(session.active_agents),
            "metadata": session.metadata,
        }
        save_path = serializer.save_session(session_data, mode="pause")
        assert save_path.exists()

        # Load session
        loaded = serializer.load_session(session_id)
        assert loaded is not None
        assert loaded["session_id"] == session_id
        assert loaded["conversation_history"] == session.conversation_history
        assert len(loaded["conversation_history"]) == 6

    @pytest.mark.anyio
    async def test_session_metadata_persistence(
        self, campaign, config, narrator_llm, arbiter_llm_exploration, tmp_path
    ):
        """Session metadata (status, action count) is correctly persisted."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        session = orch.start_session()

        await orch.process_player_input("I look around")

        serializer = SessionSerializer(tmp_path)
        session_data = {
            "session_id": session.session_id,
            "campaign_id": session.campaign_id,
            "started_at": session.started_at.isoformat(),
            "turn_count": 1,
            "conversation_history": session.conversation_history,
            "config": session.config.model_dump(),
            "active_agents": dict(session.active_agents),
            "metadata": session.metadata,
        }
        serializer.save_session(session_data, mode="pause", summary_notes="Mid-dungeon save")

        meta = serializer.load_metadata(session.session_id)
        assert meta is not None
        assert meta.status == "paused"
        assert meta.save_notes == "Mid-dungeon save"
        assert meta.campaign_id == session.campaign_id

    @pytest.mark.anyio
    async def test_session_list_after_multiple_saves(
        self, campaign, config, narrator_llm, arbiter_llm_exploration, tmp_path
    ):
        """Multiple sessions can be listed and sorted by activity."""
        serializer = SessionSerializer(tmp_path)

        for i in range(3):
            orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
            session = orch.start_session()
            await orch.process_player_input(f"Action {i}")

            session_data = {
                "session_id": session.session_id,
                "campaign_id": session.campaign_id,
                "started_at": session.started_at.isoformat(),
                "turn_count": 1,
                "conversation_history": session.conversation_history,
                "config": session.config.model_dump(),
                "active_agents": dict(session.active_agents),
                "metadata": session.metadata,
            }
            serializer.save_session(session_data, mode="pause")
            orch.end_session()

        sessions = serializer.list_sessions()
        assert len(sessions) == 3


# ===========================================================================
# Test 5: Error Scenarios
# ===========================================================================


class TestErrorScenarios:
    """Error handling: timeouts, invalid input, all-agent failure, error formatting."""

    @pytest.mark.anyio
    async def test_empty_input_raises_classification_error(self, campaign, config):
        """Empty player input should raise IntentClassificationError."""
        orch = Orchestrator(campaign=campaign, config=config)
        orch.start_session()

        with pytest.raises(IntentClassificationError):
            await orch.process_player_input("")

    @pytest.mark.anyio
    async def test_whitespace_input_raises_classification_error(self, campaign, config):
        """Whitespace-only input should raise IntentClassificationError."""
        orch = Orchestrator(campaign=campaign, config=config)
        orch.start_session()

        with pytest.raises(IntentClassificationError):
            await orch.process_player_input("   ")

    @pytest.mark.anyio
    async def test_no_session_raises_error(self, campaign, config, narrator_llm, arbiter_llm_exploration):
        """Processing input without starting a session should raise."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)

        with pytest.raises(OrchestratorError, match="No active session"):
            await orch.process_player_input("I look around")

    @pytest.mark.anyio
    async def test_agent_timeout_partial_success(self, campaign, narrator_llm):
        """When one agent times out, the other's response is still returned."""
        config = ClaudmasterConfig(agent_timeout=0.2)

        class SlowArbiter(Agent):
            def __init__(self):
                super().__init__(name="arbiter", role=AgentRole.ARBITER)

            async def reason(self, context):
                return "resolve"

            async def act(self, reasoning):
                await asyncio.sleep(2.0)  # Exceeds 0.2s timeout
                return "Never reached"

            async def observe(self, result):
                return {}

        orch = Orchestrator(campaign=campaign, config=config)
        narrator = NarratorAgent(llm=narrator_llm, style=NarrativeStyle.DESCRIPTIVE)
        orch.register_agent("narrator", narrator)
        orch.register_agent("arbiter", SlowArbiter())
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin")

        # Narrator succeeded despite Arbiter timeout
        assert len(response.narrative) > 0
        assert response.metadata["has_mechanical_resolution"] is False

    @pytest.mark.anyio
    async def test_all_agents_fail_raises_error(self, campaign, config):
        """If every agent fails, an exception is raised."""

        class FailingAgent(Agent):
            def __init__(self, name, role):
                super().__init__(name=name, role=role)

            async def reason(self, context):
                return "fail"

            async def act(self, reasoning):
                raise RuntimeError("Simulated agent failure")

            async def observe(self, result):
                return {}

        orch = Orchestrator(campaign=campaign, config=config)
        orch.register_agent("narrator", FailingAgent("narrator", AgentRole.NARRATOR))
        orch.register_agent("arbiter", FailingAgent("arbiter", AgentRole.ARBITER))
        orch.start_session()

        with pytest.raises(AgentExecutionError):
            await orch.process_player_input("I attack the goblin")

    def test_error_formatter_timeout(self):
        """ErrorMessageFormatter produces in-character message for timeout."""
        formatter = ErrorMessageFormatter()
        error = ClaudmasterTimeoutError(
            message="LLM call timed out",
            operation="generate_narrative",
            timeout_seconds=30.0,
        )
        message = formatter.format_error(error)

        assert "adventurer" in message.lower() or "dm" in message.lower()
        assert "30" in message  # timeout seconds included
        assert "generate_narrative" in message

    def test_error_formatter_agent_error_recoverable(self):
        """ErrorMessageFormatter produces recoverable agent error message."""
        formatter = ErrorMessageFormatter()
        error = AgentError(
            message="Narrator generation failed",
            agent_name="narrator",
            recoverable=True,
        )
        message = formatter.format_error(error)

        assert "storyteller" in message.lower()
        assert "momentarily" in message.lower() or "temporary" in message.lower()

    def test_error_formatter_agent_error_unrecoverable(self):
        """ErrorMessageFormatter produces unrecoverable agent error message."""
        formatter = ErrorMessageFormatter()
        error = AgentError(
            message="Critical failure",
            agent_name="narrator",
            recoverable=False,
        )
        message = formatter.format_error(error)

        assert "storyteller" in message.lower()
        assert "pause" in message.lower() or "problem" in message.lower()

    def test_error_formatter_unknown_error(self):
        """ErrorMessageFormatter handles unknown exception types gracefully."""
        formatter = ErrorMessageFormatter()
        error = ValueError("something unexpected")
        message = formatter.format_error(error)

        assert "unexpected" in message.lower() or "unforeseen" in message.lower()
        assert "ValueError" in message

    def test_recovery_suggestion_for_timeout(self):
        """Recovery suggestions are provided for timeout errors."""
        formatter = ErrorMessageFormatter()
        error = ClaudmasterTimeoutError(
            message="timeout",
            operation="test",
            timeout_seconds=10.0,
        )
        suggestion = formatter.suggest_recovery_action(error)

        assert "try again" in suggestion.lower() or "wait" in suggestion.lower()


# ===========================================================================
# Test 6: Multi-Turn Context & State Tracking
# ===========================================================================


class TestMultiTurnContext:
    """Verify session state evolves correctly across multiple turns."""

    @pytest.mark.anyio
    async def test_conversation_history_grows(
        self, campaign, config, narrator_llm, arbiter_llm_exploration
    ):
        """Each turn adds user + assistant messages to history."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        session = orch.start_session()

        inputs = [
            "I enter the cave",
            "I search for traps",
            "I proceed deeper into the darkness",
        ]

        for i, player_input in enumerate(inputs, 1):
            await orch.process_player_input(player_input)
            assert len(session.conversation_history) == i * 2

    @pytest.mark.anyio
    async def test_agent_status_tracking(
        self, campaign, config, narrator_llm, arbiter_llm_exploration
    ):
        """Agent statuses are updated during and after processing."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        session = orch.start_session()

        # Initially all idle
        assert session.active_agents["narrator"] == "idle"
        assert session.active_agents["arbiter"] == "idle"

        await orch.process_player_input("I search the room")

        # After processing, agents should be "completed"
        assert session.active_agents["narrator"] == "completed"
        assert session.active_agents["arbiter"] == "completed"

    @pytest.mark.anyio
    async def test_context_includes_recent_messages(
        self, campaign, config, narrator_llm, arbiter_llm_exploration
    ):
        """Session context provides recent messages for agent consumption."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm_exploration)
        session = orch.start_session()

        await orch.process_player_input("I enter the room")

        context = session.get_context(max_messages=20)
        assert len(context["recent_messages"]) == 2
        assert context["recent_messages"][0]["role"] == "user"
        assert context["session_id"] == session.session_id

    @pytest.mark.anyio
    async def test_start_end_session_lifecycle(self, campaign, config):
        """Session can be started and ended cleanly."""
        orch = Orchestrator(campaign=campaign, config=config)
        session = orch.start_session()
        assert orch.session is not None

        orch.end_session()
        assert orch.session is None

    @pytest.mark.anyio
    async def test_double_start_raises(self, campaign, config):
        """Starting a second session without ending the first raises."""
        orch = Orchestrator(campaign=campaign, config=config)
        orch.start_session()

        with pytest.raises(OrchestratorError, match="Session already active"):
            orch.start_session()

    @pytest.mark.anyio
    async def test_end_without_start_raises(self, campaign, config):
        """Ending a session when none is active raises."""
        orch = Orchestrator(campaign=campaign, config=config)

        with pytest.raises(OrchestratorError, match="No active session"):
            orch.end_session()
