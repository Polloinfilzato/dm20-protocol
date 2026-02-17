"""Tests for sheets/sync.py — SheetSyncManager coordinator."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dm20_protocol.models import (
    AbilityScore,
    Character,
    CharacterClass,
    Race,
)
from dm20_protocol.sheets.models import ChangeStatus
from dm20_protocol.sheets.sync import SheetSyncManager


@pytest.fixture
def sample_character() -> Character:
    return Character(
        id="syncTest1",
        name="Aldric Stormwind",
        player_name="Marco",
        character_class=CharacterClass(name="Ranger", level=5, hit_dice="1d10", subclass="Hunter"),
        race=Race(name="Wood Elf"),
        background="Outlander",
        alignment="Neutral Good",
        description="A tall elf.",
        bio="Raised in the forest.",
        abilities={
            "strength": AbilityScore(score=12),
            "dexterity": AbilityScore(score=18),
            "constitution": AbilityScore(score=14),
            "intelligence": AbilityScore(score=10),
            "wisdom": AbilityScore(score=16),
            "charisma": AbilityScore(score=8),
        },
        armor_class=16,
        hit_points_max=42,
        hit_points_current=35,
        inspiration=False,
        notes="Tracking gnolls.",
    )


@pytest.fixture
def mock_storage(sample_character: Character) -> MagicMock:
    storage = MagicMock()
    campaign = MagicMock()
    campaign.name = "Test Campaign"
    campaign.characters = {"Aldric Stormwind": sample_character}
    storage.get_current_campaign.return_value = campaign
    storage.find_character.return_value = sample_character
    return storage


@pytest.fixture
def sync(tmp_path: Path, mock_storage: MagicMock) -> SheetSyncManager:
    sm = SheetSyncManager()
    sm.wire_storage(mock_storage)
    sm.start(tmp_path / "sheets")
    return sm


class TestRendering:

    def test_render_character(self, sync: SheetSyncManager, sample_character: Character) -> None:
        path = sync.render_character(sample_character)
        assert path is not None
        assert path.exists()
        assert "Aldric Stormwind" in path.read_text()

    def test_render_all(self, sync: SheetSyncManager, mock_storage: MagicMock) -> None:
        campaign = mock_storage.get_current_campaign()
        paths = sync.render_all(campaign.characters)
        assert len(paths) == 1

    def test_render_increments_version(self, sync: SheetSyncManager, sample_character: Character) -> None:
        sync.render_character(sample_character)
        state = sync._sync_states[sample_character.id]
        v1 = state.dm20_version
        sync.render_character(sample_character)
        assert state.dm20_version == v1 + 1

    def test_delete_sheet(self, sync: SheetSyncManager, sample_character: Character) -> None:
        path = sync.render_character(sample_character)
        assert path.exists()
        sync.delete_sheet("Aldric Stormwind", "syncTest1")
        assert not path.exists()
        assert "syncTest1" not in sync._sync_states

    def test_handle_rename(self, sync: SheetSyncManager, sample_character: Character) -> None:
        old_path = sync.render_character(sample_character)
        assert old_path.exists()
        sample_character.name = "Aldric the Great"
        new_path = sync.handle_rename("Aldric Stormwind", "Aldric the Great", sample_character)
        assert not old_path.exists()
        assert new_path is not None
        assert new_path.exists()
        assert "Aldric the Great" in new_path.name


class TestProcessFileChange:

    def test_auto_apply_free_changes(
        self, sync: SheetSyncManager, sample_character: Character, mock_storage: MagicMock
    ) -> None:
        # Render the initial sheet
        path = sync.render_character(sample_character)

        # Modify the file with a player_free change
        content = path.read_text()
        content = content.replace("hit_points_current: 35", "hit_points_current: 20")
        path.write_text(content)

        # Process the change
        diff = sync.process_file_change(path)
        assert diff is not None
        assert diff.has_changes
        assert sample_character.hit_points_current == 20
        mock_storage.save.assert_called()

    def test_queue_approval_changes(
        self, sync: SheetSyncManager, sample_character: Character
    ) -> None:
        path = sync.render_character(sample_character)

        content = path.read_text()
        content = content.replace("strength: 12", "strength: 14")
        path.write_text(content)

        diff = sync.process_file_change(path)
        assert diff is not None
        assert len(diff.approval_changes) == 1

        # Should be queued
        pending = sync.get_pending_for_character("Aldric Stormwind")
        assert len(pending) == 1
        assert pending[0].status == ChangeStatus.PENDING

    def test_dm_only_changes_rejected(
        self, sync: SheetSyncManager, sample_character: Character, mock_storage: MagicMock
    ) -> None:
        path = sync.render_character(sample_character)

        content = path.read_text()
        content = content.replace("armor_class: 16", "armor_class: 20")
        path.write_text(content)

        diff = sync.process_file_change(path)
        assert diff is not None
        assert len(diff.rejected_changes) == 1
        # AC should NOT have changed
        assert sample_character.armor_class == 16

    def test_feedback_loop_prevention(
        self, sync: SheetSyncManager, sample_character: Character
    ) -> None:
        # Render creates a hash
        path = sync.render_character(sample_character)

        # Process the same unchanged file — should be ignored
        diff = sync.process_file_change(path)
        assert diff is None

    def test_invalid_file_returns_none(self, sync: SheetSyncManager, tmp_path: Path) -> None:
        bad_file = tmp_path / "sheets" / "bad.md"
        bad_file.write_text("Not a valid sheet")
        diff = sync.process_file_change(bad_file)
        assert diff is None


class TestDMApproval:

    def test_approve_changes(
        self, sync: SheetSyncManager, sample_character: Character, mock_storage: MagicMock
    ) -> None:
        path = sync.render_character(sample_character)
        content = path.read_text()
        content = content.replace("strength: 12", "strength: 14")
        path.write_text(content)
        sync.process_file_change(path)

        result = sync.approve_changes("Aldric Stormwind")
        assert "Approved" in result
        assert sample_character.abilities["strength"].score == 14
        mock_storage.save.assert_called()

    def test_reject_changes(
        self, sync: SheetSyncManager, sample_character: Character
    ) -> None:
        path = sync.render_character(sample_character)
        content = path.read_text()
        content = content.replace("strength: 12", "strength: 14")
        path.write_text(content)
        sync.process_file_change(path)

        result = sync.reject_changes("Aldric Stormwind")
        assert "Rejected" in result
        # STR should stay at 12
        assert sample_character.abilities["strength"].score == 12
        # Pending should be marked rejected
        state = sync._sync_states[sample_character.id]
        assert all(
            p.status == ChangeStatus.REJECTED
            for p in state.pending_changes
        )

    def test_no_pending_changes(self, sync: SheetSyncManager) -> None:
        result = sync.approve_changes("Nobody")
        assert "No pending" in result


class TestLifecycle:

    def test_start_stop(self, tmp_path: Path) -> None:
        sm = SheetSyncManager()
        assert not sm.is_active
        sm.start(tmp_path / "sheets")
        assert sm.is_active
        sm.stop()
        assert not sm.is_active

    def test_on_event_saved(
        self, sync: SheetSyncManager, sample_character: Character, mock_storage: MagicMock
    ) -> None:
        # Should render all characters
        sync.on_event("saved")
        path = sync._sheets_dir / "Aldric Stormwind.md"
        assert path.exists()

    def test_on_event_deleted(
        self, sync: SheetSyncManager, sample_character: Character
    ) -> None:
        sync.render_character(sample_character)
        sync.on_event("deleted", "Aldric Stormwind")
        path = sync._sheets_dir / "Aldric Stormwind.md"
        assert not path.exists()
