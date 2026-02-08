"""
Unit tests for ClaudmasterSession model.

Tests cover:
- Session creation and auto-generated session_id
- Message history management
- Turn tracking
- Agent status management
- Context retrieval with message limiting
- Default values and field validation
"""

import pytest
from datetime import datetime

from dm20_protocol.claudmaster.session import ClaudmasterSession
from dm20_protocol.claudmaster.config import ClaudmasterConfig
from dm20_protocol.claudmaster.improvisation import ImprovisationLevel


class TestSessionCreation:
    """Tests for ClaudmasterSession creation."""

    def test_session_creation_with_campaign_id(self) -> None:
        """Test creating a session with a campaign ID."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert session.campaign_id == "campaign_123"

    def test_session_id_auto_generated(self) -> None:
        """Test that session_id is auto-generated."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert session.session_id is not None
        assert isinstance(session.session_id, str)
        assert len(session.session_id) > 0

    def test_session_id_unique_per_instance(self) -> None:
        """Test that each session gets a unique session_id."""
        session1 = ClaudmasterSession(campaign_id="campaign_123")
        session2 = ClaudmasterSession(campaign_id="campaign_123")
        assert session1.session_id != session2.session_id

    def test_session_id_length(self) -> None:
        """Test that session_id has expected length (8 chars by default)."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        # shortuuid with length=8 should produce 8-character strings
        assert len(session.session_id) == 8

    def test_started_at_auto_set(self) -> None:
        """Test that started_at is automatically set to current time."""
        before = datetime.now()
        session = ClaudmasterSession(campaign_id="campaign_123")
        after = datetime.now()
        assert before <= session.started_at <= after


class TestSessionDefaults:
    """Tests for ClaudmasterSession default values."""

    def test_default_turn_count_zero(self) -> None:
        """Test that default turn_count is 0."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert session.turn_count == 0

    def test_default_conversation_history_empty(self) -> None:
        """Test that default conversation_history is empty list."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert session.conversation_history == []

    def test_default_active_agents_empty(self) -> None:
        """Test that default active_agents is empty dict."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert session.active_agents == {}

    def test_default_metadata_empty(self) -> None:
        """Test that default metadata is empty dict."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert session.metadata == {}

    def test_default_config_instance(self) -> None:
        """Test that default config is a ClaudmasterConfig instance."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        assert isinstance(session.config, ClaudmasterConfig)


class TestAddMessage:
    """Tests for add_message() method."""

    def test_add_message_appends_to_history(self) -> None:
        """Test that add_message() appends message to conversation_history."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.add_message(role="user", content="Hello, DM!")
        
        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["role"] == "user"
        assert session.conversation_history[0]["content"] == "Hello, DM!"

    def test_add_multiple_messages(self) -> None:
        """Test adding multiple messages maintains order."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.add_message(role="user", content="First message")
        session.add_message(role="assistant", content="Second message")
        session.add_message(role="user", content="Third message")
        
        assert len(session.conversation_history) == 3
        assert session.conversation_history[0]["content"] == "First message"
        assert session.conversation_history[1]["content"] == "Second message"
        assert session.conversation_history[2]["content"] == "Third message"

    def test_add_message_with_different_roles(self) -> None:
        """Test adding messages with different roles."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.add_message(role="system", content="System prompt")
        session.add_message(role="user", content="User input")
        session.add_message(role="assistant", content="AI response")
        
        assert session.conversation_history[0]["role"] == "system"
        assert session.conversation_history[1]["role"] == "user"
        assert session.conversation_history[2]["role"] == "assistant"


class TestIncrementTurn:
    """Tests for increment_turn() method."""

    def test_increment_turn_returns_count(self) -> None:
        """Test that increment_turn() returns the new turn count."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        new_turn = session.increment_turn()
        assert new_turn == 1

    def test_increment_turn_updates_internal_count(self) -> None:
        """Test that increment_turn() updates the internal turn_count."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.increment_turn()
        assert session.turn_count == 1

    def test_multiple_increments(self) -> None:
        """Test incrementing turn multiple times."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        
        turn1 = session.increment_turn()
        turn2 = session.increment_turn()
        turn3 = session.increment_turn()
        
        assert turn1 == 1
        assert turn2 == 2
        assert turn3 == 3
        assert session.turn_count == 3


class TestSetAgentStatus:
    """Tests for set_agent_status() method."""

    def test_set_agent_status_updates_map(self) -> None:
        """Test that set_agent_status() updates the active_agents map."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.set_agent_status(agent_name="narrator", status="working")
        
        assert "narrator" in session.active_agents
        assert session.active_agents["narrator"] == "working"

    def test_set_multiple_agent_statuses(self) -> None:
        """Test setting status for multiple agents."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.set_agent_status(agent_name="narrator", status="completed")
        session.set_agent_status(agent_name="archivist", status="working")
        session.set_agent_status(agent_name="module_keeper", status="idle")
        
        assert len(session.active_agents) == 3
        assert session.active_agents["narrator"] == "completed"
        assert session.active_agents["archivist"] == "working"
        assert session.active_agents["module_keeper"] == "idle"

    def test_set_agent_status_overwrites_existing(self) -> None:
        """Test that setting status overwrites existing status."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.set_agent_status(agent_name="narrator", status="working")
        session.set_agent_status(agent_name="narrator", status="completed")
        
        assert session.active_agents["narrator"] == "completed"

    def test_set_agent_status_various_statuses(self) -> None:
        """Test setting various status values."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        statuses = ["idle", "working", "completed", "error"]
        
        for i, status in enumerate(statuses):
            session.set_agent_status(agent_name=f"agent_{i}", status=status)
        
        for i, status in enumerate(statuses):
            assert session.active_agents[f"agent_{i}"] == status


class TestGetContext:
    """Tests for get_context() method."""

    def test_get_context_returns_dict(self) -> None:
        """Test that get_context() returns a dictionary."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        context = session.get_context()
        assert isinstance(context, dict)

    def test_get_context_contains_expected_keys(self) -> None:
        """Test that get_context() returns dict with expected keys."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        context = session.get_context()
        
        expected_keys = {
            "session_id", "campaign_id", "turn_count",
            "recent_messages", "agent_statuses", "config"
        }
        assert set(context.keys()) == expected_keys

    def test_get_context_session_id(self) -> None:
        """Test that context includes correct session_id."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        context = session.get_context()
        assert context["session_id"] == session.session_id

    def test_get_context_campaign_id(self) -> None:
        """Test that context includes correct campaign_id."""
        session = ClaudmasterSession(campaign_id="campaign_456")
        context = session.get_context()
        assert context["campaign_id"] == "campaign_456"

    def test_get_context_turn_count(self) -> None:
        """Test that context includes current turn_count."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.increment_turn()
        session.increment_turn()
        context = session.get_context()
        assert context["turn_count"] == 2

    def test_get_context_recent_messages_default(self) -> None:
        """Test that get_context() includes recent messages with default limit."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        for i in range(25):
            session.add_message(role="user", content=f"Message {i}")
        
        context = session.get_context()
        # Default max_messages=20
        assert len(context["recent_messages"]) == 20
        # Should get last 20 messages (indices 5-24)
        assert context["recent_messages"][0]["content"] == "Message 5"
        assert context["recent_messages"][-1]["content"] == "Message 24"

    def test_get_context_max_messages_limit(self) -> None:
        """Test that get_context(max_messages=N) limits messages."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        for i in range(15):
            session.add_message(role="user", content=f"Message {i}")
        
        context = session.get_context(max_messages=5)
        assert len(context["recent_messages"]) == 5
        # Should get last 5 messages (indices 10-14)
        assert context["recent_messages"][0]["content"] == "Message 10"
        assert context["recent_messages"][-1]["content"] == "Message 14"

    def test_get_context_max_messages_zero(self) -> None:
        """Test that get_context(max_messages=0) returns empty messages."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.add_message(role="user", content="Message 1")
        session.add_message(role="user", content="Message 2")
        
        context = session.get_context(max_messages=0)
        assert context["recent_messages"] == []

    def test_get_context_fewer_messages_than_limit(self) -> None:
        """Test get_context() when history has fewer messages than limit."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.add_message(role="user", content="Message 1")
        session.add_message(role="user", content="Message 2")
        
        context = session.get_context(max_messages=10)
        assert len(context["recent_messages"]) == 2

    def test_get_context_agent_statuses(self) -> None:
        """Test that context includes agent statuses."""
        session = ClaudmasterSession(campaign_id="campaign_123")
        session.set_agent_status("narrator", "working")
        session.set_agent_status("archivist", "idle")
        
        context = session.get_context()
        assert "narrator" in context["agent_statuses"]
        assert context["agent_statuses"]["narrator"] == "working"
        assert context["agent_statuses"]["archivist"] == "idle"

    def test_get_context_config_serialized(self) -> None:
        """Test that context includes serialized config."""
        custom_config = ClaudmasterConfig(
            llm_provider="openai",
            improvisation_level=3
        )
        session = ClaudmasterSession(campaign_id="campaign_123", config=custom_config)
        
        context = session.get_context()
        assert isinstance(context["config"], dict)
        assert context["config"]["llm_provider"] == "openai"
        assert context["config"]["improvisation_level"] == ImprovisationLevel.HIGH
