"""
Unit tests for the Library Bindings System.

Tests the SourceBinding and LibraryBindings classes for managing
per-campaign library content enablement.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gamemaster_mcp.library.bindings import SourceBinding, LibraryBindings
from gamemaster_mcp.library.models import ContentType


class TestSourceBinding:
    """Tests for the SourceBinding dataclass."""

    def test_basic_creation(self):
        """Test basic SourceBinding creation with defaults."""
        binding = SourceBinding(source_id="tome-of-heroes")

        assert binding.source_id == "tome-of-heroes"
        assert binding.enabled is True
        assert binding.content_filter == {}

    def test_creation_with_all_fields(self):
        """Test SourceBinding creation with all fields specified."""
        binding = SourceBinding(
            source_id="tome-of-heroes",
            enabled=False,
            content_filter={
                ContentType.CLASS: ["dragon-knight"],
                ContentType.RACE: "*",
            },
        )

        assert binding.source_id == "tome-of-heroes"
        assert binding.enabled is False
        assert binding.content_filter[ContentType.CLASS] == ["dragon-knight"]
        assert binding.content_filter[ContentType.RACE] == "*"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        binding = SourceBinding(
            source_id="test-source",
            enabled=True,
            content_filter={
                ContentType.CLASS: ["fighter", "wizard"],
                ContentType.SPELL: "*",
            },
        )

        data = binding.to_dict()

        assert data["source_id"] == "test-source"
        assert data["enabled"] is True
        assert data["content_filter"]["class"] == ["fighter", "wizard"]
        assert data["content_filter"]["spell"] == "*"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "source_id": "test-source",
            "enabled": True,
            "content_filter": {
                "class": ["fighter"],
                "race": "*",
            },
        }

        binding = SourceBinding.from_dict(data)

        assert binding.source_id == "test-source"
        assert binding.enabled is True
        assert binding.content_filter[ContentType.CLASS] == ["fighter"]
        assert binding.content_filter[ContentType.RACE] == "*"

    def test_from_dict_with_missing_fields(self):
        """Test from_dict handles missing optional fields."""
        data = {"source_id": "minimal"}

        binding = SourceBinding.from_dict(data)

        assert binding.source_id == "minimal"
        assert binding.enabled is True  # Default
        assert binding.content_filter == {}

    def test_from_dict_ignores_unknown_content_types(self):
        """Test from_dict ignores unknown content types for forward compatibility."""
        data = {
            "source_id": "test",
            "content_filter": {
                "class": ["fighter"],
                "unknown_future_type": ["something"],
            },
        }

        binding = SourceBinding.from_dict(data)

        assert ContentType.CLASS in binding.content_filter
        assert len(binding.content_filter) == 1  # Unknown type was skipped

    def test_roundtrip(self):
        """Test that to_dict and from_dict are inverse operations."""
        original = SourceBinding(
            source_id="roundtrip-test",
            enabled=True,
            content_filter={
                ContentType.CLASS: ["paladin"],
                ContentType.SPELL: "*",
                ContentType.MONSTER: ["goblin", "dragon"],
            },
        )

        data = original.to_dict()
        restored = SourceBinding.from_dict(data)

        assert restored.source_id == original.source_id
        assert restored.enabled == original.enabled
        assert restored.content_filter[ContentType.CLASS] == original.content_filter[ContentType.CLASS]
        assert restored.content_filter[ContentType.SPELL] == original.content_filter[ContentType.SPELL]
        assert restored.content_filter[ContentType.MONSTER] == original.content_filter[ContentType.MONSTER]


class TestLibraryBindings:
    """Tests for the LibraryBindings dataclass."""

    def test_basic_creation(self):
        """Test basic LibraryBindings creation."""
        bindings = LibraryBindings(campaign_id="test-campaign")

        assert bindings.campaign_id == "test-campaign"
        assert bindings.sources == {}
        assert bindings.updated_at is not None

    def test_enable_source_new(self):
        """Test enabling a new source."""
        bindings = LibraryBindings(campaign_id="test")

        bindings.enable_source("tome-of-heroes")

        assert "tome-of-heroes" in bindings.sources
        assert bindings.sources["tome-of-heroes"].enabled is True

    def test_enable_source_re_enable(self):
        """Test re-enabling a disabled source."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.sources["test-source"] = SourceBinding(source_id="test-source", enabled=False)

        bindings.enable_source("test-source")

        assert bindings.sources["test-source"].enabled is True

    def test_enable_source_with_content_type_all(self):
        """Test enabling source with content type but no specific names (all)."""
        bindings = LibraryBindings(campaign_id="test")

        bindings.enable_source("test", content_type=ContentType.CLASS)

        assert bindings.sources["test"].content_filter[ContentType.CLASS] == "*"

    def test_enable_source_with_specific_content(self):
        """Test enabling source with specific content names."""
        bindings = LibraryBindings(campaign_id="test")

        bindings.enable_source(
            "test",
            content_type=ContentType.CLASS,
            content_names=["fighter", "wizard"],
        )

        classes = bindings.sources["test"].content_filter[ContentType.CLASS]
        assert isinstance(classes, list)
        assert set(classes) == {"fighter", "wizard"}

    def test_enable_source_merges_content_names(self):
        """Test that enabling with content names merges with existing."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test", content_type=ContentType.CLASS, content_names=["fighter"])

        bindings.enable_source("test", content_type=ContentType.CLASS, content_names=["wizard"])

        # Should have both classes merged
        classes = bindings.sources["test"].content_filter[ContentType.CLASS]
        assert "fighter" in classes
        assert "wizard" in classes

    def test_enable_source_no_change_if_already_all(self):
        """Test that enabling specific content doesn't override 'all' filter."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test", content_type=ContentType.CLASS)  # All classes

        # Try to enable specific class - should not change
        bindings.enable_source("test", content_type=ContentType.CLASS, content_names=["fighter"])

        assert bindings.sources["test"].content_filter[ContentType.CLASS] == "*"

    def test_disable_source_existing(self):
        """Test disabling an existing source."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test-source")

        bindings.disable_source("test-source")

        assert bindings.sources["test-source"].enabled is False

    def test_disable_source_new(self):
        """Test disabling a source that wasn't enabled creates disabled binding."""
        bindings = LibraryBindings(campaign_id="test")

        bindings.disable_source("never-enabled")

        assert "never-enabled" in bindings.sources
        assert bindings.sources["never-enabled"].enabled is False

    def test_is_content_enabled_no_binding(self):
        """Test is_content_enabled returns False for unbound source."""
        bindings = LibraryBindings(campaign_id="test")

        result = bindings.is_content_enabled("unknown", ContentType.CLASS, "fighter")

        assert result is False

    def test_is_content_enabled_disabled_source(self):
        """Test is_content_enabled returns False for disabled source."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.disable_source("disabled-source")

        result = bindings.is_content_enabled("disabled-source", ContentType.CLASS, "fighter")

        assert result is False

    def test_is_content_enabled_no_filter(self):
        """Test is_content_enabled returns True when no filter (all enabled)."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test-source")  # No filter = all enabled

        result = bindings.is_content_enabled("test-source", ContentType.CLASS, "fighter")

        assert result is True

    def test_is_content_enabled_filter_star(self):
        """Test is_content_enabled returns True for '*' filter."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test-source", content_type=ContentType.CLASS)

        result = bindings.is_content_enabled("test-source", ContentType.CLASS, "fighter")

        assert result is True

    def test_is_content_enabled_filter_list_match(self):
        """Test is_content_enabled returns True when name in list."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source(
            "test-source",
            content_type=ContentType.CLASS,
            content_names=["fighter", "wizard"],
        )

        assert bindings.is_content_enabled("test-source", ContentType.CLASS, "fighter") is True
        assert bindings.is_content_enabled("test-source", ContentType.CLASS, "wizard") is True

    def test_is_content_enabled_filter_list_no_match(self):
        """Test is_content_enabled returns False when name not in list."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source(
            "test-source",
            content_type=ContentType.CLASS,
            content_names=["fighter"],
        )

        result = bindings.is_content_enabled("test-source", ContentType.CLASS, "wizard")

        assert result is False

    def test_is_content_enabled_case_insensitive(self):
        """Test is_content_enabled is case-insensitive for content names."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source(
            "test-source",
            content_type=ContentType.CLASS,
            content_names=["Fighter"],
        )

        assert bindings.is_content_enabled("test-source", ContentType.CLASS, "fighter") is True
        assert bindings.is_content_enabled("test-source", ContentType.CLASS, "FIGHTER") is True

    def test_is_content_enabled_wrong_content_type(self):
        """Test is_content_enabled returns False for unfiltered content type."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test-source", content_type=ContentType.CLASS)

        # Only classes are filtered, spells should return False
        result = bindings.is_content_enabled("test-source", ContentType.SPELL, "fireball")

        assert result is False

    def test_get_enabled_sources(self):
        """Test get_enabled_sources returns only enabled sources."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("source-a")
        bindings.enable_source("source-b")
        bindings.disable_source("source-c")

        enabled = bindings.get_enabled_sources()

        assert "source-a" in enabled
        assert "source-b" in enabled
        assert "source-c" not in enabled

    def test_get_enabled_sources_empty(self):
        """Test get_enabled_sources returns empty list when none enabled."""
        bindings = LibraryBindings(campaign_id="test")

        enabled = bindings.get_enabled_sources()

        assert enabled == []

    def test_get_source_binding_found(self):
        """Test get_source_binding returns binding when exists."""
        bindings = LibraryBindings(campaign_id="test")
        bindings.enable_source("test-source")

        binding = bindings.get_source_binding("test-source")

        assert binding is not None
        assert binding.source_id == "test-source"

    def test_get_source_binding_not_found(self):
        """Test get_source_binding returns None when not exists."""
        bindings = LibraryBindings(campaign_id="test")

        binding = bindings.get_source_binding("nonexistent")

        assert binding is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        bindings = LibraryBindings(
            campaign_id="test-campaign",
            updated_at=datetime(2026, 2, 2, 12, 0, 0),
        )
        bindings.enable_source("source-a")
        bindings.enable_source("source-b", content_type=ContentType.CLASS)

        data = bindings.to_dict()

        assert data["campaign_id"] == "test-campaign"
        # updated_at changes when enable_source is called, so we just verify it's a valid ISO timestamp
        assert "updated_at" in data
        from datetime import datetime as dt
        dt.fromisoformat(data["updated_at"])  # validates it's a proper ISO timestamp
        assert "source-a" in data["sources"]
        assert "source-b" in data["sources"]
        assert data["sources"]["source-b"]["content_filter"]["class"] == "*"

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "campaign_id": "test-campaign",
            "updated_at": "2026-02-02T12:00:00",
            "sources": {
                "source-a": {
                    "source_id": "source-a",
                    "enabled": True,
                    "content_filter": {},
                },
                "source-b": {
                    "source_id": "source-b",
                    "enabled": True,
                    "content_filter": {
                        "class": "*",
                    },
                },
            },
        }

        bindings = LibraryBindings.from_dict(data)

        assert bindings.campaign_id == "test-campaign"
        assert bindings.updated_at == datetime(2026, 2, 2, 12, 0, 0)
        assert "source-a" in bindings.sources
        assert "source-b" in bindings.sources
        assert bindings.sources["source-b"].content_filter[ContentType.CLASS] == "*"

    def test_roundtrip(self):
        """Test that to_dict and from_dict are inverse operations."""
        original = LibraryBindings(
            campaign_id="roundtrip-test",
            updated_at=datetime(2026, 1, 15, 10, 30, 0),
        )
        original.enable_source("source-one")
        original.enable_source("source-two", content_type=ContentType.SPELL)
        original.enable_source(
            "source-three",
            content_type=ContentType.CLASS,
            content_names=["fighter", "wizard"],
        )
        original.disable_source("source-disabled")

        data = original.to_dict()
        restored = LibraryBindings.from_dict(data)

        assert restored.campaign_id == original.campaign_id
        assert len(restored.sources) == len(original.sources)
        assert restored.sources["source-one"].enabled is True
        assert restored.sources["source-two"].content_filter[ContentType.SPELL] == "*"
        assert "fighter" in restored.sources["source-three"].content_filter[ContentType.CLASS]
        assert restored.sources["source-disabled"].enabled is False


class TestLibraryBindingsPersistence:
    """Integration tests for library bindings persistence in JSON files."""

    def test_save_and_load_bindings_json(self):
        """Test saving and loading bindings to/from JSON file."""
        with TemporaryDirectory() as tmpdir:
            bindings_path = Path(tmpdir) / "library-bindings.json"

            # Create bindings
            original = LibraryBindings(campaign_id="persistence-test")
            original.enable_source("tome-of-heroes")
            original.enable_source("phb", content_type=ContentType.CLASS)
            original.enable_source(
                "xge",
                content_type=ContentType.SPELL,
                content_names=["fireball", "lightning bolt"],
            )

            # Save to file
            with open(bindings_path, 'w', encoding='utf-8') as f:
                json.dump(original.to_dict(), f, indent=2)

            # Load from file
            with open(bindings_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            restored = LibraryBindings.from_dict(data)

            # Verify
            assert restored.campaign_id == "persistence-test"
            assert restored.sources["tome-of-heroes"].enabled is True
            assert restored.sources["phb"].content_filter[ContentType.CLASS] == "*"
            assert "fireball" in restored.sources["xge"].content_filter[ContentType.SPELL]

    def test_json_output_format(self):
        """Test that JSON output matches expected format."""
        bindings = LibraryBindings(
            campaign_id="my_campaign",
            updated_at=datetime(2026, 2, 2, 16, 0, 0),
        )
        bindings.enable_source("tome-of-heroes", content_type=ContentType.CLASS, content_names=["dragon-knight"])
        bindings.enable_source("tome-of-heroes", content_type=ContentType.RACE)

        data = bindings.to_dict()

        # Check structure matches expected format from issue
        assert "campaign_id" in data
        assert "updated_at" in data
        assert "sources" in data
        assert "tome-of-heroes" in data["sources"]

        source_data = data["sources"]["tome-of-heroes"]
        assert source_data["source_id"] == "tome-of-heroes"
        assert source_data["enabled"] is True
        assert "class" in source_data["content_filter"]
        assert "race" in source_data["content_filter"]
        assert source_data["content_filter"]["class"] == ["dragon-knight"]
        assert source_data["content_filter"]["race"] == "*"


class TestStorageIntegration:
    """Integration tests for library bindings with DnDStorage."""

    def test_bindings_created_on_campaign_load(self):
        """Test that library bindings are created when loading a campaign."""
        with TemporaryDirectory() as tmpdir:
            from gamemaster_mcp.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)
            storage.create_campaign(
                name="Test Campaign",
                description="A test campaign for bindings",
            )

            # Bindings should be created automatically
            assert storage.library_bindings is not None
            assert storage.library_bindings.campaign_id == storage._current_campaign.id

    def test_enable_and_disable_library_source(self):
        """Test enabling and disabling library sources through storage."""
        with TemporaryDirectory() as tmpdir:
            from gamemaster_mcp.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)
            storage.create_campaign(
                name="Test Campaign",
                description="A test campaign",
            )

            # Enable a source
            storage.enable_library_source("test-source")
            assert "test-source" in storage.get_enabled_library_sources()

            # Disable it
            storage.disable_library_source("test-source")
            assert "test-source" not in storage.get_enabled_library_sources()

    def test_bindings_persist_across_load(self):
        """Test that library bindings are persisted and loaded correctly."""
        with TemporaryDirectory() as tmpdir:
            from gamemaster_mcp.storage import DnDStorage

            # Create campaign and enable sources
            storage1 = DnDStorage(data_dir=tmpdir)
            storage1.create_campaign(
                name="Persist Test",
                description="Testing persistence",
            )
            storage1.enable_library_source("source-a")
            storage1.enable_library_source(
                "source-b",
                content_type="class",
                content_names=["fighter"],
            )

            # Create new storage instance and load campaign
            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("Persist Test")

            # Verify bindings were loaded
            assert storage2.library_bindings is not None
            enabled = storage2.get_enabled_library_sources()
            assert "source-a" in enabled
            assert "source-b" in enabled

            # Verify content filter was preserved
            binding = storage2.library_bindings.get_source_binding("source-b")
            assert binding is not None
            assert ContentType.CLASS in binding.content_filter
            assert "fighter" in binding.content_filter[ContentType.CLASS]

    def test_bindings_file_location(self):
        """Test that bindings are saved to correct location."""
        with TemporaryDirectory() as tmpdir:
            from gamemaster_mcp.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)
            storage.create_campaign(
                name="Location Test",
                description="Testing file location",
            )
            storage.enable_library_source("test-source")

            # Check file exists at expected location
            bindings_path = Path(tmpdir) / "campaigns" / "Location Test" / "rulebooks" / "library-bindings.json"
            assert bindings_path.exists()

            # Verify content
            with open(bindings_path, "r") as f:
                data = json.load(f)
            assert "test-source" in data["sources"]
