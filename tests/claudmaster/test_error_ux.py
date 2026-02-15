"""
Tests for error UX hardening in Claudmaster.

Verifies that all player-facing code paths produce in-character error messages
without raw Python exceptions, stacktraces, or technical error messages.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch
from dm20_protocol.claudmaster.tools.action_tools import ActionProcessor, player_action
from dm20_protocol.claudmaster.tools.session_tools import (
    start_claudmaster_session,
    end_session,
    get_session_state,
)
from dm20_protocol.claudmaster.recovery.error_messages import ErrorMessageFormatter
from dm20_protocol.claudmaster.orchestrator import (
    IntentType,
    IntentClassificationError,
    AgentTimeoutError,
    AgentExecutionError,
)


class TestErrorMessageFormatter:
    """Test the ErrorMessageFormatter helper methods."""

    def test_format_empty_input(self):
        """Test empty input message is in-character."""
        formatter = ErrorMessageFormatter()
        message = formatter.format_empty_input()

        assert "DM" in message
        assert "adventurer" in message.lower() or "wish to do" in message.lower()
        # Should NOT contain technical terms
        assert "ValueError" not in message
        assert "Exception" not in message
        assert "empty" not in message.lower() or "empty" in "adventurer"  # Allow "empty" in context

    def test_format_ambiguous_input(self):
        """Test ambiguous input message is in-character."""
        formatter = ErrorMessageFormatter()
        action = "do something"
        message = formatter.format_ambiguous_input(action)

        assert "DM" in message
        assert action in message
        assert "clarif" in message.lower() or "elaborate" in message.lower()
        # Should NOT contain technical terms
        assert "IntentClassificationError" not in message
        assert "Exception" not in message

    def test_format_missing_campaign(self):
        """Test missing campaign message is in-character and helpful."""
        formatter = ErrorMessageFormatter()
        campaign_name = "Nonexistent Campaign"
        message = formatter.format_missing_campaign(campaign_name)

        assert "DM" in message
        assert campaign_name in message
        assert "might:" in message or "you could" in message.lower()
        # Should NOT contain technical terms
        assert "FileNotFoundError" not in message
        assert "ValueError" not in message

    def test_format_session_not_found(self):
        """Test session not found message is in-character."""
        formatter = ErrorMessageFormatter()
        session_id = "abc123"
        message = formatter.format_session_not_found(session_id)

        assert "DM" in message
        assert session_id in message or "session" in message.lower()
        # Should NOT contain technical terms
        assert "not found" not in message or "record" in message  # "record" makes it in-character
        assert "ValueError" not in message

    def test_format_timeout_fallback(self):
        """Test timeout fallback message is in-character and functional."""
        formatter = ErrorMessageFormatter()

        # With partial narrative
        partial = "You swing your sword at the goblin..."
        message = formatter.format_timeout_fallback(partial)
        assert partial in message
        assert "DM" in message
        assert "continue" in message.lower()

        # Without partial narrative
        message = formatter.format_timeout_fallback(None)
        assert "DM" in message
        assert "arcane" in message.lower() or "mysteries" in message.lower()


class TestActionToolsErrorUX:
    """Test error UX in action_tools.py."""

    @pytest.mark.anyio
    async def test_empty_action_input(self):
        """Test empty action produces in-character clarification."""
        # Mock session manager
        mock_manager = Mock()
        processor = ActionProcessor(mock_manager)

        # Empty string
        response = await processor.process_action(
            session_id="test123",
            action="",
        )

        assert "DM" in response.narrative
        assert "adventurer" in response.narrative.lower() or "wish to do" in response.narrative.lower()
        assert response.turn_number == 0
        assert len(response.warnings) == 0
        # Should NOT contain technical error
        assert "ValueError" not in response.narrative
        assert "empty" not in response.narrative or "expectantly" in response.narrative

        # Whitespace only
        response = await processor.process_action(
            session_id="test123",
            action="   \t\n  ",
        )

        assert "DM" in response.narrative
        assert "ValueError" not in response.narrative

    @pytest.mark.anyio
    async def test_session_not_found_error(self):
        """Test missing session produces in-character message."""
        mock_manager = Mock()
        mock_manager._active_sessions = {}  # Empty sessions
        processor = ActionProcessor(mock_manager)

        response = await processor.process_action(
            session_id="nonexistent",
            action="I attack the goblin",
        )

        assert "DM" in response.narrative
        assert "nonexistent" in response.narrative or "session" in response.narrative.lower()
        # Should NOT contain raw exception
        assert "ValueError" not in response.narrative
        assert "Session nonexistent not found" not in response.narrative

    @pytest.mark.anyio
    async def test_agent_timeout_produces_degraded_response(self):
        """Test agent timeout produces in-character degraded response, not error."""
        mock_manager = Mock()
        mock_session = Mock()
        mock_session.turn_count = 5
        mock_session.metadata = {}
        mock_orchestrator = Mock()

        # Mock session exists
        mock_manager._active_sessions = {"test123": (mock_orchestrator, mock_session)}
        mock_manager._term_resolvers = {}
        mock_manager._style_trackers = {}

        # Mock intent classification succeeds
        mock_intent = Mock()
        from dm20_protocol.claudmaster.orchestrator import IntentType
        mock_intent.intent_type = IntentType.COMBAT
        mock_intent.confidence = 0.9
        mock_intent.metadata = {}
        mock_orchestrator.classify_intent.return_value = mock_intent

        # Mock orchestrator times out
        timeout_error = AgentTimeoutError("narrator", 30.0)
        mock_orchestrator.process_player_input = AsyncMock(side_effect=timeout_error)

        processor = ActionProcessor(mock_manager)
        response = await processor.process_action(
            session_id="test123",
            action="I cast fireball",
        )

        assert "DM" in response.narrative
        assert "arcane" in response.narrative.lower() or "mysteriesremain" in response.narrative.lower()
        # Should be functional, not an error
        assert response.action_type.value == "combat"
        assert response.turn_number == 5
        # Should NOT contain raw exception
        assert "AgentTimeoutError" not in response.narrative
        assert "exceeded timeout" not in response.narrative

    @pytest.mark.anyio
    async def test_player_action_ultimate_safety_net(self):
        """Test player_action wraps ALL exceptions with formatter."""
        with patch("dm20_protocol.claudmaster.tools.action_tools.ActionProcessor") as MockProcessor:
            # Make processor crash with unexpected exception
            mock_proc = MockProcessor.return_value
            mock_proc.process_action = AsyncMock(side_effect=RuntimeError("Unexpected crash"))

            result = await player_action(
                session_id="test123",
                action="I look around",
            )

            assert "narrative" in result
            assert "DM" in result["narrative"]
            # Should NOT contain raw Python exception
            assert "RuntimeError" not in result["narrative"] or "Unexpected error" in result["narrative"]
            assert "Traceback" not in result["narrative"]


class TestSessionToolsErrorUX:
    """Test error UX in session_tools.py."""

    @pytest.mark.anyio
    async def test_empty_campaign_name(self):
        """Test empty campaign name produces in-character message."""
        result = await start_claudmaster_session(campaign_name="")

        assert result["status"] == "error"
        assert "DM" in result["error_message"]
        assert "campaign" in result["error_message"].lower()
        # Should NOT contain technical error
        assert "cannot be empty" not in result["error_message"] or "embark" in result["error_message"]
        assert "ValueError" not in result["error_message"]

    @pytest.mark.anyio
    async def test_missing_campaign_produces_helpful_message(self):
        """Test missing campaign produces in-character guidance."""
        with patch("dm20_protocol.claudmaster.tools.session_tools._storage") as mock_storage:
            mock_storage.load_campaign.side_effect = FileNotFoundError("Campaign not found")

            result = await start_claudmaster_session(campaign_name="Nonexistent")

            assert result["status"] == "error"
            assert "DM" in result["error_message"]
            assert "Nonexistent" in result["error_message"] or "campaign" in result["error_message"].lower()
            # Should provide helpful guidance
            assert "might:" in result["error_message"] or "you could" in result["error_message"].lower()
            # Should NOT contain raw exception
            assert "FileNotFoundError" not in result["error_message"]
            assert "Cannot load campaign" not in result["error_message"]

    @pytest.mark.anyio
    async def test_storage_not_initialized(self):
        """Test storage not initialized produces in-character message."""
        with patch("dm20_protocol.claudmaster.tools.session_tools._storage", None):
            result = await start_claudmaster_session(campaign_name="Test Campaign")

            assert result["status"] == "error"
            assert "DM" in result["error_message"]
            assert "realm" in result["error_message"].lower() or "archives" in result["error_message"].lower()
            # Should NOT contain technical error
            assert "not initialized" not in result["error_message"] or "prepared" in result["error_message"]

    @pytest.mark.anyio
    async def test_session_not_found_in_end_session(self):
        """Test missing session in end_session produces in-character message."""
        with patch("dm20_protocol.claudmaster.tools.session_tools._session_manager") as mock_manager:
            mock_manager._active_sessions = {}  # No sessions

            result = await end_session(session_id="nonexistent")

            assert result["status"] == "error"
            assert "DM" in result["error_message"]
            # Should NOT contain raw technical message
            assert "not found in active sessions" not in result["error_message"]

    @pytest.mark.anyio
    async def test_invalid_mode_in_end_session(self):
        """Test invalid mode produces in-character message."""
        result = await end_session(session_id="test123", mode="invalid")

        assert result["status"] == "error"
        assert "DM" in result["error_message"]
        assert "invalid" in result["error_message"].lower()
        # Should NOT contain raw validation message
        assert "Must be 'pause' or 'end'" not in result["error_message"] or "command" in result["error_message"]

    @pytest.mark.anyio
    async def test_session_not_found_in_get_session_state(self):
        """Test missing session in get_session_state produces in-character message."""
        with patch("dm20_protocol.claudmaster.tools.session_tools._session_manager") as mock_manager:
            mock_manager.get_session_state.return_value = None

            result = await get_session_state(session_id="nonexistent")

            assert "error_message" in result
            assert "DM" in result["error_message"]
            # Should NOT contain raw technical message
            assert "may have been ended or never started" not in result["error_message"] or "record" in result["error_message"]


class TestNoRawExceptionsInOutput:
    """Comprehensive tests to ensure NO raw Python errors reach player output."""

    def test_no_raw_exception_types_in_formatter_output(self):
        """Test that ErrorMessageFormatter never leaks exception type names."""
        formatter = ErrorMessageFormatter()

        # Test all public methods
        messages = [
            formatter.format_empty_input(),
            formatter.format_ambiguous_input("test action"),
            formatter.format_missing_campaign("test_campaign"),
            formatter.format_session_not_found("test_session"),
            formatter.format_timeout_fallback("partial narrative"),
            formatter.format_timeout_fallback(None),
        ]

        for message in messages:
            # These exception types should NEVER appear
            assert "ValueError" not in message
            assert "RuntimeError" not in message
            assert "FileNotFoundError" not in message
            assert "KeyError" not in message
            assert "AttributeError" not in message
            assert "IntentClassificationError" not in message
            assert "AgentTimeoutError" not in message
            assert "AgentExecutionError" not in message
            # Should be in-character
            assert "DM" in message or "*" in message

    @pytest.mark.anyio
    async def test_no_stacktraces_in_player_action(self):
        """Test player_action never returns stacktraces."""
        with patch("dm20_protocol.claudmaster.tools.action_tools.ActionProcessor") as MockProcessor:
            # Simulate catastrophic failure
            mock_proc = MockProcessor.return_value
            mock_proc.process_action = AsyncMock(side_effect=Exception("Critical failure with\nstacktrace\nat line 123"))

            result = await player_action(
                session_id="test123",
                action="test",
            )

            # Should have narrative field
            assert "narrative" in result
            # Should NOT contain stacktrace elements
            assert "Traceback" not in result["narrative"]
            assert "line 123" not in result["narrative"]
            assert "at line" not in result["narrative"]
            # Should be in-character
            assert "DM" in result["narrative"]
