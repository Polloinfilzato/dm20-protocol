"""
Tests for the Split Party Handling system.

Covers party splitting, group management, time tracking, reunification,
messaging, and edge cases.
"""

import pytest
from datetime import timedelta

from dm20_protocol.claudmaster.split_party import (
    PartyGroup,
    SplitEvent,
    ReunificationEvent,
    MessageResult,
    SplitProposal,
    SplitPartyManager,
)
from dm20_protocol.claudmaster.pc_tracking import (
    PCRegistry,
    MultiPlayerConfig,
)
from dm20_protocol.claudmaster.turn_manager import (
    TurnManager,
    TurnPhase,
)


@pytest.fixture
def config():
    """Create a multi-player configuration."""
    return MultiPlayerConfig(max_players=6, allow_dynamic_join=True)


@pytest.fixture
def pc_registry(config):
    """Create a PC registry with 4 registered PCs."""
    registry = PCRegistry(config)
    registry.register_pc("Gandalf", "Player1")
    registry.register_pc("Aragorn", "Player2")
    registry.register_pc("Legolas", "Player3")
    registry.register_pc("Gimli", "Player4")
    return registry


@pytest.fixture
def turn_manager(pc_registry, config):
    """Create a turn manager."""
    return TurnManager(pc_registry, config)


@pytest.fixture
def split_manager(pc_registry, turn_manager):
    """Create a split party manager."""
    return SplitPartyManager(pc_registry, turn_manager)


class TestPartyGroup:
    """Tests for PartyGroup data model."""

    def test_party_group_creation(self):
        """Test creating a PartyGroup."""
        group = PartyGroup(
            group_id="test-group",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern",
            is_active=True
        )

        assert group.group_id == "test-group"
        assert group.member_ids == {"Gandalf", "Aragorn"}
        assert group.location == "Tavern"
        assert group.is_active is True
        assert group.scene_description is None
        assert group.time_elapsed == timedelta(seconds=0)
        assert group.pending_events == []

    def test_party_group_with_optional_fields(self):
        """Test PartyGroup with all optional fields."""
        group = PartyGroup(
            group_id="test-group",
            member_ids={"Gandalf"},
            location="Dungeon",
            scene_description="Dark and spooky",
            is_active=True,
            time_elapsed=timedelta(minutes=30),
            pending_events=["Trap triggered", "Monster spotted"]
        )

        assert group.scene_description == "Dark and spooky"
        assert group.time_elapsed == timedelta(minutes=30)
        assert len(group.pending_events) == 2


class TestSplitPartyManager:
    """Tests for SplitPartyManager."""

    def test_initialization(self, split_manager, pc_registry, turn_manager):
        """Test manager initialization."""
        assert split_manager.pc_registry == pc_registry
        assert split_manager.turn_manager == turn_manager
        assert split_manager.groups == {}
        assert split_manager.active_group_id is None
        assert split_manager.split_history == []
        assert split_manager.reunification_history == []

    def test_is_party_split_false_initially(self, split_manager):
        """Test is_party_split returns False when no groups exist."""
        assert split_manager.is_party_split() is False

    def test_is_party_split_false_with_one_group(self, split_manager):
        """Test is_party_split returns False with only one group."""
        split_manager.groups["group1"] = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern"
        )
        assert split_manager.is_party_split() is False

    def test_is_party_split_true_with_multiple_groups(self, split_manager):
        """Test is_party_split returns True with multiple groups."""
        split_manager.groups["group1"] = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern"
        )
        split_manager.groups["group2"] = PartyGroup(
            group_id="group2",
            member_ids={"Legolas", "Gimli"},
            location="Dungeon"
        )
        assert split_manager.is_party_split() is True

    def test_get_group_for_pc_not_in_any_group(self, split_manager):
        """Test get_group_for_pc returns None when PC not in any group."""
        group = split_manager.get_group_for_pc("Gandalf")
        assert group is None

    def test_get_group_for_pc_finds_correct_group(self, split_manager):
        """Test get_group_for_pc returns the correct group."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas", "Gimli"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        found_group = split_manager.get_group_for_pc("Legolas")
        assert found_group is not None
        assert found_group.group_id == "group2"
        assert "Legolas" in found_group.member_ids


class TestExecuteSplit:
    """Tests for execute_split method."""

    def test_execute_split_creates_two_groups(self, split_manager):
        """Test first split creates both remaining and departing groups."""
        departing = {"Legolas", "Gimli"}
        group = split_manager.execute_split(
            departing_pcs=departing,
            destination="Dungeon",
            remaining_location="Tavern"
        )

        # Should create 2 groups
        assert len(split_manager.groups) == 2
        assert split_manager.is_party_split() is True

        # Departing group should exist
        assert "Legolas" in group.member_ids
        assert "Gimli" in group.member_ids
        assert group.location == "Dungeon"

        # Remaining group should exist
        remaining_groups = [
            g for g in split_manager.groups.values()
            if g.group_id != group.group_id
        ]
        assert len(remaining_groups) == 1
        remaining = remaining_groups[0]
        assert "Gandalf" in remaining.member_ids
        assert "Aragorn" in remaining.member_ids

    def test_execute_split_records_event(self, split_manager):
        """Test that split is recorded in history."""
        departing = {"Legolas", "Gimli"}
        split_manager.execute_split(
            departing_pcs=departing,
            destination="Dungeon"
        )

        assert len(split_manager.split_history) == 1
        event = split_manager.split_history[0]
        assert event.departing_pcs == departing
        assert event.destination == "Dungeon"
        assert len(event.groups_created) == 2  # First split creates both

    def test_execute_split_invalid_pc_raises_error(self, split_manager):
        """Test that invalid PC IDs raise ValueError."""
        with pytest.raises(ValueError, match="Invalid character IDs"):
            split_manager.execute_split(
                departing_pcs={"NonExistentPC"},
                destination="Dungeon"
            )

    def test_execute_split_removes_from_existing_groups(self, split_manager):
        """Test that PCs are removed from their old group when splitting."""
        # Create initial group
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn", "Legolas"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        # Split off Legolas
        split_manager.execute_split(
            departing_pcs={"Legolas"},
            destination="Dungeon"
        )

        # Legolas should no longer be in group1
        assert "Legolas" not in split_manager.groups["group1"].member_ids
        assert "Gandalf" in split_manager.groups["group1"].member_ids

    def test_execute_split_cleans_up_empty_groups(self, split_manager):
        """Test that empty groups are removed after split."""
        # Create a group with only one member
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Legolas"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        # Split that one member away
        split_manager.execute_split(
            departing_pcs={"Legolas"},
            destination="Dungeon"
        )

        # group1 should be deleted (empty)
        assert "group1" not in split_manager.groups


class TestGroupSwitching:
    """Tests for switching between groups."""

    def test_switch_to_group_success(self, split_manager):
        """Test switching to a valid group."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        result = split_manager.switch_to_group("group1")

        assert result.group_id == "group1"
        assert split_manager.active_group_id == "group1"

    def test_switch_to_group_invalid_raises_error(self, split_manager):
        """Test switching to non-existent group raises KeyError."""
        with pytest.raises(KeyError, match="does not exist"):
            split_manager.switch_to_group("invalid-group")

    def test_get_switch_narration(self, split_manager):
        """Test generating switch narration."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas", "Gimli"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        narration = split_manager.get_switch_narration("group1", "group2")

        # Should mention the destination location
        assert "Dungeon" in narration
        assert isinstance(narration, str)
        assert len(narration) > 0

    def test_get_switch_narration_invalid_group(self, split_manager):
        """Test switch narration with invalid group raises error."""
        with pytest.raises(KeyError):
            split_manager.get_switch_narration("invalid1", "invalid2")

    def test_get_switch_narration_consistency(self, split_manager):
        """Test that same group pair produces same narration."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        narration1 = split_manager.get_switch_narration("group1", "group2")
        narration2 = split_manager.get_switch_narration("group1", "group2")

        assert narration1 == narration2


class TestTimeManagement:
    """Tests for time tracking and synchronization."""

    def test_advance_group_time(self, split_manager):
        """Test advancing time for a specific group."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern",
            time_elapsed=timedelta(minutes=10)
        )
        split_manager.groups["group1"] = group1

        split_manager.advance_group_time("group1", timedelta(minutes=5))

        assert split_manager.groups["group1"].time_elapsed == timedelta(minutes=15)

    def test_advance_group_time_invalid_group(self, split_manager):
        """Test advancing time for non-existent group raises error."""
        with pytest.raises(KeyError, match="does not exist"):
            split_manager.advance_group_time("invalid", timedelta(minutes=5))

    def test_sync_all_groups(self, split_manager):
        """Test syncing all groups to the maximum time."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern",
            time_elapsed=timedelta(minutes=10)
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon",
            time_elapsed=timedelta(minutes=25)
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        max_time = split_manager.sync_all_groups()

        assert max_time == timedelta(minutes=25)
        assert split_manager.groups["group1"].time_elapsed == timedelta(minutes=25)
        assert split_manager.groups["group2"].time_elapsed == timedelta(minutes=25)

    def test_sync_all_groups_no_groups_raises_error(self, split_manager):
        """Test syncing with no groups raises ValueError."""
        with pytest.raises(ValueError, match="No groups to sync"):
            split_manager.sync_all_groups()

    def test_get_time_differential(self, split_manager):
        """Test calculating time difference between groups."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern",
            time_elapsed=timedelta(minutes=10)
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon",
            time_elapsed=timedelta(minutes=30)
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        diff = split_manager.get_time_differential("group1", "group2")

        assert diff == timedelta(minutes=20)

    def test_get_time_differential_invalid_groups(self, split_manager):
        """Test time differential with invalid groups raises error."""
        with pytest.raises(KeyError):
            split_manager.get_time_differential("invalid1", "invalid2")


class TestReunification:
    """Tests for merging groups back together."""

    def test_execute_reunification(self, split_manager):
        """Test merging two groups."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern",
            time_elapsed=timedelta(minutes=10),
            pending_events=["Event A"]
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas", "Gimli"},
            location="Dungeon",
            time_elapsed=timedelta(minutes=25),
            pending_events=["Event B"]
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        unified = split_manager.execute_reunification(
            groups_to_merge=["group1", "group2"],
            location="Forest",
            trigger="voluntary meeting"
        )

        # Should have all 4 members
        assert len(unified.member_ids) == 4
        assert "Gandalf" in unified.member_ids
        assert "Legolas" in unified.member_ids

        # Should sync to max time
        assert unified.time_elapsed == timedelta(minutes=25)

        # Should combine pending events
        assert "Event A" in unified.pending_events
        assert "Event B" in unified.pending_events

        # Old groups should be removed
        assert "group1" not in split_manager.groups
        assert "group2" not in split_manager.groups

        # Only unified group should remain
        assert len(split_manager.groups) == 1

    def test_execute_reunification_records_event(self, split_manager):
        """Test that reunification is recorded in history."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        split_manager.execute_reunification(
            groups_to_merge=["group1", "group2"],
            location="Forest"
        )

        assert len(split_manager.reunification_history) == 1
        event = split_manager.reunification_history[0]
        assert event.location == "Forest"
        assert "group1" in event.groups_merged
        assert "group2" in event.groups_merged

    def test_execute_reunification_too_few_groups_raises_error(self, split_manager):
        """Test that merging fewer than 2 groups raises ValueError."""
        with pytest.raises(ValueError, match="at least 2 groups"):
            split_manager.execute_reunification(
                groups_to_merge=["group1"],
                location="Forest"
            )

    def test_execute_reunification_invalid_group_raises_error(self, split_manager):
        """Test that invalid group ID raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            split_manager.execute_reunification(
                groups_to_merge=["invalid1", "invalid2"],
                location="Forest"
            )

    def test_execute_reunification_updates_active_group(self, split_manager):
        """Test that active_group_id is updated on reunification."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2
        split_manager.active_group_id = "group1"

        unified = split_manager.execute_reunification(
            groups_to_merge=["group1", "group2"],
            location="Forest"
        )

        # Active group should now be the unified group
        assert split_manager.active_group_id == unified.group_id

    def test_generate_catchup_summary(self, split_manager):
        """Test generating catchup summary for reunification."""
        event = ReunificationEvent(
            groups_merged=["group1", "group2"],
            location="Forest",
            trigger="voluntary meeting",
            time_adjustment=timedelta(minutes=15),
            shared_discoveries=["Found treasure", "Defeated orcs"]
        )

        summary = split_manager.generate_catchup_summary(event)

        assert "Forest" in summary
        assert "voluntary meeting" in summary
        assert "15 minutes" in summary
        assert "Found treasure" in summary
        assert "Defeated orcs" in summary


class TestMessaging:
    """Tests for cross-group messaging."""

    def test_send_message_same_group_instant(self, split_manager):
        """Test that same-group messages are instant."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf", "Aragorn"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        result = split_manager.send_message(
            from_pc="Gandalf",
            to_pc="Aragorn",
            message="Hello"
        )

        assert result.success is True
        assert result.delay == timedelta(seconds=0)
        assert "instant" in result.reason.lower()

    def test_send_message_cross_group_has_delay(self, split_manager):
        """Test that cross-group messages have a delay."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        result = split_manager.send_message(
            from_pc="Gandalf",
            to_pc="Legolas",
            message="Hello"
        )

        assert result.success is True
        assert result.delay > timedelta(seconds=0)
        assert "delay" in result.reason.lower()

    def test_send_message_invalid_from_pc_raises_error(self, split_manager):
        """Test that invalid from_pc raises ValueError."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        with pytest.raises(ValueError, match="not in any group"):
            split_manager.send_message(
                from_pc="InvalidPC",
                to_pc="Gandalf",
                message="Hello"
            )

    def test_send_message_invalid_to_pc_raises_error(self, split_manager):
        """Test that invalid to_pc raises ValueError."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        with pytest.raises(ValueError, match="not in any group"):
            split_manager.send_message(
                from_pc="Gandalf",
                to_pc="InvalidPC",
                message="Hello"
            )


class TestEventBroadcast:
    """Tests for broadcasting events to groups."""

    def test_broadcast_event_to_all_groups(self, split_manager):
        """Test broadcasting event to all groups."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        split_manager.broadcast_event("Earthquake!")

        assert "Earthquake!" in split_manager.groups["group1"].pending_events
        assert "Earthquake!" in split_manager.groups["group2"].pending_events

    def test_broadcast_event_to_specific_groups(self, split_manager):
        """Test broadcasting event to specific groups only."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        split_manager.broadcast_event(
            "Trap triggered!",
            affected_groups=["group2"]
        )

        assert "Trap triggered!" not in split_manager.groups["group1"].pending_events
        assert "Trap triggered!" in split_manager.groups["group2"].pending_events

    def test_broadcast_event_invalid_group_raises_error(self, split_manager):
        """Test broadcasting to non-existent group raises ValueError."""
        with pytest.raises(ValueError, match="does not exist"):
            split_manager.broadcast_event(
                "Event",
                affected_groups=["invalid-group"]
            )


class TestGettersAndQueries:
    """Tests for getter and query methods."""

    def test_get_active_groups(self, split_manager):
        """Test getting all active groups."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern",
            is_active=True
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Legolas"},
            location="Dungeon",
            is_active=False
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2

        active = split_manager.get_active_groups()

        assert len(active) == 1
        assert active[0].group_id == "group1"

    def test_get_group_exists(self, split_manager):
        """Test get_group returns the correct group."""
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        split_manager.groups["group1"] = group1

        found = split_manager.get_group("group1")

        assert found is not None
        assert found.group_id == "group1"

    def test_get_group_not_exists(self, split_manager):
        """Test get_group returns None for non-existent group."""
        found = split_manager.get_group("invalid")
        assert found is None


class TestComplexScenarios:
    """Tests for complex multi-split scenarios."""

    def test_multiple_sequential_splits(self, split_manager):
        """Test multiple sequential splits."""
        # First split
        split_manager.execute_split(
            departing_pcs={"Legolas", "Gimli"},
            destination="Dungeon"
        )
        assert len(split_manager.groups) == 2

        # Second split from remaining group
        split_manager.execute_split(
            departing_pcs={"Aragorn"},
            destination="Forest"
        )
        assert len(split_manager.groups) == 3

        # Verify all PCs are accounted for
        all_members = set()
        for group in split_manager.groups.values():
            all_members.update(group.member_ids)
        assert all_members == {"Gandalf", "Aragorn", "Legolas", "Gimli"}

    def test_partial_reunification(self, split_manager):
        """Test reunifying some but not all groups."""
        # Create 3 groups
        group1 = PartyGroup(
            group_id="group1",
            member_ids={"Gandalf"},
            location="Tavern"
        )
        group2 = PartyGroup(
            group_id="group2",
            member_ids={"Aragorn"},
            location="Forest"
        )
        group3 = PartyGroup(
            group_id="group3",
            member_ids={"Legolas", "Gimli"},
            location="Dungeon"
        )
        split_manager.groups["group1"] = group1
        split_manager.groups["group2"] = group2
        split_manager.groups["group3"] = group3

        # Reunify group1 and group2, leaving group3 separate
        split_manager.execute_reunification(
            groups_to_merge=["group1", "group2"],
            location="Road"
        )

        # Should have 2 groups now
        assert len(split_manager.groups) == 2

        # group3 should still exist
        assert any(
            "Legolas" in g.member_ids
            for g in split_manager.groups.values()
        )

    def test_time_progression_across_groups(self, split_manager):
        """Test realistic time progression across split groups."""
        # Create 2 groups
        split_manager.execute_split(
            departing_pcs={"Legolas", "Gimli"},
            destination="Dungeon"
        )

        group_ids = list(split_manager.groups.keys())
        group1_id = group_ids[0]
        group2_id = group_ids[1]

        # Group 1 has a short encounter (10 minutes)
        split_manager.advance_group_time(group1_id, timedelta(minutes=10))

        # Group 2 has a long encounter (45 minutes)
        split_manager.advance_group_time(group2_id, timedelta(minutes=45))

        # Check time differential
        diff = split_manager.get_time_differential(group1_id, group2_id)
        assert diff == timedelta(minutes=35)

        # Sync groups
        max_time = split_manager.sync_all_groups()
        assert max_time == timedelta(minutes=45)

        # Both groups should now be at 45 minutes
        assert split_manager.groups[group1_id].time_elapsed == timedelta(minutes=45)
        assert split_manager.groups[group2_id].time_elapsed == timedelta(minutes=45)
