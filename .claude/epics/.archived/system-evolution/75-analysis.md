---
issue: 75
title: Dual-Agent Response Architecture (Fast Narrator + Arbiter)
analyzed: 2026-02-12T21:29:46Z
estimated_hours: 14
parallelization_factor: 1.8
---

# Parallel Work Analysis: Issue #75

## Overview

Implement a dual-agent response architecture where a fast Narrator (Haiku) provides immediate narrative feedback while a slower Arbiter (Sonnet) resolves mechanics in parallel. This requires:

1. A real LLM client (Anthropic SDK) — currently missing entirely
2. Multi-model support (different models per agent)
3. A new Arbiter agent for mechanical resolution
4. Orchestrator changes to run both agents concurrently and merge results
5. Performance benchmarking

### Critical Discovery: No LLM Client Exists Yet

The codebase has NO Anthropic SDK integration. The `NarratorAgent` uses a `LLMClient` protocol with only `MockLLM` in tests. This is the foundational blocker — everything else depends on it.

### Existing Infrastructure We Can Leverage

| Component | File | Status | Reusable? |
|-----------|------|--------|-----------|
| `LLMClient` protocol | `agents/narrator.py` | Defined | Yes — extend for multi-model |
| `NarratorAgent` | `agents/narrator.py` | Complete with mocks | Yes — just wire real client |
| `ArchivistAgent` | `agents/archivist.py` | Complete (pure Python) | Yes — unchanged |
| Orchestrator routing | `orchestrator.py` | Intent → agents | Yes — extend aggregation |
| Async execution | `performance/parallel_executor.py` | Exists | Yes — already async |
| `ClaudmasterConfig` | `config.py` | Has model/temp settings | Extend for per-agent models |
| Session management | `session.py` + `tools/session_tools.py` | Complete | Yes — wire LLM in startup |

## Parallel Streams

### Stream A: LLM Client & Multi-Model Foundation
**Scope**: Create the real Anthropic SDK client, extend config for per-agent model selection, wire into session startup
**Files**:
- `src/dm20_protocol/claudmaster/llm_client.py` (NEW)
- `src/dm20_protocol/claudmaster/config.py` (MODIFY — add per-agent model fields)
- `src/dm20_protocol/claudmaster/tools/session_tools.py` (MODIFY — wire LLM client on start)
- `tests/claudmaster/test_llm_client.py` (NEW)
**Agent Type**: backend-specialist
**Can Start**: immediately
**Estimated Hours**: 4
**Dependencies**: none
**Details**:
- Implement `AnthropicLLMClient` matching existing `LLMClient` protocol (async `generate(prompt, max_tokens) -> str`)
- Add streaming support (`generate_stream()` method)
- Extend `ClaudmasterConfig` with `narrator_model` (default: haiku) and `arbiter_model` (default: sonnet)
- Wire client creation in `SessionManager.start_session()` — create separate clients per model
- Register NarratorAgent with Haiku client (currently a TODO in session_tools.py line 151)

### Stream B: Arbiter Agent
**Scope**: New agent for mechanical resolution — rules adjudication, dice interpretation, state change proposals
**Files**:
- `src/dm20_protocol/claudmaster/agents/arbiter.py` (NEW)
- `tests/claudmaster/test_arbiter_agent.py` (NEW)
**Agent Type**: backend-specialist
**Can Start**: immediately (uses MockLLM for tests)
**Estimated Hours**: 4
**Dependencies**: none (testable with MockLLM)
**Details**:
- Follows existing ReAct pattern (`reason → act → observe`)
- Takes player action + game state context → produces mechanical resolution
- Output structure: `MechanicalResolution(dice_rolls[], state_changes[], rules_applied[], narrative_hooks[])`
- `narrative_hooks` = brief mechanical outcome summaries for the Narrator to weave into narration
- Uses Sonnet model for reasoning about complex rule interactions
- Different from ArchivistAgent: Archivist retrieves data, Arbiter makes judgments

### Stream C: Orchestrator Dual-Response & Integration
**Scope**: Modify orchestrator to run Narrator + Arbiter in parallel, merge results coherently, add response streaming
**Files**:
- `src/dm20_protocol/claudmaster/orchestrator.py` (MODIFY — response aggregation)
- `src/dm20_protocol/claudmaster/tools/action_tools.py` (MODIFY — structured dual response)
- `src/dm20_protocol/claudmaster/config.py` (MODIFY — if not done in Stream A)
- `tests/claudmaster/test_dual_agent_flow.py` (NEW)
**Agent Type**: backend-specialist
**Can Start**: after Stream A + B complete (needs both agents wired)
**Estimated Hours**: 4
**Dependencies**: Stream A, Stream B
**Details**:
- Phase 1 (immediate): Narrator receives player action → fast narrative response (~1-2s)
- Phase 2 (parallel): Arbiter receives same action + game state → mechanical resolution (~5-10s)
- Phase 3 (merge): If Arbiter's result changes the narrative (e.g., attack hits/misses), append/amend the narrative
- Merge strategies: append (most common), amend (combat outcomes), override (critical failures)
- Response format: `DualAgentResponse(narrative: str, mechanics: MechanicalResolution, merged_narrative: str)`

### Stream D: Performance Benchmarks & E2E Tests
**Scope**: End-to-end tests of dual-agent flow, latency benchmarks, quality verification
**Files**:
- `tests/claudmaster/test_dual_agent_e2e.py` (NEW)
- `tests/claudmaster/test_performance_benchmarks.py` (NEW)
**Agent Type**: backend-specialist
**Can Start**: after Stream C completes
**Estimated Hours**: 2
**Dependencies**: Stream C
**Details**:
- E2E: player_action → dual response with mock LLM → verify narrative + mechanics
- Latency: measure time-to-first-response (Narrator) vs total-time (Arbiter)
- Quality: verify merged narrative coherence
- Regression: existing single-agent tests still pass

## Coordination Points

### Shared Files
- `config.py` — Stream A adds per-agent model fields, Stream C may need merge strategy config
  → **Mitigation**: Stream A handles all config changes, Stream C reads only
- `orchestrator.py` — Stream C modifies agent routing and response aggregation
  → **Mitigation**: Only Stream C touches this file
- `tools/session_tools.py` — Stream A wires LLM client + NarratorAgent
  → **Mitigation**: Only Stream A touches this file; Stream C wires Arbiter if needed

### Sequential Requirements
1. LLM Client (A) must exist before integration (C) can wire real models
2. Arbiter Agent (B) must exist before orchestrator (C) can route to it
3. Both A + B must complete before C can integrate
4. C must complete before D can run E2E tests

## Conflict Risk Assessment

- **Low Risk**: Streams A and B work on completely different files (no overlap)
- **Medium Risk**: Stream C modifies orchestrator.py which is a core file — but only C touches it
- **Low Risk**: Config changes are additive (new fields with defaults)

## Parallelization Strategy

**Recommended Approach**: hybrid

```
Timeline:
  ├── Stream A (LLM Client)     [4h] ─────┐
  ├── Stream B (Arbiter Agent)   [4h] ─────┤
  │                                        ├── Stream C (Integration)  [4h] ──── Stream D (E2E) [2h]
  └────────────────────────────────────────┘
```

Launch Streams A and B simultaneously. Start C when both complete. D follows C.

## Expected Timeline

With parallel execution:
- Wall time: ~10 hours (A/B parallel: 4h + C: 4h + D: 2h)
- Total work: 14 hours
- Efficiency gain: 29%

Without parallel execution:
- Wall time: 14 hours

## Notes

1. **LLM Client is the real MVP** — Without it, nothing else works in production. Stream A is the critical path.
2. **Arbiter vs Archivist distinction**: The Archivist retrieves facts (pure Python). The Arbiter makes judgments using LLM (e.g., "does this creative spell usage work within RAW?"). They complement each other.
3. **Streaming is a stretch goal**: The initial implementation should work with non-streaming responses. Streaming can be added as a follow-up optimization.
4. **The academic paper** (arxiv:2502.19519v2) validates multi-agent GM architecture — we're aligning with proven research.
5. **Config per-agent models** open the door to future cost optimization (e.g., Haiku for simple narration, Sonnet for complex scenes, Opus for critical plot moments).
