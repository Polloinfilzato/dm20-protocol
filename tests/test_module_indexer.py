"""
Tests for module content chunking and ChromaDB indexing.

Tests the ModuleIndexer class including text chunking with overlap,
metadata attachment, special content detection (boxed text, stat blocks),
re-indexing detection, and full module indexing workflow.

VectorStoreManager and PDF access are mocked to keep tests fast and
independent of external resources.
"""

import hashlib
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dm20_protocol.claudmaster.module_indexer import (
    ChunkConfig,
    IndexingResult,
    ModuleIndexer,
    _is_boxed_text,
    _is_stat_block,
    extract_text_from_pdf,
)
from dm20_protocol.claudmaster.models.module import (
    ContentType,
    ModuleElement,
    ModuleStructure,
    NPCReference,
    LocationReference,
)
from dm20_protocol.claudmaster.vector_store import (
    CollectionNotFoundError,
    VectorStoreManager,
)


# ---------------------------------------------------------------------------
# Helpers and fixtures
# ---------------------------------------------------------------------------


def _make_module_structure(
    module_id: str = "test-module",
    title: str = "Test Module",
    chapters: list[ModuleElement] | None = None,
    npcs: list[NPCReference] | None = None,
    locations: list[LocationReference] | None = None,
) -> ModuleStructure:
    """Create a minimal ModuleStructure for testing."""
    return ModuleStructure(
        module_id=module_id,
        title=title,
        source_file="test-module.pdf",
        chapters=chapters or [],
        npcs=npcs or [],
        locations=locations or [],
    )


def _make_mock_store() -> MagicMock:
    """Create a mocked VectorStoreManager."""
    store = MagicMock(spec=VectorStoreManager)
    store.list_collections.return_value = []
    store._collection_name.side_effect = lambda mid: f"mod_{mid}"
    store._get_embedding_function.return_value = MagicMock()
    return store


def _sample_text(length: int = 600) -> str:
    """Generate sample adventure text of approximately *length* characters."""
    paragraph = (
        "The ancient stone corridor stretches into darkness ahead. "
        "Flickering torchlight reveals worn carvings on the walls "
        "depicting scenes of forgotten battles. A faint smell of "
        "decay hangs in the air."
    )
    # Repeat to reach desired length
    parts = []
    current = 0
    while current < length:
        parts.append(paragraph)
        current += len(paragraph) + 2  # +2 for "\n\n"
    return "\n\n".join(parts)


STAT_BLOCK_TEXT = """
Goblin Boss
Small humanoid, neutral evil

Armor Class 17 (chain shirt, shield)
Hit Points 21 (6d6)
Speed 30 ft.

STR 10 (+0) DEX 14 (+2) CON 10 (+0) INT 10 (+0) WIS 8 (-1) CHA 10 (+0)

Senses darkvision 60 ft., passive Perception 9
Languages Common, Goblin
Challenge 1 (200 XP)
"""

BOXED_TEXT = """
Read the following aloud:

You step through the heavy oak doors into a vast chamber.
The ceiling soars fifty feet overhead, supported by massive
stone pillars. At the far end, a figure sits upon a throne
of bones.
"""


@pytest.fixture
def mock_store() -> MagicMock:
    """Mocked VectorStoreManager."""
    return _make_mock_store()


@pytest.fixture
def default_config() -> ChunkConfig:
    """Default ChunkConfig."""
    return ChunkConfig()


@pytest.fixture
def indexer(mock_store: MagicMock) -> ModuleIndexer:
    """ModuleIndexer backed by a mocked store."""
    return ModuleIndexer(mock_store)


@pytest.fixture
def small_config() -> ChunkConfig:
    """Small chunk config for testing splitting behaviour."""
    return ChunkConfig(chunk_size=200, chunk_overlap=50, min_chunk_size=50)


@pytest.fixture
def small_indexer(mock_store: MagicMock, small_config: ChunkConfig) -> ModuleIndexer:
    """ModuleIndexer with small chunks."""
    return ModuleIndexer(mock_store, chunk_config=small_config)


# ---------------------------------------------------------------------------
# ChunkConfig tests
# ---------------------------------------------------------------------------


class TestChunkConfig:
    """Tests for ChunkConfig dataclass defaults and customization."""

    def test_default_values(self) -> None:
        cfg = ChunkConfig()
        assert cfg.chunk_size == 500
        assert cfg.chunk_overlap == 100
        assert cfg.min_chunk_size == 100
        assert cfg.respect_paragraphs is True
        assert cfg.respect_sections is True

    def test_custom_values(self) -> None:
        cfg = ChunkConfig(
            chunk_size=1000,
            chunk_overlap=200,
            min_chunk_size=50,
            respect_paragraphs=False,
            respect_sections=False,
        )
        assert cfg.chunk_size == 1000
        assert cfg.chunk_overlap == 200
        assert cfg.min_chunk_size == 50
        assert cfg.respect_paragraphs is False
        assert cfg.respect_sections is False


# ---------------------------------------------------------------------------
# IndexingResult tests
# ---------------------------------------------------------------------------


class TestIndexingResult:
    """Tests for IndexingResult dataclass."""

    def test_default_fields(self) -> None:
        result = IndexingResult(
            module_id="test",
            chunks_created=10,
            chapters_indexed=3,
            npcs_indexed=2,
            locations_indexed=5,
            indexing_time_seconds=1.5,
        )
        assert result.module_id == "test"
        assert result.chunks_created == 10
        assert result.chapters_indexed == 3
        assert result.npcs_indexed == 2
        assert result.locations_indexed == 5
        assert result.indexing_time_seconds == 1.5
        assert result.skipped is False
        assert result.errors == []

    def test_errors_mutable_default(self) -> None:
        """Ensure errors default is a fresh list per instance."""
        r1 = IndexingResult("a", 0, 0, 0, 0, 0.0)
        r2 = IndexingResult("b", 0, 0, 0, 0, 0.0)
        r1.errors.append("something")
        assert r2.errors == []


# ---------------------------------------------------------------------------
# Special content detection
# ---------------------------------------------------------------------------


class TestSpecialContentDetection:
    """Tests for boxed text and stat block detection."""

    def test_is_stat_block_positive(self) -> None:
        assert _is_stat_block(STAT_BLOCK_TEXT) is True

    def test_is_stat_block_negative(self) -> None:
        assert _is_stat_block("The goblin runs away screaming.") is False

    def test_is_stat_block_partial(self) -> None:
        """Even a partial stat block header should be detected."""
        text = "Armor Class 15\nHit Points 30\nSpeed 30 ft."
        assert _is_stat_block(text) is True

    def test_is_boxed_text_positive(self) -> None:
        assert _is_boxed_text(BOXED_TEXT) is True

    def test_is_boxed_text_with_read_aloud(self) -> None:
        text = "Read aloud: The room is dark and cold."
        assert _is_boxed_text(text) is True

    def test_is_boxed_text_negative(self) -> None:
        assert _is_boxed_text("The party enters the dungeon.") is False

    def test_is_boxed_text_quoted(self) -> None:
        text = '"You hear a distant rumbling as the walls begin to shake."'
        assert _is_boxed_text(text) is True


# ---------------------------------------------------------------------------
# chunk_text tests
# ---------------------------------------------------------------------------


class TestChunkText:
    """Tests for the chunk_text method."""

    def _basic_context(self) -> dict[str, Any]:
        return {
            "module_id": "test-mod",
            "chapter": "Chapter 1",
            "section": "Section A",
            "content_type": "narrative",
            "page_start": 1,
            "page_end": 3,
            "npc_names": ["Strahd"],
            "location_names": ["Castle Ravenloft"],
        }

    def test_empty_text_returns_empty(self, indexer: ModuleIndexer) -> None:
        result = indexer.chunk_text("", self._basic_context())
        assert result == []

    def test_whitespace_only_returns_empty(self, indexer: ModuleIndexer) -> None:
        result = indexer.chunk_text("   \n\n   ", self._basic_context())
        assert result == []

    def test_short_text_single_chunk(self, indexer: ModuleIndexer) -> None:
        text = "A short paragraph about a goblin."
        result = indexer.chunk_text(text, self._basic_context())
        assert len(result) == 1
        assert result[0][0] == text

    def test_metadata_attached_to_chunks(self, indexer: ModuleIndexer) -> None:
        text = "The dark tower looms in the distance."
        result = indexer.chunk_text(text, self._basic_context())
        assert len(result) == 1
        _, meta = result[0]
        assert meta["module_id"] == "test-mod"
        assert meta["chapter"] == "Chapter 1"
        assert meta["section"] == "Section A"
        assert meta["content_type"] == "narrative"
        assert meta["page_start"] == 1
        assert meta["page_end"] == 3
        assert meta["chunk_index"] == 0
        assert meta["total_chunks_in_section"] == 1
        assert meta["is_boxed_text"] is False
        assert meta["is_stat_block"] is False

    def test_multiple_chunks_created(self, small_indexer: ModuleIndexer) -> None:
        """Long text should be split into multiple chunks."""
        text = _sample_text(800)
        result = small_indexer.chunk_text(text, self._basic_context())
        assert len(result) > 1

    def test_chunk_index_sequential(self, small_indexer: ModuleIndexer) -> None:
        text = _sample_text(800)
        result = small_indexer.chunk_text(text, self._basic_context())
        for i, (_, meta) in enumerate(result):
            assert meta["chunk_index"] == i

    def test_total_chunks_in_section_consistent(self, small_indexer: ModuleIndexer) -> None:
        text = _sample_text(800)
        result = small_indexer.chunk_text(text, self._basic_context())
        total = len(result)
        for _, meta in result:
            assert meta["total_chunks_in_section"] == total

    def test_overlap_present_in_later_chunks(self) -> None:
        """Second chunk should start with overlap from the first."""
        config = ChunkConfig(chunk_size=100, chunk_overlap=30, min_chunk_size=20)
        store = _make_mock_store()
        indexer = ModuleIndexer(store, chunk_config=config)

        # Create two paragraphs that together exceed chunk_size
        para1 = "A" * 80
        para2 = "B" * 80
        text = f"{para1}\n\n{para2}"
        ctx = {
            "module_id": "m", "chapter": "c", "section": "s",
            "content_type": "narrative", "page_start": 1, "page_end": 1,
            "npc_names": [], "location_names": [],
        }
        result = indexer.chunk_text(text, ctx)
        assert len(result) >= 2
        # The second chunk should contain some characters from the first
        # because of overlap
        second_text = result[1][0]
        assert len(second_text) > len(para2)

    def test_npc_cross_reference(self, indexer: ModuleIndexer) -> None:
        """NPCs mentioned in text should appear in metadata."""
        text = "Count Strahd surveyed the courtyard of Castle Ravenloft."
        ctx = self._basic_context()
        ctx["npc_names"] = ["Strahd"]
        ctx["location_names"] = ["Castle Ravenloft"]
        result = indexer.chunk_text(text, ctx)
        _, meta = result[0]
        assert "Strahd" in meta["npcs_referenced"]
        assert "Castle Ravenloft" in meta["locations_referenced"]

    def test_no_npc_cross_reference_when_absent(self, indexer: ModuleIndexer) -> None:
        text = "The empty room holds nothing of interest."
        ctx = self._basic_context()
        ctx["npc_names"] = ["Strahd"]
        ctx["location_names"] = ["Castle Ravenloft"]
        result = indexer.chunk_text(text, ctx)
        _, meta = result[0]
        assert meta["npcs_referenced"] == ""
        assert meta["locations_referenced"] == ""

    def test_stat_block_detection_in_chunk(self, indexer: ModuleIndexer) -> None:
        result = indexer.chunk_text(STAT_BLOCK_TEXT, self._basic_context())
        assert len(result) >= 1
        _, meta = result[0]
        assert meta["is_stat_block"] is True
        # Stat blocks override content_type to "npc"
        assert meta["content_type"] == "npc"

    def test_boxed_text_detection_in_chunk(self, indexer: ModuleIndexer) -> None:
        result = indexer.chunk_text(BOXED_TEXT, self._basic_context())
        assert len(result) >= 1
        _, meta = result[0]
        assert meta["is_boxed_text"] is True

    def test_respect_paragraphs_false(self) -> None:
        """With respect_paragraphs=False, split on newlines instead."""
        config = ChunkConfig(
            chunk_size=500, chunk_overlap=0,
            min_chunk_size=10, respect_paragraphs=False,
        )
        store = _make_mock_store()
        indexer = ModuleIndexer(store, chunk_config=config)

        text = "Line one.\nLine two.\nLine three."
        ctx = {
            "module_id": "m", "chapter": "c", "section": "s",
            "content_type": "narrative", "page_start": 1, "page_end": 1,
            "npc_names": [], "location_names": [],
        }
        result = indexer.chunk_text(text, ctx)
        # All lines should end up in a single chunk (short text)
        assert len(result) == 1

    def test_min_chunk_merge(self) -> None:
        """A trailing short chunk should be merged into the previous one."""
        config = ChunkConfig(chunk_size=100, chunk_overlap=0, min_chunk_size=50)
        store = _make_mock_store()
        indexer = ModuleIndexer(store, chunk_config=config)

        para1 = "A" * 90
        para2 = "B" * 20  # Below min_chunk_size
        text = f"{para1}\n\n{para2}"
        ctx = {
            "module_id": "m", "chapter": "c", "section": "s",
            "content_type": "narrative", "page_start": 1, "page_end": 1,
            "npc_names": [], "location_names": [],
        }
        result = indexer.chunk_text(text, ctx)
        # The short trailing chunk should be merged
        assert len(result) == 1
        assert "B" * 20 in result[0][0]

    def test_force_split_long_paragraph(self) -> None:
        """A single paragraph exceeding chunk_size is force-split."""
        config = ChunkConfig(chunk_size=100, chunk_overlap=0, min_chunk_size=10)
        store = _make_mock_store()
        indexer = ModuleIndexer(store, chunk_config=config)

        long_text = "word " * 50  # ~250 chars
        ctx = {
            "module_id": "m", "chapter": "c", "section": "s",
            "content_type": "narrative", "page_start": 1, "page_end": 1,
            "npc_names": [], "location_names": [],
        }
        result = indexer.chunk_text(long_text.strip(), ctx)
        assert len(result) >= 2
        # No chunk should exceed chunk_size significantly
        # (overlap may add a bit)
        for chunk_text, _ in result:
            assert len(chunk_text) <= 200  # generous bound accounting for overlap


# ---------------------------------------------------------------------------
# is_indexed / get_index_metadata / delete_index
# ---------------------------------------------------------------------------


class TestIndexManagement:
    """Tests for index lifecycle methods."""

    def test_is_indexed_false_initially(self, indexer: ModuleIndexer, mock_store: MagicMock) -> None:
        mock_store.list_collections.return_value = []
        assert indexer.is_indexed("some-module") is False

    def test_is_indexed_true(self, indexer: ModuleIndexer, mock_store: MagicMock) -> None:
        mock_store.list_collections.return_value = ["some-module"]
        assert indexer.is_indexed("some-module") is True

    def test_get_index_metadata_returns_none_when_not_indexed(
        self, indexer: ModuleIndexer, mock_store: MagicMock,
    ) -> None:
        mock_store.list_collections.return_value = []
        assert indexer.get_index_metadata("absent") is None

    def test_get_index_metadata_returns_dict(
        self, indexer: ModuleIndexer, mock_store: MagicMock,
    ) -> None:
        mock_store.list_collections.return_value = ["my-mod"]
        mock_store._collection_name.return_value = "mod_my-mod"
        col = MagicMock()
        col.metadata = {"source_hash": "abc123", "indexed_at": "2026-02-05T00:00:00Z"}
        mock_store._client = MagicMock()
        mock_store._client.get_collection.return_value = col
        mock_store._get_embedding_function.return_value = MagicMock()
        meta = indexer.get_index_metadata("my-mod")
        assert meta is not None
        assert meta["source_hash"] == "abc123"

    def test_delete_index_calls_store(self, indexer: ModuleIndexer, mock_store: MagicMock) -> None:
        indexer.delete_index("mod-to-delete")
        mock_store.delete_collection.assert_called_once_with("mod-to-delete")

    def test_delete_index_propagates_error(
        self, indexer: ModuleIndexer, mock_store: MagicMock,
    ) -> None:
        mock_store.delete_collection.side_effect = CollectionNotFoundError("not found")
        with pytest.raises(CollectionNotFoundError):
            indexer.delete_index("ghost")


# ---------------------------------------------------------------------------
# index_module tests
# ---------------------------------------------------------------------------


class TestIndexModule:
    """Tests for the full index_module workflow."""

    @pytest.fixture
    def sample_structure(self) -> ModuleStructure:
        return _make_module_structure(
            module_id="curse-of-strahd",
            title="Curse of Strahd",
            chapters=[
                ModuleElement(
                    name="Chapter 1: Into the Mists",
                    content_type=ContentType.CHAPTER,
                    page_start=1,
                    page_end=10,
                    children=["Death House"],
                ),
                ModuleElement(
                    name="Death House",
                    content_type=ContentType.SECTION,
                    page_start=3,
                    page_end=8,
                    parent="Chapter 1: Into the Mists",
                ),
            ],
            npcs=[
                NPCReference(name="Strahd", chapter="Chapter 1", page=5),
            ],
            locations=[
                LocationReference(name="Castle Ravenloft", chapter="Chapter 1", page=3),
            ],
        )

    @pytest.fixture
    def tmp_pdf(self, tmp_path: Path) -> Path:
        """Create a dummy PDF-like file for hashing."""
        pdf = tmp_path / "curse-of-strahd.pdf"
        pdf.write_bytes(b"fake pdf content for hashing")
        return pdf

    def test_index_module_basic(
        self,
        mock_store: MagicMock,
        sample_structure: ModuleStructure,
        tmp_pdf: Path,
    ) -> None:
        """Basic indexing creates collection and adds documents."""
        indexer = ModuleIndexer(mock_store)

        with patch(
            "dm20_protocol.claudmaster.module_indexer.extract_text_from_pdf",
            return_value="The mists close in around the party. Strahd watches from Castle Ravenloft.",
        ):
            result = indexer.index_module(sample_structure, str(tmp_pdf))

        assert result.module_id == "curse-of-strahd"
        assert result.chunks_created > 0
        assert result.chapters_indexed >= 1
        assert result.skipped is False
        assert result.errors == []

        # Verify store interactions
        mock_store.create_collection.assert_called_once()
        mock_store.add_documents.assert_called_once()

    def test_index_module_skips_unchanged(
        self,
        mock_store: MagicMock,
        sample_structure: ModuleStructure,
        tmp_pdf: Path,
    ) -> None:
        """Already indexed and unchanged module should be skipped."""
        # Simulate module is already indexed with matching hash
        file_hash = hashlib.sha256(b"fake pdf content for hashing").hexdigest()
        mock_store.list_collections.return_value = ["curse-of-strahd"]
        mock_store._collection_name.return_value = "mod_curse-of-strahd"
        col = MagicMock()
        col.metadata = {"source_hash": file_hash}
        mock_store._client = MagicMock()
        mock_store._client.get_collection.return_value = col
        mock_store._get_embedding_function.return_value = MagicMock()

        indexer = ModuleIndexer(mock_store)
        result = indexer.index_module(sample_structure, str(tmp_pdf))

        assert result.skipped is True
        assert result.chunks_created == 0
        mock_store.add_documents.assert_not_called()

    def test_index_module_force_reindex(
        self,
        mock_store: MagicMock,
        sample_structure: ModuleStructure,
        tmp_pdf: Path,
    ) -> None:
        """force_reindex=True should re-index even when unchanged."""
        mock_store.list_collections.return_value = ["curse-of-strahd"]

        indexer = ModuleIndexer(mock_store)

        with patch(
            "dm20_protocol.claudmaster.module_indexer.extract_text_from_pdf",
            return_value="Some adventure text about Strahd.",
        ):
            result = indexer.index_module(
                sample_structure, str(tmp_pdf), force_reindex=True,
            )

        assert result.skipped is False
        assert result.chunks_created > 0
        # Old collection should have been deleted
        mock_store.delete_collection.assert_called_once_with("curse-of-strahd")
        mock_store.create_collection.assert_called_once()

    def test_index_module_handles_extraction_error(
        self,
        mock_store: MagicMock,
        sample_structure: ModuleStructure,
        tmp_pdf: Path,
    ) -> None:
        """Errors during text extraction should be recorded but not fatal."""
        indexer = ModuleIndexer(mock_store)

        with patch(
            "dm20_protocol.claudmaster.module_indexer.extract_text_from_pdf",
            side_effect=RuntimeError("PDF read failure"),
        ):
            result = indexer.index_module(sample_structure, str(tmp_pdf))

        # Should still return a result with errors
        assert len(result.errors) > 0
        assert "PDF read failure" in result.errors[0]

    def test_index_module_empty_text_skipped(
        self,
        mock_store: MagicMock,
        sample_structure: ModuleStructure,
        tmp_pdf: Path,
    ) -> None:
        """Elements with no extractable text should be skipped gracefully."""
        indexer = ModuleIndexer(mock_store)

        with patch(
            "dm20_protocol.claudmaster.module_indexer.extract_text_from_pdf",
            return_value="",
        ):
            result = indexer.index_module(sample_structure, str(tmp_pdf))

        assert result.chunks_created == 0
        assert result.errors == []

    def test_index_module_npc_and_location_counts(
        self,
        mock_store: MagicMock,
        sample_structure: ModuleStructure,
        tmp_pdf: Path,
    ) -> None:
        """NPC and location cross-reference counts should be populated."""
        indexer = ModuleIndexer(mock_store)

        with patch(
            "dm20_protocol.claudmaster.module_indexer.extract_text_from_pdf",
            return_value="Strahd lurks in Castle Ravenloft, watching.",
        ):
            result = indexer.index_module(sample_structure, str(tmp_pdf))

        assert result.npcs_indexed >= 1
        assert result.locations_indexed >= 1

    def test_index_module_with_no_chapters(
        self,
        mock_store: MagicMock,
        tmp_pdf: Path,
    ) -> None:
        """Module with no chapters should produce zero chunks."""
        empty_structure = _make_module_structure(chapters=[])
        indexer = ModuleIndexer(mock_store)

        result = indexer.index_module(empty_structure, str(tmp_pdf))

        assert result.chunks_created == 0
        assert result.chapters_indexed == 0


# ---------------------------------------------------------------------------
# Hash computation
# ---------------------------------------------------------------------------


class TestFileHash:
    """Tests for the internal file hash helper."""

    def test_hash_deterministic(self, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        f.write_bytes(b"hello world")
        h1 = ModuleIndexer._compute_file_hash(f)
        h2 = ModuleIndexer._compute_file_hash(f)
        assert h1 == h2

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        f.write_bytes(b"version 1")
        h1 = ModuleIndexer._compute_file_hash(f)
        f.write_bytes(b"version 2")
        h2 = ModuleIndexer._compute_file_hash(f)
        assert h1 != h2

    def test_hash_matches_stdlib(self, tmp_path: Path) -> None:
        f = tmp_path / "test.pdf"
        content = b"some content"
        f.write_bytes(content)
        expected = hashlib.sha256(content).hexdigest()
        assert ModuleIndexer._compute_file_hash(f) == expected


# ---------------------------------------------------------------------------
# Force-split helper
# ---------------------------------------------------------------------------


class TestForceSplit:
    """Tests for the _force_split static method."""

    def test_short_text_not_split(self) -> None:
        result = ModuleIndexer._force_split("hello", 100)
        assert result == ["hello"]

    def test_long_text_split(self) -> None:
        text = "word " * 100  # ~500 chars
        result = ModuleIndexer._force_split(text.strip(), 100)
        assert len(result) >= 4
        # Verify all chunks are within bounds
        for chunk in result:
            assert len(chunk) <= 100

    def test_no_spaces(self) -> None:
        """Text without spaces is split at exact boundary."""
        text = "A" * 250
        result = ModuleIndexer._force_split(text, 100)
        assert len(result) == 3
        assert result[0] == "A" * 100
        assert result[1] == "A" * 100
        assert result[2] == "A" * 50


# ---------------------------------------------------------------------------
# extract_text_from_pdf (mocked fitz)
# ---------------------------------------------------------------------------


class TestExtractTextFromPdf:
    """Tests for extract_text_from_pdf with mocked PyMuPDF."""

    @patch("fitz.open")
    def test_basic_extraction(self, mock_fitz_open: MagicMock) -> None:
        """Should extract text from the correct page range."""
        mock_page1 = MagicMock()
        mock_page1.get_text.return_value = "Page 1 text"
        mock_page2 = MagicMock()
        mock_page2.get_text.return_value = "Page 2 text"

        pages = [mock_page1, mock_page2, MagicMock(), MagicMock(), MagicMock()]
        mock_doc = MagicMock()
        mock_doc.page_count = 5
        mock_doc.__getitem__ = MagicMock(side_effect=lambda idx: pages[idx])
        mock_fitz_open.return_value = mock_doc

        result = extract_text_from_pdf("/fake/path.pdf", 1, 2)
        assert "Page 1 text" in result
        assert "Page 2 text" in result

    @patch("fitz.open")
    def test_single_page(self, mock_fitz_open: MagicMock) -> None:
        mock_page = MagicMock()
        mock_page.get_text.return_value = "Solo page"

        mock_doc = MagicMock()
        mock_doc.page_count = 10
        mock_doc.__getitem__ = MagicMock(return_value=mock_page)
        mock_fitz_open.return_value = mock_doc

        result = extract_text_from_pdf("/fake/path.pdf", 5, None)
        assert "Solo page" in result

    @patch("fitz.open")
    def test_open_failure(self, mock_fitz_open: MagicMock) -> None:
        mock_fitz_open.side_effect = RuntimeError("Cannot open")
        result = extract_text_from_pdf("/bad/path.pdf", 1, 5)
        assert result == ""


# ---------------------------------------------------------------------------
# Integration-style test (full pipeline, mocked I/O)
# ---------------------------------------------------------------------------


class TestFullPipeline:
    """End-to-end test of the indexing pipeline with mocked dependencies."""

    def test_round_trip(self, tmp_path: Path) -> None:
        """Index a module, verify chunks are created, check metadata."""
        store = _make_mock_store()

        structure = _make_module_structure(
            module_id="lost-mine",
            title="Lost Mine of Phandelver",
            chapters=[
                ModuleElement(
                    name="Part 1: Goblin Arrows",
                    content_type=ContentType.CHAPTER,
                    page_start=1,
                    page_end=15,
                ),
                ModuleElement(
                    name="Cragmaw Hideout",
                    content_type=ContentType.SECTION,
                    page_start=5,
                    page_end=10,
                    parent="Part 1: Goblin Arrows",
                ),
            ],
            npcs=[NPCReference(name="Sildar Hallwinter", chapter="Part 1", page=3)],
            locations=[LocationReference(name="Cragmaw Cave", chapter="Part 1", page=5)],
        )

        pdf_file = tmp_path / "lost-mine.pdf"
        pdf_file.write_bytes(b"fake PDF data")

        indexer = ModuleIndexer(store, chunk_config=ChunkConfig(chunk_size=300, chunk_overlap=50))

        long_text = (
            "The adventurers travel along the Triboar Trail toward Phandalin. "
            "Sildar Hallwinter has been captured by goblins and is held in "
            "the Cragmaw Cave. The party must rescue him before time runs out.\n\n"
            "Deep inside the cave, goblin sentries stand guard at every turn. "
            "The sounds of dripping water echo through the tunnels."
        )

        with patch(
            "dm20_protocol.claudmaster.module_indexer.extract_text_from_pdf",
            return_value=long_text,
        ):
            result = indexer.index_module(structure, str(pdf_file))

        assert result.module_id == "lost-mine"
        assert result.chunks_created > 0
        assert result.chapters_indexed >= 1
        assert result.skipped is False

        # Verify add_documents was called with correct structure
        call_args = store.add_documents.call_args
        docs = call_args[1]["documents"] if "documents" in call_args[1] else call_args[0][1]
        metas = call_args[1]["metadatas"] if "metadatas" in call_args[1] else call_args[0][2]
        ids = call_args[1]["ids"] if "ids" in call_args[1] else call_args[0][3]

        assert len(docs) == len(metas) == len(ids)
        assert all(isinstance(d, str) for d in docs)
        assert all(isinstance(m, dict) for m in metas)
        assert all(isinstance(i, str) for i in ids)

        # Verify metadata structure
        for meta in metas:
            assert "module_id" in meta
            assert "chapter" in meta
            assert "section" in meta
            assert "content_type" in meta
            assert "page_start" in meta
            assert "page_end" in meta
            assert "chunk_index" in meta
            assert "total_chunks_in_section" in meta
            assert "npcs_referenced" in meta
            assert "locations_referenced" in meta
            assert "is_boxed_text" in meta
            assert "is_stat_block" in meta


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------


class TestExports:
    """Verify public API exports from the package."""

    def test_module_indexer_importable_from_package(self) -> None:
        from dm20_protocol.claudmaster import (
            ChunkConfig,
            IndexingResult,
            ModuleIndexer,
        )
        assert ChunkConfig is not None
        assert IndexingResult is not None
        assert ModuleIndexer is not None

    def test_module_indexer_in_all(self) -> None:
        import dm20_protocol.claudmaster as pkg
        assert "ChunkConfig" in pkg.__all__
        assert "IndexingResult" in pkg.__all__
        assert "ModuleIndexer" in pkg.__all__
