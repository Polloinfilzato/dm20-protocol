"""
Vector store management for the Claudmaster RAG system.

Uses ChromaDB as the backend for storing and querying document embeddings,
with sentence-transformers for generating embeddings locally.
Each adventure module gets its own collection for isolated queries.
"""

import logging
from typing import Any

logger = logging.getLogger("dm20-protocol")

# Try to import ChromaDB — it's an optional dependency for RAG features.
# When not installed, the module still loads but VectorStoreManager raises
# a clear error at instantiation time rather than crashing at import.
try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.errors import NotFoundError as ChromaNotFoundError

    HAS_CHROMADB = True
except ImportError:
    chromadb = None  # type: ignore[assignment]
    Settings = None  # type: ignore[assignment,misc]
    ChromaNotFoundError = Exception  # type: ignore[assignment,misc]
    HAS_CHROMADB = False
    logger.info(
        "chromadb not installed — vector store features disabled. "
        "Install with: pip install chromadb"
    )

# Default embedding model - good balance of speed and quality for English text
DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"

# Valid content types for document metadata
VALID_CONTENT_TYPES = frozenset({
    "narrative", "encounter", "npc", "location", "item",
    "trap", "puzzle", "lore", "map_description",
})


class VectorStoreError(Exception):
    """Base exception for vector store operations."""


class CollectionNotFoundError(VectorStoreError):
    """Raised when a requested collection does not exist."""


class VectorStoreManager:
    """Manages ChromaDB vector store for RAG operations.

    Provides collection management (create, delete, list) per adventure module,
    document insertion with structured metadata, and similarity search with
    optional metadata filtering.

    Args:
        persist_directory: Path where ChromaDB stores data on disk.
        embedding_model: Name of the sentence-transformers model for embeddings.
        embedding_function: Optional pre-built embedding function to inject.
            When provided, ``embedding_model`` is ignored and no lazy import
            of sentence-transformers occurs. Useful for testing or when a
            different embedding backend is desired.
    """

    def __init__(
        self,
        persist_directory: str,
        embedding_model: str = DEFAULT_EMBEDDING_MODEL,
        embedding_function: Any = None,
    ) -> None:
        if not HAS_CHROMADB:
            raise VectorStoreError(
                "chromadb is not installed. Install it with: pip install chromadb"
            )

        self._persist_directory = persist_directory
        self._embedding_model_name = embedding_model

        # Initialize ChromaDB with persistent storage
        self._client = chromadb.PersistentClient(
            path=persist_directory,
            settings=Settings(anonymized_telemetry=False),
        )

        # Use injected function or lazy-load later
        self._embedding_fn: Any = embedding_function

        logger.info(
            "VectorStoreManager initialized (persist_dir=%s, model=%s)",
            persist_directory,
            embedding_model,
        )

    def _get_embedding_function(self) -> Any:
        """Return the embedding function, lazy-loading if needed.

        If an embedding function was injected via __init__, returns it directly.
        Otherwise, imports sentence-transformers on first call.
        """
        if self._embedding_fn is None:
            from chromadb.utils.embedding_functions import (
                SentenceTransformerEmbeddingFunction,
            )
            self._embedding_fn = SentenceTransformerEmbeddingFunction(
                model_name=self._embedding_model_name,
            )
            logger.info("Embedding model '%s' loaded", self._embedding_model_name)
        return self._embedding_fn

    # ------------------------------------------------------------------
    # Collection management
    # ------------------------------------------------------------------

    def _collection_name(self, module_id: str) -> str:
        """Derive a ChromaDB-safe collection name from a module ID."""
        # ChromaDB requires: 3-63 chars, starts/ends with alphanum, no consecutive dots
        safe = module_id.replace(" ", "_").replace("/", "_")[:60]
        return f"mod_{safe}"

    def create_collection(
        self,
        module_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Create a new collection for an adventure module.

        If the collection already exists, this is a no-op.

        Args:
            module_id: Unique identifier for the adventure module.
            metadata: Optional metadata to attach to the collection.
        """
        name = self._collection_name(module_id)
        col_metadata = metadata or {}
        col_metadata["module_id"] = module_id

        self._client.get_or_create_collection(
            name=name,
            embedding_function=self._get_embedding_function(),
            metadata=col_metadata,
        )
        logger.info("Collection '%s' ready for module '%s'", name, module_id)

    def delete_collection(self, module_id: str) -> None:
        """Delete a module's collection and all its documents.

        Args:
            module_id: The module whose collection should be removed.

        Raises:
            CollectionNotFoundError: If the collection does not exist.
        """
        name = self._collection_name(module_id)
        try:
            self._client.delete_collection(name=name)
            logger.info("Collection '%s' deleted", name)
        except (ValueError, ChromaNotFoundError) as exc:
            raise CollectionNotFoundError(
                f"No collection for module '{module_id}'"
            ) from exc

    def list_collections(self) -> list[str]:
        """List all module IDs that have a collection.

        Returns:
            List of module_id strings extracted from collection metadata.
        """
        collections = self._client.list_collections()
        module_ids: list[str] = []
        for entry in collections:
            # ChromaDB may return strings or Collection objects depending on version
            col_name = entry if isinstance(entry, str) else entry.name
            col = self._client.get_collection(
                name=col_name,
                embedding_function=self._get_embedding_function(),
            )
            mid = (col.metadata or {}).get("module_id", col_name)
            module_ids.append(mid)
        return module_ids

    # ------------------------------------------------------------------
    # Document operations
    # ------------------------------------------------------------------

    def add_documents(
        self,
        module_id: str,
        documents: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        """Add documents to a module's collection with metadata.

        Args:
            module_id: Target module collection.
            documents: List of text chunks to embed and store.
            metadatas: Per-document metadata dicts. Expected keys:
                chapter, section, content_type, page_range, chunk_index.
            ids: Unique identifiers for each document.

        Raises:
            CollectionNotFoundError: If the module collection doesn't exist.
            ValueError: If input list lengths don't match.
        """
        if not (len(documents) == len(metadatas) == len(ids)):
            raise ValueError(
                f"Length mismatch: documents={len(documents)}, "
                f"metadatas={len(metadatas)}, ids={len(ids)}"
            )

        name = self._collection_name(module_id)
        try:
            collection = self._client.get_collection(
                name=name,
                embedding_function=self._get_embedding_function(),
            )
        except (ValueError, ChromaNotFoundError) as exc:
            raise CollectionNotFoundError(
                f"No collection for module '{module_id}'. Call create_collection first."
            ) from exc

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(
            "Added %d documents to collection '%s'", len(documents), name,
        )

    def query(
        self,
        module_id: str,
        query_text: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Query for similar documents with optional metadata filter.

        Args:
            module_id: Module collection to search.
            query_text: Natural-language query string.
            n_results: Maximum number of results to return.
            where: Optional ChromaDB where-filter on metadata fields.

        Returns:
            List of result dicts, each containing:
                - id: Document ID
                - document: The text content
                - metadata: The document's metadata dict
                - distance: Similarity distance (lower is more similar)

        Raises:
            CollectionNotFoundError: If the module collection doesn't exist.
        """
        name = self._collection_name(module_id)
        try:
            collection = self._client.get_collection(
                name=name,
                embedding_function=self._get_embedding_function(),
            )
        except (ValueError, ChromaNotFoundError) as exc:
            raise CollectionNotFoundError(
                f"No collection for module '{module_id}'"
            ) from exc

        query_params: dict[str, Any] = {
            "query_texts": [query_text],
            "n_results": min(n_results, collection.count() or n_results),
        }
        if where:
            query_params["where"] = where

        raw = collection.query(**query_params)

        # Flatten ChromaDB's nested list structure into simple dicts
        results: list[dict[str, Any]] = []
        if raw["ids"] and raw["ids"][0]:
            for i, doc_id in enumerate(raw["ids"][0]):
                results.append({
                    "id": doc_id,
                    "document": raw["documents"][0][i] if raw["documents"] else "",
                    "metadata": raw["metadatas"][0][i] if raw["metadatas"] else {},
                    "distance": raw["distances"][0][i] if raw["distances"] else None,
                })

        return results

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    def collection_count(self, module_id: str) -> int:
        """Return the number of documents in a module's collection.

        Args:
            module_id: The module to check.

        Returns:
            Number of stored documents.

        Raises:
            CollectionNotFoundError: If the collection doesn't exist.
        """
        name = self._collection_name(module_id)
        try:
            collection = self._client.get_collection(
                name=name,
                embedding_function=self._get_embedding_function(),
            )
        except (ValueError, ChromaNotFoundError) as exc:
            raise CollectionNotFoundError(
                f"No collection for module '{module_id}'"
            ) from exc
        return collection.count()


__all__ = [
    "HAS_CHROMADB",
    "VectorStoreManager",
    "VectorStoreError",
    "CollectionNotFoundError",
    "DEFAULT_EMBEDDING_MODEL",
    "VALID_CONTENT_TYPES",
]
