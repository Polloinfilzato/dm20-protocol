---
issue: 33
title: Claudmaster Directory Structure and Base Classes
analyzed: 2026-02-06T00:00:00Z
---

# Issue #33 Analysis: Claudmaster Directory Structure and Base Classes

## Overview

Foundation task establishing the directory structure and core abstract classes for the Claudmaster AI DM system. No dependencies — this is the starting point for the entire epic.

## Codebase Context

- **Project uses**: Pydantic v2 models, FastMCP, Python 3.12+, pytest
- **Existing patterns**: Models in `models.py` use Pydantic `BaseModel`, `Field`, enums
- **Test framework**: pytest with conftest.py, tests in `tests/` directory
- **Code style**: ruff with E, F, I, N, W rules; mypy strict mode

## Work Streams

### Stream A: Directory Structure and Base Agent Class
**Agent type:** python-pro
**Files to create:**
- `src/gamemaster_mcp/claudmaster/__init__.py`
- `src/gamemaster_mcp/claudmaster/base.py`
- `src/gamemaster_mcp/claudmaster/agents/__init__.py`

**Scope:**
- Create directory structure
- Implement abstract `Agent` base class with ReAct pattern (reason, act, observe)
- Define `AgentRequest`, `AgentResponse` types
- Set up `__init__.py` with public exports

**Can start immediately:** Yes

### Stream B: Config and Session Classes
**Agent type:** python-pro
**Files to create:**
- `src/gamemaster_mcp/claudmaster/config.py`
- `src/gamemaster_mcp/claudmaster/session.py`

**Scope:**
- `ClaudmasterConfig` dataclass with Pydantic v2 (LLM config, agent behavior, narrative style, difficulty, house rules)
- `ClaudmasterSession` class (conversation history, active agents, turn counter, metadata)

**Can start immediately:** Yes (parallel with Stream A)

### Stream C: Unit Tests
**Agent type:** python-pro
**Files to create:**
- `tests/test_claudmaster_base.py`
- `tests/test_claudmaster_config.py`
- `tests/test_claudmaster_session.py`

**Scope:**
- Tests for Agent abstract class (verify interface, test concrete subclass)
- Tests for ClaudmasterConfig (defaults, validation, serialization)
- Tests for ClaudmasterSession (state management, turn tracking)

**Can start immediately:** No — depends on Stream A and Stream B

## Dependencies Between Streams

```
Stream A (base.py) ──┐
                     ├──> Stream C (tests)
Stream B (config/session) ──┘
```

## Coordination Notes

- Stream A and B are fully independent and can run in parallel
- Stream C must wait for both A and B to complete
- No conflicts with existing files (all new files in new directory)
- Config should follow existing Pydantic patterns from `models.py`

## Risk Assessment

- **Low risk**: All new files, no modifications to existing code
- **Pattern consistency**: Must match existing code style (Pydantic v2, type hints, docstrings)
- **Key decision**: How much detail in ClaudmasterConfig — keep minimal for now, extend in later tasks
