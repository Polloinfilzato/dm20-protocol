"""
Tests for the discovery tracking module.

Tests DiscoveryLevel, FeatureDiscovery, LocationDiscovery, and DiscoveryTracker
for tracking what the party has discovered about locations and their features.
"""

import json
import pytest
from pathlib import Path

from dm20_protocol.consistency.discovery import (
    DiscoveryLevel,
    DiscoveryTracker,
    FeatureDiscovery,
    LocationDiscovery,
)


class TestDiscoveryLevel:
    """Tests for DiscoveryLevel enum."""

    def test_ordering(self):
        """Test that discovery levels are ordered correctly."""
        assert DiscoveryLevel.UNDISCOVERED < DiscoveryLevel.GLIMPSED
        assert DiscoveryLevel.GLIMPSED < DiscoveryLevel.EXPLORED
        assert DiscoveryLevel.EXPLORED < DiscoveryLevel.FULLY_MAPPED

    def test_int_values(self):
        """Test integer values of discovery levels."""
        assert DiscoveryLevel.UNDISCOVERED == 0
        assert DiscoveryLevel.GLIMPSED == 1
        assert DiscoveryLevel.EXPLORED == 2
        assert DiscoveryLevel.FULLY_MAPPED == 3

    def test_comparison_with_int(self):
        """Test that discovery levels can be compared with integers."""
        assert DiscoveryLevel.EXPLORED > 1
        assert DiscoveryLevel.GLIMPSED >= 1
        assert DiscoveryLevel.UNDISCOVERED == 0


class TestFeatureDiscovery:
    """Tests for FeatureDiscovery model."""

    def test_create_default(self):
        """Test creating a FeatureDiscovery with defaults."""
        fd = FeatureDiscovery(feature_name="Hidden Passage")
        assert fd.feature_name == "Hidden Passage"
        assert fd.discovery_level == DiscoveryLevel.UNDISCOVERED
        assert fd.discovered_by is None
        assert fd.discovered_session is None
        assert fd.discovery_method is None

    def test_create_full(self):
        """Test creating a FeatureDiscovery with all fields."""
        fd = FeatureDiscovery(
            feature_name="Ancient Altar",
            discovery_level=DiscoveryLevel.EXPLORED,
            discovered_by="Aldric",
            discovered_session=3,
            discovery_method="investigation",
        )
        assert fd.feature_name == "Ancient Altar"
        assert fd.discovery_level == DiscoveryLevel.EXPLORED
        assert fd.discovered_by == "Aldric"
        assert fd.discovered_session == 3
        assert fd.discovery_method == "investigation"

    def test_serialization_roundtrip(self):
        """Test model_dump and model_validate roundtrip."""
        fd = FeatureDiscovery(
            feature_name="Crystal Pool",
            discovery_level=DiscoveryLevel.GLIMPSED,
            discovered_by="Elara",
            discovered_session=2,
            discovery_method="perception check",
        )
        data = fd.model_dump(mode="json")
        fd2 = FeatureDiscovery.model_validate(data)
        assert fd2.feature_name == fd.feature_name
        assert fd2.discovery_level == fd.discovery_level
        assert fd2.discovered_by == fd.discovered_by


class TestLocationDiscovery:
    """Tests for LocationDiscovery model."""

    def test_create_default(self):
        """Test creating a LocationDiscovery with defaults."""
        ld = LocationDiscovery(location_id="dungeon_1")
        assert ld.location_id == "dungeon_1"
        assert ld.overall_level == DiscoveryLevel.UNDISCOVERED
        assert len(ld.feature_discoveries) == 0
        assert ld.first_visited is None
        assert ld.last_visited is None

    def test_create_with_features(self):
        """Test creating a LocationDiscovery with features."""
        features = [
            FeatureDiscovery(
                feature_name="Drawbridge",
                discovery_level=DiscoveryLevel.EXPLORED,
            ),
            FeatureDiscovery(
                feature_name="Secret Room",
                discovery_level=DiscoveryLevel.UNDISCOVERED,
            ),
        ]
        ld = LocationDiscovery(
            location_id="castle",
            overall_level=DiscoveryLevel.GLIMPSED,
            feature_discoveries=features,
        )
        assert len(ld.feature_discoveries) == 2
        assert ld.overall_level == DiscoveryLevel.GLIMPSED


class TestDiscoveryTracker:
    """Tests for DiscoveryTracker manager class."""

    def test_init_creates_directory(self, tmp_path):
        """Test that initialization creates the campaign directory."""
        campaign_dir = tmp_path / "test_campaign"
        tracker = DiscoveryTracker(campaign_dir)
        assert campaign_dir.exists()
        assert tracker.location_count == 0

    def test_discover_location_basic(self, tmp_path):
        """Test basic location discovery."""
        tracker = DiscoveryTracker(tmp_path)
        result = tracker.discover_location("tavern", DiscoveryLevel.GLIMPSED)
        assert result.location_id == "tavern"
        assert result.overall_level == DiscoveryLevel.GLIMPSED
        assert result.first_visited is not None
        assert result.last_visited is not None

    def test_discover_location_upgrade(self, tmp_path):
        """Test that location discovery can be upgraded."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("tavern", DiscoveryLevel.GLIMPSED)
        result = tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        assert result.overall_level == DiscoveryLevel.EXPLORED

    def test_discover_location_no_downgrade(self, tmp_path):
        """Test that location discovery cannot be downgraded."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        result = tracker.discover_location("tavern", DiscoveryLevel.GLIMPSED)
        # Should remain at EXPLORED
        assert result.overall_level == DiscoveryLevel.EXPLORED

    def test_discover_location_same_level(self, tmp_path):
        """Test discovering at the same level (no change)."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        result = tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        assert result.overall_level == DiscoveryLevel.EXPLORED

    def test_discover_location_updates_timestamps(self, tmp_path):
        """Test that discover_location updates visit timestamps."""
        tracker = DiscoveryTracker(tmp_path)
        result1 = tracker.discover_location("tavern", DiscoveryLevel.GLIMPSED)
        first_visit = result1.first_visited

        result2 = tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        # first_visited should not change on subsequent visits
        assert result2.first_visited == first_visit
        # last_visited should be updated
        assert result2.last_visited is not None

    def test_discover_feature_basic(self, tmp_path):
        """Test basic feature discovery."""
        tracker = DiscoveryTracker(tmp_path)
        fd = tracker.discover_feature(
            "dungeon_1",
            "Hidden Treasure Room",
            DiscoveryLevel.GLIMPSED,
            method="perception check",
            discovered_by="Aldric",
            session=3,
        )
        assert fd.feature_name == "Hidden Treasure Room"
        assert fd.discovery_level == DiscoveryLevel.GLIMPSED
        assert fd.discovery_method == "perception check"
        assert fd.discovered_by == "Aldric"
        assert fd.discovered_session == 3

    def test_discover_feature_upgrade(self, tmp_path):
        """Test that feature discovery can be upgraded."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_feature(
            "dungeon_1",
            "Hidden Passage",
            DiscoveryLevel.GLIMPSED,
            method="perception check",
        )
        fd = tracker.discover_feature(
            "dungeon_1",
            "Hidden Passage",
            DiscoveryLevel.FULLY_MAPPED,
            method="thorough investigation",
            discovered_by="Elara",
        )
        assert fd.discovery_level == DiscoveryLevel.FULLY_MAPPED
        assert fd.discovery_method == "thorough investigation"
        assert fd.discovered_by == "Elara"

    def test_discover_feature_no_downgrade(self, tmp_path):
        """Test that feature discovery cannot be downgraded."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_feature(
            "dungeon_1",
            "Trap Door",
            DiscoveryLevel.EXPLORED,
        )
        fd = tracker.discover_feature(
            "dungeon_1",
            "Trap Door",
            DiscoveryLevel.GLIMPSED,
        )
        assert fd.discovery_level == DiscoveryLevel.EXPLORED

    def test_discover_feature_preserves_metadata_on_no_upgrade(self, tmp_path):
        """Test that metadata is preserved when upgrade is refused."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_feature(
            "dungeon_1",
            "Altar",
            DiscoveryLevel.EXPLORED,
            method="investigation",
            discovered_by="Aldric",
            session=2,
        )
        fd = tracker.discover_feature(
            "dungeon_1",
            "Altar",
            DiscoveryLevel.GLIMPSED,
            method="different method",
            discovered_by="Elara",
            session=5,
        )
        # Original metadata should be preserved
        assert fd.discovered_by == "Aldric"
        assert fd.discovered_session == 2
        assert fd.discovery_method == "investigation"

    def test_discover_multiple_features(self, tmp_path):
        """Test discovering multiple features in the same location."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_feature(
            "castle", "Drawbridge", DiscoveryLevel.EXPLORED,
        )
        tracker.discover_feature(
            "castle", "Secret Room", DiscoveryLevel.GLIMPSED,
        )
        tracker.discover_feature(
            "castle", "Tower", DiscoveryLevel.FULLY_MAPPED,
        )
        loc = tracker.get_discovery_state("castle")
        assert len(loc.feature_discoveries) == 3

    def test_get_discovery_state_tracked(self, tmp_path):
        """Test getting discovery state for a tracked location."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        state = tracker.get_discovery_state("tavern")
        assert state.location_id == "tavern"
        assert state.overall_level == DiscoveryLevel.EXPLORED

    def test_get_discovery_state_untracked_backward_compat(self, tmp_path):
        """Test that untracked locations default to EXPLORED for backward compatibility."""
        tracker = DiscoveryTracker(tmp_path)
        state = tracker.get_discovery_state("unknown_location")
        assert state.location_id == "unknown_location"
        assert state.overall_level == DiscoveryLevel.EXPLORED
        # Should NOT persist this default
        assert tracker.location_count == 0

    def test_get_visible_features(self, tmp_path):
        """Test getting visible features (GLIMPSED or above)."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_feature(
            "dungeon_1", "Hidden Room", DiscoveryLevel.UNDISCOVERED,
        )
        tracker.discover_feature(
            "dungeon_1", "Main Hall", DiscoveryLevel.GLIMPSED,
        )
        tracker.discover_feature(
            "dungeon_1", "Armory", DiscoveryLevel.EXPLORED,
        )
        tracker.discover_feature(
            "dungeon_1", "Boss Chamber", DiscoveryLevel.FULLY_MAPPED,
        )

        visible = tracker.get_visible_features("dungeon_1")
        visible_names = [fd.feature_name for fd in visible]
        assert "Hidden Room" not in visible_names
        assert "Main Hall" in visible_names
        assert "Armory" in visible_names
        assert "Boss Chamber" in visible_names
        assert len(visible) == 3

    def test_get_visible_features_untracked_location(self, tmp_path):
        """Test getting visible features for an untracked location."""
        tracker = DiscoveryTracker(tmp_path)
        visible = tracker.get_visible_features("unknown")
        assert visible == []

    def test_is_fully_explored_true(self, tmp_path):
        """Test is_fully_explored returns True when all features are FULLY_MAPPED."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("dungeon_1", DiscoveryLevel.FULLY_MAPPED)
        tracker.discover_feature(
            "dungeon_1", "Room A", DiscoveryLevel.FULLY_MAPPED,
        )
        tracker.discover_feature(
            "dungeon_1", "Room B", DiscoveryLevel.FULLY_MAPPED,
        )
        assert tracker.is_fully_explored("dungeon_1") is True

    def test_is_fully_explored_false_overall_not_mapped(self, tmp_path):
        """Test is_fully_explored when overall level is not FULLY_MAPPED."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("dungeon_1", DiscoveryLevel.EXPLORED)
        tracker.discover_feature(
            "dungeon_1", "Room A", DiscoveryLevel.FULLY_MAPPED,
        )
        assert tracker.is_fully_explored("dungeon_1") is False

    def test_is_fully_explored_false_feature_not_mapped(self, tmp_path):
        """Test is_fully_explored when a feature is not FULLY_MAPPED."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("dungeon_1", DiscoveryLevel.FULLY_MAPPED)
        tracker.discover_feature(
            "dungeon_1", "Room A", DiscoveryLevel.FULLY_MAPPED,
        )
        tracker.discover_feature(
            "dungeon_1", "Room B", DiscoveryLevel.EXPLORED,
        )
        assert tracker.is_fully_explored("dungeon_1") is False

    def test_is_fully_explored_no_features(self, tmp_path):
        """Test is_fully_explored with no tracked features."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("dungeon_1", DiscoveryLevel.FULLY_MAPPED)
        assert tracker.is_fully_explored("dungeon_1") is True

    def test_is_fully_explored_untracked(self, tmp_path):
        """Test is_fully_explored for an untracked location returns False."""
        tracker = DiscoveryTracker(tmp_path)
        assert tracker.is_fully_explored("unknown") is False

    def test_location_count(self, tmp_path):
        """Test location count tracking."""
        tracker = DiscoveryTracker(tmp_path)
        assert tracker.location_count == 0

        tracker.discover_location("tavern", DiscoveryLevel.GLIMPSED)
        assert tracker.location_count == 1

        tracker.discover_location("dungeon", DiscoveryLevel.EXPLORED)
        assert tracker.location_count == 2

        # Discovering a feature in a new location also increments count
        tracker.discover_feature(
            "forest", "Ancient Tree", DiscoveryLevel.GLIMPSED,
        )
        assert tracker.location_count == 3

    def test_save_and_load_roundtrip(self, tmp_path):
        """Test persistence round-trip."""
        # Create and populate tracker
        tracker1 = DiscoveryTracker(tmp_path)
        tracker1.discover_location("tavern", DiscoveryLevel.EXPLORED)
        tracker1.discover_location("dungeon", DiscoveryLevel.GLIMPSED)
        tracker1.discover_feature(
            "dungeon",
            "Hidden Passage",
            DiscoveryLevel.EXPLORED,
            method="perception check",
            discovered_by="Aldric",
            session=2,
        )
        tracker1.discover_feature(
            "dungeon",
            "Trap Room",
            DiscoveryLevel.GLIMPSED,
            method="told by NPC",
        )
        tracker1.save()

        # Verify file exists
        state_file = tmp_path / "discovery_state.json"
        assert state_file.exists()

        # Load into new tracker
        tracker2 = DiscoveryTracker(tmp_path)
        assert tracker2.location_count == 2

        # Verify tavern
        tavern = tracker2.get_discovery_state("tavern")
        assert tavern.overall_level == DiscoveryLevel.EXPLORED

        # Verify dungeon
        dungeon = tracker2.get_discovery_state("dungeon")
        assert dungeon.overall_level == DiscoveryLevel.GLIMPSED
        assert len(dungeon.feature_discoveries) == 2

        # Verify feature details
        hidden_passage = None
        for fd in dungeon.feature_discoveries:
            if fd.feature_name == "Hidden Passage":
                hidden_passage = fd
                break
        assert hidden_passage is not None
        assert hidden_passage.discovery_level == DiscoveryLevel.EXPLORED
        assert hidden_passage.discovery_method == "perception check"
        assert hidden_passage.discovered_by == "Aldric"
        assert hidden_passage.discovered_session == 2

    def test_save_file_structure(self, tmp_path):
        """Test the structure of the saved JSON file."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_location("tavern", DiscoveryLevel.EXPLORED)
        tracker.save()

        state_file = tmp_path / "discovery_state.json"
        data = json.loads(state_file.read_text())
        assert "version" in data
        assert data["version"] == "1.0"
        assert "locations" in data
        assert "tavern" in data["locations"]
        assert data["locations"]["tavern"]["overall_level"] == DiscoveryLevel.EXPLORED

    def test_load_nonexistent_file(self, tmp_path):
        """Test that loading from a missing file starts fresh."""
        tracker = DiscoveryTracker(tmp_path)
        assert tracker.location_count == 0

    def test_load_corrupt_file(self, tmp_path):
        """Test that loading from a corrupt file starts fresh."""
        state_file = tmp_path / "discovery_state.json"
        state_file.write_text("this is not valid json!!!")

        tracker = DiscoveryTracker(tmp_path)
        assert tracker.location_count == 0

    def test_load_invalid_structure(self, tmp_path):
        """Test that loading from an invalid structure starts fresh."""
        state_file = tmp_path / "discovery_state.json"
        state_file.write_text(json.dumps({"not_locations": {}}))

        tracker = DiscoveryTracker(tmp_path)
        assert tracker.location_count == 0

    def test_backward_compatibility_default_level(self, tmp_path):
        """Test that the default level for untracked locations is EXPLORED."""
        tracker = DiscoveryTracker(tmp_path)
        assert tracker.DEFAULT_LEVEL == DiscoveryLevel.EXPLORED

        # Getting state for an untracked location returns EXPLORED
        state = tracker.get_discovery_state("old_location")
        assert state.overall_level == DiscoveryLevel.EXPLORED

    def test_backward_compatibility_untracked_not_persisted(self, tmp_path):
        """Test that backward-compatible defaults are not persisted."""
        tracker = DiscoveryTracker(tmp_path)

        # Getting state for untracked location should not add it
        _ = tracker.get_discovery_state("ephemeral_location")
        assert tracker.location_count == 0

        # Save and reload
        tracker.save()
        tracker2 = DiscoveryTracker(tmp_path)
        assert tracker2.location_count == 0

    def test_discover_feature_creates_location_entry(self, tmp_path):
        """Test that discovering a feature auto-creates the location entry."""
        tracker = DiscoveryTracker(tmp_path)
        tracker.discover_feature(
            "new_location",
            "Interesting Rock",
            DiscoveryLevel.GLIMPSED,
        )
        assert tracker.location_count == 1
        loc = tracker.get_discovery_state("new_location")
        # Overall level should still be UNDISCOVERED (only feature was discovered)
        assert loc.overall_level == DiscoveryLevel.UNDISCOVERED
        assert len(loc.feature_discoveries) == 1

    def test_full_discovery_workflow(self, tmp_path):
        """Test a complete discovery workflow."""
        tracker = DiscoveryTracker(tmp_path)

        # Party first glimpses the dungeon
        tracker.discover_location("lost_dungeon", DiscoveryLevel.GLIMPSED)

        # Rogue scouts and sees the entrance
        tracker.discover_feature(
            "lost_dungeon",
            "Crumbling Entrance",
            DiscoveryLevel.EXPLORED,
            method="perception check",
            discovered_by="Shadow",
            session=1,
        )

        # Party enters and explores
        tracker.discover_location("lost_dungeon", DiscoveryLevel.EXPLORED)

        # Wizard investigates a hidden chamber
        tracker.discover_feature(
            "lost_dungeon",
            "Hidden Arcane Library",
            DiscoveryLevel.GLIMPSED,
            method="detect magic",
            discovered_by="Mystara",
            session=2,
        )

        # Later, they fully map the library
        tracker.discover_feature(
            "lost_dungeon",
            "Hidden Arcane Library",
            DiscoveryLevel.FULLY_MAPPED,
            method="thorough investigation",
            discovered_by="Mystara",
            session=3,
        )

        # Check visible features
        visible = tracker.get_visible_features("lost_dungeon")
        assert len(visible) == 2

        # Not fully explored yet (overall not FULLY_MAPPED)
        assert tracker.is_fully_explored("lost_dungeon") is False

        # Complete full mapping
        tracker.discover_location("lost_dungeon", DiscoveryLevel.FULLY_MAPPED)
        tracker.discover_feature(
            "lost_dungeon",
            "Crumbling Entrance",
            DiscoveryLevel.FULLY_MAPPED,
        )

        # Now it should be fully explored
        assert tracker.is_fully_explored("lost_dungeon") is True

        # Save and reload
        tracker.save()
        tracker2 = DiscoveryTracker(tmp_path)
        assert tracker2.is_fully_explored("lost_dungeon") is True
        assert tracker2.location_count == 1
