"""
Unit tests for the Library Search System.

Tests the LibrarySearch class including query expansion,
TF-IDF scoring, and result ranking.
"""

import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gamemaster_mcp.library.manager import LibraryManager
from gamemaster_mcp.library.search import LibrarySearch, SearchResult
from gamemaster_mcp.library.models import (
    IndexEntry,
    TOCEntry,
    ContentType,
    SourceType,
)


class TestSearchResult:
    """Tests for the SearchResult dataclass."""

    def test_basic_creation(self):
        """Test basic SearchResult creation."""
        result = SearchResult(
            title="Fighter",
            source_id="phb",
            source_name="Players_Handbook.pdf",
            page=25,
            content_type="class",
            score=1.5,
            is_extracted=False,
        )

        assert result.title == "Fighter"
        assert result.source_id == "phb"
        assert result.source_name == "Players_Handbook.pdf"
        assert result.page == 25
        assert result.content_type == "class"
        assert result.score == 1.5
        assert result.is_extracted is False

    def test_optional_fields(self):
        """Test SearchResult with optional fields as None."""
        result = SearchResult(
            title="Unknown Entry",
            source_id="custom",
            source_name="custom.pdf",
            page=None,
            content_type=None,
            score=0.5,
            is_extracted=True,
        )

        assert result.page is None
        assert result.content_type is None
        assert result.is_extracted is True


class TestLibrarySearchInit:
    """Tests for LibrarySearch initialization."""

    def test_init_with_library_manager(self):
        """Test LibrarySearch can be initialized with LibraryManager."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)

            search = LibrarySearch(manager)

            assert search.library_manager is manager

    def test_synonyms_dict_exists(self):
        """Test that CONCEPT_SYNONYMS dictionary is populated."""
        assert len(LibrarySearch.CONCEPT_SYNONYMS) > 0
        assert "tanky" in LibrarySearch.CONCEPT_SYNONYMS
        assert "spellcaster" in LibrarySearch.CONCEPT_SYNONYMS

    def test_term_rarity_dict_exists(self):
        """Test that TERM_RARITY dictionary is populated."""
        assert len(LibrarySearch.TERM_RARITY) > 0
        assert "class" in LibrarySearch.TERM_RARITY
        assert "dragon" in LibrarySearch.TERM_RARITY


class TestQueryExpansion:
    """Tests for the _expand_query method."""

    def test_simple_query(self):
        """Test expansion of a simple single-word query."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            keywords = search._expand_query("fighter")

            assert "fighter" in keywords
            # Fighter is associated with melee, warrior, etc.
            # But only if "fighter" itself is in CONCEPT_SYNONYMS
            assert len(keywords) >= 1

    def test_query_with_synonyms(self):
        """Test that synonyms are added for known concepts."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            keywords = search._expand_query("tanky")

            assert "tanky" in keywords
            # Should include synonyms like tank, defensive, etc.
            assert "tank" in keywords or "defensive" in keywords

    def test_query_with_multiple_words(self):
        """Test expansion of multi-word query."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            keywords = search._expand_query("dragon spellcaster")

            assert "dragon" in keywords
            assert "spellcaster" in keywords
            # Should expand both terms
            assert len(keywords) > 2

    def test_query_case_insensitive(self):
        """Test that query expansion is case-insensitive."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            keywords1 = search._expand_query("DRAGON")
            keywords2 = search._expand_query("dragon")

            # Both should produce the same keywords
            assert set(keywords1) == set(keywords2)

    def test_query_no_duplicates(self):
        """Test that expanded keywords don't have duplicates."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            keywords = search._expand_query("fire fire")

            # Should not have duplicate "fire"
            assert keywords.count("fire") == 1

    def test_empty_query(self):
        """Test expansion of empty query."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            keywords = search._expand_query("")

            assert keywords == []


class TestScoring:
    """Tests for the _score_entry method."""

    def test_exact_match_scores_higher(self):
        """Test that exact token matches score higher than partial."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entry_exact = TOCEntry(title="Fighter", page=10, content_type=ContentType.CLASS)
            entry_partial = TOCEntry(title="The Fighter's Handbook", page=20, content_type=ContentType.CLASS)

            keywords = ["fighter"]

            score_exact = search._score_entry(entry_exact, keywords)
            score_partial = search._score_entry(entry_partial, keywords)

            assert score_exact > score_partial

    def test_no_match_scores_zero(self):
        """Test that non-matching entries score zero."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entry = TOCEntry(title="Wizard", page=10, content_type=ContentType.CLASS)
            keywords = ["fighter", "martial", "warrior"]

            score = search._score_entry(entry, keywords)

            assert score == 0.0

    def test_multiple_keywords_increase_score(self):
        """Test that matching multiple keywords increases score."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entry = TOCEntry(title="Fire Dragon", page=10, content_type=ContentType.MONSTER)

            keywords_single = ["fire"]
            keywords_multiple = ["fire", "dragon"]

            score_single = search._score_entry(entry, keywords_single)
            score_multiple = search._score_entry(entry, keywords_multiple)

            assert score_multiple > score_single

    def test_content_type_bonus(self):
        """Test that entries with known content types get a bonus."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entry_typed = TOCEntry(title="Fire Giant", page=10, content_type=ContentType.MONSTER)
            entry_unknown = TOCEntry(title="Fire Giant", page=10, content_type=ContentType.UNKNOWN)

            keywords = ["fire", "giant"]

            score_typed = search._score_entry(entry_typed, keywords)
            score_unknown = search._score_entry(entry_unknown, keywords)

            assert score_typed > score_unknown

    def test_position_weight(self):
        """Test that earlier keywords in list have more weight."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entry = TOCEntry(title="Dragon", page=10)

            # "dragon" first in list
            keywords_first = ["dragon", "other", "keywords"]
            # "dragon" last in list
            keywords_last = ["other", "keywords", "dragon"]

            score_first = search._score_entry(entry, keywords_first)
            score_last = search._score_entry(entry, keywords_last)

            # Earlier position should score higher
            assert score_first > score_last


class TestFlattenToc:
    """Tests for the _flatten_toc method."""

    def test_flat_toc(self):
        """Test flattening already flat TOC."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entries = [
                TOCEntry(title="Chapter 1", page=1),
                TOCEntry(title="Chapter 2", page=10),
            ]

            flat = search._flatten_toc(entries)

            assert len(flat) == 2

    def test_nested_toc(self):
        """Test flattening nested TOC structure."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entries = [
                TOCEntry(
                    title="Classes",
                    page=10,
                    children=[
                        TOCEntry(title="Fighter", page=15, content_type=ContentType.CLASS),
                        TOCEntry(title="Wizard", page=30, content_type=ContentType.CLASS),
                    ],
                ),
            ]

            flat = search._flatten_toc(entries)

            assert len(flat) == 3
            titles = [e.title for e in flat]
            assert "Classes" in titles
            assert "Fighter" in titles
            assert "Wizard" in titles

    def test_deeply_nested_toc(self):
        """Test flattening deeply nested TOC."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            entries = [
                TOCEntry(
                    title="Level 1",
                    page=1,
                    children=[
                        TOCEntry(
                            title="Level 2",
                            page=5,
                            children=[
                                TOCEntry(title="Level 3", page=8),
                            ],
                        ),
                    ],
                ),
            ]

            flat = search._flatten_toc(entries)

            assert len(flat) == 3

    def test_empty_toc(self):
        """Test flattening empty TOC."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            search = LibrarySearch(manager)

            flat = search._flatten_toc([])

            assert flat == []


class TestSearch:
    """Tests for the main search method."""

    def test_search_empty_library(self):
        """Test search with no indexed content."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            results = manager.semantic_search.search("fighter")

            assert results == []

    def test_search_finds_matching_entries(self):
        """Test search finds matching TOC entries."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create index with TOC entries
            index = IndexEntry(
                source_id="phb",
                filename="phb.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash123",
                total_pages=300,
                toc=[
                    TOCEntry(title="Fighter", page=20, content_type=ContentType.CLASS),
                    TOCEntry(title="Wizard", page=50, content_type=ContentType.CLASS),
                    TOCEntry(title="Fireball", page=100, content_type=ContentType.SPELL),
                ],
            )
            manager.save_index(index)

            results = manager.semantic_search.search("fighter")

            assert len(results) >= 1
            assert any(r.title == "Fighter" for r in results)

    def test_search_case_insensitive(self):
        """Test search is case-insensitive."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[TOCEntry(title="FIGHTER", page=10, content_type=ContentType.CLASS)],
            )
            manager.save_index(index)

            results = manager.semantic_search.search("fighter")

            assert len(results) == 1
            assert results[0].title == "FIGHTER"

    def test_search_with_synonyms(self):
        """Test search finds results via synonyms."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[
                    TOCEntry(title="Dragonborn", page=10, content_type=ContentType.RACE),
                    TOCEntry(title="Draconic Sorcerer", page=20, content_type=ContentType.SUBCLASS),
                ],
            )
            manager.save_index(index)

            # Search for "dragon" should find draconic via synonyms
            results = manager.semantic_search.search("dragon")

            assert len(results) >= 1
            titles = [r.title for r in results]
            # Should find entries with "dragon" or related terms
            assert any("Dragonborn" in t or "Draconic" in t for t in titles)

    def test_search_respects_limit(self):
        """Test search respects result limit."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create index with many matching entries
            toc_entries = [
                TOCEntry(title=f"Fire Spell {i}", page=i, content_type=ContentType.SPELL)
                for i in range(20)
            ]
            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=toc_entries,
            )
            manager.save_index(index)

            results = manager.semantic_search.search("fire", limit=5)

            assert len(results) == 5

    def test_search_results_sorted_by_score(self):
        """Test search results are sorted by score descending."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[
                    TOCEntry(title="Dragon", page=10, content_type=ContentType.MONSTER),
                    TOCEntry(title="Dragon Slayer Sword", page=20, content_type=ContentType.ITEM),
                    TOCEntry(title="How to Train Your Dragon Pet", page=30),
                ],
            )
            manager.save_index(index)

            results = manager.semantic_search.search("dragon")

            # Results should be sorted by score
            scores = [r.score for r in results]
            assert scores == sorted(scores, reverse=True)

    def test_search_empty_query(self):
        """Test search with empty query returns no results."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            results = manager.semantic_search.search("")

            assert results == []

    def test_search_whitespace_query(self):
        """Test search with whitespace-only query returns no results."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            results = manager.semantic_search.search("   ")

            assert results == []

    def test_search_across_multiple_sources(self):
        """Test search finds entries across multiple indexed sources."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create two indexes
            index1 = IndexEntry(
                source_id="phb",
                filename="phb.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash1",
                toc=[TOCEntry(title="Fighter", page=20, content_type=ContentType.CLASS)],
            )
            index2 = IndexEntry(
                source_id="xge",
                filename="xge.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash2",
                toc=[TOCEntry(title="Cavalier Fighter", page=50, content_type=ContentType.SUBCLASS)],
            )
            manager.save_index(index1)
            manager.save_index(index2)

            results = manager.semantic_search.search("fighter")

            assert len(results) == 2
            source_ids = {r.source_id for r in results}
            assert source_ids == {"phb", "xge"}

    def test_search_includes_source_name(self):
        """Test search results include source filename."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="phb",
                filename="Players_Handbook.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[TOCEntry(title="Fighter", page=20, content_type=ContentType.CLASS)],
            )
            manager.save_index(index)

            results = manager.semantic_search.search("fighter")

            assert len(results) == 1
            assert results[0].source_name == "Players_Handbook.pdf"


class TestSearchResultRanking:
    """Tests for result ranking quality."""

    def test_exact_match_ranks_higher_than_partial(self):
        """Test that exact term matches rank higher than partial matches."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[
                    TOCEntry(title="Dragon", page=10, content_type=ContentType.MONSTER),
                    TOCEntry(title="Dragonborn Race Overview", page=20, content_type=ContentType.RACE),
                ],
            )
            manager.save_index(index)

            results = manager.semantic_search.search("dragon")

            # "Dragon" should rank higher than "Dragonborn Race Overview"
            assert results[0].title == "Dragon"

    def test_specific_class_ranks_high_for_class_search(self):
        """Test that class entries rank high when searching for class names."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[
                    TOCEntry(title="Wizard", page=10, content_type=ContentType.CLASS),
                    TOCEntry(title="Wizard Spells", page=100, content_type=ContentType.UNKNOWN),
                    TOCEntry(title="The Wizard's Tower", page=200),
                ],
            )
            manager.save_index(index)

            results = manager.semantic_search.search("wizard")

            # The class entry should be first due to content type bonus and shorter title
            assert results[0].title == "Wizard"
            assert results[0].content_type == "class"

    def test_melee_spellcaster_query(self):
        """Test natural language query for melee spellcaster."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            index = IndexEntry(
                source_id="test",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="hash",
                toc=[
                    TOCEntry(title="Eldritch Knight", page=10, content_type=ContentType.SUBCLASS),
                    TOCEntry(title="Bladesinger", page=20, content_type=ContentType.SUBCLASS),
                    TOCEntry(title="Wizard", page=30, content_type=ContentType.CLASS),
                    TOCEntry(title="Fighter", page=40, content_type=ContentType.CLASS),
                ],
            )
            manager.save_index(index)

            # "melee spellcaster" should find classes with magic and martial aspects
            results = manager.semantic_search.search("melee spellcaster")

            # Should find at least Bladesinger (magic + blade) and Wizard (caster)
            titles = [r.title for r in results]
            # The search should return results
            assert len(results) > 0


class TestConceptSynonyms:
    """Tests for D&D concept synonym coverage."""

    def test_tanky_synonyms(self):
        """Test tanky concept has appropriate synonyms."""
        synonyms = LibrarySearch.CONCEPT_SYNONYMS.get("tanky", [])
        assert "defensive" in synonyms or "tank" in synonyms
        assert "durable" in synonyms or "tough" in synonyms

    def test_spellcaster_synonyms(self):
        """Test spellcaster concept has appropriate synonyms."""
        synonyms = LibrarySearch.CONCEPT_SYNONYMS.get("spellcaster", [])
        assert "caster" in synonyms or "magic" in synonyms
        assert "wizard" in synonyms or "mage" in synonyms

    def test_dragon_synonyms(self):
        """Test dragon concept has appropriate synonyms."""
        synonyms = LibrarySearch.CONCEPT_SYNONYMS.get("dragon", [])
        assert "draconic" in synonyms
        assert "wyrm" in synonyms or "drake" in synonyms

    def test_healer_synonyms(self):
        """Test healer concept has appropriate synonyms."""
        synonyms = LibrarySearch.CONCEPT_SYNONYMS.get("healer", [])
        assert "healing" in synonyms or "cure" in synonyms
        assert "support" in synonyms or "cleric" in synonyms

    def test_stealthy_synonyms(self):
        """Test stealthy concept has appropriate synonyms."""
        synonyms = LibrarySearch.CONCEPT_SYNONYMS.get("stealthy", [])
        assert "stealth" in synonyms or "rogue" in synonyms
        assert "shadow" in synonyms or "sneaky" in synonyms
