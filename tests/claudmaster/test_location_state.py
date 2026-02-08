"""
Tests for location state management module.

Tests StateChange, LocationState, and LocationStateManager classes for
tracking persistent state changes in locations.
"""

import pytest
from pathlib import Path

from dm20_protocol.claudmaster.consistency.location_state import (
    StateChange,
    StateChangeType,
    LocationState,
    LocationStateManager,
)
from dm20_protocol.claudmaster.consistency.timeline import GameTime


class TestStateChange:
    """Tests for StateChange class."""

    def test_create_state_change(self):
        """Test creating a state change."""
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)
        change = StateChange(
            id="sc_001",
            change_type=StateChangeType.DOOR_OPENED,
            description="Opened the iron door",
            game_time=gt,
            session_number=1,
            target_object="iron_door",
            reversible=True
        )
        assert change.id == "sc_001"
        assert change.change_type == StateChangeType.DOOR_OPENED
        assert change.target_object == "iron_door"
        assert change.reversible is True
        assert change.reverted is False


class TestLocationStateManager:
    """Tests for LocationStateManager class."""

    def test_get_location_state_new(self, tmp_path):
        """Test getting state for a new location."""
        manager = LocationStateManager(tmp_path)
        state = manager.get_location_state("dungeon_1")
        assert state.location_id == "dungeon_1"
        assert state.visited is False
        assert len(state.state_changes) == 0

    def test_record_state_change(self, tmp_path):
        """Test recording a state change."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)
        change = StateChange(
            change_type=StateChangeType.DOOR_OPENED,
            description="Opened the door",
            game_time=gt,
            session_number=1,
            target_object="door_1"
        )
        change_id = manager.record_state_change("dungeon_1", change)
        assert change_id.startswith("sc_")

        state = manager.get_location_state("dungeon_1")
        assert len(state.state_changes) == 1
        assert state.state_changes[0].target_object == "door_1"

    def test_is_door_open_after_opening(self, tmp_path):
        """Test door state after opening."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        # Door should be closed by default
        assert manager.is_door_open("dungeon_1", "door_1") is False

        # Open the door
        change = StateChange(
            change_type=StateChangeType.DOOR_OPENED,
            description="Opened the door",
            game_time=gt,
            session_number=1,
            target_object="door_1"
        )
        manager.record_state_change("dungeon_1", change)

        # Door should now be open
        assert manager.is_door_open("dungeon_1", "door_1") is True

    def test_is_door_closed_default(self, tmp_path):
        """Test that doors are closed by default."""
        manager = LocationStateManager(tmp_path)
        assert manager.is_door_open("dungeon_1", "any_door") is False

    def test_is_door_locked(self, tmp_path):
        """Test door locking."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        # Open the door
        change1 = StateChange(
            change_type=StateChangeType.DOOR_OPENED,
            description="Opened the door",
            game_time=gt,
            session_number=1,
            target_object="door_1"
        )
        manager.record_state_change("dungeon_1", change1)
        assert manager.is_door_open("dungeon_1", "door_1") is True

        # Lock the door
        gt2 = gt.advance(1, "minute")
        change2 = StateChange(
            change_type=StateChangeType.DOOR_LOCKED,
            description="Locked the door",
            game_time=gt2,
            session_number=1,
            target_object="door_1"
        )
        manager.record_state_change("dungeon_1", change2)

        # Door should now be closed
        assert manager.is_door_open("dungeon_1", "door_1") is False

    def test_door_broken(self, tmp_path):
        """Test broken door state."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        # Break the door
        change = StateChange(
            change_type=StateChangeType.DOOR_BROKEN,
            description="Broke down the door",
            game_time=gt,
            session_number=1,
            target_object="door_1"
        )
        manager.record_state_change("dungeon_1", change)

        # Broken door is considered open
        assert manager.is_door_open("dungeon_1", "door_1") is True

    def test_is_trap_active_default(self, tmp_path):
        """Test that traps are active by default."""
        manager = LocationStateManager(tmp_path)
        assert manager.is_trap_active("dungeon_1", "trap_1") is True

    def test_is_trap_triggered(self, tmp_path):
        """Test trap after being triggered."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        # Trigger the trap
        change = StateChange(
            change_type=StateChangeType.TRAP_TRIGGERED,
            description="Trap triggered!",
            game_time=gt,
            session_number=1,
            target_object="trap_1"
        )
        manager.record_state_change("dungeon_1", change)

        # Trap should no longer be active
        assert manager.is_trap_active("dungeon_1", "trap_1") is False

    def test_is_trap_disarmed(self, tmp_path):
        """Test trap after being disarmed."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        # Disarm the trap
        change = StateChange(
            change_type=StateChangeType.TRAP_DISARMED,
            description="Trap disarmed",
            game_time=gt,
            session_number=1,
            target_object="trap_1"
        )
        manager.record_state_change("dungeon_1", change)

        # Trap should no longer be active
        assert manager.is_trap_active("dungeon_1", "trap_1") is False

    def test_is_loot_collected(self, tmp_path):
        """Test loot collection."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        # Loot not collected by default
        assert manager.is_loot_collected("dungeon_1", "chest_1") is False

        # Collect the loot
        change = StateChange(
            change_type=StateChangeType.LOOT_COLLECTED,
            description="Collected treasure",
            game_time=gt,
            session_number=1,
            target_object="chest_1"
        )
        manager.record_state_change("dungeon_1", change)

        # Loot should now be collected
        assert manager.is_loot_collected("dungeon_1", "chest_1") is True

    def test_is_loot_not_collected(self, tmp_path):
        """Test loot that hasn't been collected."""
        manager = LocationStateManager(tmp_path)
        assert manager.is_loot_collected("dungeon_1", "chest_99") is False

    def test_get_changes_since(self, tmp_path):
        """Test retrieving changes since a specific time."""
        manager = LocationStateManager(tmp_path)
        gt1 = GameTime(year=1492, month=1, day=1, hour=10, minute=0)
        gt2 = GameTime(year=1492, month=1, day=1, hour=11, minute=0)
        gt3 = GameTime(year=1492, month=1, day=1, hour=12, minute=0)

        # Add changes at different times
        change1 = StateChange(
            change_type=StateChangeType.DOOR_OPENED,
            description="Change 1",
            game_time=gt1,
            session_number=1
        )
        change2 = StateChange(
            change_type=StateChangeType.TRAP_TRIGGERED,
            description="Change 2",
            game_time=gt2,
            session_number=1
        )
        change3 = StateChange(
            change_type=StateChangeType.LOOT_COLLECTED,
            description="Change 3",
            game_time=gt3,
            session_number=1
        )

        manager.record_state_change("dungeon_1", change1)
        manager.record_state_change("dungeon_1", change2)
        manager.record_state_change("dungeon_1", change3)

        # Get changes since gt2
        changes = manager.get_changes_since("dungeon_1", gt2)
        assert len(changes) == 2
        assert changes[0].description == "Change 2"
        assert changes[1].description == "Change 3"

    def test_revert_change_reversible(self, tmp_path):
        """Test reverting a reversible change."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        change = StateChange(
            id="sc_001",
            change_type=StateChangeType.DOOR_OPENED,
            description="Opened door",
            game_time=gt,
            session_number=1,
            target_object="door_1",
            reversible=True
        )
        change_id = manager.record_state_change("dungeon_1", change)

        # Door should be open
        assert manager.is_door_open("dungeon_1", "door_1") is True

        # Revert the change
        success = manager.revert_change("dungeon_1", change_id)
        assert success is True

        # Door should be closed again (change is reverted)
        assert manager.is_door_open("dungeon_1", "door_1") is False

    def test_revert_change_irreversible(self, tmp_path):
        """Test attempting to revert an irreversible change."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        change = StateChange(
            id="sc_001",
            change_type=StateChangeType.DOOR_BROKEN,
            description="Broke door",
            game_time=gt,
            session_number=1,
            target_object="door_1",
            reversible=False
        )
        change_id = manager.record_state_change("dungeon_1", change)

        # Attempt to revert
        success = manager.revert_change("dungeon_1", change_id)
        assert success is False

    def test_mark_visited(self, tmp_path):
        """Test marking a location as visited."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        state = manager.get_location_state("dungeon_1")
        assert state.visited is False
        assert state.first_visited is None

        manager.mark_visited("dungeon_1", gt)

        state = manager.get_location_state("dungeon_1")
        assert state.visited is True
        assert state.first_visited == gt
        assert state.last_visited == gt

    def test_mark_visited_updates_last(self, tmp_path):
        """Test that subsequent visits update last_visited."""
        manager = LocationStateManager(tmp_path)
        gt1 = GameTime(year=1492, month=1, day=1, hour=10, minute=0)
        gt2 = GameTime(year=1492, month=1, day=2, hour=10, minute=0)

        manager.mark_visited("dungeon_1", gt1)
        manager.mark_visited("dungeon_1", gt2)

        state = manager.get_location_state("dungeon_1")
        assert state.first_visited == gt1
        assert state.last_visited == gt2

    def test_get_location_summary(self, tmp_path):
        """Test getting location summary."""
        manager = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        manager.mark_visited("dungeon_1", gt)

        change1 = StateChange(
            change_type=StateChangeType.DOOR_OPENED,
            description="Change 1",
            game_time=gt,
            session_number=1,
            reversible=True
        )
        change2 = StateChange(
            change_type=StateChangeType.TRAP_TRIGGERED,
            description="Change 2",
            game_time=gt,
            session_number=1
        )

        id1 = manager.record_state_change("dungeon_1", change1)
        manager.record_state_change("dungeon_1", change2)

        # Revert one change
        manager.revert_change("dungeon_1", id1)

        summary = manager.get_location_summary("dungeon_1")
        assert summary["location_id"] == "dungeon_1"
        assert summary["visited"] is True
        assert summary["total_changes"] == 2
        assert summary["active_changes"] == 1  # One was reverted

    def test_save_and_load(self, tmp_path):
        """Test persistence round-trip."""
        manager1 = LocationStateManager(tmp_path)
        gt = GameTime(year=1492, month=1, day=1, hour=10, minute=0)

        manager1.mark_visited("dungeon_1", gt)

        change = StateChange(
            change_type=StateChangeType.LOOT_COLLECTED,
            description="Collected gold",
            game_time=gt,
            session_number=1,
            target_object="chest_1"
        )
        manager1.record_state_change("dungeon_1", change)
        manager1.save()

        # Load into new manager
        manager2 = LocationStateManager(tmp_path)
        assert manager2.location_count == 1

        state = manager2.get_location_state("dungeon_1")
        assert state.visited is True
        assert len(state.state_changes) == 1
        assert state.state_changes[0].description == "Collected gold"
        assert manager2.is_loot_collected("dungeon_1", "chest_1") is True

    def test_location_count(self, tmp_path):
        """Test location count property."""
        manager = LocationStateManager(tmp_path)
        assert manager.location_count == 0

        manager.get_location_state("dungeon_1")
        assert manager.location_count == 1

        manager.get_location_state("dungeon_2")
        assert manager.location_count == 2
