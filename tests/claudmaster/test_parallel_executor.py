"""
Tests for ParallelAgentExecutor (Issue #68 Stream B).

Tests cover:
- Parallel execution of multiple agents
- Concurrency limiting with semaphore
- Timeout handling
- Error collection and tracking
- Dependency analysis
- Batched execution with ordering
"""

from __future__ import annotations

import asyncio

import pytest

from gamemaster_mcp.claudmaster.base import Agent, AgentRequest, AgentResponse, AgentRole
from gamemaster_mcp.claudmaster.exceptions import ClaudmasterTimeoutError
from gamemaster_mcp.claudmaster.performance.parallel_executor import (
    ExecutionBatch,
    ParallelAgentExecutor,
    ParallelExecutionResult,
)


# ============================================================================
# Mock Agents for Testing
# ============================================================================

class MockAgent(Agent):
    """Simple mock agent for testing."""

    def __init__(self, name: str, role: AgentRole, delay: float = 0.0, should_fail: bool = False):
        super().__init__(name, role)
        self.delay = delay
        self.should_fail = should_fail
        self.call_count = 0

    async def reason(self, context: dict) -> str:
        return f"Mock reasoning from {self.name}"

    async def act(self, reasoning: str) -> str:
        if self.delay > 0:
            await asyncio.sleep(self.delay)

        self.call_count += 1

        if self.should_fail:
            raise RuntimeError(f"Mock failure from {self.name}")

        return f"Mock action result from {self.name}"

    async def observe(self, result: str) -> dict:
        return {"mock_observation": True, "agent": self.name}


# ============================================================================
# Test ParallelAgentExecutor
# ============================================================================

class TestParallelAgentExecutor:
    """Test parallel agent execution."""

    @pytest.mark.anyio
    async def test_execute_parallel_basic(self):
        """Test basic parallel execution."""
        executor = ParallelAgentExecutor(max_concurrent=2)

        agents = [
            MockAgent("agent1", AgentRole.NARRATOR, delay=0.1),
            MockAgent("agent2", AgentRole.ARCHIVIST, delay=0.1),
        ]

        requests = [
            AgentRequest(context={"test": "request1"}),
            AgentRequest(context={"test": "request2"}),
        ]

        result = await executor.execute_parallel(agents, requests)

        assert isinstance(result, ParallelExecutionResult)
        assert len(result.responses) == 2
        assert all(r is not None for r in result.responses)
        assert len(result.individual_times) == 2
        assert len(result.errors) == 0

        # Both agents should have been called
        assert agents[0].call_count == 1
        assert agents[1].call_count == 1

        # Total time should be roughly the delay time (parallel execution)
        assert result.total_time < 0.25  # Less than 2 * delay

    @pytest.mark.anyio
    async def test_execute_parallel_empty(self):
        """Test execution with empty lists."""
        executor = ParallelAgentExecutor()

        result = await executor.execute_parallel([], [])

        assert len(result.responses) == 0
        assert len(result.individual_times) == 0
        assert len(result.errors) == 0
        assert result.total_time >= 0.0

    @pytest.mark.anyio
    async def test_execute_parallel_mismatched_lengths(self):
        """Test error handling for mismatched agent/request lists."""
        executor = ParallelAgentExecutor()

        agents = [MockAgent("agent1", AgentRole.NARRATOR)]
        requests = [
            AgentRequest(context={"test": "1"}),
            AgentRequest(context={"test": "2"}),
        ]

        with pytest.raises(ValueError, match="same length"):
            await executor.execute_parallel(agents, requests)

    @pytest.mark.anyio
    async def test_concurrency_limiting(self):
        """Test that semaphore limits concurrent execution."""
        executor = ParallelAgentExecutor(max_concurrent=2)

        # Create 4 agents with delays
        agents = [
            MockAgent(f"agent{i}", AgentRole.NARRATOR, delay=0.1)
            for i in range(4)
        ]

        requests = [
            AgentRequest(context={"test": f"request{i}"})
            for i in range(4)
        ]

        result = await executor.execute_parallel(agents, requests)

        # All should succeed
        assert len(result.responses) == 4
        assert all(r is not None for r in result.responses)
        assert len(result.errors) == 0

        # With max_concurrent=2 and 4 agents at 0.1s each,
        # total time should be roughly 2 * 0.1s = 0.2s (two batches)
        # Allow some overhead
        assert 0.15 < result.total_time < 0.35

    @pytest.mark.anyio
    async def test_timeout_handling(self):
        """Test timeout detection and error handling."""
        executor = ParallelAgentExecutor(max_concurrent=2, default_timeout=0.1)

        agents = [
            MockAgent("fast", AgentRole.NARRATOR, delay=0.05),
            MockAgent("slow", AgentRole.ARCHIVIST, delay=0.5),  # Will timeout
        ]

        requests = [
            AgentRequest(context={"test": "fast"}),
            AgentRequest(context={"test": "slow"}),
        ]

        result = await executor.execute_parallel(agents, requests)

        # Fast agent should succeed, slow should timeout
        assert result.responses[0] is not None  # Fast succeeded
        assert result.responses[1] is None  # Slow failed

        # Should have one error
        assert len(result.errors) == 1
        error_idx, error = result.errors[0]
        assert error_idx == 1
        assert isinstance(error, ClaudmasterTimeoutError)
        assert "slow" in error.operation

    @pytest.mark.anyio
    async def test_error_collection(self):
        """Test error collection from failing agents."""
        executor = ParallelAgentExecutor()

        agents = [
            MockAgent("good1", AgentRole.NARRATOR, should_fail=False),
            MockAgent("bad1", AgentRole.ARCHIVIST, should_fail=True),
            MockAgent("good2", AgentRole.MODULE_KEEPER, should_fail=False),
            MockAgent("bad2", AgentRole.NARRATOR, should_fail=True),
        ]

        requests = [AgentRequest(context={"test": f"req{i}"}) for i in range(4)]

        result = await executor.execute_parallel(agents, requests)

        # Good agents should succeed
        assert result.responses[0] is not None
        assert result.responses[2] is not None

        # Bad agents should fail
        assert result.responses[1] is None
        assert result.responses[3] is None

        # Should have two errors
        assert len(result.errors) == 2
        error_indices = {idx for idx, _ in result.errors}
        assert error_indices == {1, 3}

        # Check error types
        for _, error in result.errors:
            assert isinstance(error, RuntimeError)
            assert "Mock failure" in str(error)

    @pytest.mark.anyio
    async def test_individual_times_tracking(self):
        """Test that individual execution times are tracked."""
        executor = ParallelAgentExecutor()

        agents = [
            MockAgent("agent1", AgentRole.NARRATOR, delay=0.05),
            MockAgent("agent2", AgentRole.ARCHIVIST, delay=0.1),
            MockAgent("agent3", AgentRole.MODULE_KEEPER, delay=0.15),
        ]

        requests = [AgentRequest(context={"test": f"req{i}"}) for i in range(3)]

        result = await executor.execute_parallel(agents, requests)

        # All should have valid times
        assert len(result.individual_times) == 3
        assert all(t > 0 for t in result.individual_times)

        # Times should roughly match delays (allow overhead)
        assert 0.03 < result.individual_times[0] < 0.1
        assert 0.08 < result.individual_times[1] < 0.15
        assert 0.13 < result.individual_times[2] < 0.2


# ============================================================================
# Test Dependency Analysis
# ============================================================================

class TestDependencyAnalysis:
    """Test request dependency analysis."""

    def test_analyze_dependencies_no_deps(self):
        """Test analysis with no dependencies."""
        executor = ParallelAgentExecutor()

        requests = [
            AgentRequest(context={"test": "1"}),
            AgentRequest(context={"test": "2"}),
            AgentRequest(context={"test": "3"}),
        ]

        batches = executor.analyze_dependencies(requests)

        # All should be in one batch at level 0
        assert len(batches) == 1
        assert batches[0].batch_index == 0
        assert len(batches[0].requests) == 3
        assert batches[0].depends_on == []

    def test_analyze_dependencies_with_deps(self):
        """Test analysis with dependencies."""
        executor = ParallelAgentExecutor()

        requests = [
            AgentRequest(context={"test": "1"}),  # No deps -> level 0
            AgentRequest(context={"test": "2"}),  # No deps -> level 0
            AgentRequest(context={"test": "3"}, metadata={"depends_on": [0, 1]}),  # Deps on 0,1 -> level 2
            AgentRequest(context={"test": "4"}, metadata={"depends_on": [2]}),  # Deps on 2 -> level 3
        ]

        batches = executor.analyze_dependencies(requests)

        # Should have multiple levels
        assert len(batches) >= 2

        # Sort by batch index
        batches.sort(key=lambda b: b.batch_index)

        # Level 0 should have requests 0 and 1
        level_0 = [b for b in batches if b.batch_index == 0][0]
        assert len(level_0.requests) == 2

    def test_analyze_dependencies_empty(self):
        """Test analysis with empty request list."""
        executor = ParallelAgentExecutor()

        batches = executor.analyze_dependencies([])

        assert batches == []


# ============================================================================
# Test Batched Execution
# ============================================================================

class TestBatchedExecution:
    """Test batched execution with dependencies."""

    @pytest.mark.anyio
    async def test_execute_batched_sequential(self):
        """Test batched execution respects ordering."""
        executor = ParallelAgentExecutor()

        agents = [
            MockAgent("agent1", AgentRole.NARRATOR),
            MockAgent("agent2", AgentRole.ARCHIVIST),
            MockAgent("agent3", AgentRole.MODULE_KEEPER),
        ]

        requests = [
            AgentRequest(context={"test": "1"}),
            AgentRequest(context={"test": "2"}),
            AgentRequest(context={"test": "3"}),
        ]

        # Create two batches: [0, 1] then [2]
        batches = [
            ExecutionBatch(batch_index=0, requests=[requests[0], requests[1]]),
            ExecutionBatch(batch_index=1, requests=[requests[2]], depends_on=[0]),
        ]

        result = await executor.execute_batched(agents, requests, batches)

        # All should succeed
        assert len(result.responses) == 3
        assert all(r is not None for r in result.responses)
        assert len(result.errors) == 0

    @pytest.mark.anyio
    async def test_execute_batched_all_at_once(self):
        """Test batched execution with everything in one batch."""
        executor = ParallelAgentExecutor()

        agents = [
            MockAgent("agent1", AgentRole.NARRATOR, delay=0.05),
            MockAgent("agent2", AgentRole.ARCHIVIST, delay=0.05),
        ]

        requests = [
            AgentRequest(context={"test": "1"}),
            AgentRequest(context={"test": "2"}),
        ]

        batches = [
            ExecutionBatch(batch_index=0, requests=requests),
        ]

        result = await executor.execute_batched(agents, requests, batches)

        assert len(result.responses) == 2
        assert all(r is not None for r in result.responses)

        # Should run in parallel, so total time ~ delay
        assert result.total_time < 0.15

    @pytest.mark.anyio
    async def test_execute_batched_invalid_config(self):
        """Test error handling for invalid batch configuration."""
        executor = ParallelAgentExecutor()

        agents = [MockAgent("agent1", AgentRole.NARRATOR)]
        requests = [AgentRequest(context={"test": "1"})]

        # Batch doesn't cover all requests
        batches = [
            ExecutionBatch(batch_index=0, requests=[]),
        ]

        with pytest.raises(ValueError, match="cover all requests"):
            await executor.execute_batched(agents, requests, batches)

    @pytest.mark.anyio
    async def test_execute_batched_errors_tracked(self):
        """Test that errors in batched execution are tracked correctly."""
        executor = ParallelAgentExecutor()

        agents = [
            MockAgent("good", AgentRole.NARRATOR, should_fail=False),
            MockAgent("bad", AgentRole.ARCHIVIST, should_fail=True),
        ]

        requests = [
            AgentRequest(context={"test": "1"}),
            AgentRequest(context={"test": "2"}),
        ]

        batches = [
            ExecutionBatch(batch_index=0, requests=requests),
        ]

        result = await executor.execute_batched(agents, requests, batches)

        # Good agent succeeds, bad agent fails
        assert result.responses[0] is not None
        assert result.responses[1] is None

        # Error should be tracked
        assert len(result.errors) == 1
        error_idx, error = result.errors[0]
        assert error_idx == 1
        assert isinstance(error, RuntimeError)
