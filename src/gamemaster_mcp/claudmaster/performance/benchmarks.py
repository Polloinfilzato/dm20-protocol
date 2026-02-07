"""
Performance benchmarking for the Claudmaster AI DM system.

This module provides a framework for running performance benchmarks,
collecting metrics, and comparing results against target thresholds.
"""

from __future__ import annotations

import asyncio
import inspect
import math
import time
from dataclasses import dataclass, field
from typing import Callable


@dataclass
class BenchmarkResult:
    """Result of a single benchmark."""
    name: str
    iterations: int
    times: list[float]
    min_time: float
    max_time: float
    avg_time: float
    p50: float
    p95: float
    p99: float


@dataclass
class BenchmarkSuite:
    """Results of a full benchmark run."""
    results: list[BenchmarkResult]
    total_time: float
    target_comparison: list[str] = field(default_factory=list)  # Human-readable comparison notes


# Performance targets (seconds)
PERFORMANCE_TARGETS = {
    "player_action": {"p50": 3.0, "p95": 10.0, "p99": 15.0},
    "context_building": {"p50": 0.5, "p95": 1.5, "p99": 3.0},
    "agent_query": {"p50": 1.0, "p95": 3.0, "p99": 5.0},
    "state_update": {"p50": 0.1, "p95": 0.3, "p99": 0.5},
    "cache_lookup": {"p50": 0.005, "p95": 0.02, "p99": 0.05},
}


class PerformanceBenchmark:
    """
    Runs performance benchmarks for the Claudmaster system.

    This class manages benchmark registration, execution, and result analysis.
    Benchmarks can be sync or async functions and are run multiple times
    to collect statistical data.

    Usage:
        benchmark = PerformanceBenchmark()

        # Register benchmarks
        benchmark.register_benchmark("cache_lookup", lambda: cache.get("key"))
        benchmark.register_benchmark("agent_query", lambda: agent.run(request))

        # Run all
        suite = await benchmark.run_all(iterations=100)

        # Compare to targets
        comparison = benchmark.compare_to_targets(suite)
        for line in comparison:
            print(line)
    """

    def __init__(self):
        """Initialize the benchmark runner."""
        self._benchmarks: dict[str, Callable] = {}

    def register_benchmark(self, name: str, func: Callable) -> None:
        """
        Register a benchmark function.

        The function can be sync or async. It will be called multiple times
        during benchmark execution.

        Args:
            name: Name of the benchmark
            func: The function to benchmark (sync or async)
        """
        self._benchmarks[name] = func

    async def run_benchmark(
        self,
        name: str,
        iterations: int = 100,
    ) -> BenchmarkResult:
        """
        Run a single named benchmark.

        Args:
            name: Name of the benchmark to run
            iterations: Number of times to run the benchmark (default: 100)

        Returns:
            BenchmarkResult with timing statistics

        Raises:
            KeyError: If benchmark name is not registered
        """
        if name not in self._benchmarks:
            raise KeyError(f"Benchmark '{name}' not registered")

        func = self._benchmarks[name]
        times: list[float] = []

        # Determine if function is async
        is_async = inspect.iscoroutinefunction(func)

        # Run iterations
        for _ in range(iterations):
            start = time.perf_counter()

            if is_async:
                await func()
            else:
                func()

            duration = time.perf_counter() - start
            times.append(duration)

        # Compute statistics
        return BenchmarkResult(
            name=name,
            iterations=iterations,
            times=times,
            min_time=min(times),
            max_time=max(times),
            avg_time=sum(times) / len(times),
            p50=self._compute_percentile(times, 50),
            p95=self._compute_percentile(times, 95),
            p99=self._compute_percentile(times, 99),
        )

    async def run_all(self, iterations: int = 100) -> BenchmarkSuite:
        """
        Run all registered benchmarks.

        Benchmarks are run sequentially. The total time includes all
        benchmark execution time.

        Args:
            iterations: Number of iterations per benchmark (default: 100)

        Returns:
            BenchmarkSuite with results from all benchmarks
        """
        suite_start = time.perf_counter()
        results: list[BenchmarkResult] = []

        for name in self._benchmarks:
            result = await self.run_benchmark(name, iterations)
            results.append(result)

        total_time = time.perf_counter() - suite_start

        # Generate target comparison
        comparison = self.compare_to_targets(BenchmarkSuite(
            results=results,
            total_time=total_time,
            target_comparison=[],
        ))

        return BenchmarkSuite(
            results=results,
            total_time=total_time,
            target_comparison=comparison,
        )

    def compare_to_targets(
        self,
        suite: BenchmarkSuite,
    ) -> list[str]:
        """
        Compare results to PERFORMANCE_TARGETS.

        Generates human-readable comparison messages like:
        - "✅ cache_lookup p95: 0.015s (target: 0.02s)"
        - "❌ agent_query p95: 4.5s (target: 3.0s)"

        Args:
            suite: The benchmark suite to compare

        Returns:
            List of comparison message strings
        """
        messages: list[str] = []

        for result in suite.results:
            # Check if this benchmark has targets
            if result.name not in PERFORMANCE_TARGETS:
                # No targets defined for this benchmark
                messages.append(f"ℹ️  {result.name}: no targets defined")
                continue

            targets = PERFORMANCE_TARGETS[result.name]

            # Compare p50, p95, p99
            for percentile_name in ["p50", "p95", "p99"]:
                if percentile_name not in targets:
                    continue

                target_value = targets[percentile_name]
                actual_value = getattr(result, percentile_name)

                # Determine pass/fail
                if actual_value <= target_value:
                    status = "✅"
                else:
                    status = "❌"

                messages.append(
                    f"{status} {result.name} {percentile_name}: "
                    f"{actual_value:.3f}s (target: {target_value}s)"
                )

        return messages

    @staticmethod
    def _compute_percentile(values: list[float], percentile: float) -> float:
        """
        Compute percentile from list of values.

        Args:
            values: List of numeric values
            percentile: Percentile to compute (0-100)

        Returns:
            The percentile value
        """
        if not values:
            return 0.0

        sorted_values = sorted(values)
        count = len(sorted_values)

        # Calculate index: ceil(percentile/100 * count) - 1
        index = math.ceil(percentile / 100.0 * count) - 1

        # Clamp to valid range
        index = max(0, min(index, count - 1))

        return sorted_values[index]


__all__ = [
    "BenchmarkResult",
    "BenchmarkSuite",
    "PERFORMANCE_TARGETS",
    "PerformanceBenchmark",
]
