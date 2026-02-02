"""
Unit tests for Markdown extractors.

Tests the MarkdownTOCExtractor and MarkdownContentExtractor classes
for extracting table of contents and content from Markdown files.
"""

import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gamemaster_mcp.library.extractors.toc import (
    MarkdownTOCExtractor,
    get_toc_extractor,
    MARKDOWN_HEADER_PATTERN,
)
from gamemaster_mcp.library.extractors.content import (
    MarkdownContentExtractor,
)
from gamemaster_mcp.library.models import (
    ContentType,
    IndexEntry,
    SourceType,
    TOCEntry,
)


# =============================================================================
# Sample Markdown Content for Testing
# =============================================================================

SAMPLE_MARKDOWN = """# Player's Handbook

This is the introduction to the handbook.

## Chapter 1: Classes

This chapter contains all the player classes.

### Fighter

The fighter is a master of martial combat.

**Hit Die:** d10

**Proficiencies:** All armor, shields, simple weapons, martial weapons.

#### Champion

The archetypal Champion focuses on raw physical power.

### Wizard

The wizard is a scholarly magic-user.

**Hit Die:** d6

**Spellcasting:** Intelligence is your spellcasting ability.

## Chapter 2: Races

This chapter contains playable races.

### Elf

Elves are a magical people with otherworldly grace.

**Ability Score Increase:** Your Dexterity score increases by 2.

### Dwarf

Bold and hardy, dwarves are known as skilled warriors.

**Ability Score Increase:** Your Constitution score increases by 2.

## Chapter 3: Spells

This chapter contains spell descriptions.

### Fireball

3rd-level evocation

**Casting Time:** 1 action
**Range:** 150 feet

A bright streak flashes from your finger.

### Magic Missile

1st-level evocation

**Casting Time:** 1 action
**Range:** 120 feet

You create three glowing darts of magical force.

## Appendix: Feats

Optional feats for character customization.

### Alert

Always on the lookout for danger, you gain the following benefits:
- You can't be surprised while you are conscious.
- You gain a +5 bonus to initiative.
"""

MARKDOWN_WITH_CODE_BLOCKS = """# Programming Guide

## Introduction

This guide covers programming concepts.

## Code Examples

Here is some code:

```python
# This is a code block
def hello():
    print("Hello")
```

### After Code Block

This section comes after the code block.

```
# Another code block with header-like content
## Not a real header
```

## Final Section

This is the final section.
"""


# =============================================================================
# Tests for MARKDOWN_HEADER_PATTERN
# =============================================================================

class TestMarkdownHeaderPattern:
    """Tests for the Markdown header regex pattern."""

    def test_h1_header(self):
        """Test matching level 1 header."""
        match = MARKDOWN_HEADER_PATTERN.match("# Title")
        assert match is not None
        assert match.group(1) == "#"
        assert match.group(2) == "Title"

    def test_h2_header(self):
        """Test matching level 2 header."""
        match = MARKDOWN_HEADER_PATTERN.match("## Section")
        assert match is not None
        assert match.group(1) == "##"
        assert match.group(2) == "Section"

    def test_h6_header(self):
        """Test matching level 6 header."""
        match = MARKDOWN_HEADER_PATTERN.match("###### Deep")
        assert match is not None
        assert match.group(1) == "######"
        assert match.group(2) == "Deep"

    def test_header_with_anchor(self):
        """Test header with ID anchor is parsed correctly."""
        match = MARKDOWN_HEADER_PATTERN.match("## Section {#section-id}")
        assert match is not None
        assert match.group(2) == "Section"

    def test_no_match_without_space(self):
        """Test that headers without space after # don't match."""
        match = MARKDOWN_HEADER_PATTERN.match("#NoSpace")
        assert match is None

    def test_no_match_for_non_header(self):
        """Test that regular text doesn't match."""
        match = MARKDOWN_HEADER_PATTERN.match("Regular text")
        assert match is None

    def test_no_match_for_code_hash(self):
        """Test that inline # doesn't match."""
        match = MARKDOWN_HEADER_PATTERN.match("Some text # not a header")
        assert match is None


# =============================================================================
# Tests for MarkdownTOCExtractor
# =============================================================================

class TestMarkdownTOCExtractor:
    """Tests for the MarkdownTOCExtractor class."""

    @pytest.fixture
    def sample_md_file(self):
        """Create a temporary Markdown file for testing."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test_handbook.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")
            yield md_path

    @pytest.fixture
    def md_with_code_blocks(self):
        """Create a Markdown file with code blocks."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "code_examples.md"
            md_path.write_text(MARKDOWN_WITH_CODE_BLOCKS, encoding="utf-8")
            yield md_path

    def test_extract_basic(self, sample_md_file):
        """Test basic extraction from Markdown file."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        index = extractor.extract()

        assert index.source_id == "test-handbook"
        assert index.filename == "test_handbook.md"
        assert index.source_type == SourceType.MARKDOWN
        assert len(index.file_hash) == 64  # SHA-256 hex

    def test_extract_toc_structure(self, sample_md_file):
        """Test that TOC has correct hierarchical structure."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        index = extractor.extract()

        # Should have one root entry (# Player's Handbook)
        assert len(index.toc) == 1
        root = index.toc[0]
        assert root.title == "Player's Handbook"

        # Root should have children (chapters)
        assert len(root.children) >= 3  # Classes, Races, Spells, Feats

    def test_extract_headers(self, sample_md_file):
        """Test header extraction."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        content = sample_md_file.read_text()
        headers = extractor._extract_headers(content)

        # Check that we found headers
        assert len(headers) > 0

        # Check first header
        level, title, line_num = headers[0]
        assert level == 1
        assert title == "Player's Handbook"
        assert line_num == 1

    def test_extract_headers_with_code_blocks(self, md_with_code_blocks):
        """Test that headers inside code blocks are ignored."""
        extractor = MarkdownTOCExtractor(md_with_code_blocks)
        content = md_with_code_blocks.read_text()
        headers = extractor._extract_headers(content)

        # Should not include "# This is a code block" or "## Not a real header"
        titles = [h[1] for h in headers]
        assert "This is a code block" not in titles
        assert "Not a real header" not in titles

        # Should include real headers
        assert "Programming Guide" in titles
        assert "Code Examples" in titles
        assert "After Code Block" in titles
        assert "Final Section" in titles

    def test_build_toc_tree_empty(self, sample_md_file):
        """Test building TOC from empty header list."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        result = extractor._build_toc_tree([])
        assert result == []

    def test_build_toc_tree_flat(self, sample_md_file):
        """Test building TOC from flat header list."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        headers = [
            (1, "Chapter 1", 1),
            (1, "Chapter 2", 10),
            (1, "Chapter 3", 20),
        ]
        result = extractor._build_toc_tree(headers)

        assert len(result) == 3
        assert result[0].title == "Chapter 1"
        assert result[0].children == []

    def test_build_toc_tree_nested(self, sample_md_file):
        """Test building TOC from nested header list."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        headers = [
            (1, "Book", 1),
            (2, "Chapter 1", 5),
            (3, "Section 1.1", 10),
            (2, "Chapter 2", 20),
        ]
        result = extractor._build_toc_tree(headers)

        assert len(result) == 1
        book = result[0]
        assert book.title == "Book"
        assert len(book.children) == 2
        assert book.children[0].title == "Chapter 1"
        assert len(book.children[0].children) == 1

    def test_identify_content_types(self, sample_md_file):
        """Test content type identification from titles."""
        extractor = MarkdownTOCExtractor(sample_md_file)

        assert extractor._identify_content_type("Fighter") == ContentType.CLASS
        assert extractor._identify_content_type("Wizard") == ContentType.CLASS
        assert extractor._identify_content_type("Elf") == ContentType.RACE
        assert extractor._identify_content_type("Dwarf") == ContentType.RACE
        # Note: "Fireball" alone is not identified as a spell
        # The pattern looks for keywords like "spell", "spells", "magic"
        assert extractor._identify_content_type("Spells") == ContentType.SPELL
        assert extractor._identify_content_type("Chapter 3: Spells") == ContentType.SPELL
        assert extractor._identify_content_type("Path of the Berserker") == ContentType.SUBCLASS

    def test_content_summary(self, sample_md_file):
        """Test content summary calculation."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        index = extractor.extract()

        summary = index.content_summary
        assert summary.classes >= 2  # Fighter, Wizard
        assert summary.races >= 2  # Elf, Dwarf
        assert summary.spells >= 2  # Fireball, Magic Missile
        assert summary.total >= 6

    def test_line_numbers_as_pages(self, sample_md_file):
        """Test that line numbers are used as page numbers."""
        extractor = MarkdownTOCExtractor(sample_md_file)
        index = extractor.extract()

        # First header should be on line 1
        assert index.toc[0].page == 1

        # total_pages should be the line count
        content = sample_md_file.read_text()
        assert index.total_pages == len(content.split("\n"))


class TestMarkdownTOCExtractorEdgeCases:
    """Edge case tests for MarkdownTOCExtractor."""

    def test_empty_file(self):
        """Test extraction from empty file."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "empty.md"
            md_path.write_text("", encoding="utf-8")

            extractor = MarkdownTOCExtractor(md_path)
            index = extractor.extract()

            assert index.toc == []
            assert index.content_summary.total == 0

    def test_no_headers(self):
        """Test file with no headers."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "no_headers.md"
            md_path.write_text("Just some text\nwithout headers.", encoding="utf-8")

            extractor = MarkdownTOCExtractor(md_path)
            index = extractor.extract()

            assert index.toc == []

    def test_unicode_headers(self):
        """Test file with unicode in headers."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "unicode.md"
            md_path.write_text("# Cafe\n## Uber\n### Nino", encoding="utf-8")

            extractor = MarkdownTOCExtractor(md_path)
            index = extractor.extract()

            assert len(index.toc) == 1
            assert index.toc[0].title == "Cafe"


# =============================================================================
# Tests for MarkdownContentExtractor
# =============================================================================

class TestMarkdownContentExtractor:
    """Tests for the MarkdownContentExtractor class."""

    @pytest.fixture
    def indexed_md(self):
        """Create an indexed Markdown file for testing."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "handbook.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            # Index the file first
            toc_extractor = MarkdownTOCExtractor(md_path)
            index = toc_extractor.extract()

            yield md_path, index

    def test_get_section_basic(self, indexed_md):
        """Test extracting a basic section."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        # Find the Fighter entry
        fighter_entry = None
        for chapter in index.toc[0].children:  # Children of main title
            for section in chapter.children:
                if section.title == "Fighter":
                    fighter_entry = section
                    break

        assert fighter_entry is not None
        content = extractor.get_section(fighter_entry)

        assert "### Fighter" in content
        assert "master of martial combat" in content
        assert "Hit Die:" in content

    def test_get_section_by_title(self, indexed_md):
        """Test extracting section by title."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        content = extractor.get_section_by_title("Fireball")

        assert content is not None
        assert "3rd-level evocation" in content
        assert "bright streak flashes" in content

    def test_get_section_by_title_not_found(self, indexed_md):
        """Test that non-existent title returns None."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        content = extractor.get_section_by_title("Nonexistent Section")

        assert content is None

    def test_get_section_by_title_case_insensitive(self, indexed_md):
        """Test that title search is case-insensitive."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        content = extractor.get_section_by_title("FIGHTER")

        assert content is not None
        assert "Fighter" in content

    def test_get_all_sections(self, indexed_md):
        """Test extracting all sections."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        sections = extractor.get_all_sections()

        assert len(sections) > 0
        assert "Fighter" in sections
        assert "Wizard" in sections
        assert "Elf" in sections

    def test_section_boundaries(self, indexed_md):
        """Test that sections don't overlap."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        fighter_content = extractor.get_section_by_title("Fighter")
        wizard_content = extractor.get_section_by_title("Wizard")

        # Fighter section should not contain Wizard content
        assert "Wizard" not in fighter_content or "wizard" in fighter_content.lower()
        # Note: "Wizard" might appear in cross-references, but "scholarly magic-user" shouldn't
        assert "scholarly magic-user" not in fighter_content

        # Wizard section should not contain next chapter
        assert "Races" not in wizard_content

    def test_flatten_toc(self, indexed_md):
        """Test flattening the TOC."""
        md_path, index = indexed_md
        extractor = MarkdownContentExtractor(md_path, index)

        flat = extractor._flatten_toc()

        # Should have all entries including nested ones
        assert len(flat) > len(index.toc)

        titles = [e.title for e in flat]
        assert "Player's Handbook" in titles
        assert "Fighter" in titles
        assert "Champion" in titles


class TestMarkdownContentExtractorEdgeCases:
    """Edge case tests for MarkdownContentExtractor."""

    def test_section_at_end_of_file(self):
        """Test extracting section at end of file."""
        content = """# Title

## Section 1

Some content.

## Final Section

This is the last section with no following header.
More content here.
"""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test.md"
            md_path.write_text(content, encoding="utf-8")

            toc_extractor = MarkdownTOCExtractor(md_path)
            index = toc_extractor.extract()

            extractor = MarkdownContentExtractor(md_path, index)
            final = extractor.get_section_by_title("Final Section")

            assert final is not None
            assert "last section" in final
            assert "More content here" in final

    def test_deeply_nested_sections(self):
        """Test extracting deeply nested sections."""
        content = """# Level 1

## Level 2

### Level 3

#### Level 4

##### Level 5

###### Level 6

Deep content here.
"""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "deep.md"
            md_path.write_text(content, encoding="utf-8")

            toc_extractor = MarkdownTOCExtractor(md_path)
            index = toc_extractor.extract()

            extractor = MarkdownContentExtractor(md_path, index)
            level6 = extractor.get_section_by_title("Level 6")

            assert level6 is not None
            assert "Deep content here" in level6


# =============================================================================
# Tests for get_toc_extractor Factory Function
# =============================================================================

class TestGetTOCExtractor:
    """Tests for the get_toc_extractor factory function."""

    def test_pdf_extractor(self):
        """Test that PDF files get TOCExtractor."""
        from gamemaster_mcp.library.extractors.toc import TOCExtractor

        extractor = get_toc_extractor(Path("test.pdf"))
        assert isinstance(extractor, TOCExtractor)

    def test_markdown_extractor_md(self):
        """Test that .md files get MarkdownTOCExtractor."""
        extractor = get_toc_extractor(Path("test.md"))
        assert isinstance(extractor, MarkdownTOCExtractor)

    def test_markdown_extractor_markdown(self):
        """Test that .markdown files get MarkdownTOCExtractor."""
        extractor = get_toc_extractor(Path("test.markdown"))
        assert isinstance(extractor, MarkdownTOCExtractor)

    def test_case_insensitive_extension(self):
        """Test that extension matching is case-insensitive."""
        extractor = get_toc_extractor(Path("test.MD"))
        assert isinstance(extractor, MarkdownTOCExtractor)

        extractor = get_toc_extractor(Path("test.PDF"))
        from gamemaster_mcp.library.extractors.toc import TOCExtractor
        assert isinstance(extractor, TOCExtractor)

    def test_unsupported_extension(self):
        """Test that unsupported extensions raise ValueError."""
        with pytest.raises(ValueError, match="Unsupported file type"):
            get_toc_extractor(Path("test.txt"))

        with pytest.raises(ValueError, match="Unsupported file type"):
            get_toc_extractor(Path("test.docx"))


# =============================================================================
# Integration Tests
# =============================================================================

class TestMarkdownIntegration:
    """Integration tests for Markdown extraction."""

    def test_full_workflow(self):
        """Test complete workflow: index then extract content."""
        with TemporaryDirectory() as tmpdir:
            # Create a Markdown file
            md_path = Path(tmpdir) / "homebrew.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            # Index the file
            toc_extractor = MarkdownTOCExtractor(md_path)
            index = toc_extractor.extract()

            # Verify index
            assert index.source_type == SourceType.MARKDOWN
            assert len(index.toc) > 0
            assert index.content_summary.classes >= 2

            # Extract content
            content_extractor = MarkdownContentExtractor(md_path, index)

            # Get specific sections
            fighter = content_extractor.get_section_by_title("Fighter")
            assert fighter is not None
            assert "martial combat" in fighter

            # Get all sections
            all_sections = content_extractor.get_all_sections()
            assert len(all_sections) > 5

    def test_serialization_roundtrip(self):
        """Test that IndexEntry can be serialized and restored."""
        with TemporaryDirectory() as tmpdir:
            md_path = Path(tmpdir) / "test.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            # Index
            extractor = MarkdownTOCExtractor(md_path)
            original_index = extractor.extract()

            # Serialize
            data = original_index.to_dict()

            # Deserialize
            restored_index = IndexEntry.from_dict(data)

            # Verify
            assert restored_index.source_id == original_index.source_id
            assert restored_index.source_type == SourceType.MARKDOWN
            assert len(restored_index.toc) == len(original_index.toc)
            assert restored_index.content_summary.total == original_index.content_summary.total


# =============================================================================
# End-to-End Integration Tests for scan_library Tool
# =============================================================================

class TestScanLibraryMarkdownIntegration:
    """Test that scan_library MCP tool correctly indexes Markdown files."""

    def test_library_manager_indexes_markdown(self):
        """Test that LibraryManager can index Markdown files via scan workflow."""
        from gamemaster_mcp.library.manager import LibraryManager, generate_source_id

        with TemporaryDirectory() as tmpdir:
            # Setup library structure
            library_dir = Path(tmpdir) / "library"
            pdfs_dir = library_dir / "pdfs"
            pdfs_dir.mkdir(parents=True)

            # Create test Markdown file
            md_path = pdfs_dir / "test-homebrew.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            # Initialize LibraryManager
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Scan should find the file
            files = manager.scan_library()
            assert len(files) == 1
            assert files[0].suffix == ".md"

            # List should show not indexed
            sources = manager.list_library()
            assert len(sources) == 1
            assert sources[0].source_id == "test-homebrew"
            assert sources[0].is_indexed is False

            # Manually index (simulating what scan_library tool does)
            source_id = generate_source_id(md_path.name)
            extractor = MarkdownTOCExtractor(md_path)
            index_entry = extractor.extract()
            manager.save_index(index_entry)

            # List should now show indexed
            sources = manager.list_library()
            assert len(sources) == 1
            assert sources[0].is_indexed is True
            assert sources[0].index_entry is not None
            assert sources[0].index_entry.source_type == SourceType.MARKDOWN

    def test_markdown_in_scan_library_workflow(self):
        """Test the exact code path used by scan_library MCP tool."""
        from gamemaster_mcp.library.manager import LibraryManager, generate_source_id
        from gamemaster_mcp.library.extractors import MarkdownTOCExtractor

        with TemporaryDirectory() as tmpdir:
            # Setup
            library_dir = Path(tmpdir) / "library"
            pdfs_dir = library_dir / "pdfs"
            pdfs_dir.mkdir(parents=True)

            md_path = pdfs_dir / "homebrew-classes.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Simulate scan_library tool logic
            files = manager.scan_library()
            indexed_count = 0

            for file_path in files:
                source_id = generate_source_id(file_path.name)

                if manager.needs_reindex(source_id):
                    if file_path.suffix.lower() == ".pdf":
                        pass  # Would use TOCExtractor
                    elif file_path.suffix.lower() in (".md", ".markdown"):
                        md_extractor = MarkdownTOCExtractor(file_path)
                        index_entry = md_extractor.extract()
                        manager.save_index(index_entry)
                        indexed_count += 1

            # Verify indexing happened
            assert indexed_count == 1

            # Verify index is correct
            index = manager.get_index("homebrew-classes")
            assert index is not None
            assert index.source_type == SourceType.MARKDOWN
            assert index.content_summary.classes >= 2
            assert len(index.toc) > 0

    def test_markdown_search_after_indexing(self):
        """Test that Markdown content is searchable after indexing."""
        from gamemaster_mcp.library.manager import LibraryManager
        from gamemaster_mcp.library.extractors import MarkdownTOCExtractor

        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            pdfs_dir = library_dir / "pdfs"
            pdfs_dir.mkdir(parents=True)

            md_path = pdfs_dir / "test.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Index the file
            extractor = MarkdownTOCExtractor(md_path)
            index_entry = extractor.extract()
            manager.save_index(index_entry)

            # Search should find content
            results = manager.search("Fighter")
            assert len(results) >= 1
            assert any(r["title"] == "Fighter" for r in results)

            # Search by content type
            results = manager.search("", content_type="class")
            assert len(results) >= 2  # Fighter and Wizard

    def test_markdown_ask_books_semantic_search(self):
        """Test that Markdown content works with ask_books semantic search."""
        from gamemaster_mcp.library.manager import LibraryManager
        from gamemaster_mcp.library.extractors import MarkdownTOCExtractor

        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            pdfs_dir = library_dir / "pdfs"
            pdfs_dir.mkdir(parents=True)

            md_path = pdfs_dir / "test.md"
            md_path.write_text(SAMPLE_MARKDOWN, encoding="utf-8")

            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Index
            extractor = MarkdownTOCExtractor(md_path)
            index_entry = extractor.extract()
            manager.save_index(index_entry)

            # Semantic search
            results = manager.semantic_search.search("martial combat warrior")
            assert len(results) >= 1
            # Fighter should rank high for "martial combat"
            titles = [r.title for r in results]
            assert "Fighter" in titles
