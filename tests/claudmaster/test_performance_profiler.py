"""
Tests for the Performance Profiler (Issue #68 Stream A).

Tests cover:
- Trace context manager timing
- Manual recording
- Percentile calculations (p50/p95/p99)
- Operation metrics retrieval
- Performance report generation
- Bottleneck detection
- Reset operations
- Edge cases (no data, single measurement)
"""

from __future__ import annotations

import time

import pytest

from gamemaster_mcp.claudmaster.performance.profiler import (
    PerformanceProfiler,
    PerformanceReport,
    OperationMetrics,
)


# ============================================================================
# Basic Profiling Tests
# ============================================================================

class TestBasicProfiling:
    """Test basic profiling functionality."""

    def test_trace_context_manager(self):
        """Test that trace context manager records timing."""
        profiler = PerformanceProfiler()

        with profiler.trace("test_operation"):
            time.sleep(0.01)  # Sleep 10ms

        metrics = profiler.get_operation_metrics("test_operation")
        assert metrics is not None
        assert metrics.count == 1
        assert metrics.total_time >= 0.01  # At least 10ms
        assert metrics.min_time >= 0.01
        assert metrics.max_time >= 0.01

    def test_trace_multiple_operations(self):
        """Test tracing multiple different operations."""
        profiler = PerformanceProfiler()

        with profiler.trace("op1"):
            time.sleep(0.005)

        with profiler.trace("op2"):
            time.sleep(0.01)

        with profiler.trace("op1"):
            time.sleep(0.005)

        metrics1 = profiler.get_operation_metrics("op1")
        metrics2 = profiler.get_operation_metrics("op2")

        assert metrics1.count == 2
        assert metrics2.count == 1

    def test_trace_with_exception(self):
        """Test that trace records timing even when exception occurs."""
        profiler = PerformanceProfiler()

        with pytest.raises(ValueError):
            with profiler.trace("failing_op"):
                raise ValueError("Test error")

        metrics = profiler.get_operation_metrics("failing_op")
        assert metrics is not None
        assert metrics.count == 1

    def test_manual_record(self):
        """Test manual timing recording."""
        profiler = PerformanceProfiler()

        profiler.record("manual_op", 0.5)
        profiler.record("manual_op", 1.0)
        profiler.record("manual_op", 0.75)

        metrics = profiler.get_operation_metrics("manual_op")
        assert metrics is not None
        assert metrics.count == 3
        assert metrics.min_time == 0.5
        assert metrics.max_time == 1.0
        assert metrics.avg_time == 0.75


# ============================================================================
# Percentile Calculation Tests
# ============================================================================

class TestPercentiles:
    """Test percentile calculations."""

    def test_percentiles_basic(self):
        """Test percentile calculations with known data."""
        profiler = PerformanceProfiler()

        # Record 10 values: 0.1, 0.2, ..., 1.0
        for i in range(1, 11):
            profiler.record("test_op", i / 10.0)

        # p50 should be around 0.5-0.6
        p50 = profiler.get_percentile("test_op", 50)
        assert 0.5 <= p50 <= 0.6

        # p95 should be around 0.9-1.0
        p95 = profiler.get_percentile("test_op", 95)
        assert 0.9 <= p95 <= 1.0

        # p99 should be around 1.0
        p99 = profiler.get_percentile("test_op", 99)
        assert 0.9 <= p99 <= 1.0

    def test_percentile_single_value(self):
        """Test percentile with single value."""
        profiler = PerformanceProfiler()
        profiler.record("single_op", 0.5)

        # All percentiles should be the single value
        assert profiler.get_percentile("single_op", 50) == 0.5
        assert profiler.get_percentile("single_op", 95) == 0.5
        assert profiler.get_percentile("single_op", 99) == 0.5

    def test_percentile_no_data(self):
        """Test percentile returns 0.0 when no data."""
        profiler = PerformanceProfiler()
        assert profiler.get_percentile("nonexistent", 50) == 0.0
        assert profiler.get_percentile("nonexistent", 95) == 0.0

    def test_percentile_edge_cases(self):
        """Test percentile edge cases (0, 100)."""
        profiler = PerformanceProfiler()

        for i in range(1, 11):
            profiler.record("test_op", i / 10.0)

        # p0 should be minimum
        p0 = profiler.get_percentile("test_op", 0)
        assert p0 == 0.1

        # p100 should be maximum
        p100 = profiler.get_percentile("test_op", 100)
        assert p100 == 1.0


# ============================================================================
# Metrics and Reports Tests
# ============================================================================

class TestMetricsAndReports:
    """Test operation metrics and report generation."""

    def test_operation_metrics_complete(self):
        """Test that operation metrics include all fields."""
        profiler = PerformanceProfiler()

        profiler.record("test_op", 0.1)
        profiler.record("test_op", 0.2)
        profiler.record("test_op", 0.3)

        metrics = profiler.get_operation_metrics("test_op")
        assert metrics is not None
        assert metrics.count == 3
        assert metrics.total_time == pytest.approx(0.6)
        assert metrics.min_time == 0.1
        assert metrics.max_time == 0.3
        assert metrics.avg_time == pytest.approx(0.2)
        assert metrics.p50 > 0
        assert metrics.p95 > 0
        assert metrics.p99 > 0

    def test_operation_metrics_nonexistent(self):
        """Test that nonexistent operation returns None."""
        profiler = PerformanceProfiler()
        assert profiler.get_operation_metrics("nonexistent") is None

    def test_performance_report_basic(self):
        """Test performance report generation."""
        profiler = PerformanceProfiler()

        profiler.record("op1", 0.5)
        profiler.record("op2", 1.0)
        profiler.record("op1", 0.3)

        report = profiler.get_report()

        assert isinstance(report, PerformanceReport)
        assert len(report.operations) == 2
        assert "op1" in report.operations
        assert "op2" in report.operations
        assert report.total_traces == 3

    def test_performance_report_empty(self):
        """Test performance report with no data."""
        profiler = PerformanceProfiler()
        report = profiler.get_report()

        assert isinstance(report, PerformanceReport)
        assert len(report.operations) == 0
        assert report.total_traces == 0
        assert len(report.bottlenecks) == 0


# ============================================================================
# Bottleneck Detection Tests
# ============================================================================

class TestBottleneckDetection:
    """Test bottleneck identification."""

    def test_bottleneck_exceeds_threshold(self):
        """Test that operations exceeding threshold are flagged."""
        profiler = PerformanceProfiler(
            thresholds={"fast_op": 0.1, "slow_op": 0.5}
        )

        # fast_op stays under threshold
        profiler.record("fast_op", 0.05)
        profiler.record("fast_op", 0.06)

        # slow_op exceeds threshold
        profiler.record("slow_op", 0.8)
        profiler.record("slow_op", 0.9)

        bottlenecks = profiler.identify_bottlenecks()
        assert "slow_op" in bottlenecks
        assert "fast_op" not in bottlenecks

    def test_bottleneck_default_threshold(self):
        """Test that operations without explicit threshold use default."""
        profiler = PerformanceProfiler()

        # Unknown operation should use default threshold of 5.0s
        profiler.record("unknown_op", 6.0)
        profiler.record("unknown_op", 7.0)

        bottlenecks = profiler.identify_bottlenecks()
        assert "unknown_op" in bottlenecks

    def test_bottleneck_p95_check(self):
        """Test that bottleneck uses p95, not max."""
        profiler = PerformanceProfiler(
            thresholds={"variable_op": 0.5}
        )

        # Most values under threshold, but one outlier
        for _ in range(19):
            profiler.record("variable_op", 0.1)
        profiler.record("variable_op", 2.0)  # Single outlier

        # p95 should be around 0.1-0.2, well under threshold
        bottlenecks = profiler.identify_bottlenecks()
        assert "variable_op" not in bottlenecks

    def test_bottleneck_in_report(self):
        """Test that bottlenecks appear in report."""
        profiler = PerformanceProfiler(
            thresholds={"slow_op": 0.1}
        )

        profiler.record("slow_op", 0.5)
        profiler.record("slow_op", 0.6)

        report = profiler.get_report()
        assert "slow_op" in report.bottlenecks


# ============================================================================
# Reset Tests
# ============================================================================

class TestReset:
    """Test reset functionality."""

    def test_reset_all(self):
        """Test that reset clears all metrics."""
        profiler = PerformanceProfiler()

        profiler.record("op1", 0.5)
        profiler.record("op2", 1.0)

        profiler.reset()

        assert profiler.get_operation_metrics("op1") is None
        assert profiler.get_operation_metrics("op2") is None
        report = profiler.get_report()
        assert report.total_traces == 0

    def test_reset_single_operation(self):
        """Test that reset_operation only clears one operation."""
        profiler = PerformanceProfiler()

        profiler.record("op1", 0.5)
        profiler.record("op2", 1.0)

        profiler.reset_operation("op1")

        assert profiler.get_operation_metrics("op1") is None
        assert profiler.get_operation_metrics("op2") is not None

    def test_reset_nonexistent_operation(self):
        """Test that resetting nonexistent operation doesn't error."""
        profiler = PerformanceProfiler()
        profiler.reset_operation("nonexistent")  # Should not raise


# ============================================================================
# Integration Tests
# ============================================================================

class TestIntegration:
    """Integration tests combining multiple features."""

    def test_realistic_workflow(self):
        """Test realistic profiling workflow."""
        profiler = PerformanceProfiler()

        # Simulate player action processing
        with profiler.trace("player_action"):
            time.sleep(0.02)

            with profiler.trace("intent_classification"):
                time.sleep(0.005)

            with profiler.trace("agent_query"):
                time.sleep(0.01)

        # Generate report
        report = profiler.get_report()

        assert "player_action" in report.operations
        assert "intent_classification" in report.operations
        assert "agent_query" in report.operations

        # player_action should include nested time
        player_metrics = report.operations["player_action"]
        assert player_metrics.total_time >= 0.02

    def test_custom_thresholds(self):
        """Test profiler with custom thresholds."""
        custom_thresholds = {
            "critical_op": 0.1,
            "normal_op": 1.0,
        }
        profiler = PerformanceProfiler(thresholds=custom_thresholds)

        profiler.record("critical_op", 0.15)
        profiler.record("normal_op", 0.5)

        bottlenecks = profiler.identify_bottlenecks()
        assert "critical_op" in bottlenecks
        assert "normal_op" not in bottlenecks
