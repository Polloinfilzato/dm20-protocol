"""
Tests for Module Cache and Lazy Load Manager (Issue #68 Stream A).

Tests cover:
- Cache get/put operations
- TTL expiration
- LRU eviction
- Invalidation (single and pattern)
- Cache statistics
- Max size enforcement
- Lazy load manager section registration
- Synchronous and asynchronous loading
- Preload priorities
- Section unloading
"""

from __future__ import annotations

import asyncio
import time

import pytest

# Configure pytest to use anyio with asyncio backend for async tests
pytestmark = pytest.mark.anyio

from dm20_protocol.claudmaster.performance.cache import (
    ModuleCache,
    CacheEntry,
    CacheStats,
)
from dm20_protocol.claudmaster.performance.lazy_load import (
    LazyLoadManager,
    LoadableSection,
)


# ============================================================================
# ModuleCache Basic Tests
# ============================================================================

class TestModuleCacheBasic:
    """Test basic cache operations."""

    def test_put_and_get(self):
        """Test basic put and get operations."""
        cache = ModuleCache(max_size_mb=10, ttl_minutes=30)

        cache.put("key1", "value1", size=100)
        result = cache.get("key1")

        assert result == "value1"

    def test_get_nonexistent(self):
        """Test getting nonexistent key returns None."""
        cache = ModuleCache()
        assert cache.get("nonexistent") is None

    def test_get_miss_increments_counter(self):
        """Test that cache misses are counted."""
        cache = ModuleCache()
        cache.get("nonexistent")

        stats = cache.get_stats()
        assert stats.miss_count == 1
        assert stats.hit_count == 0

    def test_get_hit_increments_counter(self):
        """Test that cache hits are counted."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)
        cache.get("key1")

        stats = cache.get_stats()
        assert stats.hit_count == 1
        assert stats.miss_count == 0

    def test_update_existing_key(self):
        """Test updating an existing key."""
        cache = ModuleCache()

        cache.put("key1", "value1", size=100)
        cache.put("key1", "value2", size=150)

        result = cache.get("key1")
        assert result == "value2"

        # Old size should be replaced
        stats = cache.get_stats()
        assert stats.total_size_bytes == 150

    def test_access_updates_metadata(self):
        """Test that accessing entry updates last_accessed and access_count."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)

        time.sleep(0.01)
        cache.get("key1")

        entry = cache.cache["key1"]
        assert entry.access_count == 1
        assert entry.last_accessed > entry.created_at


# ============================================================================
# TTL Expiration Tests
# ============================================================================

class TestTTLExpiration:
    """Test TTL expiration behavior."""

    def test_expired_entry_returns_none(self):
        """Test that expired entries return None."""
        cache = ModuleCache(max_size_mb=10, ttl_minutes=0)  # 0 minute TTL

        cache.put("key1", "value1", size=100)
        time.sleep(0.1)  # Wait for expiration

        result = cache.get("key1")
        assert result is None

    def test_expired_entry_removed(self):
        """Test that expired entries are removed from cache."""
        cache = ModuleCache(max_size_mb=10, ttl_minutes=0)

        cache.put("key1", "value1", size=100)
        time.sleep(0.1)

        cache.get("key1")  # Should trigger removal

        stats = cache.get_stats()
        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0

    def test_expired_counts_as_miss(self):
        """Test that accessing expired entry counts as miss."""
        cache = ModuleCache(max_size_mb=10, ttl_minutes=0)

        cache.put("key1", "value1", size=100)
        time.sleep(0.1)

        cache.get("key1")

        stats = cache.get_stats()
        assert stats.miss_count == 1
        assert stats.hit_count == 0


# ============================================================================
# LRU Eviction Tests
# ============================================================================

class TestLRUEviction:
    """Test LRU eviction behavior."""

    def test_eviction_when_size_exceeded(self):
        """Test that entries are evicted when size limit is exceeded."""
        cache = ModuleCache(max_size_mb=1, ttl_minutes=30)  # 1 MB = 1048576 bytes

        # Fill cache close to limit
        cache.put("key1", "value1", size=500000)
        cache.put("key2", "value2", size=500000)

        # This should trigger eviction of key1 (LRU)
        cache.put("key3", "value3", size=200000)

        assert cache.get("key1") is None  # Evicted
        assert cache.get("key2") is not None
        assert cache.get("key3") is not None

    def test_lru_evicts_oldest_access(self):
        """Test that LRU evicts least recently accessed entry."""
        cache = ModuleCache(max_size_mb=1, ttl_minutes=30)

        cache.put("key1", "value1", size=400000)
        cache.put("key2", "value2", size=400000)

        # Access key1 to make it more recent
        cache.get("key1")

        # This should evict key2 (older access)
        cache.put("key3", "value3", size=400000)

        assert cache.get("key1") is not None
        assert cache.get("key2") is None  # Evicted
        assert cache.get("key3") is not None

    def test_eviction_count_tracked(self):
        """Test that eviction count is tracked."""
        cache = ModuleCache(max_size_mb=1, ttl_minutes=30)

        cache.put("key1", "value1", size=600000)
        cache.put("key2", "value2", size=600000)  # Should evict key1

        stats = cache.get_stats()
        assert stats.eviction_count >= 1


# ============================================================================
# Invalidation Tests
# ============================================================================

class TestInvalidation:
    """Test cache invalidation operations."""

    def test_invalidate_existing_key(self):
        """Test invalidating existing key."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)

        result = cache.invalidate("key1")
        assert result is True
        assert cache.get("key1") is None

    def test_invalidate_nonexistent_key(self):
        """Test invalidating nonexistent key."""
        cache = ModuleCache()
        result = cache.invalidate("nonexistent")
        assert result is False

    def test_invalidate_updates_size(self):
        """Test that invalidation updates total size."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)

        cache.invalidate("key1")

        stats = cache.get_stats()
        assert stats.total_size_bytes == 0

    def test_invalidate_pattern_basic(self):
        """Test pattern-based invalidation."""
        cache = ModuleCache()
        cache.put("module_123_ch1", "data1", size=100)
        cache.put("module_123_ch2", "data2", size=100)
        cache.put("module_456_ch1", "data3", size=100)

        count = cache.invalidate_pattern("module_123")

        assert count == 2
        assert cache.get("module_123_ch1") is None
        assert cache.get("module_123_ch2") is None
        assert cache.get("module_456_ch1") is not None

    def test_invalidate_pattern_no_matches(self):
        """Test pattern invalidation with no matches."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)

        count = cache.invalidate_pattern("nonexistent")
        assert count == 0

    def test_clear_all(self):
        """Test clearing all cache entries."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)
        cache.put("key2", "value2", size=200)

        cache.clear()

        stats = cache.get_stats()
        assert stats.total_entries == 0
        assert stats.total_size_bytes == 0


# ============================================================================
# Cache Statistics Tests
# ============================================================================

class TestCacheStats:
    """Test cache statistics."""

    def test_stats_basic(self):
        """Test basic statistics calculation."""
        cache = ModuleCache(max_size_mb=10, ttl_minutes=30)
        cache.put("key1", "value1", size=100)
        cache.put("key2", "value2", size=200)

        stats = cache.get_stats()

        assert stats.total_entries == 2
        assert stats.total_size_bytes == 300
        assert stats.max_size_bytes == 10 * 1024 * 1024

    def test_hit_rate_calculation(self):
        """Test hit rate calculation."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)

        cache.get("key1")  # Hit
        cache.get("key1")  # Hit
        cache.get("nonexistent")  # Miss

        stats = cache.get_stats()
        assert stats.hit_count == 2
        assert stats.miss_count == 1
        assert stats.hit_rate == pytest.approx(2/3)

    def test_hit_rate_no_requests(self):
        """Test hit rate when no requests made."""
        cache = ModuleCache()
        stats = cache.get_stats()
        assert stats.hit_rate == 0.0

    def test_avg_entry_size(self):
        """Test average entry size calculation."""
        cache = ModuleCache()
        cache.put("key1", "value1", size=100)
        cache.put("key2", "value2", size=200)

        stats = cache.get_stats()
        assert stats.avg_entry_size == 150.0

    def test_avg_entry_size_empty_cache(self):
        """Test average entry size with empty cache."""
        cache = ModuleCache()
        stats = cache.get_stats()
        assert stats.avg_entry_size == 0.0


# ============================================================================
# LazyLoadManager Basic Tests
# ============================================================================

class TestLazyLoadManagerBasic:
    """Test basic lazy load manager functionality."""

    def test_register_section(self):
        """Test registering a section."""
        manager = LazyLoadManager()

        def loader():
            return "test_data"

        manager.register_section("test_section", loader, priority=10)

        assert "test_section" in manager.sections
        assert manager.sections["test_section"].priority == 10

    def test_is_loaded_false(self):
        """Test is_loaded returns False for unloaded section."""
        manager = LazyLoadManager()
        manager.register_section("test", lambda: "data")

        assert not manager.is_loaded("test")

    def test_is_loaded_true(self):
        """Test is_loaded returns True after loading."""
        manager = LazyLoadManager()
        manager.register_section("test", lambda: "data")

        manager.ensure_loaded("test")
        assert manager.is_loaded("test")

    def test_ensure_loaded_synchronous(self):
        """Test ensure_loaded loads section synchronously."""
        manager = LazyLoadManager()

        def loader():
            return "loaded_data"

        manager.register_section("test", loader)
        manager.ensure_loaded("test")

        assert manager.sections["test"].loaded
        assert manager.sections["test"].data == "loaded_data"

    def test_ensure_loaded_multiple_sections(self):
        """Test ensure_loaded with multiple sections."""
        manager = LazyLoadManager()

        manager.register_section("sec1", lambda: "data1")
        manager.register_section("sec2", lambda: "data2")

        manager.ensure_loaded("sec1", "sec2")

        assert manager.is_loaded("sec1")
        assert manager.is_loaded("sec2")

    def test_ensure_loaded_nonexistent_section(self):
        """Test ensure_loaded with nonexistent section (should not error)."""
        manager = LazyLoadManager()
        manager.ensure_loaded("nonexistent")  # Should not raise

    def test_ensure_loaded_idempotent(self):
        """Test that ensure_loaded doesn't reload already loaded section."""
        manager = LazyLoadManager()

        call_count = 0

        def loader():
            nonlocal call_count
            call_count += 1
            return "data"

        manager.register_section("test", loader)

        manager.ensure_loaded("test")
        manager.ensure_loaded("test")  # Second call

        assert call_count == 1  # Should only load once


# ============================================================================
# LazyLoadManager Async Tests
# ============================================================================


async def test_load_background_sync_loader():
    """Test background loading with sync loader."""
    manager = LazyLoadManager()

    def loader():
        return "background_data"

    manager.register_section("test", loader)
    await manager.load_background("test")

    assert manager.is_loaded("test")
    assert manager.sections["test"].data == "background_data"


async def test_load_background_async_loader():
    """Test background loading with async loader."""
    manager = LazyLoadManager()

    async def async_loader():
        await asyncio.sleep(0.01)
        return "async_data"

    manager.register_section("test", async_loader)
    await manager.load_background("test")

    assert manager.is_loaded("test")
    assert manager.sections["test"].data == "async_data"


async def test_load_background_nonexistent():
    """Test background loading nonexistent section (should not error)."""
    manager = LazyLoadManager()
    await manager.load_background("nonexistent")  # Should not raise


async def test_preload_for_action_combat():
    """Test preloading sections for combat action."""
    manager = LazyLoadManager()

    manager.register_section("encounters", lambda: "encounter_data", priority=10)
    manager.register_section("monsters", lambda: "monster_data", priority=5)
    manager.register_section("lore", lambda: "lore_data", priority=1)

    await manager.preload_for_action("combat")

    # Combat should preload encounters and monsters, not lore
    assert manager.is_loaded("encounters")
    assert manager.is_loaded("monsters")
    assert not manager.is_loaded("lore")


async def test_preload_for_action_exploration():
    """Test preloading sections for exploration action."""
    manager = LazyLoadManager()

    manager.register_section("locations", lambda: "loc_data", priority=10)
    manager.register_section("traps", lambda: "trap_data", priority=5)
    manager.register_section("monsters", lambda: "monster_data", priority=1)

    await manager.preload_for_action("exploration")

    # Exploration should preload locations and traps, not monsters
    assert manager.is_loaded("locations")
    assert manager.is_loaded("traps")
    assert not manager.is_loaded("monsters")


async def test_preload_unknown_action():
    """Test preload with unknown action type (should not error)."""
    manager = LazyLoadManager()
    manager.register_section("test", lambda: "data")

    await manager.preload_for_action("unknown_action")  # Should not raise
    assert not manager.is_loaded("test")


# ============================================================================
# LazyLoadManager Priority Tests
# ============================================================================

class TestLazyLoadPriority:
    """Test lazy load priority system."""

    def test_get_load_priority(self):
        """Test getting load priority for action type."""
        manager = LazyLoadManager()

        manager.register_section("encounters", lambda: "data", priority=10)
        manager.register_section("monsters", lambda: "data", priority=5)
        manager.register_section("rules", lambda: "data", priority=1)

        priorities = manager.get_load_priority("combat")

        # Should be ordered by priority (highest first)
        assert priorities == ["encounters", "monsters", "rules"]

    def test_get_load_priority_filters_unregistered(self):
        """Test that priority list only includes registered sections."""
        manager = LazyLoadManager()

        # Only register encounters, not monsters or rules
        manager.register_section("encounters", lambda: "data", priority=10)

        priorities = manager.get_load_priority("combat")

        # Should only include registered section
        assert priorities == ["encounters"]

    def test_get_load_priority_unknown_action(self):
        """Test priority for unknown action type."""
        manager = LazyLoadManager()
        priorities = manager.get_load_priority("unknown_action")
        assert priorities == []


# ============================================================================
# LazyLoadManager Management Tests
# ============================================================================

class TestLazyLoadManagement:
    """Test section management operations."""

    def test_get_loaded_sections(self):
        """Test getting list of loaded sections."""
        manager = LazyLoadManager()

        manager.register_section("sec1", lambda: "data1")
        manager.register_section("sec2", lambda: "data2")
        manager.register_section("sec3", lambda: "data3")

        manager.ensure_loaded("sec1", "sec2")

        loaded = manager.get_loaded_sections()
        assert set(loaded) == {"sec1", "sec2"}

    def test_unload_section(self):
        """Test unloading a section."""
        manager = LazyLoadManager()
        manager.register_section("test", lambda: "data")

        manager.ensure_loaded("test")
        assert manager.is_loaded("test")

        manager.unload_section("test")
        assert not manager.is_loaded("test")
        assert manager.sections["test"].data is None

    def test_unload_all(self):
        """Test unloading all sections."""
        manager = LazyLoadManager()

        manager.register_section("sec1", lambda: "data1")
        manager.register_section("sec2", lambda: "data2")

        manager.ensure_loaded("sec1", "sec2")

        manager.unload_all()

        assert not manager.is_loaded("sec1")
        assert not manager.is_loaded("sec2")
        assert manager.sections["sec1"].data is None
        assert manager.sections["sec2"].data is None


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining cache and lazy load."""

    def test_cache_and_lazy_load_workflow(self):
        """Test realistic workflow using both cache and lazy load."""
        cache = ModuleCache(max_size_mb=10, ttl_minutes=30)
        manager = LazyLoadManager()

        # Register section with loader that uses cache
        def load_encounters():
            cached = cache.get("encounters_data")
            if cached:
                return cached

            # Simulate expensive load
            data = "expensive_encounter_data"
            cache.put("encounters_data", data, size=1000)
            return data

        manager.register_section("encounters", load_encounters)

        # First load should hit loader and cache
        manager.ensure_loaded("encounters")
        data1 = manager.sections["encounters"].data

        # Unload and reload - should hit cache
        manager.unload_section("encounters")
        manager.ensure_loaded("encounters")
        data2 = manager.sections["encounters"].data

        assert data1 == data2

        stats = cache.get_stats()
        assert stats.hit_count >= 1
