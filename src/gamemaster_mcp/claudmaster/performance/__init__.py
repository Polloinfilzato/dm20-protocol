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
from gamemaster_mcp.claudmaster.performance.parallel_executor import (
    ParallelAgentExecutor,
    ExecutionBatch,
    ParallelExecutionResult,
)
from gamemaster_mcp.claudmaster.performance.context_optimizer import (
    OptimizedContextBuilder,
    ContextBuildResult,
)
from gamemaster_mcp.claudmaster.performance.benchmarks import (
    PerformanceBenchmark,
    BenchmarkResult,
    BenchmarkSuite,
    PERFORMANCE_TARGETS,
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
    "ParallelAgentExecutor",
    "ExecutionBatch",
    "ParallelExecutionResult",
    "OptimizedContextBuilder",
    "ContextBuildResult",
    "PerformanceBenchmark",
    "BenchmarkResult",
    "BenchmarkSuite",
    "PERFORMANCE_TARGETS",
]
