"""
Unit tests for the TOC Extractor.

Tests the TOCExtractor class for PDF table of contents extraction.
"""

import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from dm20_protocol.library.extractors.toc import (
    TOCExtractor,
    CONTENT_TYPE_PATTERNS,
)
from dm20_protocol.library.models import (
    ContentType,
    IndexEntry,
    SourceType,
    TOCEntry,
)


class TestContentTypeIdentification:
    """Tests for content type identification from titles."""

    def test_identify_class(self):
        """Test identifying class content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Fighter") == ContentType.CLASS
        assert extractor._identify_content_type("Chapter 2: Classes") == ContentType.CLASS
        assert extractor._identify_content_type("Tactician") == ContentType.CLASS

    def test_identify_subclass(self):
        """Test identifying subclass content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Path of the Berserker") == ContentType.SUBCLASS
        assert extractor._identify_content_type("College of Lore") == ContentType.SUBCLASS
        assert extractor._identify_content_type("Circle of the Moon") == ContentType.SUBCLASS
        assert extractor._identify_content_type("War Mind") == ContentType.SUBCLASS

    def test_identify_race(self):
        """Test identifying race content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Races") == ContentType.RACE
        assert extractor._identify_content_type("Elf") == ContentType.RACE
        assert extractor._identify_content_type("Dragonborn") == ContentType.RACE

    def test_identify_spell(self):
        """Test identifying spell content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Spells") == ContentType.SPELL
        assert extractor._identify_content_type("Chapter 5: Magic") == ContentType.SPELL

    def test_identify_monster(self):
        """Test identifying monster content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Monsters") == ContentType.MONSTER
        assert extractor._identify_content_type("Bestiary") == ContentType.MONSTER
        assert extractor._identify_content_type("Creature Stat Blocks") == ContentType.MONSTER

    def test_identify_feat(self):
        """Test identifying feat content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Feats") == ContentType.FEAT
        assert extractor._identify_content_type("New Feats") == ContentType.FEAT

    def test_identify_item(self):
        """Test identifying item content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Magic Items") == ContentType.ITEM
        assert extractor._identify_content_type("Equipment") == ContentType.ITEM
        assert extractor._identify_content_type("Weapons") == ContentType.ITEM

    def test_identify_background(self):
        """Test identifying background content."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Backgrounds") == ContentType.BACKGROUND

    def test_unknown_content(self):
        """Test that unrecognized content returns UNKNOWN."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._identify_content_type("Introduction") == ContentType.UNKNOWN
        assert extractor._identify_content_type("Credits") == ContentType.UNKNOWN
        assert extractor._identify_content_type("Random Title") == ContentType.UNKNOWN


class TestTOCHierarchy:
    """Tests for building TOC hierarchy from flat bookmark list."""

    def test_single_level(self):
        """Test single-level TOC."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        raw_toc = [
            (1, "Chapter 1", 1),
            (1, "Chapter 2", 10),
            (1, "Chapter 3", 20),
        ]

        result = extractor._build_toc_hierarchy(raw_toc)

        assert len(result) == 3
        assert result[0].title == "Chapter 1"
        assert result[0].page == 1
        assert result[0].children == []

    def test_nested_levels(self):
        """Test nested TOC with children."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        raw_toc = [
            (1, "Chapter 1", 1),
            (2, "Section 1.1", 2),
            (2, "Section 1.2", 5),
            (1, "Chapter 2", 10),
            (2, "Section 2.1", 11),
        ]

        result = extractor._build_toc_hierarchy(raw_toc)

        assert len(result) == 2
        assert result[0].title == "Chapter 1"
        assert len(result[0].children) == 2
        assert result[0].children[0].title == "Section 1.1"
        assert result[1].title == "Chapter 2"
        assert len(result[1].children) == 1

    def test_deep_nesting(self):
        """Test deeply nested TOC."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        raw_toc = [
            (1, "Chapter 1", 1),
            (2, "Section 1.1", 2),
            (3, "Subsection 1.1.1", 3),
            (3, "Subsection 1.1.2", 4),
            (2, "Section 1.2", 5),
        ]

        result = extractor._build_toc_hierarchy(raw_toc)

        assert len(result) == 1
        chapter = result[0]
        assert len(chapter.children) == 2
        section = chapter.children[0]
        assert len(section.children) == 2
        assert section.children[0].title == "Subsection 1.1.1"

    def test_empty_toc(self):
        """Test empty TOC list."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        result = extractor._build_toc_hierarchy([])

        assert result == []


class TestContentSummary:
    """Tests for content summary calculation."""

    def test_count_flat_entries(self):
        """Test counting content types in flat list."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        entries = [
            TOCEntry(title="Fighter", page=1, content_type=ContentType.CLASS),
            TOCEntry(title="Wizard", page=10, content_type=ContentType.CLASS),
            TOCEntry(title="Elf", page=20, content_type=ContentType.RACE),
        ]

        summary = extractor._calculate_content_summary(entries)

        assert summary.classes == 2
        assert summary.races == 1
        assert summary.spells == 0
        assert summary.total == 3

    def test_count_nested_entries(self):
        """Test counting content types in nested structure."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        entries = [
            TOCEntry(
                title="Classes",
                page=1,
                content_type=ContentType.UNKNOWN,
                children=[
                    TOCEntry(title="Fighter", page=2, content_type=ContentType.CLASS),
                    TOCEntry(title="Wizard", page=10, content_type=ContentType.CLASS),
                ],
            ),
            TOCEntry(
                title="Races",
                page=20,
                content_type=ContentType.UNKNOWN,
                children=[
                    TOCEntry(title="Elf", page=21, content_type=ContentType.RACE),
                ],
            ),
        ]

        summary = extractor._calculate_content_summary(entries)

        assert summary.classes == 2
        assert summary.races == 1
        assert summary.total == 3


class TestCleanTitle:
    """Tests for title cleaning."""

    def test_remove_trailing_dots(self):
        """Test removing trailing dots from TOC entries."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        # Trailing dots and whitespace are removed
        assert extractor._clean_title("Introduction...") == "Introduction"
        assert extractor._clean_title("Fighter...") == "Fighter"

    def test_remove_page_numbers(self):
        """Test removing trailing page numbers."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        # Trailing page numbers are removed
        assert extractor._clean_title("Fighter 42") == "Fighter"
        assert extractor._clean_title("Spells 100") == "Spells"

    def test_normalize_whitespace(self):
        """Test normalizing excessive whitespace."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        # Whitespace is normalized
        assert extractor._clean_title("  Fighter  ") == "Fighter"
        assert extractor._clean_title("The   Fighter") == "The Fighter"


class TestNoiseDetection:
    """Tests for noise detection in text."""

    def test_detect_page_numbers(self):
        """Test detecting page numbers as noise."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._is_noise("42") is True
        assert extractor._is_noise("page 5") is True

    def test_detect_short_text(self):
        """Test detecting very short text as noise."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._is_noise("A") is True
        assert extractor._is_noise("AB") is True

    def test_valid_titles(self):
        """Test that valid titles are not noise."""
        extractor = TOCExtractor(Path("dummy.pdf"))

        assert extractor._is_noise("Fighter") is False
        assert extractor._is_noise("Chapter 1: Classes") is False


class TestIntegration:
    """Integration tests with real PDF if available."""

    @pytest.fixture
    def drizzt_pdf_path(self):
        """Get path to Drizzt PDF if it exists."""
        # This path is relative to the project root
        pdf_path = Path("dnd_data/library/pdfs/Drizzt's Travelogue of Everything.pdf")
        if not pdf_path.exists():
            pytest.skip("Drizzt PDF not available for testing")
        return pdf_path

    def test_extract_real_pdf(self, drizzt_pdf_path):
        """Test extraction from a real PDF file."""
        extractor = TOCExtractor(drizzt_pdf_path)
        index = extractor.extract()

        # Basic structure checks
        assert index.source_id == "drizzt's-travelogue-of-everything"
        assert index.source_type == SourceType.PDF
        assert index.total_pages == 93
        assert len(index.file_hash) == 64  # SHA-256 hex

        # Content checks
        assert index.content_summary.classes >= 10  # Should find many classes
        assert len(index.toc) >= 1  # At least one top-level entry

    def test_index_entry_serialization(self, drizzt_pdf_path):
        """Test that IndexEntry can be serialized and deserialized."""
        extractor = TOCExtractor(drizzt_pdf_path)
        index = extractor.extract()

        # Serialize
        data = index.to_dict()

        # Check structure
        assert "source_id" in data
        assert "toc" in data
        assert "content_summary" in data

        # Deserialize
        restored = IndexEntry.from_dict(data)

        assert restored.source_id == index.source_id
        assert restored.total_pages == index.total_pages
        assert restored.content_summary.classes == index.content_summary.classes
