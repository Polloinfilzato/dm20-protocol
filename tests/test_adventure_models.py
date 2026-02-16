"""
Tests for adventure data models using fixture data.

Tests AdventureIndexEntry, StorylineGroup, and AdventureSearchResult
using realistic fixture data from the 5etools format.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from dm20_protocol.adventures.models import (
    AdventureIndexEntry,
    AdventureSearchResult,
    StorylineGroup,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures" / "adventures"


@pytest.fixture
def index_data() -> dict:
    """Load the sample index fixture."""
    with open(FIXTURES_DIR / "adventures_index_sample.json") as f:
        return json.load(f)


@pytest.fixture
def all_entries(index_data: dict) -> list[AdventureIndexEntry]:
    """Parse all entries from the fixture."""
    return [
        AdventureIndexEntry.model_validate(raw)
        for raw in index_data["adventure"]
    ]


# --- AdventureIndexEntry construction from raw JSON ---


class TestAdventureIndexEntryFromFixture:
    """Test AdventureIndexEntry construction against fixture data."""

    def test_parse_all_fixture_entries(self, index_data: dict):
        """All fixture entries should parse without errors."""
        entries = []
        for raw in index_data["adventure"]:
            entry = AdventureIndexEntry.model_validate(raw)
            entries.append(entry)
        assert len(entries) == 10

    def test_cos_full_entry(self, all_entries: list[AdventureIndexEntry]):
        """CoS entry should have all fields populated."""
        cos = next(e for e in all_entries if e.id == "CoS")
        assert cos.name == "Curse of Strahd"
        assert cos.source == "CoS"
        assert cos.storyline == "Ravenloft"
        assert cos.level_start == 1
        assert cos.level_end == 10
        assert cos.chapter_count == 5
        assert cos.published == "2016-03-15"

    def test_tftyp_no_level(self, all_entries: list[AdventureIndexEntry]):
        """TftYP entry without level data should have None."""
        tftyp = next(e for e in all_entries if e.id == "TftYP")
        assert tftyp.level_start is None
        assert tftyp.level_end is None
        assert tftyp.level_range == "Any"

    def test_lmop_empty_storyline(self, all_entries: list[AdventureIndexEntry]):
        """LMoP with empty storyline should store empty string."""
        lmop = next(e for e in all_entries if e.id == "LMoP")
        assert lmop.storyline == ""

    def test_chapter_count_derived_from_contents(
        self, all_entries: list[AdventureIndexEntry]
    ):
        """Chapter count auto-derived from contents length."""
        hotdq = next(e for e in all_entries if e.id == "HotDQ")
        assert hotdq.chapter_count == 8

    def test_level_range_property_formats(
        self, all_entries: list[AdventureIndexEntry]
    ):
        """Level range property produces correct format strings."""
        cos = next(e for e in all_entries if e.id == "CoS")
        assert cos.level_range == "1-10"

        rot = next(e for e in all_entries if e.id == "RoT")
        assert rot.level_range == "8-15"

    def test_flatten_nested_level_from_fixture(self, index_data: dict):
        """Verify level.start/end flattening from real JSON format."""
        raw_cos = next(a for a in index_data["adventure"] if a["id"] == "CoS")
        assert "level" in raw_cos
        assert raw_cos["level"]["start"] == 1
        assert raw_cos["level"]["end"] == 10

        entry = AdventureIndexEntry.model_validate(raw_cos)
        assert entry.level_start == 1
        assert entry.level_end == 10


# --- StorylineGroup tests ---


class TestStorylineGroupFromFixture:
    """Test StorylineGroup with fixture-derived entries."""

    def test_multi_part_strixhaven(self, all_entries: list[AdventureIndexEntry]):
        """Strixhaven should have 4 adventures (multi-part)."""
        strix = [e for e in all_entries if e.storyline == "Strixhaven"]
        group = StorylineGroup(storyline="Strixhaven", adventures=strix)

        assert group.is_multi_part
        assert len(group.adventures) == 4

    def test_multi_part_tyranny(self, all_entries: list[AdventureIndexEntry]):
        """Tyranny of Dragons should have 2 parts with correct range."""
        tyranny = [e for e in all_entries if e.storyline == "Tyranny of Dragons"]
        group = StorylineGroup(storyline="Tyranny of Dragons", adventures=tyranny)

        assert group.is_multi_part
        assert len(group.adventures) == 2
        assert group.level_range == "1-15"

    def test_single_adventure_not_multi(self, all_entries: list[AdventureIndexEntry]):
        """Waterdeep with one adventure should not be multi-part."""
        waterdeep = [e for e in all_entries if e.storyline == "Waterdeep"]
        group = StorylineGroup(storyline="Waterdeep", adventures=waterdeep)

        assert not group.is_multi_part
        assert len(group.adventures) == 1

    def test_no_level_range_group(self, all_entries: list[AdventureIndexEntry]):
        """Group with no-level adventures should return 'Any'."""
        entry = AdventureIndexEntry(id="X", name="X", source="X")
        group = StorylineGroup(storyline="Test", adventures=[entry])
        assert group.level_range == "Any"


# --- AdventureSearchResult tests ---


class TestAdventureSearchResult:
    """Test AdventureSearchResult model properties."""

    def test_empty_result(self):
        result = AdventureSearchResult(query="nonexistent")
        assert result.total_matches == 0
        assert result.storyline_count == 0
        assert result.groups == []

    def test_storyline_count(self, all_entries: list[AdventureIndexEntry]):
        ravenloft = [e for e in all_entries if e.storyline == "Ravenloft"]
        strix = [e for e in all_entries if e.storyline == "Strixhaven"]

        groups = [
            StorylineGroup(storyline="Ravenloft", adventures=ravenloft),
            StorylineGroup(storyline="Strixhaven", adventures=strix),
        ]
        result = AdventureSearchResult(
            query="test", total_matches=5, groups=groups
        )
        assert result.storyline_count == 2

    def test_field_validation(self, all_entries: list[AdventureIndexEntry]):
        """Missing optional fields should have sensible defaults."""
        entry = all_entries[0]
        group = StorylineGroup(storyline="Test", adventures=[entry])
        result = AdventureSearchResult(groups=[group])

        assert result.query == ""
        assert result.total_matches == 0
        assert result.storyline_count == 1
