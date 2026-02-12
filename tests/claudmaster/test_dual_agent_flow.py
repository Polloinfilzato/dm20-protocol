"""
Tests for the dual-agent response architecture (Narrator + Arbiter).

These tests verify:
1. Orchestrator routes to both Narrator and Arbiter for combat/action intents
2. Agents execute in parallel (not sequentially)
3. Response aggregation merges narrative + mechanical results
4. Narrative hooks from Arbiter are appended to the narrative
5. State changes from Arbiter appear in the aggregated response
6. Partial failures (one agent fails) are handled gracefully
"""

import asyncio
import json
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dm20_protocol.claudmaster.base import Agent, AgentResponse, AgentRole
from dm20_protocol.claudmaster.config import ClaudmasterConfig
from dm20_protocol.claudmaster.orchestrator import (
    IntentType,
    Orchestrator,
    OrchestratorResponse,
    AgentTimeoutError,
    AgentExecutionError,
)
from dm20_protocol.claudmaster.agents.narrator import NarratorAgent, NarrativeStyle
from dm20_protocol.claudmaster.agents.arbiter import ArbiterAgent, MechanicalResolution
from dm20_protocol.claudmaster.llm_client import MockLLMClient
from dm20_protocol.models import Campaign, GameState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def campaign():
    """Create a minimal campaign for testing."""
    return Campaign(
        name="Test Campaign",
        description="A test campaign",
        game_state=GameState(campaign_name="Test Campaign"),
    )


@pytest.fixture
def config():
    """Create a ClaudmasterConfig with fast timeout for tests."""
    return ClaudmasterConfig(agent_timeout=5.0)


@pytest.fixture
def narrator_llm():
    """Mock LLM for Narrator (returns narrative text)."""
    return MockLLMClient(
        default_response="The goblin snarls as your blade arcs through the air."
    )


@pytest.fixture
def arbiter_llm():
    """Mock LLM for Arbiter (returns JSON mechanical resolution)."""
    resolution = {
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
        "narrative_hooks": ["Your blade strikes true, cutting deep into the goblin's shoulder."],
        "reasoning": "Melee attack roll 18 vs AC 13 hits. Damage: 1d8+3 = 8.",
    }
    return MockLLMClient(default_response=json.dumps(resolution))


@pytest.fixture
def orchestrator_with_dual_agents(campaign, config, narrator_llm, arbiter_llm):
    """Create an orchestrator with both Narrator and Arbiter registered."""
    orch = Orchestrator(campaign=campaign, config=config)

    narrator = NarratorAgent(llm=narrator_llm, style=NarrativeStyle.DESCRIPTIVE)
    arbiter = ArbiterAgent(llm=arbiter_llm, campaign=campaign)

    orch.register_agent("narrator", narrator)
    orch.register_agent("arbiter", arbiter)

    return orch


# ---------------------------------------------------------------------------
# Test: Agent Routing
# ---------------------------------------------------------------------------


class TestDualAgentRouting:
    """Test that the orchestrator routes to both agents for appropriate intents."""

    def test_combat_routes_to_narrator_and_arbiter(self, orchestrator_with_dual_agents):
        """Combat intent should route to both Narrator and Arbiter."""
        orch = orchestrator_with_dual_agents
        intent = orch.classify_intent("I attack the goblin with my sword")
        agents = orch._get_agents_for_intent(intent)

        roles = {a.role for a in agents}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER in roles

    def test_action_routes_to_narrator_and_arbiter(self, orchestrator_with_dual_agents):
        """General action intent should route to Narrator and Arbiter."""
        orch = orchestrator_with_dual_agents
        intent = orch.classify_intent("I try to climb the wall")
        agents = orch._get_agents_for_intent(intent)

        roles = {a.role for a in agents}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER in roles

    def test_exploration_routes_to_narrator_and_arbiter(self, orchestrator_with_dual_agents):
        """Exploration intent should include Arbiter for skill checks."""
        orch = orchestrator_with_dual_agents
        intent = orch.classify_intent("I search the room for traps")
        agents = orch._get_agents_for_intent(intent)

        roles = {a.role for a in agents}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER in roles

    def test_question_routes_to_narrator_only(self, orchestrator_with_dual_agents):
        """Question intent should not include Arbiter (no mechanics needed)."""
        orch = orchestrator_with_dual_agents
        intent = orch.classify_intent("what is the history of this castle?")
        agents = orch._get_agents_for_intent(intent)

        roles = {a.role for a in agents}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER not in roles

    def test_system_routes_to_narrator_only(self, orchestrator_with_dual_agents):
        """System commands should not include Arbiter."""
        orch = orchestrator_with_dual_agents
        intent = orch.classify_intent("show my inventory")
        agents = orch._get_agents_for_intent(intent)

        roles = {a.role for a in agents}
        assert AgentRole.NARRATOR in roles
        # System routes to Archivist, not Arbiter
        assert AgentRole.ARBITER not in roles

    def test_roleplay_routes_to_narrator_and_arbiter(self, orchestrator_with_dual_agents):
        """Roleplay may need Arbiter for persuasion/deception checks."""
        orch = orchestrator_with_dual_agents
        intent = orch.classify_intent("I try to persuade the guard to let us through")
        agents = orch._get_agents_for_intent(intent)

        roles = {a.role for a in agents}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER in roles


# ---------------------------------------------------------------------------
# Test: Parallel Execution
# ---------------------------------------------------------------------------


class TestParallelExecution:
    """Test that agents run in parallel, not sequentially."""

    @pytest.mark.anyio
    async def test_agents_run_concurrently(self, campaign, config):
        """Both agents should start ~simultaneously, not wait for each other."""
        execution_log = []

        class SlowNarrator(Agent):
            def __init__(self):
                super().__init__(name="narrator", role=AgentRole.NARRATOR)

            async def reason(self, context):
                return "narrate"

            async def act(self, reasoning):
                execution_log.append(("narrator_start", time.monotonic()))
                await asyncio.sleep(0.1)
                execution_log.append(("narrator_end", time.monotonic()))
                return "The scene unfolds..."

            async def observe(self, result):
                return {"word_count": 3}

        class SlowArbiter(Agent):
            def __init__(self):
                super().__init__(name="arbiter", role=AgentRole.ARBITER)

            async def reason(self, context):
                return "resolve"

            async def act(self, reasoning):
                execution_log.append(("arbiter_start", time.monotonic()))
                await asyncio.sleep(0.1)
                execution_log.append(("arbiter_end", time.monotonic()))
                return MechanicalResolution(
                    success=True, reasoning="mock", narrative_hooks=["Hit!"]
                )

            async def observe(self, result):
                return {"success": True, "narrative_hooks": ["Hit!"]}

        orch = Orchestrator(campaign=campaign, config=config)
        orch.register_agent("narrator", SlowNarrator())
        orch.register_agent("arbiter", SlowArbiter())
        orch.start_session()

        await orch.process_player_input("I attack the goblin")

        # Both agents should have started before either finished
        starts = [t for name, t in execution_log if name.endswith("_start")]
        ends = [t for name, t in execution_log if name.endswith("_end")]

        assert len(starts) == 2
        assert len(ends) == 2

        # The gap between the two start times should be small (< 50ms)
        # If sequential, it would be ~100ms apart
        start_gap = abs(starts[1] - starts[0])
        assert start_gap < 0.05, f"Agents started {start_gap:.3f}s apart — not parallel!"

    @pytest.mark.anyio
    async def test_total_time_is_max_not_sum(self, campaign, config):
        """Total execution time should be ~max(agent_times), not sum."""

        class TimedNarrator(Agent):
            def __init__(self):
                super().__init__(name="narrator", role=AgentRole.NARRATOR)

            async def reason(self, context):
                return "narrate"

            async def act(self, reasoning):
                await asyncio.sleep(0.1)
                return "Narrative text"

            async def observe(self, result):
                return {}

        class TimedArbiter(Agent):
            def __init__(self):
                super().__init__(name="arbiter", role=AgentRole.ARBITER)

            async def reason(self, context):
                return "resolve"

            async def act(self, reasoning):
                await asyncio.sleep(0.15)
                return MechanicalResolution(
                    success=True, reasoning="mock", narrative_hooks=[]
                )

            async def observe(self, result):
                return {"success": True}

        orch = Orchestrator(campaign=campaign, config=config)
        orch.register_agent("narrator", TimedNarrator())
        orch.register_agent("arbiter", TimedArbiter())
        orch.start_session()

        start = time.monotonic()
        await orch.process_player_input("I attack")
        elapsed = time.monotonic() - start

        # If parallel: elapsed ~ 0.15s. If sequential: elapsed ~ 0.25s
        assert elapsed < 0.22, f"Took {elapsed:.3f}s — agents likely ran sequentially"


# ---------------------------------------------------------------------------
# Test: Response Aggregation
# ---------------------------------------------------------------------------


class TestResponseAggregation:
    """Test that dual-agent responses are merged correctly."""

    @pytest.mark.anyio
    async def test_narrative_hooks_appended(self, orchestrator_with_dual_agents):
        """Arbiter narrative hooks should appear in the final narrative."""
        orch = orchestrator_with_dual_agents
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin with my sword")

        assert "goblin snarls" in response.narrative.lower() or "blade arcs" in response.narrative.lower()
        assert "strikes true" in response.narrative.lower()

    @pytest.mark.anyio
    async def test_state_changes_from_arbiter(self, orchestrator_with_dual_agents):
        """Arbiter state changes should appear in the aggregated response."""
        orch = orchestrator_with_dual_agents
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin with my sword")

        assert len(response.state_changes) > 0
        goblin_change = response.state_changes[0]
        assert goblin_change["target"] == "Goblin"
        assert goblin_change["type"] == "hp"
        assert goblin_change["value"] == -8

    @pytest.mark.anyio
    async def test_metadata_includes_arbiter_info(self, orchestrator_with_dual_agents):
        """Response metadata should include Arbiter mechanical summary."""
        orch = orchestrator_with_dual_agents
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin")

        assert response.metadata["has_mechanical_resolution"] is True
        assert response.metadata["arbiter_success"] is True
        assert response.metadata["dice_roll_count"] == 1

    @pytest.mark.anyio
    async def test_both_agent_responses_preserved(self, orchestrator_with_dual_agents):
        """Both raw agent responses should be preserved in the response."""
        orch = orchestrator_with_dual_agents
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin")

        roles = {r.agent_role for r in response.agent_responses}
        assert AgentRole.NARRATOR in roles
        assert AgentRole.ARBITER in roles

    @pytest.mark.anyio
    async def test_no_arbiter_means_no_mechanical_metadata(self, campaign, config, narrator_llm):
        """When no Arbiter is registered, metadata should reflect that."""
        orch = Orchestrator(campaign=campaign, config=config)
        narrator = NarratorAgent(llm=narrator_llm, style=NarrativeStyle.DESCRIPTIVE)
        orch.register_agent("narrator", narrator)
        orch.start_session()

        response = await orch.process_player_input("what is that sound?")

        assert response.metadata["has_mechanical_resolution"] is False


# ---------------------------------------------------------------------------
# Test: Partial Failures
# ---------------------------------------------------------------------------


class TestPartialFailures:
    """Test graceful handling when one agent fails but the other succeeds."""

    @pytest.mark.anyio
    async def test_arbiter_failure_still_returns_narrative(self, campaign, config, narrator_llm):
        """If Arbiter fails, Narrator response should still be returned."""

        class FailingArbiter(Agent):
            def __init__(self):
                super().__init__(name="arbiter", role=AgentRole.ARBITER)

            async def reason(self, context):
                return "resolve"

            async def act(self, reasoning):
                raise RuntimeError("LLM API error")

            async def observe(self, result):
                return {}

        orch = Orchestrator(campaign=campaign, config=config)
        narrator = NarratorAgent(llm=narrator_llm, style=NarrativeStyle.DESCRIPTIVE)
        orch.register_agent("narrator", narrator)
        orch.register_agent("arbiter", FailingArbiter())
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin")

        # Narrator should still succeed
        assert len(response.narrative) > 0
        assert "goblin snarls" in response.narrative.lower() or "blade arcs" in response.narrative.lower()

    @pytest.mark.anyio
    async def test_narrator_failure_still_returns_arbiter_fallback(self, campaign, config, arbiter_llm):
        """If Narrator fails, Arbiter results should still be accessible."""

        class FailingNarrator(Agent):
            def __init__(self):
                super().__init__(name="narrator", role=AgentRole.NARRATOR)

            async def reason(self, context):
                return "narrate"

            async def act(self, reasoning):
                raise RuntimeError("LLM connection timeout")

            async def observe(self, result):
                return {}

        orch = Orchestrator(campaign=campaign, config=config)
        arbiter = ArbiterAgent(llm=arbiter_llm, campaign=campaign)
        orch.register_agent("narrator", FailingNarrator())
        orch.register_agent("arbiter", arbiter)
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin")

        # Arbiter should have succeeded — its response should be in agent_responses
        assert len(response.agent_responses) >= 1
        arbiter_resp = next(
            (r for r in response.agent_responses if r.agent_role == AgentRole.ARBITER),
            None,
        )
        assert arbiter_resp is not None

    @pytest.mark.anyio
    async def test_all_agents_fail_raises_error(self, campaign, config):
        """If ALL agents fail, an error should be raised."""

        class FailingAgent(Agent):
            def __init__(self, name, role):
                super().__init__(name=name, role=role)

            async def reason(self, context):
                return "fail"

            async def act(self, reasoning):
                raise RuntimeError("Everything is broken")

            async def observe(self, result):
                return {}

        orch = Orchestrator(campaign=campaign, config=config)
        orch.register_agent("narrator", FailingAgent("narrator", AgentRole.NARRATOR))
        orch.register_agent("arbiter", FailingAgent("arbiter", AgentRole.ARBITER))
        orch.start_session()

        with pytest.raises(AgentExecutionError):
            await orch.process_player_input("I attack the goblin")

    @pytest.mark.anyio
    async def test_timeout_one_agent_other_succeeds(self, campaign, narrator_llm):
        """If one agent times out but other succeeds, response is still returned."""
        config = ClaudmasterConfig(agent_timeout=0.2)

        class SlowArbiter(Agent):
            def __init__(self):
                super().__init__(name="arbiter", role=AgentRole.ARBITER)

            async def reason(self, context):
                return "resolve"

            async def act(self, reasoning):
                await asyncio.sleep(1.0)  # Will timeout
                return "Never reached"

            async def observe(self, result):
                return {}

        orch = Orchestrator(campaign=campaign, config=config)
        narrator = NarratorAgent(llm=narrator_llm, style=NarrativeStyle.DESCRIPTIVE)
        orch.register_agent("narrator", narrator)
        orch.register_agent("arbiter", SlowArbiter())
        orch.start_session()

        response = await orch.process_player_input("I attack the goblin")

        # Narrator should succeed despite Arbiter timeout
        assert len(response.narrative) > 0


# ---------------------------------------------------------------------------
# Test: Session Tools LLM Client Creation
# ---------------------------------------------------------------------------


class TestSessionToolsIntegration:
    """Test that SessionManager creates and wires LLM clients correctly."""

    def test_create_llm_clients_returns_mock_fallback(self):
        """When Anthropic SDK is unavailable, should return MockLLMClient."""
        from dm20_protocol.claudmaster.tools.session_tools import SessionManager

        config = ClaudmasterConfig()
        manager = SessionManager()

        # Force mock by patching the import check
        with patch(
            "dm20_protocol.claudmaster.tools.session_tools.AnthropicLLMClient",
            side_effect=Exception("No API key"),
        ):
            narrator_llm, arbiter_llm = manager._create_llm_clients(config)

        assert isinstance(narrator_llm, MockLLMClient)
        assert isinstance(arbiter_llm, MockLLMClient)

    def test_mock_arbiter_llm_returns_valid_json(self):
        """The mock Arbiter LLM should return parseable JSON."""
        from dm20_protocol.claudmaster.tools.session_tools import SessionManager

        config = ClaudmasterConfig()
        manager = SessionManager()

        with patch(
            "dm20_protocol.claudmaster.tools.session_tools.AnthropicLLMClient",
            side_effect=Exception("No API key"),
        ):
            _, arbiter_llm = manager._create_llm_clients(config)

        # Verify the default response is valid JSON
        data = json.loads(arbiter_llm.default_response)
        assert "success" in data
        assert "reasoning" in data
        assert isinstance(data["narrative_hooks"], list)


# ---------------------------------------------------------------------------
# Test: End-to-End Action Processing
# ---------------------------------------------------------------------------


class TestEndToEndActionProcessing:
    """Full pipeline test: player_action -> dual response -> structured output."""

    @pytest.mark.anyio
    async def test_combat_action_full_pipeline(self, orchestrator_with_dual_agents):
        """A combat action should produce narrative + mechanics."""
        orch = orchestrator_with_dual_agents
        orch.start_session()

        response = await orch.process_player_input("I swing my sword at the goblin")

        # Narrative should exist
        assert len(response.narrative) > 10

        # Metadata should show both agents participated
        assert "narrator" in response.metadata["agents_used"]
        assert "arbiter" in response.metadata["agents_used"]

        # Mechanical resolution should be present
        assert response.metadata["has_mechanical_resolution"] is True

    @pytest.mark.anyio
    async def test_session_turn_tracking(self, orchestrator_with_dual_agents):
        """Turn counter should increment with each processed input."""
        orch = orchestrator_with_dual_agents
        session = orch.start_session()

        assert session.turn_count == 0

        await orch.process_player_input("I attack the goblin")
        # process_player_input doesn't increment turn, but adds to history
        assert len(session.conversation_history) == 2  # user + assistant

        await orch.process_player_input("I cast fireball")
        assert len(session.conversation_history) == 4  # 2 more messages
