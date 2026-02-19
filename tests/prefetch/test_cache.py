"""
Tests for PrefetchCache (Issue #172).

Tests cover:
- Store and retrieve variants
- TTL expiration behavior
- Pattern-based and key-based invalidation
- Cache statistics tracking
- Cleanup of expired entries
- Edge cases (empty cache, duplicate keys)
"""

from __future__ import annotations

import time

import pytest

from dm20_protocol.prefetch.cache import (
    PrefetchCache,
    CacheEntry,
    PrefetchCacheStats,
)


# ============================================================================
# Basic Store and Get Tests
# ============================================================================


class TestPrefetchCacheBasic:
    """Test basic store and get operations."""

    def test_store_and_get(self):
        """Test storing and retrieving variants."""
        cache = PrefetchCache(default_ttl=60)

        variants = ["Hit narrative", "Miss narrative", "Critical narrative"]
        cache.store("turn_1", variants)

        result = cache.get("turn_1")
        assert result == variants

    def test_get_nonexistent_returns_none(self):
        """Test that getting a nonexistent key returns None."""
        cache = PrefetchCache()
        assert cache.get("nonexistent") is None

    def test_store_returns_defensive_copy(self):
        """Test that get returns a copy, not the original list."""
        cache = PrefetchCache()

        variants = ["Hit", "Miss"]
        cache.store("key", variants)

        result = cache.get("key")
        result.append("Modified")

        # Original cache should be unaffected
        original = cache.get("key")
        assert len(original) == 2

    def test_store_with_custom_ttl(self):
        """Test storing with a custom TTL."""
        cache = PrefetchCache(default_ttl=30)

        cache.store("key", ["variant"], ttl=120)

        # Entry should exist
        assert cache.get("key") is not None

    def test_store_with_metadata(self):
        """Test storing with metadata."""
        cache = PrefetchCache()

        metadata = {"character": "Goblin", "round": 3}
        cache.store("key", ["variant"], metadata=metadata)

        # Metadata is stored internally
        assert cache._cache["key"].metadata == metadata

    def test_store_overwrites_existing(self):
        """Test that storing with same key replaces the entry."""
        cache = PrefetchCache()

        cache.store("key", ["old_variant"])
        cache.store("key", ["new_variant"])

        result = cache.get("key")
        assert result == ["new_variant"]

    def test_size_property(self):
        """Test the size property."""
        cache = PrefetchCache()

        assert cache.size == 0
        cache.store("key1", ["v1"])
        assert cache.size == 1
        cache.store("key2", ["v2"])
        assert cache.size == 2

    def test_store_empty_variants(self):
        """Test storing an empty variants list."""
        cache = PrefetchCache()
        cache.store("key", [])

        result = cache.get("key")
        assert result == []


# ============================================================================
# TTL Expiration Tests
# ============================================================================


class TestTTLExpiration:
    """Test TTL expiration behavior."""

    def test_expired_entry_returns_none(self):
        """Test that expired entries return None."""
        cache = PrefetchCache(default_ttl=0)  # Immediate expiration

        cache.store("key", ["variant"])
        time.sleep(0.05)

        result = cache.get("key")
        assert result is None

    def test_expired_entry_is_removed(self):
        """Test that expired entries are removed from cache on access."""
        cache = PrefetchCache(default_ttl=0)

        cache.store("key", ["variant"])
        time.sleep(0.05)

        cache.get("key")  # Should trigger removal
        assert cache.size == 0

    def test_non_expired_entry_available(self):
        """Test that non-expired entries are still available."""
        cache = PrefetchCache(default_ttl=60)

        cache.store("key", ["variant"])
        result = cache.get("key")

        assert result == ["variant"]

    def test_custom_ttl_expiration(self):
        """Test expiration with custom per-entry TTL."""
        cache = PrefetchCache(default_ttl=60)

        # Short TTL entry
        cache.store("short", ["short_variant"], ttl=0)
        # Long TTL entry
        cache.store("long", ["long_variant"], ttl=60)

        time.sleep(0.05)

        assert cache.get("short") is None
        assert cache.get("long") == ["long_variant"]

    def test_expired_counts_as_miss(self):
        """Test that accessing expired entry counts as a cache miss."""
        cache = PrefetchCache(default_ttl=0)

        cache.store("key", ["variant"])
        time.sleep(0.05)

        cache.get("key")

        stats = cache.get_stats()
        assert stats.miss_count == 1
        assert stats.expired_count == 1
        assert stats.hit_count == 0


# ============================================================================
# Invalidation Tests
# ============================================================================


class TestInvalidation:
    """Test cache invalidation operations."""

    def test_invalidate_pattern_basic(self):
        """Test pattern-based invalidation."""
        cache = PrefetchCache()

        cache.store("round_1_goblin", ["v1"])
        cache.store("round_1_orc", ["v2"])
        cache.store("round_2_goblin", ["v3"])

        count = cache.invalidate("round_1")

        assert count == 2
        assert cache.get("round_1_goblin") is None
        assert cache.get("round_1_orc") is None
        assert cache.get("round_2_goblin") is not None

    def test_invalidate_pattern_no_matches(self):
        """Test pattern invalidation with no matches."""
        cache = PrefetchCache()

        cache.store("key1", ["v1"])
        count = cache.invalidate("nonexistent_pattern")

        assert count == 0
        assert cache.get("key1") is not None

    def test_invalidate_all_with_broad_pattern(self):
        """Test invalidating all entries with a broad pattern."""
        cache = PrefetchCache()

        cache.store("round_1_a", ["v1"])
        cache.store("round_2_b", ["v2"])
        cache.store("round_3_c", ["v3"])

        count = cache.invalidate("round_")
        assert count == 3
        assert cache.size == 0

    def test_invalidate_key_existing(self):
        """Test invalidating a specific key."""
        cache = PrefetchCache()

        cache.store("key1", ["v1"])
        result = cache.invalidate_key("key1")

        assert result is True
        assert cache.get("key1") is None

    def test_invalidate_key_nonexistent(self):
        """Test invalidating a nonexistent key."""
        cache = PrefetchCache()

        result = cache.invalidate_key("nonexistent")
        assert result is False

    def test_invalidation_updates_stats(self):
        """Test that invalidation updates statistics."""
        cache = PrefetchCache()

        cache.store("key1", ["v1"])
        cache.store("key2", ["v2"])

        cache.invalidate("key")

        stats = cache.get_stats()
        assert stats.invalidated_count == 2

    def test_clear_removes_all(self):
        """Test clearing all cache entries."""
        cache = PrefetchCache()

        cache.store("key1", ["v1"])
        cache.store("key2", ["v2"])

        cache.clear()

        assert cache.size == 0
        assert cache.get("key1") is None
        assert cache.get("key2") is None


# ============================================================================
# Cleanup Tests
# ============================================================================


class TestCleanup:
    """Test expired entry cleanup."""

    def test_cleanup_expired(self):
        """Test cleanup removes expired entries."""
        cache = PrefetchCache(default_ttl=0)

        cache.store("key1", ["v1"])
        cache.store("key2", ["v2"])

        time.sleep(0.05)

        removed = cache.cleanup_expired()

        assert removed == 2
        assert cache.size == 0

    def test_cleanup_preserves_non_expired(self):
        """Test cleanup preserves non-expired entries."""
        cache = PrefetchCache(default_ttl=60)

        cache.store("keep", ["v1"])

        removed = cache.cleanup_expired()

        assert removed == 0
        assert cache.get("keep") == ["v1"]

    def test_cleanup_mixed_entries(self):
        """Test cleanup with mixed expired and non-expired entries."""
        cache = PrefetchCache(default_ttl=60)

        cache.store("keep", ["v1"], ttl=60)
        cache.store("expire", ["v2"], ttl=0)

        time.sleep(0.05)

        removed = cache.cleanup_expired()

        assert removed == 1
        assert cache.get("keep") == ["v1"]
        assert cache.size == 1


# ============================================================================
# Statistics Tests
# ============================================================================


class TestCacheStats:
    """Test cache statistics tracking."""

    def test_initial_stats(self):
        """Test statistics start at zero."""
        cache = PrefetchCache()

        stats = cache.get_stats()

        assert stats.total_entries == 0
        assert stats.hit_count == 0
        assert stats.miss_count == 0
        assert stats.expired_count == 0
        assert stats.invalidated_count == 0
        assert stats.hit_rate == 0.0

    def test_hit_count_tracked(self):
        """Test hit count is tracked correctly."""
        cache = PrefetchCache()

        cache.store("key", ["v1"])
        cache.get("key")
        cache.get("key")

        stats = cache.get_stats()
        assert stats.hit_count == 2

    def test_miss_count_tracked(self):
        """Test miss count is tracked correctly."""
        cache = PrefetchCache()

        cache.get("nonexistent1")
        cache.get("nonexistent2")

        stats = cache.get_stats()
        assert stats.miss_count == 2

    def test_hit_rate_calculation(self):
        """Test hit rate is calculated correctly."""
        cache = PrefetchCache()

        cache.store("key", ["v1"])

        cache.get("key")          # Hit
        cache.get("key")          # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats.hit_rate == pytest.approx(2 / 3)

    def test_hit_rate_no_lookups(self):
        """Test hit rate is 0 when no lookups made."""
        cache = PrefetchCache()

        stats = cache.get_stats()
        assert stats.hit_rate == 0.0

    def test_expired_count_tracked(self):
        """Test expired count is tracked."""
        cache = PrefetchCache(default_ttl=0)

        cache.store("key", ["v1"])
        time.sleep(0.05)
        cache.get("key")

        stats = cache.get_stats()
        assert stats.expired_count == 1

    def test_stats_returns_dataclass(self):
        """Test that stats returns a PrefetchCacheStats instance."""
        cache = PrefetchCache()
        stats = cache.get_stats()
        assert isinstance(stats, PrefetchCacheStats)
