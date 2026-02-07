"""
Performance optimization components for the Claudmaster multi-agent system.

This module provides tools for profiling, caching, and lazy loading to
optimize the performance of the AI DM system.
"""

from __future__ import annotations

from gamemaster_mcp.claudmaster.performance.profiler import (
    PerformanceProfiler,
    PerformanceReport,
    OperationMetrics,
)
from gamemaster_mcp.claudmaster.performance.cache import (
    ModuleCache,
    CacheEntry,
    CacheStats,
)
from gamemaster_mcp.claudmaster.performance.lazy_load import (
    LazyLoadManager,
    LoadableSection,
)

__all__ = [
    "PerformanceProfiler",
    "PerformanceReport",
    "OperationMetrics",
    "ModuleCache",
    "CacheEntry",
    "CacheStats",
    "LazyLoadManager",
    "LoadableSection",
]
