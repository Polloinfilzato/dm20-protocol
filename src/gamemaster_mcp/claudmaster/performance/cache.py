"""
LRU cache for module content in Claudmaster.

This module provides a size-aware LRU (Least Recently Used) cache with TTL
(Time To Live) support for frequently accessed module content, reducing
repeated PDF parsing and improving response times.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class CacheEntry:
    """
    Single cache entry with metadata.

    Tracks the cached value along with size, timestamps, and access patterns
    for LRU eviction and TTL expiration.
    """
    key: str
    value: Any
    size: int  # Approximate size in bytes
    created_at: float  # time.time()
    last_accessed: float
    access_count: int = 0


@dataclass
class CacheStats:
    """Cache performance statistics."""
    total_entries: int
    total_size_bytes: int
    max_size_bytes: int
    hit_count: int
    miss_count: int
    hit_rate: float  # 0.0-1.0
    eviction_count: int
    avg_entry_size: float


class ModuleCache:
    """
    LRU cache for frequently accessed module content.

    This cache implements LRU (Least Recently Used) eviction with TTL
    (Time To Live) support and size limits to optimize memory usage.

    Features:
    - Size-aware eviction (tracks approximate memory usage)
    - TTL expiration for stale entries
    - LRU eviction when size limit is exceeded
    - Pattern-based invalidation
    - Performance statistics (hit rate, eviction count)

    Usage:
        cache = ModuleCache(max_size_mb=50, ttl_minutes=30)

        # Store data
        cache.put("module_123_chapter_1", content, size=1024)

        # Retrieve data
        content = cache.get("module_123_chapter_1")  # Returns None if miss or expired

        # Invalidate patterns
        cache.invalidate_pattern("module_123")  # Removes all module_123_* entries
    """

    def __init__(self, max_size_mb: int = 50, ttl_minutes: int = 30):
        """
        Initialize the cache.

        Args:
            max_size_mb: Maximum cache size in megabytes
            ttl_minutes: Time to live for cache entries in minutes
        """
        self.cache: dict[str, CacheEntry] = {}
        self.max_size = max_size_mb * 1024 * 1024
        self.ttl = ttl_minutes * 60
        self._current_size = 0
        self._hit_count = 0
        self._miss_count = 0
        self._eviction_count = 0

    def get(self, key: str) -> Any | None:
        """
        Get cached item. Returns None if miss or expired.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        if key not in self.cache:
            self._miss_count += 1
            return None

        entry = self.cache[key]

        # Check TTL expiration
        if self._is_expired(entry):
            # Remove expired entry
            self._current_size -= entry.size
            del self.cache[key]
            self._miss_count += 1
            return None

        # Update access metadata
        entry.last_accessed = time.time()
        entry.access_count += 1
        self._hit_count += 1

        return entry.value

    def put(self, key: str, value: Any, size: int) -> None:
        """
        Cache item with LRU eviction if needed.

        Args:
            key: Cache key
            value: Value to cache
            size: Approximate size in bytes
        """
        current_time = time.time()

        # If key exists, remove old entry first
        if key in self.cache:
            old_entry = self.cache[key]
            self._current_size -= old_entry.size
            del self.cache[key]

        # Evict LRU entries until there's room
        needed_space = size
        if self._current_size + needed_space > self.max_size:
            self._evict_lru(needed_space)

        # Add new entry
        entry = CacheEntry(
            key=key,
            value=value,
            size=size,
            created_at=current_time,
            last_accessed=current_time,
            access_count=0,
        )

        self.cache[key] = entry
        self._current_size += size

    def invalidate(self, key: str) -> bool:
        """
        Remove specific entry.

        Args:
            key: Cache key to remove

        Returns:
            True if entry existed and was removed, False otherwise
        """
        if key in self.cache:
            entry = self.cache[key]
            self._current_size -= entry.size
            del self.cache[key]
            return True
        return False

    def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate entries whose keys contain the pattern string.

        Args:
            pattern: Substring pattern to match

        Returns:
            Number of entries removed
        """
        # Find matching keys
        matching_keys = [key for key in self.cache if pattern in key]

        # Remove them
        count = 0
        for key in matching_keys:
            if self.invalidate(key):
                count += 1

        return count

    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
        self._current_size = 0

    def get_stats(self) -> CacheStats:
        """
        Return cache performance statistics.

        Returns:
            CacheStats object with current cache metrics
        """
        total_entries = len(self.cache)
        total_requests = self._hit_count + self._miss_count

        hit_rate = 0.0
        if total_requests > 0:
            hit_rate = self._hit_count / total_requests

        avg_entry_size = 0.0
        if total_entries > 0:
            avg_entry_size = self._current_size / total_entries

        return CacheStats(
            total_entries=total_entries,
            total_size_bytes=self._current_size,
            max_size_bytes=self.max_size,
            hit_count=self._hit_count,
            miss_count=self._miss_count,
            hit_rate=hit_rate,
            eviction_count=self._eviction_count,
            avg_entry_size=avg_entry_size,
        )

    def _evict_lru(self, needed_space: int) -> None:
        """
        Evict least recently used entries until needed_space is freed.

        Args:
            needed_space: Amount of space to free in bytes
        """
        # Sort entries by last_accessed (oldest first)
        sorted_entries = sorted(
            self.cache.items(),
            key=lambda item: item[1].last_accessed
        )

        freed_space = 0
        for key, entry in sorted_entries:
            if self._current_size - freed_space + needed_space <= self.max_size:
                break

            # Evict this entry
            freed_space += entry.size
            del self.cache[key]
            self._eviction_count += 1

        self._current_size -= freed_space

    def _is_expired(self, entry: CacheEntry) -> bool:
        """
        Check if entry has exceeded TTL.

        Args:
            entry: Cache entry to check

        Returns:
            True if entry is expired, False otherwise
        """
        current_time = time.time()
        return (current_time - entry.created_at) > self.ttl


__all__ = [
    "ModuleCache",
    "CacheEntry",
    "CacheStats",
]
