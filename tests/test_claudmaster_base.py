"""
Unit tests for Claudmaster base agent classes and types.

Tests cover:
- AgentRole enum values and validation
- AgentRequest creation and defaults
- AgentResponse creation and field access
- Agent abstract class enforcement
- Concrete agent implementation and ReAct cycle
"""

import asyncio
import pytest
from typing import Any

from gamemaster_mcp.claudmaster.base import (
    Agent,
    AgentRole,
    AgentRequest,
    AgentResponse,
)


class TestAgentRole:
    """Tests for AgentRole enum."""

    def test_agent_role_values(self) -> None:
        """Test that AgentRole has all expected values."""
        assert AgentRole.NARRATOR == "narrator"
        assert AgentRole.ARCHIVIST == "archivist"
        assert AgentRole.MODULE_KEEPER == "module_keeper"
        assert AgentRole.CONSISTENCY == "consistency"

    def test_agent_role_enum_members(self) -> None:
        """Test that AgentRole has exactly the expected members."""
        expected_roles = {"NARRATOR", "ARCHIVIST", "MODULE_KEEPER", "CONSISTENCY"}
        actual_roles = {role.name for role in AgentRole}
        assert actual_roles == expected_roles

    def test_agent_role_string_conversion(self) -> None:
        """Test that AgentRole values convert correctly to strings."""
        assert AgentRole.NARRATOR.value == "narrator"
        assert AgentRole.ARCHIVIST.value == "archivist"


class TestAgentRequest:
    """Tests for AgentRequest model."""

    def test_agent_request_defaults(self) -> None:
        """Test AgentRequest creation with default values."""
        request = AgentRequest()
        assert request.context == {}
        assert request.metadata == {}

    def test_agent_request_with_context(self) -> None:
        """Test AgentRequest creation with custom context."""
        context = {"session_id": "abc123", "player_action": "attack"}
        request = AgentRequest(context=context)
        assert request.context == context
        assert request.metadata == {}

    def test_agent_request_with_metadata(self) -> None:
        """Test AgentRequest creation with custom metadata."""
        metadata = {"timestamp": "2025-01-01T00:00:00", "priority": "high"}
        request = AgentRequest(metadata=metadata)
        assert request.context == {}
        assert request.metadata == metadata

    def test_agent_request_full_initialization(self) -> None:
        """Test AgentRequest with all fields populated."""
        context = {"turn": 5, "location": "dungeon"}
        metadata = {"agent": "narrator", "version": "1.0"}
        request = AgentRequest(context=context, metadata=metadata)
        assert request.context == context
        assert request.metadata == metadata


class TestAgentResponse:
    """Tests for AgentResponse model."""

    def test_agent_response_creation(self) -> None:
        """Test AgentResponse creation with required fields."""
        response = AgentResponse(
            agent_name="TestAgent",
            agent_role=AgentRole.NARRATOR,
            reasoning="I decided to describe the scene",
            action_result="You see a dark corridor..."
        )
        assert response.agent_name == "TestAgent"
        assert response.agent_role == AgentRole.NARRATOR
        assert response.reasoning == "I decided to describe the scene"
        assert response.action_result == "You see a dark corridor..."
        assert response.observations == {}
        assert response.metadata == {}

    def test_agent_response_with_observations(self) -> None:
        """Test AgentResponse with observation data."""
        observations = {"mood": "tense", "visibility": "low"}
        response = AgentResponse(
            agent_name="TestAgent",
            agent_role=AgentRole.ARCHIVIST,
            reasoning="Updated game state",
            action_result={"hp": 45, "status": "wounded"},
            observations=observations
        )
        assert response.observations == observations

    def test_agent_response_field_access(self) -> None:
        """Test accessing all fields of AgentResponse."""
        response = AgentResponse(
            agent_name="MockAgent",
            agent_role=AgentRole.CONSISTENCY,
            reasoning="Checking for contradictions",
            action_result=None,
            observations={"contradictions_found": 0},
            metadata={"processing_time": "150ms"}
        )
        assert response.agent_name == "MockAgent"
        assert response.agent_role == AgentRole.CONSISTENCY
        assert response.reasoning == "Checking for contradictions"
        assert response.action_result is None
        assert response.observations["contradictions_found"] == 0
        assert response.metadata["processing_time"] == "150ms"


class TestAgentAbstractClass:
    """Tests for Agent abstract base class."""

    def test_agent_cannot_be_instantiated_directly(self) -> None:
        """Test that Agent abstract class cannot be instantiated."""
        with pytest.raises(TypeError, match="Can't instantiate abstract class"):
            Agent(name="TestAgent", role=AgentRole.NARRATOR)


class MockAgent(Agent):
    """Concrete implementation of Agent for testing purposes."""

    def __init__(self, name: str, role: AgentRole) -> None:
        super().__init__(name, role)
        self.reason_called = False
        self.act_called = False
        self.observe_called = False
        self.call_order: list[str] = []

    async def reason(self, context: dict[str, Any]) -> str:
        """Mock reasoning implementation that tracks execution."""
        self.reason_called = True
        self.call_order.append("reason")
        return f"Reasoning based on context: {context}"

    async def act(self, reasoning: str) -> Any:
        """Mock action implementation that tracks execution."""
        self.act_called = True
        self.call_order.append("act")
        return f"Action result from: {reasoning}"

    async def observe(self, result: Any) -> dict[str, Any]:
        """Mock observation implementation that tracks execution."""
        self.observe_called = True
        self.call_order.append("observe")
        return {"observed": str(result)}


class TestConcreteAgent:
    """Tests for concrete Agent implementation."""

    def test_mock_agent_creation(self) -> None:
        """Test that a concrete agent can be instantiated."""
        agent = MockAgent(name="TestMock", role=AgentRole.NARRATOR)
        assert agent.name == "TestMock"
        assert agent.role == AgentRole.NARRATOR

    def test_mock_agent_reason_method(self) -> None:
        """Test that concrete agent reason() method works."""
        agent = MockAgent(name="TestMock", role=AgentRole.NARRATOR)
        context = {"scene": "forest"}
        result = asyncio.run(agent.reason(context))
        assert "Reasoning based on context" in result
        assert agent.reason_called

    def test_mock_agent_act_method(self) -> None:
        """Test that concrete agent act() method works."""
        agent = MockAgent(name="TestMock", role=AgentRole.ARCHIVIST)
        reasoning = "Update character HP"
        result = asyncio.run(agent.act(reasoning))
        assert "Action result from" in result
        assert agent.act_called

    def test_mock_agent_observe_method(self) -> None:
        """Test that concrete agent observe() method works."""
        agent = MockAgent(name="TestMock", role=AgentRole.MODULE_KEEPER)
        result = asyncio.run(agent.observe("test result"))
        assert "observed" in result
        assert agent.observe_called

    def test_mock_agent_run_executes_react_cycle(self) -> None:
        """Test that run() executes the full ReAct cycle in correct order."""
        agent = MockAgent(name="TestMock", role=AgentRole.NARRATOR)
        context = {"player_action": "look around"}

        # Execute the ReAct cycle
        response = asyncio.run(agent.run(context))

        # Verify response structure is correct
        assert isinstance(response, AgentResponse)
        assert response.agent_name == "TestMock"
        assert response.agent_role == AgentRole.NARRATOR

        # All three phases were called
        assert agent.reason_called
        assert agent.act_called
        assert agent.observe_called

        # Correct execution order: reason -> act -> observe
        assert agent.call_order == ["reason", "act", "observe"]

        # Results flow through the pipeline
        assert "Reasoning based on context" in response.reasoning
        assert "Action result from" in response.action_result
        assert "observed" in response.observations

    def test_mock_agent_run_returns_proper_response(self) -> None:
        """Test that run() returns a properly structured AgentResponse."""
        agent = MockAgent(name="ResponseTest", role=AgentRole.CONSISTENCY)
        context = {"check": "consistency"}

        response = asyncio.run(agent.run(context))

        # Verify all required fields are present
        assert hasattr(response, "agent_name")
        assert hasattr(response, "agent_role")
        assert hasattr(response, "reasoning")
        assert hasattr(response, "action_result")
        assert hasattr(response, "observations")
        assert hasattr(response, "metadata")

        # Verify field values
        assert response.agent_name == "ResponseTest"
        assert response.agent_role == AgentRole.CONSISTENCY
        assert isinstance(response.reasoning, str)
        assert response.observations is not None
