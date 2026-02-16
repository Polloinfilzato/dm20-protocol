"""
Tests for adventure data models, index cache, and fivetools_utils extraction.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from dm20_protocol.adventures.models import (
    AdventureIndexEntry,
    StorylineGroup,
    AdventureSearchResult,
)
from dm20_protocol.adventures.index import (
    AdventureIndex,
    AdventureIndexError,
)
from dm20_protocol.rulebooks.sources.fivetools_utils import (
    convert_5etools_markup,
    render_entries,
)


def run_async(coro):
    """Helper to run async code in sync tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# =============================================================================
# Sample Data Fixtures
# =============================================================================

SAMPLE_ADVENTURE_RAW = {
    "id": "CoS",
    "name": "Curse of Strahd",
    "source": "CoS",
    "storyline": "Ravenloft",
    "level": {"start": 1, "end": 10},
    "group": "supplement",
    "published": "2016-03-15",
    "contents": [
        {"name": "Into the Mists", "headers": []},
        {"name": "The Village of Barovia", "headers": []},
        {"name": "Castle Ravenloft", "headers": []},
    ],
}

SAMPLE_ADVENTURE_MINIMAL = {
    "id": "TYP",
    "name": "Tales from the Yawning Portal",
    "source": "TftYP",
    "storyline": "",
    "group": "supplement",
}

SAMPLE_INDEX_JSON = {
    "adventure": [
        SAMPLE_ADVENTURE_RAW,
        SAMPLE_ADVENTURE_MINIMAL,
        {
            "id": "SCC",
            "name": "Strixhaven: A Curriculum of Chaos",
            "source": "SCC",
            "storyline": "Strixhaven",
            "level": {"start": 1, "end": 10},
            "group": "supplement",
            "published": "2021-12-07",
            "contents": [
                {"name": "Orientation"},
                {"name": "Strixhaven Semester 1"},
            ],
        },
    ]
}


# =============================================================================
# AdventureIndexEntry Model Tests
# =============================================================================

class TestAdventureIndexEntry:
    """Tests for AdventureIndexEntry Pydantic model."""

    def test_parse_full_entry(self):
        """Parse a complete 5etools adventure entry."""
        entry = AdventureIndexEntry.model_validate(SAMPLE_ADVENTURE_RAW)
        assert entry.id == "CoS"
        assert entry.name == "Curse of Strahd"
        assert entry.storyline == "Ravenloft"
        assert entry.level_start == 1
        assert entry.level_end == 10
        assert entry.chapter_count == 3
        assert len(entry.contents) == 3

    def test_parse_minimal_entry(self):
        """Parse an entry with no level or contents."""
        entry = AdventureIndexEntry.model_validate(SAMPLE_ADVENTURE_MINIMAL)
        assert entry.id == "TYP"
        assert entry.level_start is None
        assert entry.level_end is None
        assert entry.chapter_count == 0
        assert entry.contents == []

    def test_level_range_property(self):
        """Test level_range string formatting."""
        full = AdventureIndexEntry.model_validate(SAMPLE_ADVENTURE_RAW)
        assert full.level_range == "1-10"

        minimal = AdventureIndexEntry.model_validate(SAMPLE_ADVENTURE_MINIMAL)
        assert minimal.level_range == "Any"

        # Only start level
        partial = AdventureIndexEntry(
            id="X", name="X", source="X", level_start=5
        )
        assert partial.level_range == "5+"

    def test_flatten_nested_level(self):
        """Ensure model_validator flattens level.start/end correctly."""
        raw = {"id": "T", "name": "T", "source": "T", "level": {"start": 3, "end": 8}}
        entry = AdventureIndexEntry.model_validate(raw)
        assert entry.level_start == 3
        assert entry.level_end == 8

    def test_chapter_count_from_contents(self):
        """Chapter count is auto-derived from contents length."""
        raw = {
            "id": "T", "name": "T", "source": "T",
            "contents": [{"name": "Ch1"}, {"name": "Ch2"}],
        }
        entry = AdventureIndexEntry.model_validate(raw)
        assert entry.chapter_count == 2


# =============================================================================
# StorylineGroup Tests
# =============================================================================

class TestStorylineGroup:
    """Tests for StorylineGroup model."""

    def test_single_adventure(self):
        entry = AdventureIndexEntry.model_validate(SAMPLE_ADVENTURE_RAW)
        group = StorylineGroup(storyline="Ravenloft", adventures=[entry])
        assert not group.is_multi_part
        assert group.level_range == "1-10"

    def test_multi_part(self):
        a = AdventureIndexEntry(id="A", name="A", source="A", level_start=1, level_end=5)
        b = AdventureIndexEntry(id="B", name="B", source="B", level_start=5, level_end=15)
        group = StorylineGroup(storyline="S", adventures=[a, b])
        assert group.is_multi_part
        assert group.level_range == "1-15"


# =============================================================================
# AdventureSearchResult Tests
# =============================================================================

class TestAdventureSearchResult:
    def test_empty_result(self):
        result = AdventureSearchResult(query="vampires")
        assert result.total_matches == 0
        assert result.storyline_count == 0

    def test_with_groups(self):
        entry = AdventureIndexEntry.model_validate(SAMPLE_ADVENTURE_RAW)
        group = StorylineGroup(storyline="Ravenloft", adventures=[entry])
        result = AdventureSearchResult(
            query="gothic", total_matches=1, groups=[group]
        )
        assert result.storyline_count == 1


# =============================================================================
# AdventureIndex Tests
# =============================================================================

class TestAdventureIndex:
    """Tests for AdventureIndex cache and loading."""

    def test_cache_fresh_check_no_metadata(self, tmp_path):
        """No metadata file means cache is not fresh."""
        idx = AdventureIndex(cache_dir=tmp_path)
        assert not idx._is_cache_fresh()

    def test_cache_fresh_check_valid(self, tmp_path):
        """Recent metadata means cache is fresh."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        metadata = {"downloaded_at": datetime.now(timezone.utc).isoformat()}
        (cache_dir / "metadata.json").write_text(json.dumps(metadata))
        idx = AdventureIndex(cache_dir=tmp_path)
        assert idx._is_cache_fresh()

    def test_cache_fresh_check_stale(self, tmp_path):
        """Old metadata means cache is stale."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        old_date = datetime.now(timezone.utc) - timedelta(days=10)
        metadata = {"downloaded_at": old_date.isoformat()}
        (cache_dir / "metadata.json").write_text(json.dumps(metadata))
        idx = AdventureIndex(cache_dir=tmp_path)
        assert not idx._is_cache_fresh()

    def test_load_from_cache(self, tmp_path):
        """Load entries from cached JSON file."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "adventures.json").write_text(json.dumps(SAMPLE_INDEX_JSON))
        idx = AdventureIndex(cache_dir=tmp_path)
        idx._load_from_cache()
        assert idx.loaded
        assert len(idx.entries) == 3

    def test_load_from_cache_missing_file(self, tmp_path):
        """Raise error if cache file doesn't exist."""
        idx = AdventureIndex(cache_dir=tmp_path)
        with pytest.raises(AdventureIndexError, match="No cached index"):
            idx._load_from_cache()

    def test_get_by_id(self, tmp_path):
        """Lookup adventure by short ID."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "adventures.json").write_text(json.dumps(SAMPLE_INDEX_JSON))
        idx = AdventureIndex(cache_dir=tmp_path)
        idx._load_from_cache()

        result = idx.get_by_id("cos")
        assert result is not None
        assert result.name == "Curse of Strahd"

        assert idx.get_by_id("nonexistent") is None

    def test_get_by_name(self, tmp_path):
        """Lookup adventure by name."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "adventures.json").write_text(json.dumps(SAMPLE_INDEX_JSON))
        idx = AdventureIndex(cache_dir=tmp_path)
        idx._load_from_cache()

        result = idx.get_by_name("curse of strahd")
        assert result is not None
        assert result.id == "CoS"

    def test_get_storylines(self, tmp_path):
        """Group adventures by storyline."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "adventures.json").write_text(json.dumps(SAMPLE_INDEX_JSON))
        idx = AdventureIndex(cache_dir=tmp_path)
        idx._load_from_cache()

        storylines = idx.get_storylines()
        assert "Ravenloft" in storylines
        assert "Strixhaven" in storylines
        assert len(storylines["Ravenloft"]) == 1

    def test_load_uses_fresh_cache(self, tmp_path):
        """load() reads from cache when fresh."""
        cache_dir = tmp_path / "adventures" / "cache"
        cache_dir.mkdir(parents=True)
        (cache_dir / "adventures.json").write_text(json.dumps(SAMPLE_INDEX_JSON))
        metadata = {"downloaded_at": datetime.now(timezone.utc).isoformat()}
        (cache_dir / "metadata.json").write_text(json.dumps(metadata))

        idx = AdventureIndex(cache_dir=tmp_path)
        run_async(idx.load())
        assert idx.loaded
        assert len(idx.entries) == 3


# =============================================================================
# Shared fivetools_utils Tests
# =============================================================================

class TestFivetoolsUtils:
    """Tests that extracted utils produce same results as original."""

    def test_convert_markup_dc(self):
        assert convert_5etools_markup("{@dc 15}") == "DC 15"

    def test_convert_markup_hit(self):
        assert convert_5etools_markup("{@hit 5}") == "+5"

    def test_convert_markup_spell(self):
        assert convert_5etools_markup("{@spell fireball}") == "fireball"

    def test_convert_markup_with_source(self):
        assert convert_5etools_markup("{@spell fireball|PHB}") == "fireball"

    def test_convert_markup_empty(self):
        assert convert_5etools_markup("") == ""
        assert convert_5etools_markup("{@h}") == ""

    def test_render_entries_strings(self):
        result = render_entries(["Hello", "World"])
        assert result == ["Hello", "World"]

    def test_render_entries_nested(self):
        entries = [
            {
                "type": "entries",
                "name": "Feature",
                "entries": ["Some description"],
            }
        ]
        result = render_entries(entries)
        assert result == ["Feature. Some description"]

    def test_render_entries_list(self):
        entries = [
            {
                "type": "list",
                "items": ["item one", "item two"],
            }
        ]
        result = render_entries(entries)
        assert result == ["- item one", "- item two"]

    def test_render_entries_table(self):
        entries = [{"type": "table", "caption": "Weapons"}]
        result = render_entries(entries)
        assert result == ["[Table: Weapons]"]

    def test_render_entries_none(self):
        assert render_entries(None) == []
        assert render_entries([]) == []

    def test_render_entries_with_markup(self):
        entries = ["Cast {@spell fireball} at {@dc 15}"]
        result = render_entries(entries)
        assert result == ["Cast fireball at DC 15"]


# =============================================================================
# ModuleStructure read_aloud field test
# =============================================================================

class TestModuleStructureReadAloud:
    """Test the read_aloud field added to ModuleStructure."""

    def test_default_empty(self):
        from dm20_protocol.claudmaster.models.module import ModuleStructure
        ms = ModuleStructure(
            module_id="test", title="Test", source_file="test.pdf"
        )
        assert ms.read_aloud == {}

    def test_to_dict_omits_empty(self):
        from dm20_protocol.claudmaster.models.module import ModuleStructure
        ms = ModuleStructure(
            module_id="test", title="Test", source_file="test.pdf"
        )
        d = ms.to_dict()
        assert "read_aloud" not in d

    def test_to_dict_includes_when_populated(self):
        from dm20_protocol.claudmaster.models.module import ModuleStructure
        ms = ModuleStructure(
            module_id="test", title="Test", source_file="test.pdf",
            read_aloud={"ch1-intro": ["As you enter the tavern..."]},
        )
        d = ms.to_dict()
        assert d["read_aloud"] == {"ch1-intro": ["As you enter the tavern..."]}

    def test_from_dict_with_read_aloud(self):
        from dm20_protocol.claudmaster.models.module import ModuleStructure
        data = {
            "module_id": "test",
            "title": "Test",
            "source_file": "test.pdf",
            "read_aloud": {"scene-1": ["The door creaks open..."]},
        }
        ms = ModuleStructure.from_dict(data)
        assert ms.read_aloud == {"scene-1": ["The door creaks open..."]}

    def test_from_dict_without_read_aloud(self):
        from dm20_protocol.claudmaster.models.module import ModuleStructure
        data = {
            "module_id": "test",
            "title": "Test",
            "source_file": "test.pdf",
        }
        ms = ModuleStructure.from_dict(data)
        assert ms.read_aloud == {}
