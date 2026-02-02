"""
Unit tests for the PDF Library System.

Tests the LibraryManager class and associated data models.
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from gamemaster_mcp.library.manager import (
    LibraryManager,
    generate_source_id,
    compute_file_hash,
)
from gamemaster_mcp.library.models import (
    LibrarySource,
    IndexEntry,
    TOCEntry,
    ContentSummary,
    SourceType,
    ContentType,
)


class TestGenerateSourceId:
    """Tests for the generate_source_id function."""

    def test_basic_filename(self):
        """Test basic filename conversion."""
        assert generate_source_id("Tome_of_Heroes.pdf") == "tome-of-heroes"

    def test_spaces_and_underscores(self):
        """Test that spaces and underscores become hyphens."""
        assert generate_source_id("My Cool Book.pdf") == "my-cool-book"
        assert generate_source_id("My_Cool_Book.pdf") == "my-cool-book"

    def test_mixed_case(self):
        """Test that output is lowercase."""
        assert generate_source_id("PHB.pdf") == "phb"
        assert generate_source_id("DnD_5e_SRD.pdf") == "dnd-5e-srd"

    def test_consecutive_separators(self):
        """Test that consecutive hyphens are collapsed."""
        assert generate_source_id("My__Cool__Book.pdf") == "my-cool-book"
        assert generate_source_id("My  Cool  Book.pdf") == "my-cool-book"

    def test_markdown_extension(self):
        """Test markdown file extension removal."""
        assert generate_source_id("homebrew.md") == "homebrew"
        assert generate_source_id("Custom Rules.markdown") == "custom-rules"


class TestComputeFileHash:
    """Tests for the compute_file_hash function."""

    def test_hash_consistency(self):
        """Test that same content produces same hash."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Hello, World!")

            hash1 = compute_file_hash(test_file)
            hash2 = compute_file_hash(test_file)

            assert hash1 == hash2

    def test_different_content_different_hash(self):
        """Test that different content produces different hash."""
        with TemporaryDirectory() as tmpdir:
            file1 = Path(tmpdir) / "file1.txt"
            file2 = Path(tmpdir) / "file2.txt"

            file1.write_text("Content A")
            file2.write_text("Content B")

            assert compute_file_hash(file1) != compute_file_hash(file2)

    def test_hash_format(self):
        """Test that hash is a valid SHA-256 hex string."""
        with TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.txt"
            test_file.write_text("Test content")

            file_hash = compute_file_hash(test_file)

            assert len(file_hash) == 64  # SHA-256 produces 64 hex chars
            assert all(c in "0123456789abcdef" for c in file_hash)


class TestTOCEntry:
    """Tests for the TOCEntry dataclass."""

    def test_basic_creation(self):
        """Test basic TOCEntry creation."""
        entry = TOCEntry(title="Classes", page=10)

        assert entry.title == "Classes"
        assert entry.page == 10
        assert entry.content_type == ContentType.UNKNOWN
        assert entry.children == []
        assert entry.end_page is None

    def test_with_content_type(self):
        """Test TOCEntry with specific content type."""
        entry = TOCEntry(
            title="Fighter",
            page=25,
            content_type=ContentType.CLASS,
            end_page=40,
        )

        assert entry.content_type == ContentType.CLASS
        assert entry.end_page == 40

    def test_with_children(self):
        """Test TOCEntry with nested children."""
        child = TOCEntry(title="Fighter", page=25, content_type=ContentType.CLASS)
        parent = TOCEntry(title="Classes", page=20, children=[child])

        assert len(parent.children) == 1
        assert parent.children[0].title == "Fighter"

    def test_to_dict(self):
        """Test serialization to dictionary."""
        entry = TOCEntry(
            title="Fighter",
            page=25,
            content_type=ContentType.CLASS,
            end_page=40,
        )

        data = entry.to_dict()

        assert data["title"] == "Fighter"
        assert data["page"] == 25
        assert data["type"] == "class"
        assert data["end_page"] == 40

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {
            "title": "Fighter",
            "page": 25,
            "type": "class",
            "end_page": 40,
        }

        entry = TOCEntry.from_dict(data)

        assert entry.title == "Fighter"
        assert entry.page == 25
        assert entry.content_type == ContentType.CLASS
        assert entry.end_page == 40

    def test_roundtrip(self):
        """Test that to_dict and from_dict are inverse operations."""
        original = TOCEntry(
            title="Chapter 1",
            page=1,
            children=[
                TOCEntry(title="Section A", page=5, content_type=ContentType.CLASS),
                TOCEntry(title="Section B", page=10, content_type=ContentType.RACE),
            ],
        )

        data = original.to_dict()
        restored = TOCEntry.from_dict(data)

        assert restored.title == original.title
        assert len(restored.children) == len(original.children)
        assert restored.children[0].content_type == ContentType.CLASS


class TestContentSummary:
    """Tests for the ContentSummary dataclass."""

    def test_default_values(self):
        """Test that all counts default to zero."""
        summary = ContentSummary()

        assert summary.classes == 0
        assert summary.races == 0
        assert summary.spells == 0
        assert summary.total == 0

    def test_total_calculation(self):
        """Test that total property correctly sums all counts."""
        summary = ContentSummary(
            classes=5,
            races=10,
            spells=100,
            monsters=50,
        )

        assert summary.total == 165

    def test_to_dict(self):
        """Test serialization to dictionary."""
        summary = ContentSummary(classes=5, spells=100)
        data = summary.to_dict()

        assert data["classes"] == 5
        assert data["spells"] == 100
        assert data["races"] == 0

    def test_from_dict(self):
        """Test deserialization from dictionary."""
        data = {"classes": 5, "spells": 100}
        summary = ContentSummary.from_dict(data)

        assert summary.classes == 5
        assert summary.spells == 100
        assert summary.races == 0  # Default value


class TestIndexEntry:
    """Tests for the IndexEntry dataclass."""

    def test_basic_creation(self):
        """Test basic IndexEntry creation."""
        entry = IndexEntry(
            source_id="tome-of-heroes",
            filename="Tome_of_Heroes.pdf",
            source_type=SourceType.PDF,
            indexed_at=datetime(2026, 1, 15, 12, 0, 0),
            file_hash="abc123",
            total_pages=350,
        )

        assert entry.source_id == "tome-of-heroes"
        assert entry.source_type == SourceType.PDF
        assert entry.total_pages == 350

    def test_to_dict_from_dict_roundtrip(self):
        """Test that to_dict and from_dict preserve data."""
        original = IndexEntry(
            source_id="test-source",
            filename="test.pdf",
            source_type=SourceType.PDF,
            indexed_at=datetime(2026, 1, 15, 12, 0, 0),
            file_hash="abc123",
            total_pages=100,
            toc=[TOCEntry(title="Chapter 1", page=1)],
            content_summary=ContentSummary(classes=5),
        )

        data = original.to_dict()
        restored = IndexEntry.from_dict(data)

        assert restored.source_id == original.source_id
        assert restored.source_type == original.source_type
        assert len(restored.toc) == 1
        assert restored.content_summary.classes == 5


class TestLibrarySource:
    """Tests for the LibrarySource dataclass."""

    def test_basic_creation(self):
        """Test basic LibrarySource creation."""
        source = LibrarySource(
            source_id="test-source",
            filename="test.pdf",
            source_type=SourceType.PDF,
            file_path=Path("/path/to/test.pdf"),
        )

        assert source.source_id == "test-source"
        assert source.is_indexed is False
        assert source.index_entry is None

    def test_to_dict(self):
        """Test serialization to dictionary."""
        source = LibrarySource(
            source_id="test-source",
            filename="test.pdf",
            source_type=SourceType.PDF,
            file_path=Path("/path/to/test.pdf"),
            file_size=1024,
        )

        data = source.to_dict()

        assert data["source_id"] == "test-source"
        assert data["is_indexed"] is False
        assert data["file_size"] == 1024


class TestLibraryManager:
    """Tests for the LibraryManager class."""

    def test_init_creates_instance(self):
        """Test that LibraryManager can be instantiated."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)

            assert manager.library_dir == library_dir
            assert manager.pdfs_dir == library_dir / "pdfs"
            assert manager.index_dir == library_dir / "index"
            assert manager.extracted_dir == library_dir / "extracted"

    def test_ensure_directories_creates_structure(self):
        """Test that ensure_directories creates all required directories."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)

            # Directories shouldn't exist yet
            assert not library_dir.exists()

            manager.ensure_directories()

            # Now all directories should exist
            assert library_dir.exists()
            assert manager.pdfs_dir.exists()
            assert manager.index_dir.exists()
            assert manager.extracted_dir.exists()

    def test_scan_library_empty(self):
        """Test scan_library with empty library."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            files = manager.scan_library()

            assert files == []

    def test_scan_library_finds_pdfs(self):
        """Test scan_library finds PDF files."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create test PDF files
            (manager.pdfs_dir / "book1.pdf").write_text("fake pdf")
            (manager.pdfs_dir / "book2.PDF").write_text("fake pdf")

            files = manager.scan_library()

            assert len(files) == 2
            filenames = [f.name for f in files]
            assert "book1.pdf" in filenames
            assert "book2.PDF" in filenames

    def test_scan_library_finds_markdown(self):
        """Test scan_library finds Markdown files."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create test Markdown files
            (manager.pdfs_dir / "rules.md").write_text("# Rules")
            (manager.pdfs_dir / "spells.markdown").write_text("# Spells")

            files = manager.scan_library()

            assert len(files) == 2

    def test_scan_library_ignores_other_files(self):
        """Test scan_library ignores non-PDF/Markdown files."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create various files
            (manager.pdfs_dir / "book.pdf").write_text("fake pdf")
            (manager.pdfs_dir / "notes.txt").write_text("notes")
            (manager.pdfs_dir / "image.png").write_bytes(b"fake image")

            files = manager.scan_library()

            assert len(files) == 1
            assert files[0].name == "book.pdf"

    def test_list_library_empty(self):
        """Test list_library with empty library."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            sources = manager.list_library()

            assert sources == []

    def test_list_library_with_files(self):
        """Test list_library returns LibrarySource objects."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create a test file
            test_file = manager.pdfs_dir / "test_book.pdf"
            test_file.write_text("fake pdf content")

            sources = manager.list_library()

            assert len(sources) == 1
            source = sources[0]
            assert source.source_id == "test-book"
            assert source.filename == "test_book.pdf"
            assert source.source_type == SourceType.PDF
            assert source.is_indexed is False
            assert source.file_size > 0

    def test_get_source_found(self):
        """Test get_source returns source when found."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create a test file
            (manager.pdfs_dir / "my_book.pdf").write_text("content")

            source = manager.get_source("my-book")

            assert source is not None
            assert source.source_id == "my-book"

    def test_get_source_not_found(self):
        """Test get_source returns None when not found."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            source = manager.get_source("nonexistent")

            assert source is None

    def test_save_and_load_index(self):
        """Test saving and loading index entries."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create an index entry
            index_entry = IndexEntry(
                source_id="test-source",
                filename="test.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash="abc123",
                total_pages=100,
            )

            # Save it
            manager.save_index(index_entry)

            # Load it back
            loaded = manager.get_index("test-source")

            assert loaded is not None
            assert loaded.source_id == "test-source"
            assert loaded.file_hash == "abc123"

    def test_needs_reindex_no_index(self):
        """Test needs_reindex returns True when no index exists."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create a file without index
            (manager.pdfs_dir / "book.pdf").write_text("content")

            assert manager.needs_reindex("book") is True

    def test_needs_reindex_hash_changed(self):
        """Test needs_reindex returns True when file hash changes."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            # Create a file
            test_file = manager.pdfs_dir / "book.pdf"
            test_file.write_text("original content")

            # Create index with original hash
            original_hash = compute_file_hash(test_file)
            index_entry = IndexEntry(
                source_id="book",
                filename="book.pdf",
                source_type=SourceType.PDF,
                indexed_at=datetime.now(),
                file_hash=original_hash,
            )
            manager.save_index(index_entry)

            # Verify it doesn't need reindex
            assert manager.needs_reindex("book") is False

            # Modify the file
            test_file.write_text("modified content")

            # Now it should need reindex
            assert manager.needs_reindex("book") is True

    def test_needs_reindex_nonexistent_source(self):
        """Test needs_reindex returns False for nonexistent source."""
        with TemporaryDirectory() as tmpdir:
            library_dir = Path(tmpdir) / "library"
            manager = LibraryManager(library_dir)
            manager.ensure_directories()

            assert manager.needs_reindex("nonexistent") is False
