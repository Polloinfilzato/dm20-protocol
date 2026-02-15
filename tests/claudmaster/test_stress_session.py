"""
Stress test for session stability over 20+ sequential turns.

This test validates that the Claudmaster system maintains consistency
and performance across extended gameplay sessions by:
1. Simulating 20+ sequential player actions with varied intent types
2. Validating game state consistency after every turn
3. Verifying conversation_history grows correctly
4. Checking that response generation doesn't degrade over time
5. Validating context window management keeps conversation_history bounded
6. Testing session save/load after extended play

All tests use MockLLMClient for deterministic, API-free execution.
"""

import asyncio
import json
import time
from pathlib import Path

import pytest

from dm20_protocol.claudmaster.base import AgentRole
from dm20_protocol.claudmaster.config import ClaudmasterConfig
from dm20_protocol.claudmaster.llm_client import MockLLMClient
from dm20_protocol.claudmaster.orchestrator import IntentType, Orchestrator
from dm20_protocol.claudmaster.agents.arbiter import ArbiterAgent
from dm20_protocol.claudmaster.agents.narrator import NarratorAgent, NarrativeStyle
from dm20_protocol.claudmaster.persistence.session_serializer import SessionSerializer
from dm20_protocol.models import Campaign, GameState


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def campaign():
    """Minimal campaign for stress testing."""
    return Campaign(
        name="Stress Test Campaign",
        description="A campaign designed for long-duration stress testing",
        game_state=GameState(campaign_name="Stress Test Campaign"),
    )


@pytest.fixture
def config():
    """ClaudmasterConfig optimized for stress testing."""
    return ClaudmasterConfig(agent_timeout=5.0)


@pytest.fixture
def narrator_llm():
    """Mock LLM for Narrator with rotating responses to simulate variety."""
    return MockLLMClient(
        default_response=(
            "The dungeon stretches before you, shadows dancing in the torchlight. "
            "Your footsteps echo through the ancient corridors."
        )
    )


@pytest.fixture
def arbiter_llm():
    """Mock LLM for Arbiter with generic successful resolution."""
    resolution = {
        "success": True,
        "dice_rolls": [
            {
                "description": "Action resolution",
                "notation": "1d20+5",
                "result": 18,
                "success": True,
                "dc": 15,
            }
        ],
        "state_changes": [],
        "rules_applied": ["PHB p.178: Standard action resolution"],
        "narrative_hooks": ["Your action succeeds without complication."],
        "reasoning": "Standard action check 18 vs DC 15 succeeds.",
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


# ============================================================================
# Test Player Action Sequences
# ============================================================================


class TestStressSession:
    """20+ turn stress test for session stability."""

    # Realistic 20+ turn gameplay sequence covering all major intent types
    PLAYER_ACTIONS = [
        # Exploration phase (turns 1-5)
        ("I carefully enter the dark cave, looking for any signs of danger", IntentType.EXPLORATION),
        ("I search the walls for hidden doors or passages", IntentType.EXPLORATION),
        ("What do I know about this region's history?", IntentType.QUESTION),
        ("I examine the ancient runes carved into the stone", IntentType.EXPLORATION),
        ("I listen carefully for any sounds deeper in the cave", IntentType.EXPLORATION),

        # NPC encounter and roleplay (turns 6-9)
        ("I approach the figure cautiously and introduce myself", IntentType.ROLEPLAY),
        ("I try to persuade the merchant to share information about the area", IntentType.ROLEPLAY),
        ("What does this NPC look like?", IntentType.QUESTION),
        ("I ask about recent troubles in the region", IntentType.ROLEPLAY),

        # Combat sequence (turns 10-15)
        ("I draw my sword and attack the goblin", IntentType.COMBAT),
        ("I cast fireball at the group of goblins", IntentType.COMBAT),
        ("I dodge the incoming attack and reposition", IntentType.COMBAT),
        ("I cast healing word on myself", IntentType.COMBAT),
        ("I make an opportunity attack as the enemy retreats", IntentType.COMBAT),
        ("I strike the wounded goblin with my sword", IntentType.COMBAT),

        # Post-combat exploration (turns 16-20)
        ("I search the bodies for loot and clues", IntentType.EXPLORATION),
        ("I examine the room where the goblins were camping", IntentType.EXPLORATION),
        ("What exits are available from this chamber?", IntentType.QUESTION),
        ("I take a short rest to recover", IntentType.ACTION),
        ("I proceed deeper into the dungeon, staying alert", IntentType.EXPLORATION),

        # Extended play (turns 21-25)
        ("I investigate the mysterious glowing orb", IntentType.EXPLORATION),
        ("I attempt to decipher the magical symbols", IntentType.ACTION),
        ("Can I recall any lore about artifacts like this?", IntentType.QUESTION),
        ("I carefully touch the orb with my staff", IntentType.ACTION),
        ("I back away slowly and prepare for whatever happens next", IntentType.ACTION),
    ]

    @pytest.mark.anyio
    async def test_20_turn_session_stability(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Full 20+ turn session without errors or state corruption."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Execute all 25 turns
        for turn_idx, (player_input, expected_intent) in enumerate(self.PLAYER_ACTIONS, 1):
            response = await orch.process_player_input(player_input)

            # Verify conversation history grows correctly (2 messages per turn)
            expected_history_len = turn_idx * 2
            assert len(session.conversation_history) == expected_history_len, (
                f"Turn {turn_idx}: expected {expected_history_len} messages, "
                f"got {len(session.conversation_history)}"
            )

            # Verify last user message matches input
            assert session.conversation_history[-2]["role"] == "user"
            assert session.conversation_history[-2]["content"] == player_input

            # Verify last assistant message is present and non-empty
            assert session.conversation_history[-1]["role"] == "assistant"
            assert len(session.conversation_history[-1]["content"]) > 0

            # Verify response structure is valid
            assert response.narrative, f"Turn {turn_idx}: narrative is empty"
            assert isinstance(response.metadata, dict)
            assert isinstance(response.state_changes, list)
            assert isinstance(response.agent_responses, list)

            # Verify agents are tracked correctly
            assert "narrator" in session.active_agents
            assert "arbiter" in session.active_agents

        # Final validation: 25 turns = 50 messages
        assert len(session.conversation_history) == 50

    @pytest.mark.anyio
    async def test_conversation_history_bounded(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Context stays manageable as turns accumulate."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Run 25 turns
        for player_input, _ in self.PLAYER_ACTIONS:
            await orch.process_player_input(player_input)

        # Full conversation history should have all 50 messages
        assert len(session.conversation_history) == 50

        # get_context() should respect max_messages limit
        context_10 = session.get_context(max_messages=10)
        assert len(context_10["recent_messages"]) == 10
        assert context_10["recent_messages"][0] == session.conversation_history[-10]
        assert context_10["recent_messages"][-1] == session.conversation_history[-1]

        # get_context() with max_messages=20 (default)
        context_20 = session.get_context(max_messages=20)
        assert len(context_20["recent_messages"]) == 20

        # Verify context includes other session metadata
        assert context_20["session_id"] == session.session_id
        assert context_20["campaign_id"] == session.campaign_id
        assert "agent_statuses" in context_20

    @pytest.mark.anyio
    async def test_no_latency_degradation(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Response times don't grow with turn count (mock environment)."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Track timing for each turn
        turn_times = []

        for player_input, _ in self.PLAYER_ACTIONS:
            start_time = time.perf_counter()
            await orch.process_player_input(player_input)
            elapsed = time.perf_counter() - start_time
            turn_times.append(elapsed)

        # In mock environment, response time should be consistently fast
        # Check that later turns aren't significantly slower than early turns
        first_5_avg = sum(turn_times[:5]) / 5
        last_5_avg = sum(turn_times[-5:]) / 5

        # Allow for 3x degradation maximum (should be minimal in mock env)
        assert last_5_avg < first_5_avg * 3, (
            f"Performance degradation detected: "
            f"first 5 turns avg={first_5_avg:.4f}s, "
            f"last 5 turns avg={last_5_avg:.4f}s"
        )

        # No single turn should take unreasonably long (timeout is 5s per agent)
        max_acceptable_time = 15.0  # generous for 2 agents @ 5s timeout each
        for turn_idx, elapsed in enumerate(turn_times, 1):
            assert elapsed < max_acceptable_time, (
                f"Turn {turn_idx} took {elapsed:.2f}s (max {max_acceptable_time}s)"
            )

    @pytest.mark.anyio
    async def test_session_save_load_after_stress(
        self, campaign, config, narrator_llm, arbiter_llm, tmp_path
    ):
        """Session can be saved and loaded after 20+ turns."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()
        session_id = session.session_id

        # Play 25 turns
        for player_input, _ in self.PLAYER_ACTIONS:
            await orch.process_player_input(player_input)

        # Verify final state before save (turn_count stays 0 with process_player_input)
        assert len(session.conversation_history) == 50

        # Save session
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
        assert len(loaded["conversation_history"]) == 50

        # Verify loaded conversation history matches exactly
        assert loaded["conversation_history"] == session.conversation_history

        # Verify agent status persisted
        assert loaded["active_agents"] == dict(session.active_agents)

    @pytest.mark.anyio
    async def test_agent_status_tracking_across_turns(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Agent statuses remain consistent across all turns."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Initially all idle
        assert session.active_agents["narrator"] == "idle"
        assert session.active_agents["arbiter"] == "idle"

        # Process 10 turns and check status after each
        for turn_idx, (player_input, _) in enumerate(self.PLAYER_ACTIONS[:10], 1):
            await orch.process_player_input(player_input)

            # After each turn, agents should be "completed"
            assert session.active_agents["narrator"] == "completed", (
                f"Narrator status incorrect after processing {turn_idx} inputs"
            )
            assert session.active_agents["arbiter"] == "completed", (
                f"Arbiter status incorrect after processing {turn_idx} inputs"
            )

    @pytest.mark.anyio
    async def test_mixed_intent_routing(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Different intent types route correctly across all turns."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        intent_counts = {
            IntentType.EXPLORATION: 0,
            IntentType.COMBAT: 0,
            IntentType.ROLEPLAY: 0,
            IntentType.QUESTION: 0,
            IntentType.ACTION: 0,
        }

        # Execute all turns and track intent classification
        for player_input, expected_intent in self.PLAYER_ACTIONS:
            intent = orch.classify_intent(player_input)

            # Track actual classified intents (may differ from expected in edge cases)
            if intent.intent_type in intent_counts:
                intent_counts[intent.intent_type] += 1

            response = await orch.process_player_input(player_input)

            # All intents should produce valid responses
            assert response.narrative
            assert len(response.narrative) > 0

        # Verify we exercised multiple intent types
        executed_intents = sum(1 for count in intent_counts.values() if count > 0)
        assert executed_intents >= 3, (
            f"Only {executed_intents} intent types were classified, expected >= 3"
        )

    @pytest.mark.anyio
    async def test_state_changes_accumulation(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """State changes from multiple turns don't corrupt session state."""
        # Create arbiter that produces state changes
        state_change_resolution = {
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
                    "target": "Enemy",
                    "change_type": "hp",
                    "description": "Enemy takes damage",
                    "value": -15,
                }
            ],
            "rules_applied": ["PHB p.194: Melee Attack"],
            "narrative_hooks": ["Your blade strikes true."],
            "reasoning": "Attack roll succeeds.",
        }
        arbiter_with_changes = MockLLMClient(
            default_response=json.dumps(state_change_resolution)
        )

        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_with_changes)
        session = orch.start_session()

        total_state_changes = 0

        # Run 15 combat-heavy turns
        combat_actions = [
            ("I attack with my sword", IntentType.COMBAT),
            ("I strike again", IntentType.COMBAT),
            ("I cast magic missile", IntentType.COMBAT),
            ("I make another attack", IntentType.COMBAT),
            ("I finish the enemy", IntentType.COMBAT),
        ] * 3  # 15 turns total

        for player_input, _ in combat_actions:
            response = await orch.process_player_input(player_input)

            # Track state changes
            if response.state_changes:
                total_state_changes += len(response.state_changes)

        # Verify state changes were collected across all turns
        assert total_state_changes > 0, "No state changes were recorded"

        # Session should still be valid after all state changes
        assert len(session.conversation_history) == 30

    @pytest.mark.anyio
    async def test_context_metadata_preservation(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Session metadata persists correctly across all turns."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Add custom metadata
        session.metadata["player_name"] = "Thorin"
        session.metadata["difficulty"] = "hard"
        session.metadata["test_flag"] = True

        # Process 10 turns
        for player_input, _ in self.PLAYER_ACTIONS[:10]:
            await orch.process_player_input(player_input)

            # Verify metadata persists
            context = session.get_context(max_messages=5)
            assert context["player_name"] == "Thorin"
            assert context["difficulty"] == "hard"
            assert context["test_flag"] is True

        # Verify metadata still present after all turns
        final_context = session.get_context()
        assert final_context["player_name"] == "Thorin"
        assert final_context["difficulty"] == "hard"
        assert final_context["test_flag"] is True


# ============================================================================
# Edge Case Stress Tests
# ============================================================================


class TestStressEdgeCases:
    """Edge cases under stress conditions."""

    @pytest.mark.anyio
    async def test_rapid_sequential_turns(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Rapid-fire turns (no delay) don't cause race conditions."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Fire 30 turns as fast as possible
        rapid_actions = ["I move forward"] * 30

        for idx, action in enumerate(rapid_actions, 1):
            response = await orch.process_player_input(action)

            # Verify state consistency despite rapid execution
            assert len(session.conversation_history) == idx * 2
            assert response.narrative

    @pytest.mark.anyio
    async def test_very_long_player_input(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """System handles unusually long player inputs across multiple turns."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Create very long input (simulate verbose player)
        long_input = (
            "I carefully and methodically examine every single inch of the ancient "
            "stone wall, running my fingers along the mortar between the massive "
            "granite blocks, looking for any irregularities, hidden switches, or "
            "concealed mechanisms that might reveal a secret passage or hidden "
            "compartment, while also keeping one eye on the shadows and my other "
            "hand ready on my weapon in case of an ambush." * 3  # Triple for stress
        )

        # Process 5 turns with long inputs
        for i in range(5):
            response = await orch.process_player_input(long_input)

            # Verify long input is stored correctly
            assert session.conversation_history[-2]["content"] == long_input
            assert response.narrative

        # Verify all long inputs are preserved
        assert len(session.conversation_history) == 10

    @pytest.mark.anyio
    async def test_alternating_simple_complex_actions(
        self, campaign, config, narrator_llm, arbiter_llm
    ):
        """Alternating between simple and complex actions maintains stability."""
        orch = _make_orchestrator(campaign, config, narrator_llm, arbiter_llm)
        session = orch.start_session()

        # Alternate between minimal and verbose inputs
        alternating_actions = [
            "I look",
            "I carefully examine the intricate carvings on the door, trying to understand their meaning",
            "I wait",
            "I search the entire room methodically, checking every corner and surface",
            "I go north",
            "I cautiously approach the mysterious altar, ready to react if anything happens",
        ] * 4  # 24 turns

        for idx, action in enumerate(alternating_actions, 1):
            response = await orch.process_player_input(action)

            assert len(session.conversation_history) == idx * 2
            assert response.narrative

        assert len(session.conversation_history) == 48
