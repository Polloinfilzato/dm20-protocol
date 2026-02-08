"""
Tests for Claudmaster error handling and recovery systems.
"""

from __future__ import annotations

import asyncio
import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

from dm20_protocol.claudmaster.base import Agent, AgentResponse, AgentRole
from dm20_protocol.claudmaster.config import ClaudmasterConfig
from dm20_protocol.claudmaster.exceptions import (
    AgentError,
    ClaudmasterError,
    ClaudmasterTimeoutError,
    RecoveryError,
    RollbackError,
    SessionError,
    StateError,
)
from dm20_protocol.claudmaster.recovery import RecoveryResult
from dm20_protocol.claudmaster.recovery.agent_recovery import AgentRecoveryManager
from dm20_protocol.claudmaster.recovery.crash_recovery import CrashRecoveryManager
from dm20_protocol.claudmaster.recovery.degradation import (
    DegradationLevel,
    DegradationManager,
)
from dm20_protocol.claudmaster.recovery.error_messages import ErrorMessageFormatter
from dm20_protocol.claudmaster.recovery.rollback import (
    StateRollbackManager,
    StateSnapshot,
)
from dm20_protocol.claudmaster.session import ClaudmasterSession


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_session():
    """Create a mock ClaudmasterSession."""
    session = ClaudmasterSession(
        campaign_id="test-campaign",
        config=ClaudmasterConfig(),
    )
    session.turn_count = 5
    session.conversation_history = [
        {"role": "user", "content": "I attack the goblin"},
        {"role": "assistant", "content": "You strike with your sword!"},
    ]
    session.active_agents = {"narrator": "idle", "archivist": "idle"}
    session.metadata = {"location": "dungeon"}
    return session


@pytest.fixture
def mock_orchestrator():
    """Create a mock Orchestrator."""
    orchestrator = Mock()
    orchestrator.agents = {}
    return orchestrator


@pytest.fixture
def mock_agent():
    """Create a mock Agent."""
    agent = Mock(spec=Agent)
    agent.name = "test-narrator"
    agent.role = AgentRole.NARRATOR
    agent.run = AsyncMock()
    return agent


@pytest.fixture
def campaign_path(tmp_path):
    """Create a temporary campaign directory."""
    return tmp_path / "test-campaign"


@pytest.fixture
def mock_serializer():
    """Create a mock SessionSerializer."""
    serializer = Mock()
    serializer.load_session = Mock(return_value=None)
    return serializer


# ============================================================================
# Exception Hierarchy Tests
# ============================================================================


def test_claudmaster_error_base():
    """Test ClaudmasterError base exception."""
    error = ClaudmasterError("Test error", details={"key": "value"})
    assert str(error) == "Test error"
    assert error.details == {"key": "value"}
    assert isinstance(error, Exception)


def test_agent_error_attributes():
    """Test AgentError has required attributes."""
    error = AgentError(
        "Agent failed", agent_name="narrator", recoverable=True, details={"attempt": 1}
    )
    assert error.agent_name == "narrator"
    assert error.recoverable is True
    assert error.details == {"attempt": 1}
    assert isinstance(error, ClaudmasterError)


def test_agent_error_defaults():
    """Test AgentError default values."""
    error = AgentError("Agent failed", agent_name="archivist")
    assert error.recoverable is True
    assert error.details == {}


def test_state_error():
    """Test StateError is a ClaudmasterError."""
    error = StateError("State corrupted")
    assert isinstance(error, ClaudmasterError)


def test_session_error():
    """Test SessionError is a ClaudmasterError."""
    error = SessionError("Session failed")
    assert isinstance(error, ClaudmasterError)


def test_timeout_error_attributes():
    """Test ClaudmasterTimeoutError has required attributes."""
    error = ClaudmasterTimeoutError(
        "Operation timed out", operation="agent_run", timeout_seconds=30.0
    )
    assert error.operation == "agent_run"
    assert error.timeout_seconds == 30.0
    assert isinstance(error, ClaudmasterError)


def test_recovery_error():
    """Test RecoveryError is a ClaudmasterError."""
    error = RecoveryError("Recovery failed")
    assert isinstance(error, ClaudmasterError)


def test_rollback_error():
    """Test RollbackError is a ClaudmasterError."""
    error = RollbackError("Rollback failed")
    assert isinstance(error, ClaudmasterError)


# ============================================================================
# AgentRecoveryManager Tests
# ============================================================================


@pytest.mark.anyio
async def test_agent_recovery_manager_init(mock_orchestrator):
    """Test AgentRecoveryManager initialization."""
    manager = AgentRecoveryManager(mock_orchestrator, max_retries=3)
    assert manager.orchestrator == mock_orchestrator
    assert manager.max_retries == 3
    assert manager.retry_delays == [1.0, 2.0, 4.0]
    assert manager.failure_counts == {}


@pytest.mark.anyio
async def test_handle_agent_failure_retry_success(mock_orchestrator, mock_agent):
    """Test successful recovery via retry."""
    manager = AgentRecoveryManager(mock_orchestrator, max_retries=3)

    # Mock will succeed on retry
    mock_response = AgentResponse(
        agent_name="test-narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="Recovered",
        action_result="Success",
    )
    mock_agent.run.return_value = mock_response

    context = {"test": "context"}
    result = await manager.handle_agent_failure(
        mock_agent, Exception("Temporary error"), context
    )

    assert result.success is True
    assert result.strategy_used == "retry"
    assert result.response == mock_response
    assert "test-narrator" not in manager.failure_counts


@pytest.mark.anyio
async def test_handle_agent_failure_max_retries_exceeded(mock_orchestrator, mock_agent):
    """Test failure when max retries exceeded."""
    manager = AgentRecoveryManager(mock_orchestrator, max_retries=2)

    # Simulate failures
    manager.failure_counts["test-narrator"] = 3
    mock_agent.run.side_effect = Exception("Persistent error")

    result = await manager.handle_agent_failure(
        mock_agent, Exception("Persistent error"), {}
    )

    assert result.success is False
    assert result.strategy_used == "degradation"


@pytest.mark.anyio
async def test_handle_agent_failure_unrecoverable(mock_orchestrator, mock_agent):
    """Test unrecoverable error returns user_intervention."""
    manager = AgentRecoveryManager(mock_orchestrator)

    error = AgentError("Critical error", agent_name="test-narrator", recoverable=False)
    result = await manager.handle_agent_failure(mock_agent, error, {})

    assert result.success is False
    assert result.strategy_used == "user_intervention"


@pytest.mark.anyio
async def test_handle_agent_failure_fallback(mock_orchestrator, mock_agent):
    """Test fallback to alternative agent."""
    manager = AgentRecoveryManager(mock_orchestrator, max_retries=1)
    manager.failure_counts["module-keeper"] = 2

    # Set up module keeper and narrator
    module_keeper = Mock(spec=Agent)
    module_keeper.name = "module-keeper"
    module_keeper.role = AgentRole.MODULE_KEEPER
    module_keeper.run = AsyncMock(side_effect=Exception("Failed"))

    narrator = Mock(spec=Agent)
    narrator.name = "narrator"
    narrator.role = AgentRole.NARRATOR
    fallback_response = AgentResponse(
        agent_name="narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="Fallback",
        action_result="Fallback response",
    )
    narrator.run = AsyncMock(return_value=fallback_response)

    mock_orchestrator.agents = {"module-keeper": module_keeper, "narrator": narrator}

    result = await manager.handle_agent_failure(module_keeper, Exception("Failed"), {})

    assert result.success is True
    assert result.strategy_used == "fallback"
    assert result.response == fallback_response


@pytest.mark.anyio
async def test_retry_with_backoff(mock_orchestrator, mock_agent):
    """Test retry with exponential backoff."""
    manager = AgentRecoveryManager(mock_orchestrator)
    manager.failure_counts["test-narrator"] = 1

    mock_response = AgentResponse(
        agent_name="test-narrator",
        agent_role=AgentRole.NARRATOR,
        reasoning="Success",
        action_result="Done",
    )
    mock_agent.run.return_value = mock_response

    with patch("asyncio.sleep") as mock_sleep:
        result = await manager.retry_with_backoff(mock_agent, {})

        # Should use first delay (1.0s)
        mock_sleep.assert_called_once_with(1.0)
        assert result == mock_response


@pytest.mark.anyio
async def test_retry_with_backoff_failure(mock_orchestrator, mock_agent):
    """Test retry returns None on failure."""
    manager = AgentRecoveryManager(mock_orchestrator)
    manager.failure_counts["test-narrator"] = 1

    mock_agent.run.side_effect = Exception("Still failing")

    result = await manager.retry_with_backoff(mock_agent, {})
    assert result is None


def test_get_fallback_agent_module_keeper(mock_orchestrator):
    """Test MODULE_KEEPER fallback to NARRATOR."""
    manager = AgentRecoveryManager(mock_orchestrator)

    module_keeper = Mock(spec=Agent)
    module_keeper.role = AgentRole.MODULE_KEEPER
    module_keeper.name = "module-keeper"

    narrator = Mock(spec=Agent)
    narrator.role = AgentRole.NARRATOR
    narrator.name = "narrator"

    mock_orchestrator.agents = {"module-keeper": module_keeper, "narrator": narrator}

    fallback = manager.get_fallback_agent(module_keeper)
    assert fallback == narrator


def test_get_fallback_agent_consistency(mock_orchestrator):
    """Test CONSISTENCY fallback to ARCHIVIST."""
    manager = AgentRecoveryManager(mock_orchestrator)

    consistency = Mock(spec=Agent)
    consistency.role = AgentRole.CONSISTENCY
    consistency.name = "consistency"

    archivist = Mock(spec=Agent)
    archivist.role = AgentRole.ARCHIVIST
    archivist.name = "archivist"

    mock_orchestrator.agents = {"consistency": consistency, "archivist": archivist}

    fallback = manager.get_fallback_agent(consistency)
    assert fallback == archivist


def test_get_fallback_agent_none_for_narrator(mock_orchestrator):
    """Test NARRATOR has no fallback."""
    manager = AgentRecoveryManager(mock_orchestrator)

    narrator = Mock(spec=Agent)
    narrator.role = AgentRole.NARRATOR
    narrator.name = "narrator"

    fallback = manager.get_fallback_agent(narrator)
    assert fallback is None


def test_reset_failure_count(mock_orchestrator):
    """Test resetting failure count."""
    manager = AgentRecoveryManager(mock_orchestrator)
    manager.failure_counts["test-agent"] = 5

    manager.reset_failure_count("test-agent")
    assert "test-agent" not in manager.failure_counts


def test_is_recoverable(mock_orchestrator):
    """Test error recoverability classification."""
    manager = AgentRecoveryManager(mock_orchestrator)

    # Timeout errors are recoverable
    assert manager._is_recoverable(asyncio.TimeoutError()) is True

    # AgentError with recoverable=False
    assert (
        manager._is_recoverable(
            AgentError("Error", agent_name="test", recoverable=False)
        )
        is False
    )

    # AgentError with recoverable=True
    assert (
        manager._is_recoverable(AgentError("Error", agent_name="test", recoverable=True))
        is True
    )

    # Generic exceptions are recoverable
    assert manager._is_recoverable(Exception("Generic")) is True


# ============================================================================
# DegradationManager Tests
# ============================================================================


def test_degradation_manager_init():
    """Test DegradationManager initialization."""
    manager = DegradationManager()
    assert manager.current_level == DegradationLevel.FULL
    assert manager.degradation_reasons == []


def test_degrade_to_lower_level():
    """Test degrading to a lower level."""
    manager = DegradationManager()

    result = manager.degrade_to(DegradationLevel.REDUCED, "Agent failure")
    assert result is True
    assert manager.current_level == DegradationLevel.REDUCED
    assert "Agent failure" in manager.degradation_reasons


def test_degrade_to_same_level():
    """Test degrading to same level returns False."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.REDUCED

    result = manager.degrade_to(DegradationLevel.REDUCED, "Test")
    assert result is False
    assert manager.current_level == DegradationLevel.REDUCED


def test_degrade_to_higher_level_blocked():
    """Test cannot degrade to higher level (use upgrade instead)."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.MINIMAL

    result = manager.degrade_to(DegradationLevel.REDUCED, "Test")
    assert result is False
    assert manager.current_level == DegradationLevel.MINIMAL


def test_upgrade_to_higher_level():
    """Test upgrading to higher level."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.MINIMAL
    manager.degradation_reasons = ["reason1", "reason2"]

    result = manager.upgrade_to(DegradationLevel.REDUCED)
    assert result is True
    assert manager.current_level == DegradationLevel.REDUCED
    assert len(manager.degradation_reasons) == 1  # One removed


def test_upgrade_to_same_level():
    """Test upgrading to same level returns False."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.REDUCED

    result = manager.upgrade_to(DegradationLevel.REDUCED)
    assert result is False


def test_get_available_actions_full():
    """Test available actions at FULL level."""
    manager = DegradationManager()
    actions = manager.get_available_actions()

    assert "exploration" in actions
    assert "combat" in actions
    assert "advanced_narrative" in actions
    assert "fact_checking" in actions


def test_get_available_actions_reduced():
    """Test available actions at REDUCED level."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.REDUCED

    actions = manager.get_available_actions()
    assert "exploration" in actions
    assert "combat" in actions
    assert "advanced_narrative" not in actions
    assert "fact_checking" not in actions


def test_get_available_actions_minimal():
    """Test available actions at MINIMAL level."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.MINIMAL

    actions = manager.get_available_actions()
    assert "basic_actions" in actions
    assert "save_session" in actions
    assert "combat" not in actions


def test_get_available_actions_emergency():
    """Test available actions at EMERGENCY level."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.EMERGENCY

    actions = manager.get_available_actions()
    assert actions == ["save_session", "exit_session"]


def test_notify_user_full():
    """Test user notification at FULL level."""
    manager = DegradationManager()
    message = manager.notify_user()
    assert message == ""


def test_notify_user_reduced():
    """Test user notification at REDUCED level."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.REDUCED
    manager.degradation_reasons = ["Test reason"]

    message = manager.notify_user()
    assert "arcane connection" in message.lower()
    assert "Test reason" in message


def test_notify_user_minimal():
    """Test user notification at MINIMAL level."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.MINIMAL

    message = manager.notify_user()
    assert "fraying" in message.lower() or "basic" in message.lower()


def test_can_upgrade():
    """Test can_upgrade check."""
    manager = DegradationManager()
    assert manager.can_upgrade() is False  # Already at FULL

    manager.current_level = DegradationLevel.REDUCED
    assert manager.can_upgrade() is True


def test_is_action_allowed():
    """Test action permission checking."""
    manager = DegradationManager()
    manager.current_level = DegradationLevel.REDUCED

    assert manager.is_action_allowed("exploration") is True
    assert manager.is_action_allowed("advanced_narrative") is False


# ============================================================================
# StateRollbackManager Tests
# ============================================================================


def test_state_rollback_manager_init(mock_session):
    """Test StateRollbackManager initialization."""
    manager = StateRollbackManager(mock_session, max_snapshots=10)
    assert manager.session == mock_session
    assert manager.max_snapshots == 10
    assert manager.snapshots == []


def test_create_snapshot(mock_session):
    """Test creating a state snapshot."""
    manager = StateRollbackManager(mock_session)

    snapshot = manager.create_snapshot(label="test-snapshot")

    assert snapshot.label == "test-snapshot"
    assert snapshot.turn_count == 5
    assert len(snapshot.session_data) > 0
    assert snapshot.session_data["turn_count"] == 5
    assert len(manager.snapshots) == 1


def test_create_snapshot_deep_copy(mock_session):
    """Test snapshot creates deep copy to prevent modifications."""
    manager = StateRollbackManager(mock_session)

    snapshot = manager.create_snapshot()
    original_turn = snapshot.session_data["turn_count"]

    # Modify session
    mock_session.turn_count = 100

    # Snapshot should be unchanged
    assert snapshot.session_data["turn_count"] == original_turn


def test_rollback_to_snapshot(mock_session):
    """Test rolling back to a specific snapshot."""
    manager = StateRollbackManager(mock_session)

    # Create snapshot at turn 5
    snapshot = manager.create_snapshot(label="save-point")

    # Advance session
    mock_session.turn_count = 10
    mock_session.conversation_history.append({"role": "user", "content": "New message"})

    # Rollback
    success = manager.rollback_to(snapshot.snapshot_id)

    assert success is True
    assert mock_session.turn_count == 5
    assert len(mock_session.conversation_history) == 2


def test_rollback_to_nonexistent_snapshot(mock_session):
    """Test rollback to non-existent snapshot raises error."""
    manager = StateRollbackManager(mock_session)

    with pytest.raises(RollbackError) as exc_info:
        manager.rollback_to("nonexistent-id")

    assert "not found" in str(exc_info.value)


def test_rollback_last(mock_session):
    """Test rolling back to most recent snapshot."""
    manager = StateRollbackManager(mock_session)

    manager.create_snapshot(label="snap1")
    manager.create_snapshot(label="snap2")

    mock_session.turn_count = 20

    success = manager.rollback_last()
    assert success is True


def test_rollback_last_no_snapshots(mock_session):
    """Test rollback_last with no snapshots raises error."""
    manager = StateRollbackManager(mock_session)

    with pytest.raises(RollbackError) as exc_info:
        manager.rollback_last()

    assert "No snapshots available" in str(exc_info.value)


def test_clear_old_snapshots(mock_session):
    """Test clearing old snapshots maintains max limit."""
    manager = StateRollbackManager(mock_session, max_snapshots=3)

    # Create 5 snapshots
    for i in range(5):
        mock_session.turn_count = i
        manager.create_snapshot(label=f"snap-{i}")

    # Should keep only 3 most recent
    assert len(manager.snapshots) == 3
    assert manager.snapshots[0].label == "snap-2"
    assert manager.snapshots[-1].label == "snap-4"


def test_list_snapshots(mock_session):
    """Test listing available snapshots."""
    manager = StateRollbackManager(mock_session)

    manager.create_snapshot(label="snap1")
    manager.create_snapshot(label="snap2")

    snapshots = manager.list_snapshots()

    assert len(snapshots) == 2
    assert snapshots[0]["label"] == "snap1"
    assert snapshots[1]["label"] == "snap2"
    assert "snapshot_id" in snapshots[0]
    assert "timestamp" in snapshots[0]


def test_get_snapshot_count(mock_session):
    """Test getting snapshot count."""
    manager = StateRollbackManager(mock_session)

    assert manager.get_snapshot_count() == 0

    manager.create_snapshot()
    manager.create_snapshot()

    assert manager.get_snapshot_count() == 2


# ============================================================================
# CrashRecoveryManager Tests
# ============================================================================


def test_crash_recovery_manager_init(campaign_path, mock_serializer):
    """Test CrashRecoveryManager initialization."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    assert manager.campaign_path == campaign_path
    assert manager.marker_file == campaign_path / ".claudmaster_recovery"
    assert manager.serializer == mock_serializer


def test_write_recovery_marker(campaign_path, mock_serializer):
    """Test writing recovery marker file."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    manager.write_recovery_marker("test-session-123")

    assert manager.marker_file.exists()

    with open(manager.marker_file, "r") as f:
        data = json.load(f)

    assert data["session_id"] == "test-session-123"
    assert "timestamp" in data
    assert "pid" in data


def test_check_for_crash_no_marker(campaign_path, mock_serializer):
    """Test check_for_crash when no marker exists."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    result = manager.check_for_crash()
    assert result is None


def test_check_for_crash_with_marker(campaign_path, mock_serializer):
    """Test check_for_crash detects existing marker."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    manager.write_recovery_marker("crashed-session")
    result = manager.check_for_crash()

    assert result == "crashed-session"


def test_check_for_crash_corrupt_marker(campaign_path, mock_serializer):
    """Test check_for_crash handles corrupt marker gracefully."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    campaign_path.mkdir(parents=True, exist_ok=True)
    with open(manager.marker_file, "w") as f:
        f.write("invalid json{")

    result = manager.check_for_crash()
    assert result is None
    assert not manager.marker_file.exists()  # Corrupt marker removed


def test_recover_session_success(campaign_path, mock_serializer):
    """Test successful session recovery."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    session_data = {
        "session_id": "recovered-session",
        "turn_count": 10,
        "campaign_id": "test-campaign",
    }
    mock_serializer.load_session.return_value = session_data

    manager.write_recovery_marker("recovered-session")
    result = manager.recover_session("recovered-session")

    assert result.success is True
    assert result.strategy_used == "crash_recovery"
    assert "turn 10" in result.message
    assert not manager.marker_file.exists()  # Marker cleaned up


def test_recover_session_failure(campaign_path, mock_serializer):
    """Test recovery failure when session data not found."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    mock_serializer.load_session.return_value = None

    result = manager.recover_session("missing-session")

    assert result.success is False
    assert result.strategy_used == "crash_recovery"


def test_clean_recovery_marker(campaign_path, mock_serializer):
    """Test cleaning recovery marker on normal shutdown."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    manager.write_recovery_marker("test-session")
    assert manager.marker_file.exists()

    manager.clean_recovery_marker()
    assert not manager.marker_file.exists()


def test_has_crashed_session(campaign_path, mock_serializer):
    """Test has_crashed_session convenience method."""
    manager = CrashRecoveryManager(campaign_path, mock_serializer)

    assert manager.has_crashed_session() is False

    manager.write_recovery_marker("test-session")
    assert manager.has_crashed_session() is True


# ============================================================================
# ErrorMessageFormatter Tests
# ============================================================================


def test_error_message_formatter_init():
    """Test ErrorMessageFormatter initialization."""
    formatter = ErrorMessageFormatter()
    assert formatter is not None


def test_format_timeout_error():
    """Test formatting timeout errors."""
    formatter = ErrorMessageFormatter()
    error = ClaudmasterTimeoutError(
        "Timeout occurred", operation="agent_run", timeout_seconds=30.0
    )

    message = formatter.format_error(error)

    assert "timeout" in message.lower() or "delayed" in message.lower()
    assert "30" in message
    assert "agent_run" in message


def test_format_agent_error_recoverable():
    """Test formatting recoverable agent errors."""
    formatter = ErrorMessageFormatter()
    error = AgentError("Test error", agent_name="narrator", recoverable=True)

    message = formatter.format_error(error)

    assert "narrator" in message.lower() or "storyteller" in message.lower()
    assert "recoverable" in message.lower() or "temporary" in message.lower()


def test_format_agent_error_unrecoverable():
    """Test formatting unrecoverable agent errors."""
    formatter = ErrorMessageFormatter()
    error = AgentError("Critical error", agent_name="archivist", recoverable=False)

    message = formatter.format_error(error)

    assert "archivist" in message.lower() or "keeper" in message.lower()
    assert "pause" in message.lower() or "unrecoverable" in message.lower()


def test_format_state_error():
    """Test formatting state errors."""
    formatter = ErrorMessageFormatter()
    error = StateError("State corrupted")

    message = formatter.format_error(error)

    assert "state" in message.lower() or "reality" in message.lower()


def test_format_session_error():
    """Test formatting session errors."""
    formatter = ErrorMessageFormatter()
    error = SessionError("Session failed")

    message = formatter.format_error(error)

    assert "session" in message.lower()


def test_format_rollback_error():
    """Test formatting rollback errors."""
    formatter = ErrorMessageFormatter()
    error = RollbackError("Rollback failed")

    message = formatter.format_error(error)

    assert "restore" in message.lower() or "rollback" in message.lower()


def test_format_recovery_error():
    """Test formatting recovery errors."""
    formatter = ErrorMessageFormatter()
    error = RecoveryError("Recovery failed")

    message = formatter.format_error(error)

    assert "recovery" in message.lower()


def test_format_generic_claudmaster_error():
    """Test formatting generic Claudmaster errors."""
    formatter = ErrorMessageFormatter()
    error = ClaudmasterError("Generic error")

    message = formatter.format_error(error)

    assert "unexpected" in message.lower() or "claudmastererror" in message.lower()


def test_format_unknown_error():
    """Test formatting unknown error types."""
    formatter = ErrorMessageFormatter()
    error = ValueError("Unknown error")

    message = formatter.format_error(error)

    assert "unexpected" in message.lower() or "unforeseen" in message.lower()
    assert "ValueError" in message


def test_suggest_recovery_action_timeout():
    """Test recovery suggestions for timeout errors."""
    formatter = ErrorMessageFormatter()
    error = ClaudmasterTimeoutError("Timeout", operation="test", timeout_seconds=30.0)

    suggestion = formatter.suggest_recovery_action(error)

    assert "try again" in suggestion.lower() or "wait" in suggestion.lower()


def test_suggest_recovery_action_recoverable_agent():
    """Test recovery suggestions for recoverable agent errors."""
    formatter = ErrorMessageFormatter()
    error = AgentError("Error", agent_name="test", recoverable=True)

    suggestion = formatter.suggest_recovery_action(error)

    assert "try" in suggestion.lower() or "rephrase" in suggestion.lower()


def test_suggest_recovery_action_unrecoverable_agent():
    """Test recovery suggestions for unrecoverable agent errors."""
    formatter = ErrorMessageFormatter()
    error = AgentError("Error", agent_name="test", recoverable=False)

    suggestion = formatter.suggest_recovery_action(error)

    assert "save" in suggestion.lower()


def test_suggest_recovery_action_state_error():
    """Test recovery suggestions for state errors."""
    formatter = ErrorMessageFormatter()
    error = StateError("State corrupted")

    suggestion = formatter.suggest_recovery_action(error)

    assert "save" in suggestion.lower()


def test_format_degradation_notice():
    """Test formatting degradation notices."""
    formatter = ErrorMessageFormatter()

    message = formatter.format_degradation_notice(
        level="reduced", reason="Agent failure", available_actions=["exploration", "combat"]
    )

    assert "reduced" in message.lower()
    assert "exploration" in message
    assert "combat" in message


def test_format_crash_recovery_notice():
    """Test formatting crash recovery notices."""
    formatter = ErrorMessageFormatter()

    message = formatter.format_crash_recovery_notice(
        session_id="test-123", turn_count=15, timestamp="2026-02-07T10:00:00"
    )

    assert "recovered" in message.lower() or "restore" in message.lower()
    assert "15" in message
    assert "test-123" in message


# ============================================================================
# Integration Tests
# ============================================================================


@pytest.mark.anyio
async def test_recovery_result_dataclass():
    """Test RecoveryResult dataclass creation."""
    result = RecoveryResult(
        success=True,
        strategy_used="retry",
        message="Recovered successfully",
        response=None,
        degradation_level=None,
    )

    assert result.success is True
    assert result.strategy_used == "retry"
    assert result.message == "Recovered successfully"
    assert result.response is None
    assert result.degradation_level is None


def test_state_snapshot_dataclass():
    """Test StateSnapshot dataclass creation."""
    snapshot = StateSnapshot(
        snapshot_id="test-id",
        label="test-label",
        timestamp=datetime.now(),
        session_data={"turn_count": 5},
        turn_count=5,
    )

    assert snapshot.snapshot_id == "test-id"
    assert snapshot.label == "test-label"
    assert snapshot.session_data["turn_count"] == 5
    assert snapshot.turn_count == 5
