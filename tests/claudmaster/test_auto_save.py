"""
Comprehensive tests for the AutoSaveManager.

Tests cover:
- Initialization and configuration
- Auto-save triggering based on interval
- Interrupt saves
- Checkpoint management
- Edge cases and error handling
"""

import pytest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from gamemaster_mcp.claudmaster.continuity import AutoSaveManager
from gamemaster_mcp.claudmaster.session import ClaudmasterSession
from gamemaster_mcp.claudmaster.persistence.session_serializer import SessionSerializer


class TestAutoSaveManagerInitialization:
    """Tests for AutoSaveManager initialization."""

    def test_init_with_defaults(self, tmp_path):
        """Test initialization with default parameters."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)

        manager = AutoSaveManager(session, serializer)

        assert manager.session == session
        assert manager.serializer == serializer
        assert manager.save_interval == 5  # Default
        assert manager.last_save is None
        assert manager.checkpoints == []

    def test_init_with_custom_interval(self, tmp_path):
        """Test initialization with custom save interval."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)

        manager = AutoSaveManager(session, serializer, save_interval_minutes=10)

        assert manager.save_interval == 10

    def test_max_checkpoints_constant(self):
        """Test that MAX_CHECKPOINTS constant is defined."""
        assert hasattr(AutoSaveManager, "MAX_CHECKPOINTS")
        assert AutoSaveManager.MAX_CHECKPOINTS == 10


class TestShouldSave:
    """Tests for should_save() method."""

    def test_should_save_when_never_saved(self, tmp_path):
        """Test that should_save returns True when no save has occurred."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        assert manager.should_save() is True

    def test_should_save_after_interval_elapsed(self, tmp_path):
        """Test that should_save returns True after interval has elapsed."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=5)

        # Set last save to 6 minutes ago
        manager.last_save = datetime.now(timezone.utc) - timedelta(minutes=6)

        assert manager.should_save() is True

    def test_should_not_save_before_interval(self, tmp_path):
        """Test that should_save returns False before interval has elapsed."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=5)

        # Set last save to 3 minutes ago
        manager.last_save = datetime.now(timezone.utc) - timedelta(minutes=3)

        assert manager.should_save() is False

    def test_should_save_at_exact_interval(self, tmp_path):
        """Test that should_save returns True at exact interval boundary."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=5)

        # Set last save to exactly 5 minutes ago
        manager.last_save = datetime.now(timezone.utc) - timedelta(minutes=5)

        assert manager.should_save() is True


class TestTriggerAutosave:
    """Tests for trigger_autosave() method."""

    @pytest.mark.anyio
    async def test_trigger_autosave_when_needed(self, tmp_path):
        """Test that autosave triggers when interval has elapsed."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        session.turn_count = 10
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=5)

        # Set last save to trigger save
        manager.last_save = datetime.now(timezone.utc) - timedelta(minutes=6)

        result = await manager.trigger_autosave()

        assert result is True
        assert manager.last_save is not None
        # Check that save was created
        session_dir = tmp_path / "claudmaster_sessions" / session.session_id
        assert session_dir.exists()

    @pytest.mark.anyio
    async def test_trigger_autosave_skips_when_not_needed(self, tmp_path):
        """Test that autosave skips when interval hasn't elapsed."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=5)

        # Set last save to recent time
        manager.last_save = datetime.now(timezone.utc) - timedelta(minutes=2)

        result = await manager.trigger_autosave()

        assert result is False

    @pytest.mark.anyio
    async def test_trigger_autosave_saves_session_data(self, tmp_path):
        """Test that autosave properly saves all session data."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        session.turn_count = 15
        session.add_message("user", "I attack the goblin")
        session.add_message("assistant", "You hit the goblin!")
        session.set_agent_status("narrator", "completed")

        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        result = await manager.trigger_autosave()

        assert result is True

        # Verify saved data
        loaded = serializer.load_session(session.session_id)
        assert loaded is not None
        assert loaded["turn_count"] == 15
        assert len(loaded["conversation_history"]) == 2
        assert loaded["active_agents"]["narrator"] == "completed"

    @pytest.mark.anyio
    async def test_trigger_autosave_handles_serializer_error(self, tmp_path):
        """Test that autosave handles serializer errors gracefully."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        # Mock save_session to raise an error
        with patch.object(serializer, 'save_session', side_effect=IOError("Disk full")):
            result = await manager.trigger_autosave()

            assert result is False
            # last_save should not be updated on error
            assert manager.last_save is None


class TestSaveOnInterrupt:
    """Tests for save_on_interrupt() method."""

    @pytest.mark.anyio
    async def test_save_on_interrupt_saves_immediately(self, tmp_path):
        """Test that interrupt save happens immediately regardless of interval."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        session.turn_count = 7
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=60)

        # Set last save to very recent time
        manager.last_save = datetime.now(timezone.utc) - timedelta(seconds=10)

        await manager.save_on_interrupt()

        # Verify save occurred
        session_dir = tmp_path / "claudmaster_sessions" / session.session_id
        assert session_dir.exists()

        # Verify last_save was updated
        assert manager.last_save is not None

    @pytest.mark.anyio
    async def test_save_on_interrupt_includes_timestamp(self, tmp_path):
        """Test that interrupt save includes timestamp in notes."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        await manager.save_on_interrupt()

        # Load metadata and check notes
        metadata = serializer.load_metadata(session.session_id)
        assert metadata is not None
        assert "Session interrupted" in metadata.save_notes
        # Should contain ISO timestamp
        assert "T" in metadata.save_notes
        assert ":" in metadata.save_notes

    @pytest.mark.anyio
    async def test_save_on_interrupt_raises_on_error(self, tmp_path):
        """Test that interrupt save raises exceptions instead of catching them."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        # Mock save_session to raise an error
        with patch.object(serializer, 'save_session', side_effect=IOError("Disk full")):
            with pytest.raises(IOError, match="Disk full"):
                await manager.save_on_interrupt()


class TestMarkCheckpoint:
    """Tests for checkpoint management."""

    def test_mark_checkpoint_creates_checkpoint(self, tmp_path):
        """Test that mark_checkpoint creates a checkpoint entry."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        session.turn_count = 5
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        manager.mark_checkpoint("Party entered the dungeon")

        assert len(manager.checkpoints) == 1
        checkpoint = manager.checkpoints[0]
        assert checkpoint["description"] == "Party entered the dungeon"
        assert checkpoint["turn_count"] == 5
        assert "timestamp" in checkpoint

    def test_mark_checkpoint_records_correct_turn(self, tmp_path):
        """Test that checkpoints record the correct turn count."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        session.turn_count = 10
        manager.mark_checkpoint("First checkpoint")

        session.turn_count = 20
        manager.mark_checkpoint("Second checkpoint")

        assert manager.checkpoints[0]["turn_count"] == 10
        assert manager.checkpoints[1]["turn_count"] == 20

    def test_mark_checkpoint_limits_to_max(self, tmp_path):
        """Test that checkpoint list is limited to MAX_CHECKPOINTS."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        # Add more than MAX_CHECKPOINTS
        for i in range(15):
            manager.mark_checkpoint(f"Checkpoint {i}")

        assert len(manager.checkpoints) == AutoSaveManager.MAX_CHECKPOINTS
        # First checkpoint should be removed (FIFO)
        assert manager.checkpoints[0]["description"] == "Checkpoint 5"
        assert manager.checkpoints[-1]["description"] == "Checkpoint 14"

    def test_mark_checkpoint_fifo_behavior(self, tmp_path):
        """Test that old checkpoints are removed in FIFO order."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        # Fill to limit
        for i in range(AutoSaveManager.MAX_CHECKPOINTS):
            manager.mark_checkpoint(f"Checkpoint {i}")

        # Add one more
        manager.mark_checkpoint("New checkpoint")

        # First checkpoint should be gone
        descriptions = [cp["description"] for cp in manager.checkpoints]
        assert "Checkpoint 0" not in descriptions
        assert "New checkpoint" in descriptions


class TestGetCheckpoints:
    """Tests for get_checkpoints() method."""

    def test_get_checkpoints_returns_list(self, tmp_path):
        """Test that get_checkpoints returns a list."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        checkpoints = manager.get_checkpoints()

        assert isinstance(checkpoints, list)

    def test_get_checkpoints_returns_empty_when_none(self, tmp_path):
        """Test that get_checkpoints returns empty list when no checkpoints."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        checkpoints = manager.get_checkpoints()

        assert checkpoints == []

    def test_get_checkpoints_returns_copy(self, tmp_path):
        """Test that get_checkpoints returns a copy, not the original list."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        manager.mark_checkpoint("Test checkpoint")

        checkpoints = manager.get_checkpoints()
        checkpoints.append({"fake": "checkpoint"})

        # Original should be unchanged
        assert len(manager.checkpoints) == 1

    def test_get_checkpoints_contains_all_fields(self, tmp_path):
        """Test that checkpoint dictionaries contain all expected fields."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        session.turn_count = 5
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer)

        manager.mark_checkpoint("Test checkpoint")

        checkpoints = manager.get_checkpoints()
        checkpoint = checkpoints[0]

        assert "timestamp" in checkpoint
        assert "turn_count" in checkpoint
        assert "description" in checkpoint
        assert checkpoint["turn_count"] == 5
        assert checkpoint["description"] == "Test checkpoint"


class TestIntegration:
    """Integration tests for AutoSaveManager."""

    @pytest.mark.anyio
    async def test_full_session_lifecycle(self, tmp_path):
        """Test complete session lifecycle with auto-saves and checkpoints."""
        session = ClaudmasterSession(campaign_id="test_campaign")
        serializer = SessionSerializer(tmp_path)
        manager = AutoSaveManager(session, serializer, save_interval_minutes=1)

        # Initial state
        session.add_message("user", "I enter the dungeon")
        manager.mark_checkpoint("Entered dungeon")

        # First autosave (should save since last_save is None)
        result = await manager.trigger_autosave()
        assert result is True

        # Add more activity
        session.increment_turn()
        session.add_message("assistant", "You see a dark corridor")
        manager.mark_checkpoint("Found corridor")

        # Try autosave immediately (should skip)
        result = await manager.trigger_autosave()
        assert result is False

        # Simulate time passing
        manager.last_save = datetime.now(timezone.utc) - timedelta(minutes=2)

        # Autosave should trigger now
        result = await manager.trigger_autosave()
        assert result is True

        # Interrupt save
        session.add_message("user", "I need to stop")
        await manager.save_on_interrupt()

        # Verify checkpoints
        checkpoints = manager.get_checkpoints()
        assert len(checkpoints) == 2
        assert checkpoints[0]["description"] == "Entered dungeon"
        assert checkpoints[1]["description"] == "Found corridor"

        # Verify final save
        loaded = serializer.load_session(session.session_id)
        assert loaded is not None
        assert loaded["turn_count"] == 1
        assert len(loaded["conversation_history"]) == 3

    @pytest.mark.anyio
    async def test_multiple_sessions_independent(self, tmp_path):
        """Test that multiple sessions can have independent auto-save managers."""
        session1 = ClaudmasterSession(campaign_id="campaign1")
        session2 = ClaudmasterSession(campaign_id="campaign2")

        serializer = SessionSerializer(tmp_path)
        manager1 = AutoSaveManager(session1, serializer, save_interval_minutes=5)
        manager2 = AutoSaveManager(session2, serializer, save_interval_minutes=10)

        # Different intervals
        assert manager1.save_interval == 5
        assert manager2.save_interval == 10

        # Independent checkpoints
        manager1.mark_checkpoint("Session 1 checkpoint")
        manager2.mark_checkpoint("Session 2 checkpoint")

        assert len(manager1.get_checkpoints()) == 1
        assert len(manager2.get_checkpoints()) == 1
        assert manager1.get_checkpoints()[0]["description"] == "Session 1 checkpoint"
        assert manager2.get_checkpoints()[0]["description"] == "Session 2 checkpoint"
