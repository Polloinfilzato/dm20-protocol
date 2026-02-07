"""
Unit tests for the NarratorAgent.

All tests use a mock LLM client so no external API calls are made.
"""

import asyncio
import pytest
from typing import Any

from gamemaster_mcp.claudmaster.base import AgentResponse, AgentRole
from gamemaster_mcp.claudmaster.agents.narrator import (
    NarratorAgent,
    NarrativeStyle,
    SCENE_DESCRIPTION_TEMPLATE,
)


# ---------------------------------------------------------------------------
# Mock LLM
# ---------------------------------------------------------------------------

class MockLLM:
    """LLM client that returns a canned response and records calls."""

    def __init__(self, response: str = "You see a dimly lit corridor stretching ahead.") -> None:
        self.response = response
        self.calls: list[dict[str, Any]] = []

    async def generate(self, prompt: str, max_tokens: int = 1024) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        return self.response


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_llm() -> MockLLM:
    return MockLLM()


@pytest.fixture
def narrator(mock_llm: MockLLM) -> NarratorAgent:
    return NarratorAgent(llm=mock_llm, style=NarrativeStyle.DESCRIPTIVE)


@pytest.fixture
def base_context() -> dict[str, Any]:
    return {
        "player_action": "look around the room",
        "location": {"name": "The Dusty Tavern", "description": "A run-down inn"},
        "recent_events": ["Party arrived in town"],
        "setting": "Forgotten Realms",
    }


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

class TestNarratorInit:
    """Tests for NarratorAgent initialization."""

    def test_default_init(self, mock_llm: MockLLM) -> None:
        agent = NarratorAgent(llm=mock_llm)
        assert agent.name == "narrator"
        assert agent.role == AgentRole.NARRATOR
        assert agent.style == NarrativeStyle.DESCRIPTIVE
        assert agent.max_tokens == 1024

    def test_custom_style(self, mock_llm: MockLLM) -> None:
        agent = NarratorAgent(llm=mock_llm, style=NarrativeStyle.DRAMATIC)
        assert agent.style == NarrativeStyle.DRAMATIC

    def test_custom_max_tokens(self, mock_llm: MockLLM) -> None:
        agent = NarratorAgent(llm=mock_llm, max_tokens=512)
        assert agent.max_tokens == 512


# ---------------------------------------------------------------------------
# Reason phase
# ---------------------------------------------------------------------------

class TestReason:
    """Tests for the reason() method - intent classification."""

    def test_look_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "look around",
            "location": {"name": "Cave"},
        }))
        assert "observing" in result.lower()
        assert "Cave" in result

    def test_move_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "enter the dungeon",
            "location": {"name": "Dungeon Entrance"},
        }))
        assert "moving" in result.lower()

    def test_talk_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "talk to the innkeeper",
            "location": {"name": "Tavern"},
        }))
        assert "dialogue" in result.lower()

    def test_generic_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "attack the goblin",
            "location": {"name": "Forest"},
        }))
        assert "attack the goblin" in result.lower()

    def test_no_player_action(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "location": {"name": "Market Square"},
        }))
        assert "ambient" in result.lower()

    def test_string_location(self, narrator: NarratorAgent) -> None:
        result = asyncio.run(narrator.reason({
            "player_action": "look",
            "location": "The Forest",
        }))
        assert "The Forest" in result


# ---------------------------------------------------------------------------
# Act phase
# ---------------------------------------------------------------------------

class TestAct:
    """Tests for the act() method - LLM generation."""

    def test_act_calls_llm(self, narrator: NarratorAgent, mock_llm: MockLLM) -> None:
        result = asyncio.run(narrator.act("Generate a scene description"))
        assert len(mock_llm.calls) == 1
        assert result == mock_llm.response

    def test_act_respects_max_tokens(self, mock_llm: MockLLM) -> None:
        agent = NarratorAgent(llm=mock_llm, max_tokens=256)
        asyncio.run(agent.act("test"))
        assert mock_llm.calls[0]["max_tokens"] == 256

    def test_act_strips_whitespace(self, mock_llm: MockLLM) -> None:
        mock_llm.response = "  trailing spaces  "
        agent = NarratorAgent(llm=mock_llm)
        result = asyncio.run(agent.act("test"))
        assert result == "trailing spaces"


# ---------------------------------------------------------------------------
# Observe phase
# ---------------------------------------------------------------------------

class TestObserve:
    """Tests for the observe() method - output validation."""

    def test_observe_word_count(self, narrator: NarratorAgent) -> None:
        obs = asyncio.run(narrator.observe("One two three four five"))
        assert obs["word_count"] == 5

    def test_observe_style(self, narrator: NarratorAgent) -> None:
        obs = asyncio.run(narrator.observe("text"))
        assert obs["style"] == "descriptive"

    def test_observe_detects_dialogue(self, narrator: NarratorAgent) -> None:
        obs = asyncio.run(narrator.observe('He said "hello"'))
        assert obs["has_dialogue"] is True

    def test_observe_no_dialogue(self, narrator: NarratorAgent) -> None:
        obs = asyncio.run(narrator.observe("A quiet scene"))
        assert obs["has_dialogue"] is False

    def test_observe_empty(self, narrator: NarratorAgent) -> None:
        obs = asyncio.run(narrator.observe(""))
        assert obs["empty"] is True

    def test_observe_curly_quotes(self, narrator: NarratorAgent) -> None:
        obs = asyncio.run(narrator.observe("She whispered \u201crun\u201d"))
        assert obs["has_dialogue"] is True


# ---------------------------------------------------------------------------
# Full ReAct cycle
# ---------------------------------------------------------------------------

class TestFullCycle:
    """Tests for the complete run() cycle."""

    def test_run_returns_agent_response(
        self, narrator: NarratorAgent, base_context: dict[str, Any],
    ) -> None:
        response = asyncio.run(narrator.run(base_context))
        assert isinstance(response, AgentResponse)
        assert response.agent_name == "narrator"
        assert response.agent_role == AgentRole.NARRATOR

    def test_run_produces_nonempty_result(
        self, narrator: NarratorAgent, base_context: dict[str, Any],
    ) -> None:
        response = asyncio.run(narrator.run(base_context))
        assert response.action_result  # Non-empty narrative
        assert response.observations["word_count"] > 0


# ---------------------------------------------------------------------------
# Narrative styles enum
# ---------------------------------------------------------------------------

class TestNarrativeStyle:
    """Tests for NarrativeStyle enum."""

    def test_all_styles(self) -> None:
        expected = {"descriptive", "terse", "dramatic", "mysterious"}
        actual = {s.value for s in NarrativeStyle}
        assert actual == expected

    def test_style_is_string_enum(self) -> None:
        assert isinstance(NarrativeStyle.DESCRIPTIVE, str)
        assert NarrativeStyle.DESCRIPTIVE == "descriptive"
