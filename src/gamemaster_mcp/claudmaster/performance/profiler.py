"""
Performance profiling for Claudmaster operations.

This module provides timing and metrics tracking for critical operations
in the AI DM system, helping identify bottlenecks and optimize performance.
"""

from __future__ import annotations

import math
import time
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class OperationMetrics:
    """Metrics for a single operation type."""
    count: int
    total_time: float
    min_time: float
    max_time: float
    avg_time: float
    p50: float
    p95: float
    p99: float


@dataclass
class PerformanceReport:
    """Summary of performance metrics."""
    operations: dict[str, OperationMetrics] = field(default_factory=dict)
    total_traces: int = 0
    bottlenecks: list[str] = field(default_factory=list)


class PerformanceProfiler:
    """
    Tracks and reports performance metrics.

    This profiler collects timing data for named operations and provides
    statistical analysis including percentiles and bottleneck detection.

    Usage:
        profiler = PerformanceProfiler()

        # Context manager for automatic timing
        with profiler.trace("player_action"):
            process_player_input()

        # Manual recording
        profiler.record("cache_lookup", 0.015)

        # Generate report
        report = profiler.get_report()
    """

    # Default thresholds (seconds)
    DEFAULT_THRESHOLDS = {
        "player_action": 10.0,
        "context_building": 1.5,
        "agent_query": 3.0,
        "state_update": 0.3,
        "cache_lookup": 0.02,
    }

    def __init__(self, thresholds: dict[str, float] | None = None):
        """
        Initialize the profiler.

        Args:
            thresholds: Custom threshold values in seconds.
                       Operations exceeding their threshold at p95 are flagged as bottlenecks.
        """
        self.metrics: dict[str, list[float]] = defaultdict(list)
        self.thresholds = thresholds if thresholds is not None else self.DEFAULT_THRESHOLDS.copy()

    @contextmanager
    def trace(self, operation: str) -> Iterator[None]:
        """
        Context manager for timing operations.

        Args:
            operation: Name of the operation being timed

        Usage:
            with profiler.trace("agent_query"):
                result = await agent.run(context)
        """
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            self.metrics[operation].append(duration)

    def record(self, operation: str, duration: float) -> None:
        """
        Manually record a timing.

        Args:
            operation: Name of the operation
            duration: Duration in seconds
        """
        self.metrics[operation].append(duration)

    def get_percentile(self, operation: str, percentile: float) -> float:
        """
        Get percentile timing (e.g., 95 for p95).

        Args:
            operation: Name of the operation
            percentile: Percentile value (0-100)

        Returns:
            The percentile value in seconds, or 0.0 if no data
        """
        if operation not in self.metrics or not self.metrics[operation]:
            return 0.0

        timings = sorted(self.metrics[operation])
        count = len(timings)

        # Calculate index: ceil(percentile/100 * count) - 1
        index = math.ceil(percentile / 100.0 * count) - 1

        # Clamp to valid range
        index = max(0, min(index, count - 1))

        return timings[index]

    def get_operation_metrics(self, operation: str) -> OperationMetrics | None:
        """
        Get full metrics for an operation.

        Args:
            operation: Name of the operation

        Returns:
            OperationMetrics object, or None if no data
        """
        if operation not in self.metrics or not self.metrics[operation]:
            return None

        timings = self.metrics[operation]
        count = len(timings)
        total = sum(timings)

        return OperationMetrics(
            count=count,
            total_time=total,
            min_time=min(timings),
            max_time=max(timings),
            avg_time=total / count,
            p50=self.get_percentile(operation, 50),
            p95=self.get_percentile(operation, 95),
            p99=self.get_percentile(operation, 99),
        )

    def get_report(self) -> PerformanceReport:
        """
        Generate comprehensive performance report.

        Returns:
            PerformanceReport with metrics for all operations
        """
        operations_metrics = {}
        total_traces = 0

        for operation in self.metrics:
            metrics = self.get_operation_metrics(operation)
            if metrics:
                operations_metrics[operation] = metrics
                total_traces += metrics.count

        bottlenecks = self.identify_bottlenecks()

        return PerformanceReport(
            operations=operations_metrics,
            total_traces=total_traces,
            bottlenecks=bottlenecks,
        )

    def identify_bottlenecks(self) -> list[str]:
        """
        Identify operations exceeding their thresholds (based on p95).

        Returns:
            List of operation names that exceed their threshold
        """
        bottlenecks = []
        default_threshold = 5.0  # Default for operations not in thresholds

        for operation in self.metrics:
            p95 = self.get_percentile(operation, 95)
            threshold = self.thresholds.get(operation, default_threshold)

            if p95 > threshold:
                bottlenecks.append(operation)

        return bottlenecks

    def reset(self) -> None:
        """Clear all collected metrics."""
        self.metrics.clear()

    def reset_operation(self, operation: str) -> None:
        """
        Clear metrics for a single operation.

        Args:
            operation: Name of the operation to reset
        """
        if operation in self.metrics:
            del self.metrics[operation]


__all__ = [
    "PerformanceProfiler",
    "PerformanceReport",
    "OperationMetrics",
]
