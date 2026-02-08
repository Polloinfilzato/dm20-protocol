"""
Unit tests for VectorStoreManager.

Tests inject ChromaDB's default embedding function (ONNX-based, no
sentence-transformers dependency) to keep the test suite fast and
free of heavy ML library imports.
"""

import pytest
from typing import Any

from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from dm20_protocol.claudmaster.vector_store import (
    VectorStoreManager,
    VectorStoreError,
    CollectionNotFoundError,
    DEFAULT_EMBEDDING_MODEL,
    VALID_CONTENT_TYPES,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def _default_ef() -> DefaultEmbeddingFunction:
    """Shared ChromaDB default embedding function (ONNX-based)."""
    return DefaultEmbeddingFunction()


@pytest.fixture
def tmp_store(tmp_path: Any, _default_ef: DefaultEmbeddingFunction) -> VectorStoreManager:
    """Create a VectorStoreManager backed by a temp directory.

    Injects the default ChromaDB embedding function to avoid importing
    sentence-transformers (which has heavy/fragile torch dependencies).
    """
    return VectorStoreManager(
        persist_directory=str(tmp_path / "chromadb"),
        embedding_function=_default_ef,
    )


@pytest.fixture
def sample_documents() -> tuple[list[str], list[dict[str, Any]], list[str]]:
    """Return a small set of sample documents with metadata and ids."""
    docs = [
        "The goblin camp sits at the edge of the Darkwood forest.",
        "Chief Gruk commands a warband of twelve goblins.",
        "A hidden tunnel beneath the camp leads to an underground river.",
    ]
    metas = [
        {
            "chapter": "Chapter 1",
            "section": "Goblin Camp",
            "content_type": "location",
            "page_range": "12-13",
            "chunk_index": 0,
        },
        {
            "chapter": "Chapter 1",
            "section": "Goblin Camp",
            "content_type": "npc",
            "page_range": "13",
            "chunk_index": 1,
        },
        {
            "chapter": "Chapter 1",
            "section": "Goblin Camp",
            "content_type": "narrative",
            "page_range": "14",
            "chunk_index": 2,
        },
    ]
    ids = ["chunk-001", "chunk-002", "chunk-003"]
    return docs, metas, ids


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:
    """Tests for module-level constants."""

    def test_default_embedding_model(self) -> None:
        assert DEFAULT_EMBEDDING_MODEL == "all-MiniLM-L6-v2"

    def test_valid_content_types_is_frozenset(self) -> None:
        assert isinstance(VALID_CONTENT_TYPES, frozenset)

    def test_valid_content_types_contains_expected(self) -> None:
        expected = {"narrative", "encounter", "npc", "location", "item"}
        assert expected.issubset(VALID_CONTENT_TYPES)


# ---------------------------------------------------------------------------
# Collection management
# ---------------------------------------------------------------------------

class TestCollectionManagement:
    """Tests for create, delete, and list operations."""

    def test_create_collection(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("lost-mine-of-phandelver")
        collections = tmp_store.list_collections()
        assert "lost-mine-of-phandelver" in collections

    def test_create_collection_idempotent(self, tmp_store: VectorStoreManager) -> None:
        """Creating the same collection twice should not raise."""
        tmp_store.create_collection("module-a")
        tmp_store.create_collection("module-a")
        assert tmp_store.list_collections().count("module-a") == 1

    def test_create_collection_with_metadata(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("module-b", metadata={"system": "dnd5e", "tier": "1"})
        assert "module-b" in tmp_store.list_collections()

    def test_delete_collection(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("to-delete")
        assert "to-delete" in tmp_store.list_collections()
        tmp_store.delete_collection("to-delete")
        assert "to-delete" not in tmp_store.list_collections()

    def test_delete_nonexistent_collection_raises(self, tmp_store: VectorStoreManager) -> None:
        with pytest.raises(CollectionNotFoundError):
            tmp_store.delete_collection("nonexistent")

    def test_list_empty(self, tmp_store: VectorStoreManager) -> None:
        assert tmp_store.list_collections() == []

    def test_list_multiple_collections(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("mod-a")
        tmp_store.create_collection("mod-b")
        tmp_store.create_collection("mod-c")
        result = tmp_store.list_collections()
        assert len(result) == 3
        assert set(result) == {"mod-a", "mod-b", "mod-c"}


# ---------------------------------------------------------------------------
# Document operations
# ---------------------------------------------------------------------------

class TestDocumentOperations:
    """Tests for adding documents and querying."""

    def test_add_documents(
        self,
        tmp_store: VectorStoreManager,
        sample_documents: tuple[list[str], list[dict[str, Any]], list[str]],
    ) -> None:
        docs, metas, ids = sample_documents
        tmp_store.create_collection("test-module")
        tmp_store.add_documents("test-module", docs, metas, ids)
        assert tmp_store.collection_count("test-module") == 3

    def test_add_documents_length_mismatch(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("test-module")
        with pytest.raises(ValueError, match="Length mismatch"):
            tmp_store.add_documents(
                "test-module",
                documents=["doc1", "doc2"],
                metadatas=[{"a": "b"}],
                ids=["id1", "id2"],
            )

    def test_add_documents_to_nonexistent_collection(
        self, tmp_store: VectorStoreManager,
    ) -> None:
        with pytest.raises(CollectionNotFoundError):
            tmp_store.add_documents(
                "nonexistent",
                documents=["text"],
                metadatas=[{"k": "v"}],
                ids=["id1"],
            )

    def test_query_returns_results(
        self,
        tmp_store: VectorStoreManager,
        sample_documents: tuple[list[str], list[dict[str, Any]], list[str]],
    ) -> None:
        docs, metas, ids = sample_documents
        tmp_store.create_collection("test-module")
        tmp_store.add_documents("test-module", docs, metas, ids)

        results = tmp_store.query("test-module", "goblin leader", n_results=2)
        assert len(results) <= 2
        assert all("id" in r for r in results)
        assert all("document" in r for r in results)
        assert all("metadata" in r for r in results)
        assert all("distance" in r for r in results)

    def test_query_with_where_filter(
        self,
        tmp_store: VectorStoreManager,
        sample_documents: tuple[list[str], list[dict[str, Any]], list[str]],
    ) -> None:
        docs, metas, ids = sample_documents
        tmp_store.create_collection("test-module")
        tmp_store.add_documents("test-module", docs, metas, ids)

        results = tmp_store.query(
            "test-module",
            "goblin",
            n_results=5,
            where={"content_type": "npc"},
        )
        # Should only return the NPC document
        assert len(results) == 1
        assert results[0]["metadata"]["content_type"] == "npc"

    def test_query_nonexistent_collection(self, tmp_store: VectorStoreManager) -> None:
        with pytest.raises(CollectionNotFoundError):
            tmp_store.query("nonexistent", "query text")

    def test_query_empty_collection(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("empty-mod")
        results = tmp_store.query("empty-mod", "anything")
        assert results == []


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

class TestUtilities:
    """Tests for utility methods."""

    def test_collection_count_empty(self, tmp_store: VectorStoreManager) -> None:
        tmp_store.create_collection("empty")
        assert tmp_store.collection_count("empty") == 0

    def test_collection_count_with_docs(
        self,
        tmp_store: VectorStoreManager,
        sample_documents: tuple[list[str], list[dict[str, Any]], list[str]],
    ) -> None:
        docs, metas, ids = sample_documents
        tmp_store.create_collection("counted")
        tmp_store.add_documents("counted", docs, metas, ids)
        assert tmp_store.collection_count("counted") == 3

    def test_collection_count_nonexistent(self, tmp_store: VectorStoreManager) -> None:
        with pytest.raises(CollectionNotFoundError):
            tmp_store.collection_count("ghost")


# ---------------------------------------------------------------------------
# Collection naming
# ---------------------------------------------------------------------------

class TestCollectionNaming:
    """Tests for the internal collection naming logic."""

    def test_name_sanitization(self, tmp_store: VectorStoreManager) -> None:
        """Special characters in module IDs should be sanitized."""
        name = tmp_store._collection_name("my module/v2")
        assert " " not in name
        assert "/" not in name
        assert name.startswith("mod_")

    def test_name_length_limit(self, tmp_store: VectorStoreManager) -> None:
        """Very long module IDs should be truncated."""
        long_id = "a" * 200
        name = tmp_store._collection_name(long_id)
        assert len(name) <= 64  # "mod_" + 60 chars max


# ---------------------------------------------------------------------------
# Dependency injection
# ---------------------------------------------------------------------------

class TestEmbeddingInjection:
    """Tests for embedding function injection and lazy loading."""

    def test_injected_fn_used_directly(self, tmp_path: Any) -> None:
        """When embedding_function is provided, it's used without lazy import."""
        ef = DefaultEmbeddingFunction()
        store = VectorStoreManager(
            persist_directory=str(tmp_path / "db"),
            embedding_function=ef,
        )
        assert store._embedding_fn is ef

    def test_no_injection_leaves_none(self, tmp_path: Any) -> None:
        """Without injection, _embedding_fn starts as None (lazy)."""
        store = VectorStoreManager(persist_directory=str(tmp_path / "db"))
        assert store._embedding_fn is None

    def test_injected_fn_cached(self, tmp_store: VectorStoreManager) -> None:
        fn1 = tmp_store._get_embedding_function()
        fn2 = tmp_store._get_embedding_function()
        assert fn1 is fn2


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------

class TestErrorHierarchy:
    """Tests for custom exception classes."""

    def test_collection_not_found_is_vector_store_error(self) -> None:
        assert issubclass(CollectionNotFoundError, VectorStoreError)

    def test_vector_store_error_is_exception(self) -> None:
        assert issubclass(VectorStoreError, Exception)
