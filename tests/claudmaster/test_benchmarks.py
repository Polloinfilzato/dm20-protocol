"""
Tests for PerformanceBenchmark and OptimizedContextBuilder (Issue #68 Stream B).

Tests cover:
- Benchmark registration and execution
- Sync and async benchmark functions
- Percentile computation
- Target comparison
- Suite execution
- Context building with relevance scoring
- Cache integration
- Budget enforcement
"""

from __future__ import annotations

import asyncio
import time

import pytest

from gamemaster_mcp.claudmaster.base import AgentRequest
from gamemaster_mcp.claudmaster.performance.benchmarks import (
    BenchmarkResult,
    BenchmarkSuite,
    PERFORMANCE_TARGETS,
    PerformanceBenchmark,
)
from gamemaster_mcp.claudmaster.performance.context_optimizer import (
    ContextBuildResult,
    OptimizedContextBuilder,
)


# ============================================================================
# Mock Cache for Testing
# ============================================================================

class MockCache:
    """Simple in-memory cache for testing."""

    def __init__(self):
        self.store: dict[str, str] = {}
        self.get_count = 0
        self.put_count = 0

    def get(self, key: str) -> str | None:
        self.get_count += 1
        return self.store.get(key)

    def put(self, key: str, value: str, size_bytes: int) -> None:
        self.put_count += 1
        self.store[key] = value


# ============================================================================
# Test PerformanceBenchmark
# ============================================================================

class TestPerformanceBenchmark:
    """Test benchmark execution and reporting."""

    @pytest.mark.anyio
    async def test_register_and_run_sync(self):
        """Test registering and running a sync benchmark."""
        benchmark = PerformanceBenchmark()

        call_count = 0

        def sync_func():
            nonlocal call_count
            call_count += 1
            time.sleep(0.001)

        benchmark.register_benchmark("test_sync", sync_func)

        result = await benchmark.run_benchmark("test_sync", iterations=10)

        assert isinstance(result, BenchmarkResult)
        assert result.name == "test_sync"
        assert result.iterations == 10
        assert len(result.times) == 10
        assert call_count == 10

        # Check statistics
        assert result.min_time > 0
        assert result.max_time > 0
        assert result.avg_time > 0
        assert result.p50 > 0
        assert result.p95 > 0
        assert result.p99 > 0

    @pytest.mark.anyio
    async def test_register_and_run_async(self):
        """Test registering and running an async benchmark."""
        benchmark = PerformanceBenchmark()

        call_count = 0

        async def async_func():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.001)

        benchmark.register_benchmark("test_async", async_func)

        result = await benchmark.run_benchmark("test_async", iterations=10)

        assert result.name == "test_async"
        assert result.iterations == 10
        assert call_count == 10
        assert result.avg_time > 0

    @pytest.mark.anyio
    async def test_run_nonexistent_benchmark(self):
        """Test error handling for unregistered benchmark."""
        benchmark = PerformanceBenchmark()

        with pytest.raises(KeyError, match="not registered"):
            await benchmark.run_benchmark("nonexistent")

    @pytest.mark.anyio
    async def test_run_all_benchmarks(self):
        """Test running all registered benchmarks."""
        benchmark = PerformanceBenchmark()

        benchmark.register_benchmark("bench1", lambda: time.sleep(0.001))
        benchmark.register_benchmark("bench2", lambda: time.sleep(0.002))

        suite = await benchmark.run_all(iterations=5)

        assert isinstance(suite, BenchmarkSuite)
        assert len(suite.results) == 2
        assert suite.total_time > 0

        # Check that both benchmarks ran
        names = {r.name for r in suite.results}
        assert names == {"bench1", "bench2"}

        # Check that target comparison was generated
        assert isinstance(suite.target_comparison, list)

    def test_percentile_computation(self):
        """Test percentile computation algorithm."""
        values = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]

        p50 = PerformanceBenchmark._compute_percentile(values, 50)
        p95 = PerformanceBenchmark._compute_percentile(values, 95)
        p99 = PerformanceBenchmark._compute_percentile(values, 99)

        # p50 should be around median
        assert 4.0 <= p50 <= 6.0

        # p95 should be near high end
        assert p95 >= 9.0

        # p99 should be at high end
        assert p99 >= 9.0

    def test_percentile_edge_cases(self):
        """Test percentile computation with edge cases."""
        # Empty list
        assert PerformanceBenchmark._compute_percentile([], 50) == 0.0

        # Single value
        assert PerformanceBenchmark._compute_percentile([5.0], 50) == 5.0
        assert PerformanceBenchmark._compute_percentile([5.0], 99) == 5.0

        # Two values
        p50 = PerformanceBenchmark._compute_percentile([1.0, 2.0], 50)
        assert p50 in [1.0, 2.0]

    def test_compare_to_targets_pass(self):
        """Test target comparison with passing benchmarks."""
        benchmark = PerformanceBenchmark()

        # Create a result that passes targets
        result = BenchmarkResult(
            name="cache_lookup",
            iterations=100,
            times=[0.001] * 100,
            min_time=0.001,
            max_time=0.001,
            avg_time=0.001,
            p50=0.001,
            p95=0.001,
            p99=0.001,
        )

        suite = BenchmarkSuite(results=[result], total_time=0.1)

        comparison = benchmark.compare_to_targets(suite)

        assert isinstance(comparison, list)
        assert len(comparison) > 0

        # Should have passing marks (✅)
        passing = [line for line in comparison if "✅" in line]
        assert len(passing) > 0

    def test_compare_to_targets_fail(self):
        """Test target comparison with failing benchmarks."""
        benchmark = PerformanceBenchmark()

        # Create a result that fails targets
        result = BenchmarkResult(
            name="cache_lookup",
            iterations=100,
            times=[1.0] * 100,  # Way over target
            min_time=1.0,
            max_time=1.0,
            avg_time=1.0,
            p50=1.0,
            p95=1.0,
            p99=1.0,
        )

        suite = BenchmarkSuite(results=[result], total_time=100.0)

        comparison = benchmark.compare_to_targets(suite)

        # Should have failing marks (❌)
        failing = [line for line in comparison if "❌" in line]
        assert len(failing) > 0

    def test_compare_to_targets_no_targets(self):
        """Test target comparison with benchmark that has no targets."""
        benchmark = PerformanceBenchmark()

        result = BenchmarkResult(
            name="unknown_benchmark",
            iterations=100,
            times=[0.1] * 100,
            min_time=0.1,
            max_time=0.1,
            avg_time=0.1,
            p50=0.1,
            p95=0.1,
            p99=0.1,
        )

        suite = BenchmarkSuite(results=[result], total_time=10.0)

        comparison = benchmark.compare_to_targets(suite)

        # Should have info message
        assert any("no targets defined" in line for line in comparison)

    def test_performance_targets_structure(self):
        """Test that PERFORMANCE_TARGETS has expected structure."""
        assert "cache_lookup" in PERFORMANCE_TARGETS
        assert "agent_query" in PERFORMANCE_TARGETS
        assert "context_building" in PERFORMANCE_TARGETS

        # Each target should have p50, p95, p99
        for name, targets in PERFORMANCE_TARGETS.items():
            assert "p50" in targets
            assert "p95" in targets
            assert "p99" in targets
            assert all(isinstance(v, (int, float)) for v in targets.values())


# ============================================================================
# Test OptimizedContextBuilder
# ============================================================================

class TestOptimizedContextBuilder:
    """Test context building with optimization."""

    def test_build_context_basic(self):
        """Test basic context building without cache."""
        builder = OptimizedContextBuilder(max_context_length=500)

        request = AgentRequest(context={"query": "tell me about dragons"})

        content_sources = [
            ("lore", "Dragons are powerful creatures with scales and wings."),
            ("rules", "Dragon breath weapons deal fire damage."),
        ]

        result = builder.build_context(request, content_sources)

        assert isinstance(result, ContextBuildResult)
        assert len(result.context) > 0
        assert result.total_tokens_estimate > 0
        assert result.build_time >= 0
        assert len(result.sources_used) == 2

    def test_build_context_with_cache(self):
        """Test context building with cache."""
        cache = MockCache()
        builder = OptimizedContextBuilder(cache=cache, max_context_length=1000)

        request = AgentRequest(context={"query": "tell me about orcs"})

        content_sources = [
            ("lore", "Orcs are fierce warriors."),
            ("combat", "Orcs have high strength."),
        ]

        # First build - cache misses
        result1 = builder.build_context(request, content_sources)

        assert result1.cache_misses == 2
        assert result1.cache_hits == 0

        # Second build - cache hits
        builder.reset_stats()
        result2 = builder.build_context(request, content_sources)

        assert result2.cache_hits == 2
        assert result2.cache_misses == 0

    def test_build_context_budget_enforcement(self):
        """Test that context stays within budget."""
        builder = OptimizedContextBuilder(max_context_length=100)

        request = AgentRequest(context={"query": "test"})

        content_sources = [
            ("source1", "A" * 200),  # 200 chars
            ("source2", "B" * 200),  # 200 chars
        ]

        result = builder.build_context(request, content_sources, budget=150)

        # Context should be within budget
        assert len(result.context) <= 150

        # Should have used at least one source
        assert len(result.sources_used) >= 1

    def test_estimate_relevance_keyword_matching(self):
        """Test relevance estimation based on keyword overlap."""
        builder = OptimizedContextBuilder()

        request = AgentRequest(context={
            "query": "tell me about fire dragons and their breath weapons"
        })

        # High relevance content
        high_relevance = "Fire dragons have powerful breath weapons that deal massive fire damage."
        score_high = builder.estimate_relevance(high_relevance, request)

        # Low relevance content
        low_relevance = "The weather today is sunny and warm."
        score_low = builder.estimate_relevance(low_relevance, request)

        # High relevance should score higher
        assert score_high > score_low
        assert 0.0 <= score_high <= 1.0
        assert 0.0 <= score_low <= 1.0

    def test_estimate_relevance_edge_cases(self):
        """Test relevance estimation with edge cases."""
        builder = OptimizedContextBuilder()

        request = AgentRequest(context={"query": "test query"})

        # Empty content
        assert builder.estimate_relevance("", request) == 0.0

        # No keywords in request
        empty_request = AgentRequest(context={})
        score = builder.estimate_relevance("some content", empty_request)
        assert score == 0.5  # Neutral score when no keywords

    def test_build_context_relevance_ordering(self):
        """Test that higher relevance sources are prioritized."""
        builder = OptimizedContextBuilder(max_context_length=200)

        request = AgentRequest(context={"query": "fire magic spells"})

        content_sources = [
            ("irrelevant", "The tavern serves good ale."),
            ("relevant", "Fire magic spells include fireball and flame strike."),
            ("somewhat", "Magic items can be found in dungeons."),
        ]

        result = builder.build_context(request, content_sources)

        # Most relevant source should be included
        assert "relevant" in result.sources_used

    def test_reset_stats(self):
        """Test stats reset functionality."""
        cache = MockCache()
        builder = OptimizedContextBuilder(cache=cache)

        request = AgentRequest(context={"query": "test"})
        content_sources = [("source", "content")]

        # Build once
        builder.build_context(request, content_sources)

        # Should have some stats
        assert builder._cache_hits > 0 or builder._cache_misses > 0

        # Reset
        builder.reset_stats()

        assert builder._cache_hits == 0
        assert builder._cache_misses == 0

    def test_cache_error_handling(self):
        """Test that cache errors don't break context building."""

        class BrokenCache:
            """Cache that always fails."""

            def get(self, key):
                raise RuntimeError("Cache is broken")

            def put(self, key, value, size):
                raise RuntimeError("Cache is broken")

        builder = OptimizedContextBuilder(cache=BrokenCache())

        request = AgentRequest(context={"query": "test"})
        content_sources = [("source", "content")]

        # Should not raise, just treat as cache misses
        result = builder.build_context(request, content_sources)

        assert len(result.context) > 0

    def test_build_context_truncation(self):
        """Test content truncation when near budget."""
        builder = OptimizedContextBuilder(max_context_length=300)

        request = AgentRequest(context={"query": "important"})

        # First source takes most of budget
        content_sources = [
            ("first", "important " * 20),  # ~200 chars
            ("second", "also important " * 20),  # Would exceed budget
        ]

        result = builder.build_context(request, content_sources, budget=300)

        # Should fit first source and maybe truncate second
        assert len(result.context) <= 300
        assert "first" in result.sources_used

    def test_tokens_estimate(self):
        """Test that token estimate is reasonable."""
        builder = OptimizedContextBuilder()

        request = AgentRequest(context={"query": "test"})
        content = "A" * 400  # 400 chars

        result = builder.build_context(request, [("source", content)])

        # Token estimate should be roughly chars / 4
        # Allow some variation for formatting
        assert 50 <= result.total_tokens_estimate <= 200
