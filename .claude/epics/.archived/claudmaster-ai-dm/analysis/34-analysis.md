---
issue: 34
title: Orchestrator Skeleton
analyzed: 2026-02-06T00:13:37Z
estimated_hours: 10
parallelization_factor: 1.4
---

# Parallel Work Analysis: Issue #34

## Overview

Implement the central Orchestrator class that coordinates all Claudmaster agents, manages game turn flow, and integrates with the existing Campaign/GameState systems. This is the heart of the AI DM system.

## Key Architectural Decisions

Before implementation, these decisions need resolution:

1. **Intent Classification**: How to classify player input?
   - Option A: Enum-based with keyword/pattern matching (simple, testable, fast)
   - Option B: LLM-based classification (flexible, slower, costs tokens)
   - Option C: Hybrid - pattern matching first, LLM fallback (recommended)

2. **Agent Execution Model**: How to call agents?
   - Option A: Sequential pipeline (simple, predictable)
   - Option B: Parallel with asyncio.gather (fast, complex merging)
   - Option C: Dynamic - parallel for independent agents, sequential for dependent ones (recommended)

3. **Response Aggregation**: How to merge multi-agent responses?
   - Option A: Priority-based (narrator wins for descriptions, archivist for rules)
   - Option B: Layered (each agent adds metadata, narrator wraps final text)
   - Recommendation: Layered with priority fallback

4. **Campaign Integration Depth**:
   - Option A: Direct Campaign model access (tight coupling)
   - Option B: Abstract interface/protocol (loose coupling, testable)
   - Recommendation: Protocol-based with Campaign adapter

## Parallel Streams

### Stream A: Protocol Types + Orchestrator Core
**Scope**: Define all communication types, Orchestrator class structure, agent registration, session lifecycle
**Files**:
- `src/gamemaster_mcp/claudmaster/orchestrator.py` (types + class skeleton)
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4
**Dependencies**: none

Key deliverables:
- `IntentType` enum (action, question, roleplay, combat, exploration, system)
- `PlayerIntent` model (classified intent with confidence)
- `OrchestratorResponse` model (narrative + state changes + metadata)
- `TurnResult` model (complete turn outcome)
- `Orchestrator.__init__`, `register_agent`, `unregister_agent`
- Session lifecycle methods (`start_session`, `end_session`)
- Error handling framework (`OrchestratorError` hierarchy)

### Stream B: Turn Flow + Campaign Integration
**Scope**: Implement the actual turn execution logic, intent classification, agent routing, response aggregation
**Files**:
- `src/gamemaster_mcp/claudmaster/orchestrator.py` (methods on existing class)
**Agent Type**: backend-specialist
**Can Start**: after Stream A (depends on types)
**Estimated Hours**: 4
**Dependencies**: Stream A

Key deliverables:
- `classify_intent()` - pattern-based intent classifier
- `route_to_agents()` - determine which agents handle which intents
- `process_player_input()` - main entry point
- `execute_turn()` - full turn cycle
- `_aggregate_responses()` - merge agent outputs
- Campaign read/write through GameState

### Stream C: Comprehensive Tests
**Scope**: Unit tests for all types and methods, integration tests with mock agents
**Files**:
- `tests/test_orchestrator.py`
**Agent Type**: backend-specialist
**Can Start**: after Stream A (can write tests against types immediately)
**Estimated Hours**: 2
**Dependencies**: Stream A (partial), Stream B (for integration tests)

Key deliverables:
- Type validation tests (IntentType, OrchestratorResponse, TurnResult)
- Agent registration/unregistration tests
- Intent classification tests
- Turn flow tests with mock agents
- Error handling and recovery tests
- Campaign integration tests

## Coordination Points

### Shared Files
- `src/gamemaster_mcp/claudmaster/orchestrator.py` - Streams A & B (sequential, no conflict)
- `src/gamemaster_mcp/claudmaster/__init__.py` - Stream A (add exports)

### Sequential Requirements
1. Types must be defined before Orchestrator methods (Stream A before B)
2. Orchestrator skeleton must exist before tests can import (Stream A before C)
3. Turn flow logic must be complete before integration tests (Stream B before C integration tests)

## Conflict Risk Assessment
- **Low Risk**: All streams work on the same module but sequentially
- Stream A creates the file, Stream B adds to it, Stream C tests it
- No parallel modification of the same file

## Parallelization Strategy

**Recommended Approach**: hybrid

Stream A (types + skeleton) first, then B and C can partially overlap:
- C can write unit tests for types as soon as A completes
- B implements turn flow while C writes type tests
- C adds integration tests after B completes

```
Timeline:
  Stream A: ████████ (4h)
  Stream B:         ████████ (4h)
  Stream C:         ████ ████ (2h, split around B)
```

## Expected Timeline

With parallel execution:
- Wall time: ~8 hours (C overlaps partially with B)
- Total work: 10 hours
- Efficiency gain: 20%

Without parallel execution:
- Wall time: 10 hours

## Notes

- The Orchestrator depends heavily on the Agent base class from #33 (completed)
- AgentRequest and AgentResponse types already exist in `base.py` — reuse them
- Campaign and GameState models in `models.py` are stable — safe to import directly
- Consider making intent classification pluggable for future LLM-based classification (#36 dependency)
- The `__init__.py` must export new types for downstream consumers
