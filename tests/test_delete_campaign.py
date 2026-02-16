"""
Unit tests for DnDStorage.delete_campaign().

Tests cover:
- Delete monolithic campaign (single JSON file)
- Delete split campaign (directory-based)
- Delete nonexistent campaign (error)
- Delete active campaign (clears all state)
- Delete inactive campaign (preserves active)
- list_campaigns after delete
"""

import json
import pytest
from datetime import datetime
from pathlib import Path

from dm20_protocol.storage import DnDStorage, StorageFormat, new_uuid
from dm20_protocol.models import Campaign, GameState


# ── Helpers ───────────────────────────────────────────────────────────

def _make_campaign_data(name: str) -> dict:
    """Create minimal campaign JSON data."""
    return {
        "id": new_uuid(),
        "name": name,
        "description": f"Test campaign: {name}",
        "dm_name": "Test DM",
        "setting": None,
        "world_notes": "",
        "created_at": datetime.now().isoformat(),
        "updated_at": None,
        "characters": {},
        "npcs": {},
        "locations": {},
        "quests": {},
        "encounters": {},
        "sessions": [],
        "game_state": {
            "campaign_name": name,
            "current_session": 1,
            "current_location": None,
            "current_date_in_game": None,
            "party_level": 1,
            "party_funds": "0 gp",
            "in_combat": False,
            "initiative_order": [],
            "current_turn": None,
            "notes": "",
            "active_quests": [],
            "updated_at": datetime.now().isoformat(),
        },
    }


def _create_monolithic_campaign(campaigns_dir: Path, name: str) -> Path:
    """Write a monolithic campaign JSON file and return its path."""
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    file_path = campaigns_dir / f"{name}.json"
    file_path.write_text(json.dumps(_make_campaign_data(name)), encoding="utf-8")
    return file_path


def _create_split_campaign(campaigns_dir: Path, name: str) -> Path:
    """Create a split campaign directory with campaign.json and return dir path."""
    campaigns_dir.mkdir(parents=True, exist_ok=True)
    dir_path = campaigns_dir / name
    dir_path.mkdir()
    campaign_file = dir_path / "campaign.json"
    campaign_file.write_text(json.dumps(_make_campaign_data(name)), encoding="utf-8")
    # Add a secondary file to verify full directory deletion
    (dir_path / "characters.json").write_text("[]", encoding="utf-8")
    return dir_path


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Path:
    """Create a temporary storage directory for tests."""
    storage_dir = tmp_path / "test_storage"
    storage_dir.mkdir()
    return storage_dir


# ── Tests ─────────────────────────────────────────────────────────────

class TestDeleteCampaign:
    """Tests for DnDStorage.delete_campaign()."""

    def test_delete_monolithic_campaign(self, temp_storage_dir: Path) -> None:
        """Deleting a monolithic campaign removes the JSON file."""
        campaigns_dir = temp_storage_dir / "campaigns"
        file_path = _create_monolithic_campaign(campaigns_dir, "Mono Quest")

        storage = DnDStorage(data_dir=temp_storage_dir)
        assert file_path.exists()

        result = storage.delete_campaign("Mono Quest")

        assert result == "Mono Quest"
        assert not file_path.exists()

    def test_delete_split_campaign(self, temp_storage_dir: Path) -> None:
        """Deleting a split campaign removes the entire directory."""
        campaigns_dir = temp_storage_dir / "campaigns"
        dir_path = _create_split_campaign(campaigns_dir, "Split Quest")

        storage = DnDStorage(data_dir=temp_storage_dir)
        assert dir_path.exists()
        assert (dir_path / "campaign.json").exists()
        assert (dir_path / "characters.json").exists()

        result = storage.delete_campaign("Split Quest")

        assert result == "Split Quest"
        assert not dir_path.exists()

    def test_delete_nonexistent_campaign_raises(self, temp_storage_dir: Path) -> None:
        """Deleting a nonexistent campaign raises FileNotFoundError."""
        storage = DnDStorage(data_dir=temp_storage_dir)

        with pytest.raises(FileNotFoundError, match="not found"):
            storage.delete_campaign("Ghost Campaign")

    def test_delete_active_campaign_clears_state(self, temp_storage_dir: Path) -> None:
        """Deleting the currently active campaign clears all internal state."""
        campaigns_dir = temp_storage_dir / "campaigns"
        _create_monolithic_campaign(campaigns_dir, "Active Quest")

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.load_campaign("Active Quest")
        assert storage._current_campaign is not None
        assert storage._current_campaign.name == "Active Quest"

        storage.delete_campaign("Active Quest")

        assert storage._current_campaign is None
        assert storage._current_format == StorageFormat.NOT_FOUND
        assert len(storage._character_id_index) == 0
        assert len(storage._player_name_index) == 0
        assert storage._campaign_hash == ""
        assert storage._rulebook_manager is None
        assert storage._library_bindings is None

    def test_delete_inactive_campaign_preserves_active(self, temp_storage_dir: Path) -> None:
        """Deleting a different campaign preserves the active campaign state."""
        campaigns_dir = temp_storage_dir / "campaigns"
        _create_monolithic_campaign(campaigns_dir, "Active Quest")
        _create_monolithic_campaign(campaigns_dir, "Other Quest")

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.load_campaign("Active Quest")
        assert storage._current_campaign.name == "Active Quest"

        storage.delete_campaign("Other Quest")

        # Active campaign is untouched
        assert storage._current_campaign is not None
        assert storage._current_campaign.name == "Active Quest"
        assert storage._current_format != StorageFormat.NOT_FOUND

    def test_list_campaigns_after_delete(self, temp_storage_dir: Path) -> None:
        """list_campaigns() no longer returns the deleted campaign."""
        campaigns_dir = temp_storage_dir / "campaigns"
        _create_monolithic_campaign(campaigns_dir, "Alpha")
        _create_split_campaign(campaigns_dir, "Beta")

        storage = DnDStorage(data_dir=temp_storage_dir)
        assert "Alpha" in storage.list_campaigns()
        assert "Beta" in storage.list_campaigns()

        storage.delete_campaign("Alpha")
        remaining = storage.list_campaigns()

        assert "Alpha" not in remaining
        assert "Beta" in remaining

    def test_delete_last_campaign(self, temp_storage_dir: Path) -> None:
        """Deleting the only campaign results in an empty list."""
        campaigns_dir = temp_storage_dir / "campaigns"
        _create_monolithic_campaign(campaigns_dir, "Solo Quest")

        storage = DnDStorage(data_dir=temp_storage_dir)
        assert len(storage.list_campaigns()) == 1

        storage.delete_campaign("Solo Quest")

        assert storage.list_campaigns() == []
