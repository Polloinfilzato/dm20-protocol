"""
Performance optimization components for the Claudmaster multi-agent system.

This module provides tools for profiling, caching, and lazy loading to
optimize the performance of the AI DM system.
"""

from __future__ import annotations

from dm20_protocol.claudmaster.performance.profiler import (
    PerformanceProfiler,
    PerformanceReport,
    OperationMetrics,
)
from dm20_protocol.claudmaster.performance.cache import (
    ModuleCache,
    CacheEntry,
    CacheStats,
)
from dm20_protocol.claudmaster.performance.lazy_load import (
    LazyLoadManager,
    LoadableSection,
)
from dm20_protocol.claudmaster.performance.parallel_executor import (
    ParallelAgentExecutor,
    ExecutionBatch,
    ParallelExecutionResult,
)
from dm20_protocol.claudmaster.performance.context_optimizer import (
    OptimizedContextBuilder,
    ContextBuildResult,
)
from dm20_protocol.claudmaster.performance.benchmarks import (
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
