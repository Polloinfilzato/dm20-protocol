"""
Module content chunking and ChromaDB indexing for adventure modules.

Implements intelligent text chunking with overlap, preserving structural
metadata (chapter, section, content type), and supports re-indexing when
modules are updated. Chunks are stored in ChromaDB via VectorStoreManager
for RAG retrieval during gameplay.
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models.module import (
    ContentType,
    ModuleElement,
    ModuleStructure,
    NPCReference,
    LocationReference,
)
from .vector_store import CollectionNotFoundError, HAS_CHROMADB, VectorStoreManager

logger = logging.getLogger("dm20-protocol")


# ---------------------------------------------------------------------------
# Configuration and result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class ChunkConfig:
    """Configuration for text chunking.

    Attributes:
        chunk_size: Target characters per chunk.
        chunk_overlap: Number of overlapping characters between consecutive chunks.
        min_chunk_size: Minimum chunk size; shorter chunks are merged with neighbours.
        respect_paragraphs: Avoid splitting mid-paragraph when possible.
        respect_sections: Prefer section boundaries as chunk boundaries.
    """

    chunk_size: int = 500
    chunk_overlap: int = 100
    min_chunk_size: int = 100
    respect_paragraphs: bool = True
    respect_sections: bool = True


@dataclass
class IndexingResult:
    """Result of a module indexing operation.

    Attributes:
        module_id: Identifier of the indexed module.
        chunks_created: Total number of chunks stored.
        chapters_indexed: Number of chapters processed.
        npcs_indexed: Number of NPC names found across chunks.
        locations_indexed: Number of location names found across chunks.
        indexing_time_seconds: Wall-clock time for the indexing run.
        skipped: True when the module was already indexed and unchanged.
        errors: List of non-fatal error messages encountered during indexing.
    """

    module_id: str
    chunks_created: int
    chapters_indexed: int
    npcs_indexed: int
    locations_indexed: int
    indexing_time_seconds: float
    skipped: bool = False
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Special content detection patterns
# ---------------------------------------------------------------------------

# Boxed text (read-aloud) is typically enclosed in quotation or special markers.
# Many adventure PDFs use italicised paragraphs or explicit "Read the following"
# cues.  We detect common patterns.
_BOXED_TEXT_PATTERNS = [
    re.compile(
        r"(?:Read\s+(?:the\s+following|aloud|this)\s*:?\s*)(.*?)(?:\n\n|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    # Text surrounded by quotation marks spanning multiple lines
    re.compile(r'^\s*"(.*?)"\s*$', re.DOTALL | re.MULTILINE),
]

# Stat block markers
_STAT_BLOCK_PATTERNS = [
    re.compile(
        r"(?:Armor\s+Class\s+\d+.*?Hit\s+Points\s+\d+.*?Speed\s+\d+)",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r"(?:STR\s+\d+.*?DEX\s+\d+.*?CON\s+\d+)",
        re.DOTALL | re.IGNORECASE,
    ),
]


def _is_boxed_text(text: str) -> bool:
    """Return True if *text* looks like read-aloud / boxed text."""
    for pattern in _BOXED_TEXT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _is_stat_block(text: str) -> bool:
    """Return True if *text* looks like a monster/NPC stat block."""
    for pattern in _STAT_BLOCK_PATTERNS:
        if pattern.search(text):
            return True
    return False


def _compute_text_hash(text: str) -> str:
    """Return a SHA-256 hex digest of *text*."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Text extraction helper
# ---------------------------------------------------------------------------


def extract_text_from_pdf(pdf_path: str | Path, page_start: int, page_end: int | None) -> str:
    """Extract text from a range of pages in a PDF.

    Uses PyMuPDF (fitz) to read pages.  Page numbers are **1-indexed**.

    Args:
        pdf_path: Path to the PDF file.
        page_start: First page to read (1-indexed).
        page_end: Last page to read (1-indexed, inclusive).  If ``None``,
            only *page_start* is read.

    Returns:
        Concatenated text from the requested pages.
    """
    import fitz  # PyMuPDF  -- imported lazily to keep module lightweight

    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        logger.error("Failed to open PDF %s: %s", pdf_path, exc)
        return ""

    try:
        start_idx = max(0, page_start - 1)
        end_idx = max(start_idx, (page_end or page_start) - 1)
        end_idx = min(end_idx, doc.page_count - 1)

        parts: list[str] = []
        for page_num in range(start_idx, end_idx + 1):
            page = doc[page_num]
            parts.append(page.get_text())
        return "\n\n".join(parts)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# ModuleIndexer
# ---------------------------------------------------------------------------


class ModuleIndexer:
    """Indexes adventure module content into ChromaDB for RAG retrieval.

    The indexer walks a :class:`ModuleStructure`, extracts PDF page text for
    each chapter/section, splits that text into overlapping chunks, attaches
    rich metadata, and stores everything in ChromaDB via a
    :class:`VectorStoreManager`.

    Args:
        vector_store: The :class:`VectorStoreManager` instance to use.
        chunk_config: Optional chunking configuration.  Defaults to
            :class:`ChunkConfig` with sensible defaults.
    """

    # Key used in ChromaDB collection metadata to persist indexing info.
    _META_KEY_SOURCE_HASH = "source_hash"
    _META_KEY_INDEXED_AT = "indexed_at"
    _META_KEY_TOTAL_CHUNKS = "total_chunks"
    _META_KEY_CHUNK_CONFIG = "chunk_config"

    def __init__(
        self,
        vector_store: VectorStoreManager,
        chunk_config: ChunkConfig | None = None,
    ) -> None:
        self._store = vector_store
        self._config = chunk_config or ChunkConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def index_module(
        self,
        module_structure: ModuleStructure,
        pdf_path: str,
        force_reindex: bool = False,
    ) -> IndexingResult:
        """Index an entire adventure module into the vector store.

        If the module is already indexed and unchanged (based on PDF hash),
        the operation is skipped unless *force_reindex* is ``True``.

        Args:
            module_structure: Parsed module structure from :class:`ModuleParser`.
            pdf_path: Path to the source PDF file.
            force_reindex: When ``True``, delete existing data and re-index.

        Returns:
            :class:`IndexingResult` with statistics about the operation.
        """
        t0 = time.monotonic()
        module_id = module_structure.module_id
        pdf_path_obj = Path(pdf_path)

        # Compute source hash
        source_hash = self._compute_file_hash(pdf_path_obj)

        # Check whether re-indexing is needed
        if not force_reindex and self.is_indexed(module_id):
            existing_meta = self.get_index_metadata(module_id)
            if existing_meta and existing_meta.get(self._META_KEY_SOURCE_HASH) == source_hash:
                logger.info(
                    "Module '%s' already indexed and unchanged; skipping.",
                    module_id,
                )
                return IndexingResult(
                    module_id=module_id,
                    chunks_created=0,
                    chapters_indexed=0,
                    npcs_indexed=0,
                    locations_indexed=0,
                    indexing_time_seconds=time.monotonic() - t0,
                    skipped=True,
                )

        # Delete existing collection if present (for re-index)
        if self.is_indexed(module_id):
            self.delete_index(module_id)

        # Prepare collection metadata
        col_metadata = {
            self._META_KEY_SOURCE_HASH: source_hash,
            self._META_KEY_INDEXED_AT: datetime.now(timezone.utc).isoformat(),
            self._META_KEY_CHUNK_CONFIG: (
                f"size={self._config.chunk_size},"
                f"overlap={self._config.chunk_overlap},"
                f"min={self._config.min_chunk_size}"
            ),
        }
        self._store.create_collection(module_id, metadata=col_metadata)

        # Gather NPC and location names for cross-referencing
        npc_names = [npc.name for npc in module_structure.npcs]
        location_names = [loc.name for loc in module_structure.locations]

        errors: list[str] = []
        all_docs: list[str] = []
        all_metas: list[dict[str, Any]] = []
        all_ids: list[str] = []
        chapters_indexed = 0

        # Walk the module elements (chapters/sections)
        for element in module_structure.chapters:
            if element.content_type in (ContentType.CHAPTER, ContentType.APPENDIX):
                chapters_indexed += 1

            # Extract text for this element
            page_end = element.page_end
            if page_end is None:
                page_end = element.page_start

            try:
                text = extract_text_from_pdf(
                    pdf_path_obj,
                    element.page_start,
                    page_end,
                )
            except Exception as exc:
                msg = (
                    f"Failed to extract text for '{element.name}' "
                    f"(pages {element.page_start}-{page_end}): {exc}"
                )
                logger.warning(msg)
                errors.append(msg)
                continue

            if not text.strip():
                continue

            # Determine chapter context
            chapter_name = element.name if element.parent is None else (element.parent or "")
            section_name = element.name if element.parent is not None else ""

            context: dict[str, Any] = {
                "module_id": module_id,
                "chapter": chapter_name,
                "section": section_name,
                "content_type": element.content_type.value,
                "page_start": element.page_start,
                "page_end": page_end,
                "npc_names": npc_names,
                "location_names": location_names,
            }

            chunks = self.chunk_text(text, context)

            for chunk_text, chunk_meta in chunks:
                doc_id = f"{module_id}_{element.page_start}_{chunk_meta.get('chunk_index', 0)}"
                all_docs.append(chunk_text)
                all_metas.append(chunk_meta)
                all_ids.append(doc_id)

        # Batch insert all chunks
        if all_docs:
            # ChromaDB can handle large batches, but we do a simple single call.
            try:
                self._store.add_documents(
                    module_id,
                    documents=all_docs,
                    metadatas=all_metas,
                    ids=all_ids,
                )
            except Exception as exc:
                msg = f"Failed to store chunks: {exc}"
                logger.error(msg)
                errors.append(msg)

        # Update collection metadata with total chunk count
        # (ChromaDB doesn't allow metadata updates on collections easily,
        #  but the count is available via collection_count.)

        # Count referenced NPCs and locations
        npcs_found: set[str] = set()
        locations_found: set[str] = set()
        for meta in all_metas:
            npcs_ref = meta.get("npcs_referenced", "")
            if npcs_ref:
                npcs_found.update(n.strip() for n in npcs_ref.split(",") if n.strip())
            locs_ref = meta.get("locations_referenced", "")
            if locs_ref:
                locations_found.update(loc.strip() for loc in locs_ref.split(",") if loc.strip())

        elapsed = time.monotonic() - t0
        result = IndexingResult(
            module_id=module_id,
            chunks_created=len(all_docs),
            chapters_indexed=chapters_indexed,
            npcs_indexed=len(npcs_found),
            locations_indexed=len(locations_found),
            indexing_time_seconds=elapsed,
            errors=errors,
        )

        logger.info(
            "Indexed module '%s': %d chunks from %d chapters in %.1fs",
            module_id,
            result.chunks_created,
            result.chapters_indexed,
            result.indexing_time_seconds,
        )
        return result

    def chunk_text(
        self,
        text: str,
        context: dict[str, Any],
    ) -> list[tuple[str, dict[str, Any]]]:
        """Split *text* into overlapping chunks with metadata.

        Each returned tuple is ``(chunk_text, metadata_dict)``.

        The chunking algorithm:
        1. Split the text into paragraphs (double newlines).
        2. Greedily accumulate paragraphs into chunks up to
           ``chunk_size``.
        3. When a chunk reaches the target size, flush it and start a
           new chunk with overlap from the tail of the previous chunk.
        4. Short trailing chunks (< ``min_chunk_size``) are merged into
           the previous chunk.

        Special content (boxed text, stat blocks) is kept intact as a
        single chunk when possible.

        Args:
            text: Raw text to chunk.
            context: Contextual metadata dict.  Expected keys:
                ``module_id``, ``chapter``, ``section``, ``content_type``,
                ``page_start``, ``page_end``, ``npc_names``, ``location_names``.

        Returns:
            List of ``(chunk_text, metadata)`` tuples.
        """
        if not text.strip():
            return []

        config = self._config
        module_id = context.get("module_id", "")
        chapter = context.get("chapter", "")
        section = context.get("section", "")
        content_type = context.get("content_type", "narrative")
        page_start = context.get("page_start", 0)
        page_end = context.get("page_end", page_start)
        npc_names: list[str] = context.get("npc_names", [])
        location_names: list[str] = context.get("location_names", [])

        # Split into paragraphs (respecting blank-line boundaries)
        if config.respect_paragraphs:
            paragraphs = re.split(r"\n\s*\n", text)
        else:
            # Treat each line as an independent unit
            paragraphs = text.split("\n")

        # Filter out empty paragraphs
        paragraphs = [p.strip() for p in paragraphs if p.strip()]

        if not paragraphs:
            return []

        # Build raw chunks by accumulating paragraphs
        raw_chunks: list[str] = []
        current_parts: list[str] = []
        current_len = 0

        for para in paragraphs:
            para_len = len(para)

            # If a single paragraph exceeds chunk_size, we must force-split it
            if para_len > config.chunk_size:
                # Flush anything accumulated so far
                if current_parts:
                    raw_chunks.append("\n\n".join(current_parts))
                    current_parts = []
                    current_len = 0
                # Force-split the long paragraph by character
                raw_chunks.extend(self._force_split(para, config.chunk_size))
                continue

            # Would adding this paragraph exceed the chunk size?
            separator_len = 2 if current_parts else 0  # "\n\n"
            if current_len + separator_len + para_len > config.chunk_size and current_parts:
                # Flush current chunk
                raw_chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_len = 0

            current_parts.append(para)
            current_len += (2 if current_len > 0 else 0) + para_len

        # Flush remaining
        if current_parts:
            raw_chunks.append("\n\n".join(current_parts))

        # Merge trailing short chunk into previous if too small
        if (
            len(raw_chunks) > 1
            and len(raw_chunks[-1]) < config.min_chunk_size
        ):
            raw_chunks[-2] = raw_chunks[-2] + "\n\n" + raw_chunks[-1]
            raw_chunks.pop()

        # Apply overlap: prepend tail of previous chunk to each subsequent chunk
        final_chunks: list[str] = []
        for i, chunk in enumerate(raw_chunks):
            if i > 0 and config.chunk_overlap > 0:
                prev = raw_chunks[i - 1]
                overlap_text = prev[-config.chunk_overlap :]
                # Try to start overlap at a word boundary
                space_idx = overlap_text.find(" ")
                if space_idx > 0:
                    overlap_text = overlap_text[space_idx + 1 :]
                chunk = overlap_text + " " + chunk
            final_chunks.append(chunk)

        total_chunks = len(final_chunks)

        # Build result tuples with metadata
        result: list[tuple[str, dict[str, Any]]] = []
        for idx, chunk in enumerate(final_chunks):
            is_boxed = _is_boxed_text(chunk)
            is_stat = _is_stat_block(chunk)

            # Detect referenced NPCs and locations in this chunk
            referenced_npcs = [
                name for name in npc_names if name.lower() in chunk.lower()
            ]
            referenced_locations = [
                name for name in location_names if name.lower() in chunk.lower()
            ]

            # Determine content type override for special content
            effective_content_type = content_type
            if is_stat:
                effective_content_type = "npc"
            elif is_boxed:
                effective_content_type = "narrative"

            meta: dict[str, Any] = {
                "module_id": module_id,
                "chapter": chapter,
                "section": section,
                "content_type": effective_content_type,
                "page_start": page_start,
                "page_end": page_end,
                "chunk_index": idx,
                "total_chunks_in_section": total_chunks,
                "npcs_referenced": ", ".join(referenced_npcs),
                "locations_referenced": ", ".join(referenced_locations),
                "is_boxed_text": is_boxed,
                "is_stat_block": is_stat,
            }
            result.append((chunk, meta))

        return result

    def is_indexed(self, module_id: str) -> bool:
        """Check whether a module already has an index in the vector store.

        Args:
            module_id: The module identifier.

        Returns:
            ``True`` if a collection exists for the module.
        """
        return module_id in self._store.list_collections()

    def get_index_metadata(self, module_id: str) -> dict[str, Any] | None:
        """Retrieve stored metadata about an indexed module.

        The metadata is attached to the ChromaDB collection and includes
        ``source_hash``, ``indexed_at``, and ``chunk_config``.

        Args:
            module_id: The module identifier.

        Returns:
            Metadata dict or ``None`` if the module is not indexed.
        """
        if not self.is_indexed(module_id):
            return None

        try:
            name = self._store._collection_name(module_id)
            col = self._store._client.get_collection(
                name=name,
                embedding_function=self._store._get_embedding_function(),
            )
            return dict(col.metadata) if col.metadata else None
        except Exception:
            return None

    def delete_index(self, module_id: str) -> None:
        """Remove a module's index from the vector store.

        Args:
            module_id: The module identifier.

        Raises:
            CollectionNotFoundError: If no index exists for the module.
        """
        self._store.delete_collection(module_id)
        logger.info("Deleted index for module '%s'", module_id)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_file_hash(file_path: Path) -> str:
        """Compute SHA-256 hash of a file for change detection.

        Args:
            file_path: Path to the file.

        Returns:
            Hex-encoded SHA-256 digest.
        """
        hasher = hashlib.sha256()
        with open(file_path, "rb") as fh:
            for block in iter(lambda: fh.read(65536), b""):
                hasher.update(block)
        return hasher.hexdigest()

    @staticmethod
    def _force_split(text: str, chunk_size: int) -> list[str]:
        """Split a long text into chunks of at most *chunk_size* characters.

        Attempts to break at word boundaries when possible.

        Args:
            text: The text to split.
            chunk_size: Maximum characters per chunk.

        Returns:
            List of text chunks.
        """
        chunks: list[str] = []
        while len(text) > chunk_size:
            # Try to find a space near the boundary
            split_at = text.rfind(" ", 0, chunk_size)
            if split_at <= 0:
                split_at = chunk_size
            chunks.append(text[:split_at].strip())
            text = text[split_at:].strip()
        if text:
            chunks.append(text)
        return chunks


__all__ = [
    "ChunkConfig",
    "IndexingResult",
    "ModuleIndexer",
    "extract_text_from_pdf",
]
