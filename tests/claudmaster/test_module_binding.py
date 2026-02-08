"""
Unit tests for module binding system.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from dm20_protocol.claudmaster.module_binding import (
    BindingResult,
    CampaignModuleManager,
    ModuleBinding,
    ModuleProgress,
    UnbindingResult,
)


class TestCampaignModuleManager:
    """Tests for CampaignModuleManager class."""

    def test_initialization(self, tmp_path: Path) -> None:
        """Test manager initialization."""
        campaign_path = tmp_path / "test_campaign"
        manager = CampaignModuleManager(campaign_path)

        assert manager.campaign_path == campaign_path
        assert manager.binding_file == campaign_path / "module_binding.json"
        assert manager.get_active_module() is None
        assert manager.list_bindings() == []

    def test_bind_module_basic(self, tmp_path: Path) -> None:
        """Test basic module binding."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        result = manager.bind_module(
            module_id="curse-of-strahd",
            source_id="lib-001",
            set_active=False,
        )

        assert isinstance(result, BindingResult)
        assert result.success is True
        assert result.module_id == "curse-of-strahd"
        assert "Successfully bound" in result.message

        # Verify binding exists
        binding = manager.get_binding("curse-of-strahd")
        assert binding is not None
        assert binding.module_id == "curse-of-strahd"
        assert binding.source_id == "lib-001"
        assert binding.is_active is False
        assert isinstance(binding.bound_at, datetime)

    def test_bind_module_set_active(self, tmp_path: Path) -> None:
        """Test binding a module and setting it as active."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        result = manager.bind_module(
            module_id="tomb-of-annihilation",
            source_id="lib-002",
            set_active=True,
        )

        assert result.success is True
        assert "set as active" in result.message

        # Verify active module is set
        assert manager.get_active_module() == "tomb-of-annihilation"

        binding = manager.get_binding("tomb-of-annihilation")
        assert binding.is_active is True

    def test_bind_module_already_bound_error(self, tmp_path: Path) -> None:
        """Test binding an already bound module returns error."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        # Bind first time
        manager.bind_module("waterdeep", "lib-003", set_active=False)

        # Try to bind again
        result = manager.bind_module("waterdeep", "lib-003", set_active=False)

        assert result.success is False
        assert result.module_id == "waterdeep"
        assert "already bound" in result.message

    def test_bind_multiple_modules_active_switches(self, tmp_path: Path) -> None:
        """Test binding multiple modules and switching active module."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        # Bind first module as active
        manager.bind_module("module-a", "lib-001", set_active=True)
        assert manager.get_active_module() == "module-a"

        # Bind second module as active - should deactivate first
        manager.bind_module("module-b", "lib-002", set_active=True)
        assert manager.get_active_module() == "module-b"

        binding_a = manager.get_binding("module-a")
        binding_b = manager.get_binding("module-b")
        assert binding_a.is_active is False
        assert binding_b.is_active is True

    def test_unbind_module_basic(self, tmp_path: Path) -> None:
        """Test basic module unbinding."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("module-x", "lib-001", set_active=False)

        result = manager.unbind_module("module-x", preserve_progress=False)

        assert isinstance(result, UnbindingResult)
        assert result.success is True
        assert result.module_id == "module-x"
        assert "Successfully unbound" in result.message
        assert result.progress_preserved is False

        # Verify binding removed
        assert manager.get_binding("module-x") is None

    def test_unbind_module_preserve_progress(self, tmp_path: Path) -> None:
        """Test unbinding with progress preservation."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("module-y", "lib-001", set_active=False)

        # Add some progress
        manager.update_progress("module-y", current_chapter="Chapter 1")

        result = manager.unbind_module("module-y", preserve_progress=True)

        assert result.success is True
        assert result.progress_preserved is True

        # Verify progress still exists
        progress = manager.get_progress("module-y")
        assert progress is not None
        assert progress.current_chapter == "Chapter 1"

    def test_unbind_module_delete_progress(self, tmp_path: Path) -> None:
        """Test unbinding with progress deletion."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("module-z", "lib-001", set_active=False)

        # Add some progress
        manager.update_progress("module-z", current_chapter="Chapter 1")

        result = manager.unbind_module("module-z", preserve_progress=False)

        assert result.success is True
        assert result.progress_preserved is False

        # Verify progress deleted
        progress = manager.get_progress("module-z")
        assert progress is None

    def test_unbind_active_module_clears_active(self, tmp_path: Path) -> None:
        """Test unbinding the active module clears active_module_id."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("active-module", "lib-001", set_active=True)

        assert manager.get_active_module() == "active-module"

        manager.unbind_module("active-module", preserve_progress=False)

        assert manager.get_active_module() is None

    def test_unbind_module_not_bound_error(self, tmp_path: Path) -> None:
        """Test unbinding a non-bound module returns error."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        result = manager.unbind_module("nonexistent", preserve_progress=False)

        assert result.success is False
        assert result.module_id == "nonexistent"
        assert "not bound" in result.message

    def test_set_active_module_success(self, tmp_path: Path) -> None:
        """Test setting active module."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        manager.bind_module("module-1", "lib-001", set_active=False)
        manager.bind_module("module-2", "lib-002", set_active=False)

        manager.set_active_module("module-2")

        assert manager.get_active_module() == "module-2"
        assert manager.get_binding("module-2").is_active is True
        assert manager.get_binding("module-1").is_active is False

    def test_set_active_module_not_bound_error(self, tmp_path: Path) -> None:
        """Test setting active module that is not bound raises error."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        with pytest.raises(ValueError, match="not bound to this campaign"):
            manager.set_active_module("nonexistent-module")

    def test_get_active_module_none_when_no_active(self, tmp_path: Path) -> None:
        """Test get_active_module returns None when no module is active."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("module-1", "lib-001", set_active=False)

        assert manager.get_active_module() is None

    def test_get_binding_returns_none_for_nonexistent(self, tmp_path: Path) -> None:
        """Test get_binding returns None for non-bound module."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        binding = manager.get_binding("nonexistent")
        assert binding is None

    def test_list_bindings(self, tmp_path: Path) -> None:
        """Test listing all bindings."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        manager.bind_module("module-1", "lib-001", set_active=False)
        manager.bind_module("module-2", "lib-002", set_active=True)
        manager.bind_module("module-3", "lib-003", set_active=False)

        bindings = manager.list_bindings()

        assert len(bindings) == 3
        assert all(isinstance(b, ModuleBinding) for b in bindings)

        module_ids = {b.module_id for b in bindings}
        assert module_ids == {"module-1", "module-2", "module-3"}

    def test_update_progress_current_chapter(self, tmp_path: Path) -> None:
        """Test updating current chapter in progress."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        progress = manager.update_progress(
            "test-module", current_chapter="Chapter 2"
        )

        assert progress.module_id == "test-module"
        assert progress.current_chapter == "Chapter 2"
        assert isinstance(progress.last_updated, datetime)

    def test_update_progress_current_location(self, tmp_path: Path) -> None:
        """Test updating current location in progress."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        progress = manager.update_progress(
            "test-module", current_location="Barovia Village"
        )

        assert progress.current_location == "Barovia Village"

    def test_update_progress_visited_location(self, tmp_path: Path) -> None:
        """Test adding visited locations."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        manager.update_progress("test-module", visited_location="Location A")
        manager.update_progress("test-module", visited_location="Location B")
        progress = manager.update_progress(
            "test-module", visited_location="Location A"
        )  # Duplicate

        assert len(progress.visited_locations) == 2
        assert "Location A" in progress.visited_locations
        assert "Location B" in progress.visited_locations

    def test_update_progress_completed_encounter(self, tmp_path: Path) -> None:
        """Test adding completed encounters."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        manager.update_progress("test-module", completed_encounter="Battle 1")
        progress = manager.update_progress(
            "test-module", completed_encounter="Battle 2"
        )

        assert len(progress.completed_encounters) == 2
        assert "Battle 1" in progress.completed_encounters
        assert "Battle 2" in progress.completed_encounters

    def test_update_progress_revealed_npc(self, tmp_path: Path) -> None:
        """Test adding revealed NPC info."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        manager.update_progress(
            "test-module", revealed_npc=("strahd", "is a vampire")
        )
        progress = manager.update_progress(
            "test-module", revealed_npc=("strahd", "rules Barovia")
        )

        assert "strahd" in progress.revealed_npcs
        assert len(progress.revealed_npcs["strahd"]) == 2
        assert "is a vampire" in progress.revealed_npcs["strahd"]
        assert "rules Barovia" in progress.revealed_npcs["strahd"]

    def test_update_progress_key_item_found(self, tmp_path: Path) -> None:
        """Test adding key items found."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        manager.update_progress("test-module", key_item_found="Holy Symbol")
        progress = manager.update_progress("test-module", key_item_found="Sunsword")

        assert len(progress.key_items_found) == 2
        assert "Holy Symbol" in progress.key_items_found
        assert "Sunsword" in progress.key_items_found

    def test_update_progress_plot_flag(self, tmp_path: Path) -> None:
        """Test setting plot flags."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        manager.update_progress("test-module", plot_flag=("ireena_rescued", True))
        progress = manager.update_progress(
            "test-module", plot_flag=("strahd_defeated", False)
        )

        assert progress.plot_flags["ireena_rescued"] is True
        assert progress.plot_flags["strahd_defeated"] is False

    def test_update_progress_combined_updates(self, tmp_path: Path) -> None:
        """Test updating multiple progress fields at once."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        progress = manager.update_progress(
            "test-module",
            current_chapter="Chapter 3",
            current_location="Castle Ravenloft",
            visited_location="Vallaki",
            completed_encounter="Vampire Spawn Fight",
            revealed_npc=("strahd", "has the Sunsword"),
            key_item_found="Tome of Strahd",
            plot_flag=("castle_entered", True),
        )

        assert progress.current_chapter == "Chapter 3"
        assert progress.current_location == "Castle Ravenloft"
        assert "Vallaki" in progress.visited_locations
        assert "Vampire Spawn Fight" in progress.completed_encounters
        assert "strahd" in progress.revealed_npcs
        assert "Tome of Strahd" in progress.key_items_found
        assert progress.plot_flags["castle_entered"] is True

    def test_update_progress_not_bound_error(self, tmp_path: Path) -> None:
        """Test updating progress for non-bound module raises error."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        with pytest.raises(ValueError, match="not bound to this campaign"):
            manager.update_progress("nonexistent", current_chapter="Chapter 1")

    def test_get_progress_specific_module(self, tmp_path: Path) -> None:
        """Test getting progress for a specific module."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("module-1", "lib-001", set_active=False)
        manager.update_progress("module-1", current_chapter="Chapter 5")

        progress = manager.get_progress("module-1")

        assert progress is not None
        assert progress.module_id == "module-1"
        assert progress.current_chapter == "Chapter 5"

    def test_get_progress_active_module_via_none(self, tmp_path: Path) -> None:
        """Test getting progress for active module by passing None."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("active-mod", "lib-001", set_active=True)
        manager.update_progress("active-mod", current_chapter="Chapter 1")

        progress = manager.get_progress(None)

        assert progress is not None
        assert progress.module_id == "active-mod"
        assert progress.current_chapter == "Chapter 1"

    def test_get_progress_none_when_no_active_module(self, tmp_path: Path) -> None:
        """Test get_progress returns None when no active module and None passed."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        progress = manager.get_progress(None)
        assert progress is None

    def test_get_progress_none_for_nonexistent_module(self, tmp_path: Path) -> None:
        """Test get_progress returns None for non-bound module."""
        manager = CampaignModuleManager(tmp_path / "campaign")

        progress = manager.get_progress("nonexistent")
        assert progress is None

    def test_save_and_load_round_trip(self, tmp_path: Path) -> None:
        """Test saving and loading bindings and progress."""
        campaign_path = tmp_path / "campaign"

        # Create manager and add data
        manager1 = CampaignModuleManager(campaign_path)
        manager1.bind_module("module-a", "lib-001", set_active=True)
        manager1.bind_module("module-b", "lib-002", set_active=False)
        manager1.update_progress("module-a", current_chapter="Chapter 1")
        manager1.update_progress("module-b", current_location="Waterdeep")

        # Create new manager and load
        manager2 = CampaignModuleManager(campaign_path)

        # Verify bindings loaded
        assert len(manager2.list_bindings()) == 2
        assert manager2.get_active_module() == "module-a"

        binding_a = manager2.get_binding("module-a")
        binding_b = manager2.get_binding("module-b")
        assert binding_a is not None
        assert binding_b is not None
        assert binding_a.is_active is True
        assert binding_b.is_active is False

        # Verify progress loaded
        progress_a = manager2.get_progress("module-a")
        progress_b = manager2.get_progress("module-b")
        assert progress_a.current_chapter == "Chapter 1"
        assert progress_b.current_location == "Waterdeep"

    def test_load_with_missing_file(self, tmp_path: Path) -> None:
        """Test loading when binding file does not exist."""
        campaign_path = tmp_path / "new_campaign"

        # Should not raise error
        manager = CampaignModuleManager(campaign_path)

        assert manager.get_active_module() is None
        assert manager.list_bindings() == []

    def test_save_creates_directory(self, tmp_path: Path) -> None:
        """Test that save creates campaign directory if it doesn't exist."""
        campaign_path = tmp_path / "nested" / "path" / "campaign"

        manager = CampaignModuleManager(campaign_path)
        manager.bind_module("test-module", "lib-001", set_active=False)

        # Verify directory and file created
        assert campaign_path.exists()
        assert (campaign_path / "module_binding.json").exists()

    def test_save_file_format(self, tmp_path: Path) -> None:
        """Test the JSON file format structure."""
        campaign_path = tmp_path / "campaign"

        manager = CampaignModuleManager(campaign_path)
        manager.bind_module("test-module", "lib-001", set_active=True)
        manager.update_progress("test-module", current_chapter="Chapter 1")

        # Read and verify JSON structure
        with open(campaign_path / "module_binding.json", "r") as f:
            data = json.load(f)

        assert "version" in data
        assert data["version"] == "1.0"
        assert "active_module_id" in data
        assert data["active_module_id"] == "test-module"
        assert "bindings" in data
        assert isinstance(data["bindings"], list)
        assert "progress" in data
        assert isinstance(data["progress"], dict)
        assert "metadata" in data
        assert "last_updated" in data["metadata"]

    def test_backward_compatibility_empty_data(self, tmp_path: Path) -> None:
        """Test loading handles empty or minimal binding data."""
        campaign_path = tmp_path / "campaign"
        campaign_path.mkdir(parents=True)

        # Write minimal binding file
        with open(campaign_path / "module_binding.json", "w") as f:
            json.dump({"version": "1.0"}, f)

        # Should load without error
        manager = CampaignModuleManager(campaign_path)

        assert manager.get_active_module() is None
        assert manager.list_bindings() == []

    def test_load_handles_corrupt_file(self, tmp_path: Path) -> None:
        """Test loading handles corrupt JSON file gracefully."""
        campaign_path = tmp_path / "campaign"
        campaign_path.mkdir(parents=True)

        # Write invalid JSON
        with open(campaign_path / "module_binding.json", "w") as f:
            f.write("{ invalid json")

        # Should not crash, just start fresh
        manager = CampaignModuleManager(campaign_path)

        assert manager.get_active_module() is None
        assert manager.list_bindings() == []

    def test_progress_timestamps_update(self, tmp_path: Path) -> None:
        """Test that progress timestamps update correctly."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        # First update
        progress1 = manager.update_progress("test-module", current_chapter="Chapter 1")
        timestamp1 = progress1.last_updated

        # Wait a moment and update again
        import time
        time.sleep(0.01)

        progress2 = manager.update_progress("test-module", current_chapter="Chapter 2")
        timestamp2 = progress2.last_updated

        # Timestamps should be different
        assert timestamp2 > timestamp1

    def test_module_progress_defaults(self, tmp_path: Path) -> None:
        """Test ModuleProgress has correct default values."""
        manager = CampaignModuleManager(tmp_path / "campaign")
        manager.bind_module("test-module", "lib-001", set_active=False)

        progress = manager.get_progress("test-module")

        assert progress.module_id == "test-module"
        assert progress.current_chapter is None
        assert progress.current_location is None
        assert progress.visited_locations == []
        assert progress.completed_encounters == []
        assert progress.revealed_npcs == {}
        assert progress.key_items_found == []
        assert progress.plot_flags == {}
        assert isinstance(progress.last_updated, datetime)
