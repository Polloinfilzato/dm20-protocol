"""
Tests for adventure discovery and search system.

Tests keyword search, filtering, grouping, and formatting of
adventure search results.
"""

from __future__ import annotations

import pytest
from dm20_protocol.adventures.models import (
    AdventureIndexEntry,
    AdventureSearchResult,
    StorylineGroup,
)
from dm20_protocol.adventures.discovery import (
    expand_keywords,
    matches_query,
    search_adventures,
    format_search_results,
    _group_by_storyline,
    _get_storyline_summary,
)
from dm20_protocol.adventures.index import AdventureIndex
from pathlib import Path
from unittest.mock import Mock


# Test fixtures

@pytest.fixture
def sample_entries() -> list[AdventureIndexEntry]:
    """Sample adventure entries for testing."""
    return [
        AdventureIndexEntry(
            id="CoS",
            name="Curse of Strahd",
            source="CoS",
            storyline="Ravenloft",
            level_start=1,
            level_end=10,
            chapter_count=15,
            published="2016-03-15",
        ),
        AdventureIndexEntry(
            id="VRGtR",
            name="Van Richten's Guide to Ravenloft",
            source="VRGtR",
            storyline="Ravenloft",
            level_start=1,
            level_end=20,
            chapter_count=5,
            published="2021-05-18",
        ),
        AdventureIndexEntry(
            id="SCC",
            name="Strixhaven: A Curriculum of Chaos",
            source="SCC",
            storyline="Strixhaven",
            level_start=1,
            level_end=10,
            chapter_count=6,
            published="2021-12-07",
        ),
        AdventureIndexEntry(
            id="HotDQ",
            name="Hoard of the Dragon Queen",
            source="HotDQ",
            storyline="Tyranny of Dragons",
            level_start=1,
            level_end=7,
            chapter_count=8,
            published="2014-08-19",
        ),
        AdventureIndexEntry(
            id="RoT",
            name="The Rise of Tiamat",
            source="RoT",
            storyline="Tyranny of Dragons",
            level_start=8,
            level_end=15,
            chapter_count=9,
            published="2014-11-04",
        ),
        AdventureIndexEntry(
            id="KftGV",
            name="Keys from the Golden Vault",
            source="KftGV",
            storyline="",
            level_start=1,
            level_end=11,
            chapter_count=13,
            published="2023-02-21",
        ),
        AdventureIndexEntry(
            id="LMoP",
            name="Lost Mine of Phandelver",
            source="LMoP",
            storyline="",
            level_start=1,
            level_end=5,
            chapter_count=4,
            published="2014-07-15",
        ),
    ]


@pytest.fixture
def mock_index(sample_entries: list[AdventureIndexEntry]) -> AdventureIndex:
    """Mock AdventureIndex with sample data."""
    mock = Mock(spec=AdventureIndex)
    mock.entries = sample_entries
    mock.get_storylines.return_value = {
        "Ravenloft": [sample_entries[0], sample_entries[1]],
        "Strixhaven": [sample_entries[2]],
        "Tyranny of Dragons": [sample_entries[3], sample_entries[4]],
        "Uncategorized": [sample_entries[5], sample_entries[6]],
    }
    return mock


# Tests for keyword expansion

def test_expand_keywords_vampire():
    """Test keyword expansion for vampire-related terms."""
    result = expand_keywords("vampire")
    assert "vampire" in result
    assert "ravenloft" in result


def test_expand_keywords_school():
    """Test keyword expansion for magic school terms."""
    result = expand_keywords("magic school")
    assert "magic school" in result
    assert "strixhaven" in result


def test_expand_keywords_heist():
    """Test keyword expansion for heist terms."""
    result = expand_keywords("heist")
    assert "heist" in result
    assert "keys from the golden vault" in result
    assert "waterdeep" in result


def test_expand_keywords_dragon():
    """Test keyword expansion for dragon terms."""
    result = expand_keywords("dragon")
    assert "dragon" in result
    assert "tyranny of dragons" in result


def test_expand_keywords_no_mapping():
    """Test keywords without mapping return only original term."""
    result = expand_keywords("random keyword")
    assert result == {"random keyword"}


def test_expand_keywords_case_insensitive():
    """Test keyword expansion is case-insensitive."""
    result = expand_keywords("VAMPIRE")
    assert "ravenloft" in result


# Tests for query matching

def test_matches_query_exact_name():
    """Test exact name match returns highest relevance."""
    entry = AdventureIndexEntry(
        id="CoS",
        name="Curse of Strahd",
        source="CoS",
        storyline="Ravenloft",
    )
    matches, score = matches_query(entry, {"curse of strahd"})
    assert matches is True
    assert score == 3


def test_matches_query_partial_name():
    """Test partial name match returns medium relevance."""
    entry = AdventureIndexEntry(
        id="CoS",
        name="Curse of Strahd",
        source="CoS",
        storyline="Ravenloft",
    )
    matches, score = matches_query(entry, {"curse"})
    assert matches is True
    assert score == 2


def test_matches_query_storyline():
    """Test storyline match returns low relevance."""
    entry = AdventureIndexEntry(
        id="CoS",
        name="Curse of Strahd",
        source="CoS",
        storyline="Ravenloft",
    )
    matches, score = matches_query(entry, {"ravenloft"})
    assert matches is True
    assert score == 1


def test_matches_query_no_match():
    """Test no match returns False with zero score."""
    entry = AdventureIndexEntry(
        id="CoS",
        name="Curse of Strahd",
        source="CoS",
        storyline="Ravenloft",
    )
    matches, score = matches_query(entry, {"strixhaven"})
    assert matches is False
    assert score == 0


def test_matches_query_case_insensitive():
    """Test query matching is case-insensitive."""
    entry = AdventureIndexEntry(
        id="CoS",
        name="Curse of Strahd",
        source="CoS",
        storyline="Ravenloft",
    )
    # Search terms should be lowercased (as done by expand_keywords)
    matches, score = matches_query(entry, {"curse"})
    assert matches is True
    assert score == 2


# Tests for search functionality

def test_search_adventures_keyword(mock_index: AdventureIndex):
    """Test keyword search finds matching adventures."""
    # "Strahd" expands to "ravenloft", so it matches both Ravenloft adventures
    result = search_adventures(mock_index, query="Strahd")
    assert result.total_matches == 2
    # Curse of Strahd should be first (name match > storyline match)
    assert result.groups[0].adventures[0].name == "Curse of Strahd"


def test_search_adventures_keyword_expansion(mock_index: AdventureIndex):
    """Test keyword expansion finds storyline matches."""
    result = search_adventures(mock_index, query="vampire")
    assert result.total_matches >= 2  # Should find Ravenloft adventures
    assert any(g.storyline == "Ravenloft" for g in result.groups)


def test_search_adventures_level_min_filter(mock_index: AdventureIndex):
    """Test level_min filter excludes low-level adventures."""
    result = search_adventures(mock_index, level_min=8)
    for group in result.groups:
        for adv in group.adventures:
            # Adventure should cover level 8 or higher
            if adv.level_end is not None:
                assert adv.level_end >= 8


def test_search_adventures_level_max_filter(mock_index: AdventureIndex):
    """Test level_max filter excludes high-level adventures."""
    result = search_adventures(mock_index, level_max=5)
    for group in result.groups:
        for adv in group.adventures:
            # Adventure should start at or below level 5
            if adv.level_start is not None:
                assert adv.level_start <= 5


def test_search_adventures_level_range_filter(mock_index: AdventureIndex):
    """Test combined level range filter."""
    result = search_adventures(mock_index, level_min=1, level_max=7)
    assert result.total_matches > 0
    for group in result.groups:
        for adv in group.adventures:
            # Adventure should overlap with 1-7 range
            if adv.level_start is not None:
                assert adv.level_start <= 7
            if adv.level_end is not None:
                assert adv.level_end >= 1


def test_search_adventures_storyline_filter(mock_index: AdventureIndex):
    """Test storyline filter returns only matching storyline."""
    result = search_adventures(mock_index, storyline="Ravenloft")
    assert result.total_matches == 2
    assert all(g.storyline == "Ravenloft" for g in result.groups)


def test_search_adventures_storyline_partial_match(mock_index: AdventureIndex):
    """Test storyline filter with partial match."""
    result = search_adventures(mock_index, storyline="Raven")
    assert result.total_matches >= 2
    assert any("Raven" in g.storyline for g in result.groups)


def test_search_adventures_combined_filters(mock_index: AdventureIndex):
    """Test combining multiple filters."""
    result = search_adventures(
        mock_index,
        query="dragon",
        level_min=1,
        level_max=10,
        storyline="Tyranny"
    )
    assert result.total_matches > 0
    assert all("Tyranny" in g.storyline for g in result.groups)


def test_search_adventures_limit(mock_index: AdventureIndex):
    """Test limit parameter restricts results."""
    # Use level filter to avoid summary path (empty query = summary)
    result = search_adventures(mock_index, level_min=1, limit=3)
    assert result.total_matches <= 3


def test_search_adventures_relevance_sorting(mock_index: AdventureIndex):
    """Test results sorted by relevance score."""
    # Search for "Curse" - should match "Curse of Strahd" exactly
    result = search_adventures(mock_index, query="Curse")
    assert result.total_matches > 0
    # First result should be exact/partial name match
    first_adv = result.groups[0].adventures[0]
    assert "Curse" in first_adv.name


def test_search_adventures_empty_query_returns_summary(mock_index: AdventureIndex):
    """Test empty query with no filters returns storyline summary."""
    result = search_adventures(mock_index)
    # Should return one adventure per storyline
    assert result.storyline_count > 0
    assert result.query == ""


# Tests for grouping

def test_group_by_storyline(sample_entries: list[AdventureIndexEntry]):
    """Test grouping entries by storyline."""
    # Take only Ravenloft entries
    ravenloft = [e for e in sample_entries if e.storyline == "Ravenloft"]
    groups = _group_by_storyline(ravenloft)

    assert len(groups) == 1
    assert groups[0].storyline == "Ravenloft"
    assert len(groups[0].adventures) == 2


def test_group_by_storyline_preserves_order(sample_entries: list[AdventureIndexEntry]):
    """Test grouping preserves first-seen order of storylines."""
    # Mix up entries
    mixed = [sample_entries[2], sample_entries[0], sample_entries[1]]
    groups = _group_by_storyline(mixed)

    # First group should be Strixhaven (first seen)
    assert groups[0].storyline == "Strixhaven"
    # Second should be Ravenloft
    assert groups[1].storyline == "Ravenloft"


def test_group_by_storyline_sorts_by_level(sample_entries: list[AdventureIndexEntry]):
    """Test adventures within group sorted by level."""
    # Tyranny of Dragons has two parts with different levels
    tyranny = [e for e in sample_entries if e.storyline == "Tyranny of Dragons"]
    groups = _group_by_storyline(tyranny)

    # First adventure should be lower level
    assert groups[0].adventures[0].level_start == 1
    assert groups[0].adventures[1].level_start == 8


def test_group_by_storyline_handles_empty_storyline(sample_entries: list[AdventureIndexEntry]):
    """Test entries with empty storyline grouped as Uncategorized."""
    uncategorized = [e for e in sample_entries if not e.storyline]
    groups = _group_by_storyline(uncategorized)

    assert len(groups) == 1
    assert groups[0].storyline == "Uncategorized"


# Tests for formatting

def test_format_search_results_no_matches():
    """Test formatting when no results found."""
    result = AdventureSearchResult(query="nonexistent", total_matches=0, groups=[])
    formatted = format_search_results(result)
    assert "No adventures found" in formatted


def test_format_search_results_with_query():
    """Test formatting includes query in header."""
    group = StorylineGroup(
        storyline="Ravenloft",
        adventures=[
            AdventureIndexEntry(
                id="CoS",
                name="Curse of Strahd",
                source="CoS",
                storyline="Ravenloft",
                level_start=1,
                level_end=10,
                chapter_count=15,
                published="2016-03-15",
            )
        ]
    )
    result = AdventureSearchResult(query="vampire", total_matches=1, groups=[group])
    formatted = format_search_results(result)

    assert "vampire" in formatted
    assert "Curse of Strahd" in formatted
    assert "Ravenloft" in formatted


def test_format_search_results_multi_part_series():
    """Test formatting identifies and labels multi-part series."""
    group = StorylineGroup(
        storyline="Tyranny of Dragons",
        adventures=[
            AdventureIndexEntry(
                id="HotDQ",
                name="Hoard of the Dragon Queen",
                source="HotDQ",
                storyline="Tyranny of Dragons",
                level_start=1,
                level_end=7,
                chapter_count=8,
            ),
            AdventureIndexEntry(
                id="RoT",
                name="The Rise of Tiamat",
                source="RoT",
                storyline="Tyranny of Dragons",
                level_start=8,
                level_end=15,
                chapter_count=9,
            ),
        ]
    )
    result = AdventureSearchResult(query="", total_matches=2, groups=[group])
    formatted = format_search_results(result)

    assert "Multi-part series" in formatted
    assert "Recommended:**" in formatted  # Markdown bold
    assert "Start with #1" in formatted
    assert "1. Hoard of the Dragon Queen" in formatted
    assert "2. The Rise of Tiamat" in formatted


def test_format_search_results_spoiler_free():
    """Test formatting does not include spoiler content."""
    group = StorylineGroup(
        storyline="Ravenloft",
        adventures=[
            AdventureIndexEntry(
                id="CoS",
                name="Curse of Strahd",
                source="CoS",
                storyline="Ravenloft",
                level_start=1,
                level_end=10,
                chapter_count=15,
                published="2016-03-15",
            )
        ]
    )
    result = AdventureSearchResult(query="", total_matches=1, groups=[group])
    formatted = format_search_results(result)

    # Should include basic info
    assert "Curse of Strahd" in formatted
    assert "Levels:" in formatted
    assert "Chapters:" in formatted
    assert "Published:" in formatted

    # Should NOT include plot details (we don't have them in the model anyway)
    # Just verify we're showing only the safe fields
    assert "1-10" in formatted  # level range
    assert "15" in formatted  # chapter count


def test_format_search_results_storyline_summary():
    """Test formatting for storyline summary (empty query)."""
    groups = [
        StorylineGroup(
            storyline="Ravenloft",
            adventures=[
                AdventureIndexEntry(
                    id="CoS",
                    name="Curse of Strahd",
                    source="CoS",
                    storyline="Ravenloft",
                    level_start=1,
                    level_end=10,
                    chapter_count=15,
                )
            ]
        ),
        StorylineGroup(
            storyline="Strixhaven",
            adventures=[
                AdventureIndexEntry(
                    id="SCC",
                    name="Strixhaven: A Curriculum of Chaos",
                    source="SCC",
                    storyline="Strixhaven",
                    level_start=1,
                    level_end=10,
                    chapter_count=6,
                )
            ]
        ),
    ]
    result = AdventureSearchResult(query="", total_matches=2, groups=groups)
    formatted = format_search_results(result)

    assert "Available Adventure Storylines" in formatted
    assert "Ravenloft" in formatted
    assert "Strixhaven" in formatted


def test_format_search_results_shows_level_range():
    """Test formatting shows level range for each adventure."""
    group = StorylineGroup(
        storyline="Test",
        adventures=[
            AdventureIndexEntry(
                id="test1",
                name="Test Adventure 1",
                source="T1",
                level_start=1,
                level_end=5,
                chapter_count=3,
            ),
            AdventureIndexEntry(
                id="test2",
                name="Test Adventure 2",
                source="T2",
                level_start=10,
                level_end=None,
                chapter_count=2,
            ),
            AdventureIndexEntry(
                id="test3",
                name="Test Adventure 3",
                source="T3",
                level_start=None,
                level_end=None,
                chapter_count=1,
            ),
        ]
    )
    result = AdventureSearchResult(query="", total_matches=3, groups=[group])
    formatted = format_search_results(result)

    assert "1-5" in formatted  # Normal range
    assert "10+" in formatted  # Open-ended
    assert "Any" in formatted  # No level restriction


# Tests for storyline summary

def test_get_storyline_summary(mock_index: AdventureIndex):
    """Test storyline summary returns one adventure per storyline."""
    result = _get_storyline_summary(mock_index)

    # Should have 4 storylines in our sample data
    assert result.storyline_count == 4
    assert result.query == ""

    # Each group should have exactly 1 adventure (representative)
    for group in result.groups:
        assert len(group.adventures) == 1


def test_get_storyline_summary_sorted():
    """Test storyline summary is sorted alphabetically."""
    mock = Mock(spec=AdventureIndex)
    mock.get_storylines.return_value = {
        "Zzzz": [AdventureIndexEntry(id="z", name="Z", source="Z")],
        "Aaaa": [AdventureIndexEntry(id="a", name="A", source="A")],
        "Mmmm": [AdventureIndexEntry(id="m", name="M", source="M")],
    }

    result = _get_storyline_summary(mock)

    assert result.groups[0].storyline == "Aaaa"
    assert result.groups[1].storyline == "Mmmm"
    assert result.groups[2].storyline == "Zzzz"
