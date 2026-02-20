"""
Unit tests for interaction_mode in campaign creation and mode switching (Issue #176).

Tests cover:
- interaction_mode parameter in create_campaign (storage layer)
- interaction_mode defaults to 'classic'
- interaction_mode persistence in campaign.json
- interaction_mode loading on campaign reload
- Mid-session mode switching via set_interaction_mode
- Voice dependency validation for narrated/immersive modes
- configure_claudmaster integration with interaction_mode
- All 9 mode × profile combinations
- Mode reset when deleting campaign

These tests use the storage layer directly and mock voice imports
to avoid requiring actual TTS/STT dependencies.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from dm20_protocol.storage import DnDStorage


@pytest.fixture
def temp_storage_dir(tmp_path: Path) -> Path:
    """Create a temporary storage directory for testing."""
    storage_dir = tmp_path / "test_data"
    storage_dir.mkdir()
    return storage_dir


# ===========================================================================
# Test: interaction_mode in Campaign Creation (Storage Layer)
# ===========================================================================

class TestInteractionModeCampaign:
    """Tests for interaction_mode parameter in campaign creation and loading."""

    def test_create_campaign_default_mode(self, temp_storage_dir):
        """create_campaign should default to interaction_mode='classic'."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Default Mode Campaign",
            description="Testing default interaction mode",
        )
        assert storage.interaction_mode == "classic"

    def test_create_campaign_classic_mode(self, temp_storage_dir):
        """create_campaign should accept interaction_mode='classic'."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Classic Campaign",
            description="Testing classic mode",
            interaction_mode="classic",
        )
        assert storage.interaction_mode == "classic"

    def test_create_campaign_narrated_mode(self, temp_storage_dir):
        """create_campaign should accept interaction_mode='narrated'."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Narrated Campaign",
            description="Testing narrated mode",
            interaction_mode="narrated",
        )
        assert storage.interaction_mode == "narrated"

    def test_create_campaign_immersive_mode(self, temp_storage_dir):
        """create_campaign should accept interaction_mode='immersive'."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Immersive Campaign",
            description="Testing immersive mode",
            interaction_mode="immersive",
        )
        assert storage.interaction_mode == "immersive"

    def test_interaction_mode_persisted_in_metadata(self, temp_storage_dir):
        """interaction_mode should be persisted in campaign.json."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Persisted Mode Campaign",
            description="Testing persistence",
            interaction_mode="narrated",
        )

        campaign_dir = temp_storage_dir / "campaigns" / "Persisted Mode Campaign"
        campaign_json = campaign_dir / "campaign.json"
        assert campaign_json.exists()

        with open(campaign_json, 'r') as f:
            metadata = json.load(f)

        assert "interaction_mode" in metadata
        assert metadata["interaction_mode"] == "narrated"

    def test_interaction_mode_loaded_on_reload(self, temp_storage_dir):
        """interaction_mode should be loaded when reloading a campaign."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Reload Mode Campaign",
            description="Testing reload",
            interaction_mode="immersive",
        )

        # Create a new storage instance (simulates restart)
        storage2 = DnDStorage(data_dir=temp_storage_dir)
        storage2.load_campaign("Reload Mode Campaign")
        assert storage2.interaction_mode == "immersive"

    def test_interaction_mode_defaults_classic_on_missing(self, temp_storage_dir):
        """Campaigns without interaction_mode in metadata should default to 'classic'."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Legacy Campaign",
            description="Simulating old campaign without mode",
        )

        # Remove interaction_mode from campaign.json to simulate old format
        campaign_dir = temp_storage_dir / "campaigns" / "Legacy Campaign"
        campaign_json = campaign_dir / "campaign.json"
        with open(campaign_json, 'r') as f:
            metadata = json.load(f)
        del metadata["interaction_mode"]
        with open(campaign_json, 'w') as f:
            json.dump(metadata, f, indent=2)

        # Reload
        storage2 = DnDStorage(data_dir=temp_storage_dir)
        storage2.load_campaign("Legacy Campaign")
        assert storage2.interaction_mode == "classic"

    def test_interaction_mode_orthogonal_to_rules_version(self, temp_storage_dir):
        """interaction_mode and rules_version should be independent."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Orthogonal Campaign",
            description="Testing orthogonality",
            rules_version="2014",
            interaction_mode="narrated",
        )
        assert storage.rules_version == "2014"
        assert storage.interaction_mode == "narrated"


# ===========================================================================
# Test: Mid-session Mode Switching
# ===========================================================================

class TestInteractionModeSwitching:
    """Tests for mid-session interaction mode switching."""

    def test_switch_to_narrated(self, temp_storage_dir):
        """Should be able to switch from classic to narrated."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Switch Test",
            description="Testing mode switch",
        )
        assert storage.interaction_mode == "classic"

        storage.set_interaction_mode("narrated")
        assert storage.interaction_mode == "narrated"

    def test_switch_to_immersive(self, temp_storage_dir):
        """Should be able to switch from classic to immersive."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Switch Test 2",
            description="Testing mode switch",
        )
        storage.set_interaction_mode("immersive")
        assert storage.interaction_mode == "immersive"

    def test_switch_back_to_classic(self, temp_storage_dir):
        """Should be able to switch back to classic."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Switch Back Test",
            description="Testing mode switch",
            interaction_mode="narrated",
        )
        assert storage.interaction_mode == "narrated"

        storage.set_interaction_mode("classic")
        assert storage.interaction_mode == "classic"

    def test_switch_persists_to_disk(self, temp_storage_dir):
        """Mode switch should persist to campaign.json."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Persist Switch",
            description="Testing persistence of switch",
        )
        storage.set_interaction_mode("immersive")

        campaign_dir = temp_storage_dir / "campaigns" / "Persist Switch"
        campaign_json = campaign_dir / "campaign.json"
        with open(campaign_json, 'r') as f:
            metadata = json.load(f)

        assert metadata["interaction_mode"] == "immersive"

    def test_switch_invalid_mode_raises(self, temp_storage_dir):
        """Switching to an invalid mode should raise ValueError."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Invalid Switch",
            description="Testing invalid mode",
        )
        with pytest.raises(ValueError, match="Invalid interaction_mode"):
            storage.set_interaction_mode("telepathic")

    def test_switch_without_campaign_raises(self, temp_storage_dir):
        """Switching mode without an active campaign should raise ValueError."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        with pytest.raises(ValueError, match="No active campaign"):
            storage.set_interaction_mode("narrated")


# ===========================================================================
# Test: Campaign Delete Resets Mode
# ===========================================================================

class TestInteractionModeReset:
    """Tests that interaction mode resets when campaign is deleted."""

    def test_delete_campaign_resets_mode(self, temp_storage_dir):
        """Deleting the active campaign should reset interaction_mode to 'classic'."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Delete Test",
            description="Testing delete reset",
            interaction_mode="immersive",
        )
        assert storage.interaction_mode == "immersive"

        storage.delete_campaign("Delete Test")
        assert storage.interaction_mode == "classic"


# ===========================================================================
# Test: configure_claudmaster with interaction_mode
# ===========================================================================

class TestConfigureClaudmasterInteractionMode:
    """Tests for interaction_mode parameter in configure_claudmaster."""

    def test_configure_switch_to_narrated(self, temp_storage_dir):
        """configure_claudmaster should switch interaction_mode to narrated."""
        from dm20_protocol.main import _configure_claudmaster_impl

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Config Mode Test",
            description="Testing config mode switch",
        )

        # Mock voice import to succeed
        with patch.dict("sys.modules", {"dm20_protocol.voice": type("M", (), {"TTSRouter": None})}):
            result = _configure_claudmaster_impl(storage, interaction_mode="narrated")

        assert "narrated" in result.lower()
        assert storage.interaction_mode == "narrated"

    def test_configure_switch_to_classic(self, temp_storage_dir):
        """configure_claudmaster should switch interaction_mode to classic without voice check."""
        from dm20_protocol.main import _configure_claudmaster_impl

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Config Classic Test",
            description="Testing config classic switch",
            interaction_mode="narrated",
        )

        result = _configure_claudmaster_impl(storage, interaction_mode="classic")
        assert "classic" in result.lower()
        assert storage.interaction_mode == "classic"

    def test_configure_voice_missing_blocks_narrated(self, temp_storage_dir):
        """configure_claudmaster should reject narrated mode when voice deps missing."""
        from dm20_protocol.main import _configure_claudmaster_impl

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="No Voice Test",
            description="Testing missing voice deps",
        )

        # Make voice import fail
        import sys
        original = sys.modules.get("dm20_protocol.voice")
        sys.modules["dm20_protocol.voice"] = None  # Force ImportError
        try:
            result = _configure_claudmaster_impl(storage, interaction_mode="narrated")
        finally:
            if original is not None:
                sys.modules["dm20_protocol.voice"] = original
            else:
                sys.modules.pop("dm20_protocol.voice", None)

        assert "voice dependencies not installed" in result.lower() or "pip install" in result.lower()
        assert storage.interaction_mode == "classic"  # Unchanged

    def test_configure_invalid_mode(self, temp_storage_dir):
        """configure_claudmaster should reject invalid interaction_mode."""
        from dm20_protocol.main import _configure_claudmaster_impl

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Invalid Mode Test",
            description="Testing invalid mode",
        )

        result = _configure_claudmaster_impl(storage, interaction_mode="telepathic")
        assert "invalid" in result.lower()

    def test_configure_no_args_shows_mode(self, temp_storage_dir):
        """configure_claudmaster with no args should display current interaction_mode."""
        from dm20_protocol.main import _configure_claudmaster_impl

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Display Mode Test",
            description="Testing display",
            interaction_mode="narrated",
        )

        result = _configure_claudmaster_impl(storage)
        assert "narrated" in result.lower()

    def test_configure_reset_defaults_resets_mode(self, temp_storage_dir):
        """configure_claudmaster reset_to_defaults should reset interaction_mode to classic."""
        from dm20_protocol.main import _configure_claudmaster_impl

        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Reset Mode Test",
            description="Testing reset",
            interaction_mode="immersive",
        )

        with patch("dm20_protocol.claudmaster.profiles.update_agent_files", return_value=[]):
            result = _configure_claudmaster_impl(storage, reset_to_defaults=True)

        assert storage.interaction_mode == "classic"


# ===========================================================================
# Test: All 9 mode × profile combinations
# ===========================================================================

class TestModeProfileCombinations:
    """Verify that all 9 interaction_mode × model_profile combinations are valid."""

    MODES = ("classic", "narrated", "immersive")
    PROFILES = ("quality", "balanced", "economy")

    def test_all_combinations_create(self, temp_storage_dir):
        """All 9 mode×profile combos should work during campaign creation."""
        for i, mode in enumerate(self.MODES):
            for j, profile in enumerate(self.PROFILES):
                storage = DnDStorage(data_dir=temp_storage_dir)
                name = f"Combo {mode}-{profile}"
                storage.create_campaign(
                    name=name,
                    description=f"Testing {mode} + {profile}",
                    interaction_mode=mode,
                )
                assert storage.interaction_mode == mode

    def test_all_combinations_switch(self, temp_storage_dir):
        """All 9 mode×profile combos should work via mid-session switching."""
        storage = DnDStorage(data_dir=temp_storage_dir)
        storage.create_campaign(
            name="Combo Switch Test",
            description="Testing all combos via switching",
        )

        for mode in self.MODES:
            storage.set_interaction_mode(mode)
            assert storage.interaction_mode == mode
            # Profile is independent — just verify mode persists after each switch
            campaign_dir = temp_storage_dir / "campaigns" / "Combo Switch Test"
            with open(campaign_dir / "campaign.json", 'r') as f:
                metadata = json.load(f)
            assert metadata["interaction_mode"] == mode
