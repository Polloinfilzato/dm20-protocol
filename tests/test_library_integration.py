"""
Unit tests for Library Integration with RulebookManager.

Tests the integration between the library system and the RulebookManager,
ensuring that enabled library content appears in search_rules, get_class_info, etc.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from dm20_protocol.library.manager import LibraryManager
from dm20_protocol.library.bindings import LibraryBindings


class TestGetCustomSourcesForCampaign:
    """Tests for LibraryManager.get_custom_sources_for_campaign"""

    def test_returns_empty_for_no_enabled_sources(self):
        """Test returns empty list when no sources are enabled."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            bindings = LibraryBindings(campaign_id="test-campaign")

            result = manager.get_custom_sources_for_campaign(bindings)

            assert result == []

    def test_returns_empty_for_enabled_source_without_extracted_content(self):
        """Test returns empty list when source is enabled but no extracted content exists."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            bindings = LibraryBindings(campaign_id="test-campaign")
            bindings.enable_source("nonexistent-source")

            result = manager.get_custom_sources_for_campaign(bindings)

            assert result == []

    def test_returns_sources_for_enabled_content(self):
        """Test returns source paths for enabled sources with extracted content."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create extracted content
            source_id = "tome-of-heroes"
            extracted_dir = manager.extracted_dir / source_id
            extracted_dir.mkdir(parents=True)

            # Create a class JSON file
            class_data = {
                "$schema": "dm20-protocol/rulebook-v1",
                "name": "Extracted from tome-of-heroes",
                "version": "1.0",
                "content": {
                    "classes": [{
                        "index": "dragon-knight",
                        "name": "Dragon Knight",
                        "hit_die": 10,
                        "desc": ["A warrior who bonds with dragons."],
                    }],
                },
            }
            class_file = extracted_dir / "class-dragon-knight.json"
            with open(class_file, "w") as f:
                json.dump(class_data, f)

            # Enable the source
            bindings = LibraryBindings(campaign_id="test-campaign")
            bindings.enable_source(source_id)

            result = manager.get_custom_sources_for_campaign(bindings)

            assert len(result) == 1
            assert result[0][0] == source_id
            assert result[0][1] == class_file

    def test_returns_multiple_files_for_same_source(self):
        """Test returns multiple JSON files from the same source."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            source_id = "tome-of-heroes"
            extracted_dir = manager.extracted_dir / source_id
            extracted_dir.mkdir(parents=True)

            # Create multiple content files
            for content_type, name in [("class", "dragon-knight"), ("race", "dragonborn"), ("spell", "fireball")]:
                content_data = {
                    "$schema": "dm20-protocol/rulebook-v1",
                    "name": f"Extracted from {source_id}",
                    "version": "1.0",
                    "content": {f"{content_type}s": [{"index": name, "name": name.title()}]},
                }
                with open(extracted_dir / f"{content_type}-{name}.json", "w") as f:
                    json.dump(content_data, f)

            bindings = LibraryBindings(campaign_id="test-campaign")
            bindings.enable_source(source_id)

            result = manager.get_custom_sources_for_campaign(bindings)

            assert len(result) == 3
            source_ids = [r[0] for r in result]
            assert all(sid == source_id for sid in source_ids)

    def test_returns_sources_from_multiple_enabled_sources(self):
        """Test returns sources from multiple enabled library sources."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create extracted content for two sources
            for source_id in ["tome-of-heroes", "book-of-magic"]:
                extracted_dir = manager.extracted_dir / source_id
                extracted_dir.mkdir(parents=True)
                content_data = {
                    "$schema": "dm20-protocol/rulebook-v1",
                    "name": f"Extracted from {source_id}",
                    "version": "1.0",
                    "content": {"classes": [{"index": "test", "name": "Test"}]},
                }
                with open(extracted_dir / "class-test.json", "w") as f:
                    json.dump(content_data, f)

            bindings = LibraryBindings(campaign_id="test-campaign")
            bindings.enable_source("tome-of-heroes")
            bindings.enable_source("book-of-magic")

            result = manager.get_custom_sources_for_campaign(bindings)

            assert len(result) == 2
            source_ids = {r[0] for r in result}
            assert "tome-of-heroes" in source_ids
            assert "book-of-magic" in source_ids

    def test_ignores_disabled_sources(self):
        """Test that disabled sources are not included."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create extracted content for two sources
            for source_id in ["enabled-source", "disabled-source"]:
                extracted_dir = manager.extracted_dir / source_id
                extracted_dir.mkdir(parents=True)
                content_data = {
                    "$schema": "dm20-protocol/rulebook-v1",
                    "name": f"Extracted from {source_id}",
                    "version": "1.0",
                    "content": {"classes": [{"index": "test", "name": "Test"}]},
                }
                with open(extracted_dir / "class-test.json", "w") as f:
                    json.dump(content_data, f)

            bindings = LibraryBindings(campaign_id="test-campaign")
            bindings.enable_source("enabled-source")
            bindings.enable_source("disabled-source")
            bindings.disable_source("disabled-source")

            result = manager.get_custom_sources_for_campaign(bindings)

            assert len(result) == 1
            assert result[0][0] == "enabled-source"


class TestLibraryContentLoadWithCampaign:
    """Tests for loading library content when campaign loads."""

    def test_library_content_loads_with_campaign(self):
        """Test that library content is loaded when campaign loads."""
        with TemporaryDirectory() as tmpdir:
            from dm20_protocol.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)

            # Create campaign
            storage.create_campaign(
                name="Test Campaign",
                description="A test campaign",
            )

            # Setup library with extracted content
            library_dir = storage.library_dir
            library_dir.mkdir(parents=True, exist_ok=True)
            extracted_dir = library_dir / "extracted" / "test-source"
            extracted_dir.mkdir(parents=True)

            # Create extracted class content
            class_data = {
                "$schema": "dm20-protocol/rulebook-v1",
                "name": "Extracted from test-source",
                "version": "1.0",
                "content": {
                    "classes": [{
                        "index": "test-warrior",
                        "name": "Test Warrior",
                        "hit_die": 12,
                        "proficiencies": [],
                        "saving_throws": ["STR", "CON"],
                        "desc": ["A test warrior class."],
                    }],
                },
            }
            with open(extracted_dir / "class-test-warrior.json", "w") as f:
                json.dump(class_data, f)

            # Enable the source
            storage.enable_library_source("test-source")

            # Create RulebookManager manifest so it loads
            campaign_dir = storage._split_backend._get_campaign_dir("Test Campaign")
            rulebooks_dir = campaign_dir / "rulebooks"
            rulebooks_dir.mkdir(exist_ok=True)
            manifest_data = {
                "active_sources": [],
                "priority": [],
                "conflict_resolution": "last_wins",
            }
            with open(rulebooks_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            # Reload campaign to trigger library content loading
            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("Test Campaign")

            # Check if RulebookManager has the library source
            assert storage2.rulebook_manager is not None
            assert storage2.rulebook_manager.is_loaded("library:test-source:class-test-warrior")

    def test_library_content_skipped_without_rulebook_manager(self):
        """Test that library content loading is skipped when no RulebookManager exists."""
        with TemporaryDirectory() as tmpdir:
            from dm20_protocol.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)

            # Create campaign (no manifest = no RulebookManager)
            storage.create_campaign(
                name="No Rulebook Campaign",
                description="A campaign without rulebooks",
            )

            # Setup library with extracted content
            library_dir = storage.library_dir
            library_dir.mkdir(parents=True, exist_ok=True)
            extracted_dir = library_dir / "extracted" / "test-source"
            extracted_dir.mkdir(parents=True)

            class_data = {
                "$schema": "dm20-protocol/rulebook-v1",
                "name": "Test",
                "version": "1.0",
                "content": {"classes": [{"index": "test", "name": "Test"}]},
            }
            with open(extracted_dir / "class-test.json", "w") as f:
                json.dump(class_data, f)

            storage.enable_library_source("test-source")

            # Reload campaign - should not fail even without RulebookManager
            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("No Rulebook Campaign")

            # RulebookManager should be None (no manifest)
            assert storage2.rulebook_manager is None

    def test_library_content_skipped_without_bindings(self):
        """Test that library content loading is skipped when no bindings exist."""
        with TemporaryDirectory() as tmpdir:
            from dm20_protocol.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)

            # Create campaign with manifest but no library bindings
            storage.create_campaign(
                name="No Bindings Campaign",
                description="A campaign without library bindings",
            )

            # Create RulebookManager manifest
            campaign_dir = storage._split_backend._get_campaign_dir("No Bindings Campaign")
            rulebooks_dir = campaign_dir / "rulebooks"
            manifest_data = {
                "active_sources": [],
                "priority": [],
                "conflict_resolution": "last_wins",
            }
            with open(rulebooks_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            # Delete the bindings file if it exists
            bindings_path = rulebooks_dir / "library-bindings.json"
            if bindings_path.exists():
                bindings_path.unlink()

            # Reload campaign - library_bindings will be created as empty
            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("No Bindings Campaign")

            # Should have RulebookManager but no library sources loaded
            assert storage2.rulebook_manager is not None
            # Check that no library sources are loaded
            library_sources = [
                sid for sid in storage2.rulebook_manager.source_ids
                if sid.startswith("library:")
            ]
            assert len(library_sources) == 0


class TestLibraryContentInSearchRules:
    """Tests for library content appearing in search_rules."""

    def test_library_class_appears_in_search(self):
        """Test that library classes appear in search results."""
        with TemporaryDirectory() as tmpdir:
            from dm20_protocol.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)

            # Create campaign with rulebook manifest
            storage.create_campaign(
                name="Search Test Campaign",
                description="Testing search integration",
            )

            # Create manifest
            campaign_dir = storage._split_backend._get_campaign_dir("Search Test Campaign")
            rulebooks_dir = campaign_dir / "rulebooks"
            manifest_data = {
                "active_sources": [],
                "priority": [],
                "conflict_resolution": "last_wins",
            }
            with open(rulebooks_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            # Setup library with extracted content
            library_dir = storage.library_dir
            extracted_dir = library_dir / "extracted" / "homebrew"
            extracted_dir.mkdir(parents=True)

            class_data = {
                "$schema": "dm20-protocol/rulebook-v1",
                "name": "Homebrew Classes",
                "version": "1.0",
                "content": {
                    "classes": [{
                        "index": "shadow-dancer",
                        "name": "Shadow Dancer",
                        "hit_die": 8,
                        "proficiencies": [],
                        "saving_throws": ["DEX", "CHA"],
                        "desc": ["A mysterious class that manipulates shadows."],
                    }],
                },
            }
            with open(extracted_dir / "class-shadow-dancer.json", "w") as f:
                json.dump(class_data, f)

            storage.enable_library_source("homebrew")

            # Reload campaign
            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("Search Test Campaign")

            # Search for the class
            results = storage2.rulebook_manager.search("shadow", categories=["class"])

            # Verify the library class appears in results
            class_names = [r.name for r in results]
            assert "Shadow Dancer" in class_names

    def test_library_spell_appears_in_search(self):
        """Test that library spells appear in search results."""
        with TemporaryDirectory() as tmpdir:
            from dm20_protocol.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)

            storage.create_campaign(
                name="Spell Search Campaign",
                description="Testing spell search",
            )

            campaign_dir = storage._split_backend._get_campaign_dir("Spell Search Campaign")
            rulebooks_dir = campaign_dir / "rulebooks"
            manifest_data = {
                "active_sources": [],
                "priority": [],
                "conflict_resolution": "last_wins",
            }
            with open(rulebooks_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            library_dir = storage.library_dir
            extracted_dir = library_dir / "extracted" / "spell-compendium"
            extracted_dir.mkdir(parents=True)

            spell_data = {
                "$schema": "dm20-protocol/rulebook-v1",
                "name": "Spell Compendium",
                "version": "1.0",
                "content": {
                    "spells": [{
                        "index": "shadow-bolt",
                        "name": "Shadow Bolt",
                        "level": 2,
                        "school": "Evocation",
                        "casting_time": "1 action",
                        "range": "60 feet",
                        "duration": "Instantaneous",
                        "components": ["V", "S"],
                        "classes": ["Sorcerer", "Warlock", "Wizard"],
                        "desc": ["You hurl a bolt of pure shadow at a creature."],
                    }],
                },
            }
            with open(extracted_dir / "spell-shadow-bolt.json", "w") as f:
                json.dump(spell_data, f)

            storage.enable_library_source("spell-compendium")

            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("Spell Search Campaign")

            results = storage2.rulebook_manager.search("shadow", categories=["spell"])

            spell_names = [r.name for r in results]
            assert "Shadow Bolt" in spell_names


class TestLibraryContentPriority:
    """Tests for library content priority in RulebookManager."""

    def test_library_sources_loaded_in_order(self):
        """Test that multiple library sources are loaded and prioritized correctly."""
        with TemporaryDirectory() as tmpdir:
            from dm20_protocol.storage import DnDStorage

            storage = DnDStorage(data_dir=tmpdir)

            storage.create_campaign(
                name="Priority Test Campaign",
                description="Testing source priority",
            )

            campaign_dir = storage._split_backend._get_campaign_dir("Priority Test Campaign")
            rulebooks_dir = campaign_dir / "rulebooks"
            manifest_data = {
                "active_sources": [],
                "priority": [],
                "conflict_resolution": "last_wins",
            }
            with open(rulebooks_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            # Create two library sources
            library_dir = storage.library_dir
            for source_name in ["source-a", "source-b"]:
                extracted_dir = library_dir / "extracted" / source_name
                extracted_dir.mkdir(parents=True)
                class_data = {
                    "$schema": "dm20-protocol/rulebook-v1",
                    "name": source_name,
                    "version": "1.0",
                    "content": {
                        "classes": [{
                            "index": f"{source_name}-class",
                            "name": f"{source_name.title()} Class",
                            "hit_die": 8,
                            "proficiencies": [],
                            "saving_throws": [],
                            "desc": [f"A class from {source_name}."],
                        }],
                    },
                }
                with open(extracted_dir / f"class-{source_name}.json", "w") as f:
                    json.dump(class_data, f)

            storage.enable_library_source("source-a")
            storage.enable_library_source("source-b")

            storage2 = DnDStorage(data_dir=tmpdir)
            storage2.load_campaign("Priority Test Campaign")

            # Both sources should be loaded
            assert storage2.rulebook_manager.is_loaded("library:source-a:class-source-a")
            assert storage2.rulebook_manager.is_loaded("library:source-b:class-source-b")

            # Both classes should be searchable
            results = storage2.rulebook_manager.search("class", categories=["class"])
            class_names = [r.name for r in results]
            assert "Source-A Class" in class_names
            assert "Source-B Class" in class_names
