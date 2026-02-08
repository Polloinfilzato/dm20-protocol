"""
Parallel execution of agent queries for the Claudmaster multi-agent system.

This module enables concurrent execution of independent agent queries,
improving response time by running agents in parallel when dependencies allow.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dm20_protocol.claudmaster.base import Agent, AgentRequest, AgentResponse

from dm20_protocol.claudmaster.exceptions import ClaudmasterTimeoutError


@dataclass
class ExecutionBatch:
    """A batch of requests to execute in parallel."""
    batch_index: int
    requests: list[AgentRequest]
    depends_on: list[int] = field(default_factory=list)  # indices of batches that must complete first


@dataclass
class ParallelExecutionResult:
    """Result of parallel execution."""
    responses: list[AgentResponse | None]  # None for failed requests
    total_time: float
    individual_times: list[float]
    errors: list[tuple[int, Exception]]  # (index, error) pairs


class ParallelAgentExecutor:
    """
    Executes independent agent queries in parallel.

    This executor manages concurrent agent execution with configurable
    concurrency limits and timeout handling. It can execute agents in
    simple parallel mode or in dependency-ordered batches.

    Attributes:
        max_concurrent: Maximum number of agents to run simultaneously
        default_timeout: Default timeout in seconds for agent execution
    """

    def __init__(self, max_concurrent: int = 4, default_timeout: float = 5.0):
        """
        Initialize the parallel executor.

        Args:
            max_concurrent: Maximum concurrent agent executions (default: 4)
            default_timeout: Default timeout in seconds (default: 5.0)
        """
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)

    async def execute_parallel(
        self,
        agents: list[Agent],
        requests: list[AgentRequest],
    ) -> ParallelExecutionResult:
        """
        Execute multiple agent requests in parallel.

        Each agent[i] handles request[i]. All agents execute concurrently
        subject to the max_concurrent limit. Timeouts and errors are tracked
        per-agent without failing the entire batch.

        Args:
            agents: List of agents to execute
            requests: List of requests, one per agent

        Returns:
            ParallelExecutionResult with responses, times, and errors

        Raises:
            ValueError: If agents and requests lists have different lengths
        """
        if len(agents) != len(requests):
            raise ValueError(
                f"Agents and requests must have same length "
                f"(got {len(agents)} agents, {len(requests)} requests)"
            )

        if not agents:
            return ParallelExecutionResult(
                responses=[],
                total_time=0.0,
                individual_times=[],
                errors=[],
            )

        start_time = time.perf_counter()

        # Create tasks for all agent executions
        tasks = [
            self._execute_single_with_tracking(i, agent, request)
            for i, (agent, request) in enumerate(zip(agents, requests))
        ]

        # Execute all tasks and collect results
        results = await asyncio.gather(*tasks, return_exceptions=True)

        total_time = time.perf_counter() - start_time

        # Process results
        responses: list[AgentResponse | None] = []
        individual_times: list[float] = []
        errors: list[tuple[int, Exception]] = []

        for i, result in enumerate(results):
            if isinstance(result, tuple):
                # Successful execution: (response, duration)
                response, duration = result
                responses.append(response)
                individual_times.append(duration)
            elif isinstance(result, Exception):
                # Error during execution
                responses.append(None)
                individual_times.append(0.0)
                errors.append((i, result))
            else:
                # Unexpected result type
                responses.append(None)
                individual_times.append(0.0)
                errors.append((i, ValueError(f"Unexpected result type: {type(result)}")))

        return ParallelExecutionResult(
            responses=responses,
            total_time=total_time,
            individual_times=individual_times,
            errors=errors,
        )

    async def execute_batched(
        self,
        agents: list[Agent],
        requests: list[AgentRequest],
        batches: list[ExecutionBatch],
    ) -> ParallelExecutionResult:
        """
        Execute requests in dependency-ordered batches.

        Each batch runs in parallel, but batches are sequential.
        This allows handling dependencies between agent executions.

        Args:
            agents: List of all agents
            requests: List of all requests
            batches: List of execution batches with dependency information

        Returns:
            ParallelExecutionResult with responses, times, and errors

        Raises:
            ValueError: If batch configuration is invalid
        """
        if len(agents) != len(requests):
            raise ValueError(
                f"Agents and requests must have same length "
                f"(got {len(agents)} agents, {len(requests)} requests)"
            )

        # Validate batches
        all_indices = set()
        for batch in batches:
            for req in batch.requests:
                req_index = requests.index(req)
                if req_index in all_indices:
                    raise ValueError(f"Request at index {req_index} appears in multiple batches")
                all_indices.add(req_index)

        if not all_indices == set(range(len(requests))):
            raise ValueError("Batches must cover all requests exactly once")

        # Initialize result tracking
        all_responses: list[AgentResponse | None] = [None] * len(requests)
        all_times: list[float] = [0.0] * len(requests)
        all_errors: list[tuple[int, Exception]] = []

        start_time = time.perf_counter()

        # Execute batches sequentially
        for batch in sorted(batches, key=lambda b: b.batch_index):
            # Build agents and requests for this batch
            batch_agents = []
            batch_requests_list = []
            batch_indices = []

            for req in batch.requests:
                req_index = requests.index(req)
                batch_indices.append(req_index)
                batch_agents.append(agents[req_index])
                batch_requests_list.append(req)

            # Execute this batch in parallel
            batch_result = await self.execute_parallel(batch_agents, batch_requests_list)

            # Store results in the overall result arrays
            for i, batch_idx in enumerate(batch_indices):
                all_responses[batch_idx] = batch_result.responses[i]
                all_times[batch_idx] = batch_result.individual_times[i]

            # Collect errors (remap indices to global indices)
            for local_idx, error in batch_result.errors:
                global_idx = batch_indices[local_idx]
                all_errors.append((global_idx, error))

        total_time = time.perf_counter() - start_time

        return ParallelExecutionResult(
            responses=all_responses,
            total_time=total_time,
            individual_times=all_times,
            errors=all_errors,
        )

    def analyze_dependencies(
        self,
        requests: list[AgentRequest],
    ) -> list[ExecutionBatch]:
        """
        Group requests into parallel execution batches.

        Simple strategy: requests with same 'depends_on' metadata
        go in same batch. Requests with no dependencies go first.

        The 'depends_on' metadata should be a list of request indices
        that must complete before this request can start.

        Args:
            requests: List of agent requests to analyze

        Returns:
            List of ExecutionBatch objects ordered by dependencies
        """
        if not requests:
            return []

        # Group requests by their dependency level
        dependency_groups: dict[int, list[tuple[int, AgentRequest]]] = {}

        for idx, request in enumerate(requests):
            depends_on = request.metadata.get("depends_on", [])

            if not depends_on:
                # No dependencies: level 0
                level = 0
            else:
                # Dependency level is max of dependencies' levels + 1
                # For simplicity, we use the max index in depends_on + 1 as the level
                level = max(depends_on) + 1 if isinstance(depends_on, list) else 1

            if level not in dependency_groups:
                dependency_groups[level] = []
            dependency_groups[level].append((idx, request))

        # Create batches from groups
        batches = []
        for level in sorted(dependency_groups.keys()):
            group_requests = [req for _, req in dependency_groups[level]]

            # Determine which batches this depends on
            depends_on_batches = []
            if level > 0:
                # Depends on all previous levels
                depends_on_batches = list(range(level))

            batches.append(ExecutionBatch(
                batch_index=level,
                requests=group_requests,
                depends_on=depends_on_batches,
            ))

        return batches

    async def _execute_single(
        self,
        agent: Agent,
        request: AgentRequest,
        timeout: float | None = None,
    ) -> AgentResponse:
        """
        Execute single request with semaphore and timeout.

        Args:
            agent: The agent to execute
            request: The request to process
            timeout: Optional timeout override

        Returns:
            The agent's response

        Raises:
            ClaudmasterTimeoutError: If execution exceeds timeout
            Exception: Any error from agent execution
        """
        async with self._semaphore:
            try:
                return await asyncio.wait_for(
                    agent.run(request.context),
                    timeout=timeout or self.default_timeout,
                )
            except asyncio.TimeoutError as e:
                raise ClaudmasterTimeoutError(
                    f"Agent '{agent.name}' timed out after {timeout or self.default_timeout}s",
                    operation=f"agent.run({agent.name})",
                    timeout_seconds=timeout or self.default_timeout,
                ) from e

    async def _execute_single_with_tracking(
        self,
        index: int,
        agent: Agent,
        request: AgentRequest,
    ) -> tuple[AgentResponse, float]:
        """
        Execute a single agent with time tracking.

        Args:
            index: Index of this request (for error reporting)
            agent: The agent to execute
            request: The request to process

        Returns:
            Tuple of (response, duration)

        Raises:
            Exception: Any error during execution (will be caught by gather)
        """
        start = time.perf_counter()
        response = await self._execute_single(agent, request)
        duration = time.perf_counter() - start
        return (response, duration)


__all__ = [
    "ExecutionBatch",
    "ParallelExecutionResult",
    "ParallelAgentExecutor",
]
