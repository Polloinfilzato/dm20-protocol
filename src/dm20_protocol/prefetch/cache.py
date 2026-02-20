"""
TTL-based cache for pre-generated narrative variants.

This module provides a lightweight cache specifically designed for the prefetch
engine. It stores pre-generated narrative variants with TTL-based expiration
and pattern-based invalidation, optimized for the short-lived nature of
combat turn predictions.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger("dm20-protocol")


@dataclass
class CacheEntry:
    """Single cache entry with TTL metadata.

    Attributes:
        key: Cache key identifier.
        variants: List of pre-generated narrative variants.
        created_at: Timestamp when entry was created.
        ttl: Time to live in seconds.
        metadata: Optional metadata about the cached variants.
    """
    key: str
    variants: list[str]
    created_at: float
    ttl: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class PrefetchCacheStats:
    """Statistics for the prefetch cache.

    Attributes:
        total_entries: Number of entries currently in cache.
        hit_count: Number of successful cache lookups.
        miss_count: Number of failed cache lookups.
        expired_count: Number of entries that expired on access.
        invalidated_count: Number of entries explicitly invalidated.
        hit_rate: Ratio of hits to total lookups (0.0-1.0).
    """
    total_entries: int
    hit_count: int
    miss_count: int
    expired_count: int
    invalidated_count: int
    hit_rate: float


class PrefetchCache:
    """TTL-based cache for pre-generated narrative variants.

    Stores pre-generated narrative variants with configurable TTL and
    supports pattern-based invalidation for when game state changes
    unexpectedly. Designed for the short-lived nature of combat turn
    predictions where variants become stale quickly.

    Features:
    - TTL-based expiration (default 60 seconds)
    - Pattern-based invalidation (e.g., invalidate all combat variants)
    - Automatic expired entry cleanup on access
    - Performance statistics tracking

    Usage:
        cache = PrefetchCache(default_ttl=60)

        # Store variants for a combat turn
        cache.store("combat_turn_5_goblin", ["Hit variant", "Miss variant", "Crit variant"])

        # Retrieve variants
        variants = cache.get("combat_turn_5_goblin")

        # Invalidate when state changes
        cache.invalidate("combat_turn_5")  # Pattern match
    """

    def __init__(self, default_ttl: int = 60) -> None:
        """Initialize the prefetch cache.

        Args:
            default_ttl: Default time to live for cache entries in seconds.
        """
        self._cache: dict[str, CacheEntry] = {}
        self.default_ttl = default_ttl
        self._hit_count = 0
        self._miss_count = 0
        self._expired_count = 0
        self._invalidated_count = 0

    def store(
        self,
        key: str,
        variants: list[str],
        ttl: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Store pre-generated variants in the cache.

        If an entry with the same key already exists, it is replaced.

        Args:
            key: Unique cache key for these variants.
            variants: List of pre-generated narrative variant strings.
            ttl: Time to live in seconds. Uses default_ttl if not specified.
            metadata: Optional metadata to associate with the entry.
        """
        effective_ttl = ttl if ttl is not None else self.default_ttl

        entry = CacheEntry(
            key=key,
            variants=list(variants),  # Defensive copy
            created_at=time.time(),
            ttl=effective_ttl,
            metadata=metadata or {},
        )

        self._cache[key] = entry
        logger.debug(
            f"Prefetch cache: stored {len(variants)} variants for key '{key}' "
            f"(TTL: {effective_ttl}s)"
        )

    def get(self, key: str) -> list[str] | None:
        """Retrieve cached variants for a key.

        Returns None if the key is not found or the entry has expired.
        Expired entries are automatically removed on access.

        Args:
            key: Cache key to look up.

        Returns:
            List of variant strings, or None if not found or expired.
        """
        if key not in self._cache:
            self._miss_count += 1
            return None

        entry = self._cache[key]

        # Check TTL expiration
        if self._is_expired(entry):
            del self._cache[key]
            self._expired_count += 1
            self._miss_count += 1
            logger.debug(f"Prefetch cache: entry '{key}' expired")
            return None

        self._hit_count += 1
        logger.debug(
            f"Prefetch cache: hit for key '{key}' "
            f"({len(entry.variants)} variants)"
        )
        return list(entry.variants)  # Defensive copy

    def invalidate(self, pattern: str) -> int:
        """Invalidate cache entries whose keys contain the pattern.

        This performs substring matching: any key that contains the
        pattern string will be removed.

        Args:
            pattern: Substring pattern to match against cache keys.

        Returns:
            Number of entries invalidated.
        """
        matching_keys = [key for key in self._cache if pattern in key]

        for key in matching_keys:
            del self._cache[key]
            self._invalidated_count += 1

        if matching_keys:
            logger.debug(
                f"Prefetch cache: invalidated {len(matching_keys)} entries "
                f"matching pattern '{pattern}'"
            )

        return len(matching_keys)

    def invalidate_key(self, key: str) -> bool:
        """Invalidate a single cache entry by exact key.

        Args:
            key: Exact cache key to remove.

        Returns:
            True if the entry existed and was removed, False otherwise.
        """
        if key in self._cache:
            del self._cache[key]
            self._invalidated_count += 1
            return True
        return False

    def clear(self) -> None:
        """Remove all entries from the cache."""
        count = len(self._cache)
        self._cache.clear()
        if count > 0:
            logger.debug(f"Prefetch cache: cleared {count} entries")

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the cache.

        This is useful for periodic maintenance to prevent memory leaks
        from entries that are never accessed after expiration.

        Returns:
            Number of expired entries removed.
        """
        current_time = time.time()
        expired_keys = [
            key for key, entry in self._cache.items()
            if (current_time - entry.created_at) > entry.ttl
        ]

        for key in expired_keys:
            del self._cache[key]
            self._expired_count += 1

        if expired_keys:
            logger.debug(
                f"Prefetch cache: cleanup removed {len(expired_keys)} expired entries"
            )

        return len(expired_keys)

    def get_stats(self) -> PrefetchCacheStats:
        """Return cache performance statistics.

        Returns:
            PrefetchCacheStats with current metrics.
        """
        total_lookups = self._hit_count + self._miss_count
        hit_rate = self._hit_count / total_lookups if total_lookups > 0 else 0.0

        return PrefetchCacheStats(
            total_entries=len(self._cache),
            hit_count=self._hit_count,
            miss_count=self._miss_count,
            expired_count=self._expired_count,
            invalidated_count=self._invalidated_count,
            hit_rate=hit_rate,
        )

    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if an entry has exceeded its TTL.

        Args:
            entry: Cache entry to check.

        Returns:
            True if the entry is expired, False otherwise.
        """
        return (time.time() - entry.created_at) > entry.ttl

    @property
    def size(self) -> int:
        """Return the number of entries currently in the cache."""
        return len(self._cache)


__all__ = [
    "PrefetchCache",
    "CacheEntry",
    "PrefetchCacheStats",
]
