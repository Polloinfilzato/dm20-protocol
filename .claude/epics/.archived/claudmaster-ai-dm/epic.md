---
name: Claudmaster - Autonomous AI Dungeon Master
status: completed
created: 2026-02-05T19:06:45Z
updated: 2026-02-09T00:55:46Z
completed: 2026-02-09T00:55:46Z
prd: claudmaster-ai-dm
github: https://github.com/Polloinfilzato/dm20-protocol/issues/29
progress: 100
---

# Epic: Claudmaster - Autonomous AI Dungeon Master

## Overview

Transform gamemaster-mcp from a campaign tracker into a complete AI Dungeon Master that can run published adventures autonomously, supporting both solo play and multi-player sessions.

## Goals

1. **Multi-Agent Architecture** — Specialized agents (Narrator, Archivist, Module Keeper) for different DM responsibilities
2. **Module Integration** — RAG-based system to follow published adventure modules (Curse of Strahd, etc.)
3. **Improvisation Control** — 5 configurable levels of AI creative freedom vs module fidelity
4. **Narrative Engine** — Coherent storytelling with memory, consistency, and atmospheric descriptions
5. **Autonomous Resolution** — AI handles all DM decisions without human intervention
6. **Scalable Sessions** — Same system works for solo play and multi-player groups

## Technical Approach

### Architecture

```
CLAUDMASTER ORCHESTRATOR
├── Narrator Agent (ReAct) — Scene descriptions, NPC dialogue, atmosphere
├── Archivist Agent — Game state, rules, combat, dice
├── Module Keeper Agent (RAG) — PDF module knowledge, plot, NPCs, locations
└── Consistency Engine — Fact tracking, contradiction detection
```

### Key Technologies

- **LangChain** — Agent framework and ReAct implementation
- **ChromaDB** — Vector store for RAG on adventure modules
- **Existing PDF Library** — Module content access (dependency)
- **Existing Game State** — HP, inventory, combat (dependency)

### Improvisation Levels

| Level | Module Adherence | AI Freedom |
|-------|------------------|------------|
| None | 100% script | Zero |
| Low | 95% faithful | Descriptions only |
| Medium | 70% plot intact | Dialogue, side content |
| High | 40% key beats | Most decisions |
| Full | 0% inspiration | Complete freedom |

## Dependencies

- **PDF Rulebook Library** (PRD: pdf-rulebook-library) — Must be implemented for module access
- **Existing Game State System** — HP, inventory, conditions
- **Existing Combat System** — Initiative, rounds, attacks
- **Existing Character System** — PCs, NPCs, stats

## Success Criteria

| Metric | Target |
|--------|--------|
| Solo session completion | Player never acts as DM |
| Module fidelity | Major plot points hit at Low/Medium |
| NPC consistency | No contradictions noticed |
| Response time p95 | < 10 seconds |
| Session continuity | 100% state recovery |

## Implementation Phases

### Phase 1: Foundation (Tasks 33-36)
- Orchestrator skeleton and basic structure
- Basic Narrator agent (descriptions only)
- Integration with existing game state
- Claudmaster configuration system

### Phase 2: Module Integration (Tasks 37-41)
- Module Keeper agent with RAG
- Adventure module parsing (chapters, encounters, NPCs)
- Vector store setup (ChromaDB)
- Module binding to campaigns

### Phase 3: Full Narrative (Tasks 42-46)
- Complete Narrator agent with NPC dialogue
- Archivist agent for rules/state queries
- Action interpretation system
- Combat narration

### Phase 4: Consistency (Tasks 47-50)
- Fact tracker for established narrative
- NPC knowledge state tracking
- Contradiction detection
- Timeline consistency

### Phase 5: Improvisation Control (Tasks 51-54)
- 5 improvisation levels implementation
- Locked/flexible elements configuration
- Module fidelity enforcement
- Canonical vs improvised tagging

### Phase 6: Companion System (Tasks 55-58)
- AI-controlled companion profiles
- Combat tactics for companions
- Companion personality/roleplay
- Player guidance system

### Phase 7: Multi-Player (Tasks 59-62)
- Multiple PC tracking
- Turn distribution and management
- Split party handling
- Player-specific information

### Phase 8: MCP Tools & Polish (Tasks 63-68)
- `start_claudmaster_session` tool
- `player_action` tool
- `configure_claudmaster` tool
- Session continuity
- Error handling
- Performance optimization

## Task Breakdown Preview

Based on PRD requirements and 8 phases:

| Phase | Tasks | Focus |
|-------|-------|-------|
| 1. Foundation | 4 | Orchestrator, basic Narrator |
| 2. Module Integration | 5 | Module Keeper, RAG, parsing |
| 3. Full Narrative | 5 | Complete Narrator, Archivist |
| 4. Consistency | 4 | Fact tracking, contradictions |
| 5. Improvisation | 4 | Levels, configuration |
| 6. Companions | 4 | AI-controlled party members |
| 7. Multi-Player | 4 | Multiple PCs, turn mgmt |
| 8. MCP Tools & Polish | 6 | Tools, continuity, errors |

**Total: ~36 tasks** (numbered 33-68 based on GitHub issue sequence)

## References

- [PRD: claudmaster-ai-dm](.claude/prds/claudmaster-ai-dm.md)
- [arxiv:2502.19519v2](https://arxiv.org/html/2502.19519v2) - Static vs Agentic GM AI research
- [GameMasterAI](https://github.com/deckofdmthings/GameMasterAI)
- [D&D Solo Adventure](https://github.com/MarcosN7/dnd-ai-beta)
- [Mnehmos' D&D MCP](https://skywork.ai/skypage/en/ai-dungeon-master-toolkit/1980458059440967680)

## Tasks Created

### Phase 1: Foundation
- [ ] 33.md - Claudmaster Directory Structure and Base Classes (parallel: true)
- [ ] 34.md - Orchestrator Skeleton (parallel: false)
- [ ] 35.md - Basic Narrator Agent (parallel: true)
- [ ] 36.md - Claudmaster Configuration MCP Tool (parallel: false)

### Phase 2: Module Integration
- [ ] 37.md - ChromaDB Vector Store Setup (parallel: true)
- [ ] 38.md - Adventure Module Parser (parallel: false)
- [ ] 39.md - Module Content Chunking and Indexing (parallel: false)
- [ ] 40.md - Module Keeper Agent (parallel: false)
- [ ] 41.md - Campaign Module Binding (parallel: false)

### Phase 3: Full Narrative
- [ ] 42.md - Enhanced Narrator with NPC Dialogue (parallel: false)
- [ ] 43.md - Archivist Agent Implementation (parallel: true)
- [ ] 44.md - Player Action Interpretation (parallel: false)
- [ ] 45.md - Combat Narration System (parallel: true)
- [ ] 46.md - Scene Atmosphere and Pacing (parallel: true)

### Phase 4: Consistency
- [ ] 47.md - Fact Tracker System (parallel: true)
- [ ] 48.md - NPC Knowledge State Tracking (parallel: false)
- [ ] 49.md - Contradiction Detection (parallel: false)
- [ ] 50.md - Timeline and Location State Consistency (parallel: true)

### Phase 5: Improvisation Control
- [ ] 51.md - Improvisation Level System (parallel: true)
- [ ] 52.md - Locked and Flexible Elements Configuration (parallel: false)
- [ ] 53.md - Module Fidelity Enforcement (parallel: false)
- [ ] 54.md - Canonical vs Improvised Tagging (parallel: true)

### Phase 6: Companion System
- [ ] 55.md - Companion NPC Profiles (parallel: true)
- [ ] 56.md - AI Combat Tactics for Companions (parallel: false)
- [ ] 57.md - Companion Roleplay and Dialogue (parallel: true)
- [ ] 58.md - Player Guidance System for Companions (parallel: false)

### Phase 7: Multi-Player
- [ ] 59.md - Multiple PC Tracking (parallel: true)
- [ ] 60.md - Turn Distribution and Management (parallel: false)
- [ ] 61.md - Split Party Handling (parallel: false)
- [ ] 62.md - Player-Specific Information (parallel: true)

### Phase 8: MCP Tools & Polish
- [ ] 63.md - start_claudmaster_session MCP Tool (parallel: true)
- [ ] 64.md - player_action MCP Tool (parallel: true)
- [ ] 65.md - end_session and get_session_state MCP Tools (parallel: true)
- [ ] 66.md - Session Continuity and Recaps (parallel: false)
- [ ] 67.md - Error Handling and Recovery (parallel: true)
- [ ] 68.md - Performance Optimization (parallel: false)

## Summary

| Metric | Value |
|--------|-------|
| Total tasks | 36 |
| Parallel tasks | 17 |
| Sequential tasks | 19 |
| Estimated total effort | ~252 hours |
