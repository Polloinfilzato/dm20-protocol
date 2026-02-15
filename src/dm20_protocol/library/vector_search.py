"""
Vector-based semantic search for the PDF Library System.

Provides semantic search across the library using ChromaDB vector embeddings.
Falls back gracefully to TF-IDF search when chromadb is not installed.
Uses per-source collections (library_{source_id}) for namespace isolation.
"""

import logging
import re
from typing import TYPE_CHECKING, Any

from .search import SearchResult

if TYPE_CHECKING:
    from .manager import LibraryManager
    from .models import TOCEntry

logger = logging.getLogger("dm20-protocol")

# Try importing vector store components
try:
    from ..claudmaster.vector_store import HAS_CHROMADB, VectorStoreManager
except ImportError:
    HAS_CHROMADB = False
    VectorStoreManager = None  # type: ignore[assignment,misc]

# Chunk configuration for library content
LIBRARY_CHUNK_SIZE = 500
LIBRARY_CHUNK_OVERLAP = 100
LIBRARY_MIN_CHUNK_SIZE = 100


def _collection_name_for_source(source_id: str) -> str:
    """Derive a ChromaDB collection name for a library source.

    Args:
        source_id: The library source identifier (e.g., 'tome-of-heroes').

    Returns:
        ChromaDB-safe collection name.
    """
    safe = source_id.replace(" ", "_").replace("/", "_")[:55]
    return f"library_{safe}"


class VectorLibrarySearch:
    """Semantic search across the library using ChromaDB vector embeddings.

    Drop-in replacement for LibrarySearch with the same search() API.
    Uses one ChromaDB collection per library source for isolated queries.
    Results are ranked by cosine similarity distance.

    Args:
        library_manager: Reference to the LibraryManager for accessing indexes.
        vector_store: VectorStoreManager instance for ChromaDB operations.
    """

    def __init__(
        self,
        library_manager: "LibraryManager",
        vector_store: "VectorStoreManager",
    ) -> None:
        self.library_manager = library_manager
        self._store = vector_store

    def search(self, query: str, limit: int = 10) -> list[SearchResult]:
        """Search across all indexed library content using vector similarity.

        Args:
            query: Natural language search query.
            limit: Maximum number of results to return.

        Returns:
            List of SearchResult objects sorted by relevance (best first).
        """
        if not query or not query.strip():
            return []

        results: list[SearchResult] = []

        for source_id, index in self.library_manager._index_cache.items():
            col_name = _collection_name_for_source(source_id)

            # Check if this source has been indexed into the vector store
            try:
                collection = self._store._client.get_collection(
                    name=col_name,
                    embedding_function=self._store._get_embedding_function(),
                )
            except Exception:
                # Collection not yet created for this source — skip
                continue

            if collection.count() == 0:
                continue

            # Query the collection
            n = min(limit, collection.count())
            try:
                raw = collection.query(
                    query_texts=[query],
                    n_results=n,
                )
            except Exception as exc:
                logger.warning(
                    "Vector search failed for source '%s': %s", source_id, exc,
                )
                continue

            if not raw["ids"] or not raw["ids"][0]:
                continue

            # Check if extracted content exists
            extracted_dir = self.library_manager.extracted_dir / source_id
            has_extracted = extracted_dir.exists() and any(extracted_dir.glob("*.json"))

            # Convert results to SearchResult objects
            for i, doc_id in enumerate(raw["ids"][0]):
                metadata = raw["metadatas"][0][i] if raw["metadatas"] else {}
                distance = raw["distances"][0][i] if raw["distances"] else 1.0

                # Convert distance to a relevance score (lower distance = higher score)
                # ChromaDB cosine distance is in [0, 2], where 0 = identical
                score = max(0.0, 2.0 - distance)

                results.append(
                    SearchResult(
                        title=metadata.get("title", doc_id),
                        source_id=source_id,
                        source_name=index.filename,
                        page=metadata.get("page"),
                        content_type=metadata.get("content_type"),
                        score=score,
                        is_extracted=has_extracted,
                    )
                )

        # Sort by score descending (best match first)
        results.sort(key=lambda r: r.score, reverse=True)
        return results[:limit]

    def index_source(
        self,
        source_id: str,
        toc_entries: list["TOCEntry"],
        source_filename: str,
    ) -> int:
        """Index a library source's TOC entries into the vector store.

        Creates text chunks from TOC entry titles and metadata,
        then stores them in a per-source ChromaDB collection.

        Args:
            source_id: The library source identifier.
            toc_entries: Flat list of TOC entries to index.
            source_filename: Original filename for metadata.

        Returns:
            Number of chunks indexed.
        """
        col_name = _collection_name_for_source(source_id)

        # Create or get collection
        collection = self._store._client.get_or_create_collection(
            name=col_name,
            embedding_function=self._store._get_embedding_function(),
            metadata={"source_id": source_id, "filename": source_filename},
        )

        if not toc_entries:
            return 0

        documents: list[str] = []
        metadatas: list[dict[str, Any]] = []
        ids: list[str] = []

        for idx, entry in enumerate(toc_entries):
            # Build a searchable text from the TOC entry
            doc_text = entry.title
            content_type = entry.content_type.value if entry.content_type else "unknown"

            # Add content type context for better semantic matching
            if content_type != "unknown":
                doc_text = f"{content_type}: {entry.title}"

            doc_id = f"{source_id}_{idx}"
            metadata = {
                "title": entry.title,
                "source_id": source_id,
                "page": entry.page,
                "content_type": content_type,
            }
            if entry.end_page is not None:
                metadata["end_page"] = entry.end_page

            documents.append(doc_text)
            metadatas.append(metadata)
            ids.append(doc_id)

        # Batch add to collection
        if documents:
            collection.add(documents=documents, metadatas=metadatas, ids=ids)
            logger.info(
                "Indexed %d entries for library source '%s'",
                len(documents), source_id,
            )

        return len(documents)

    def is_source_indexed(self, source_id: str) -> bool:
        """Check whether a library source has been indexed into the vector store.

        Args:
            source_id: The library source identifier.

        Returns:
            True if the source collection exists and has documents.
        """
        col_name = _collection_name_for_source(source_id)
        try:
            collection = self._store._client.get_collection(
                name=col_name,
                embedding_function=self._store._get_embedding_function(),
            )
            return collection.count() > 0
        except Exception:
            return False

    def delete_source_index(self, source_id: str) -> None:
        """Delete a source's vector index.

        Args:
            source_id: The library source identifier.
        """
        col_name = _collection_name_for_source(source_id)
        try:
            self._store._client.delete_collection(name=col_name)
            logger.info("Deleted vector index for library source '%s'", source_id)
        except Exception:
            pass  # Collection may not exist


__all__ = [
    "VectorLibrarySearch",
]
