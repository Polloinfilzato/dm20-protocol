---
name: claudmaster-production-polish
description: End-to-end integration hardening, onboarding experience, session continuity, RAG activation with ChromaDB, and UX polish to make Claudmaster a production-ready "wow" product
status: backlog
created: 2026-02-15T12:00:00Z
updated: 2026-02-15T01:28:47Z
---

# PRD: Claudmaster Production Polish

## Executive Summary

Claudmaster has ~23,000 lines of Python across 62 modules with comprehensive unit tests. The multi-agent architecture (Narrator, Archivist, Module Keeper, Arbiter), consistency engine, companion system, DM persona, game loop, and slash commands are all implemented. However, the system has never been stress-tested as a **cohesive product** under real gameplay conditions.

This PRD bridges the gap between "code complete" and "product ready" — the last mile that transforms working code into an experience that makes users say "wow."

**Key deliverables:**

1. **Integration Test Suite** — End-to-end scenarios validating the full game loop under realistic conditions
2. **Onboarding Experience** — Guided first-session flow that gets a new user playing within 5 minutes
3. **Session Continuity** — Automatic recap generation and cross-session context preservation
4. **Agent Prompt Tuning** — Calibrated prompts for narrative quality, tone consistency, and response format
5. **Error UX** — User-facing error messages that maintain immersion instead of breaking it
6. **Robustness Hardening** — Edge case handling, timeout resilience, and graceful degradation under real conditions
7. **RAG Activation & ChromaDB Integration** — Wire the existing ModuleKeeper agent into the game loop and upgrade Library search from TF-IDF to vector embeddings for semantic rulebook retrieval

**Value proposition:** A new user installs dm20-protocol, runs `/dm:start`, and within 5 minutes is immersed in a D&D session with rich narration, responsive mechanics, semantic rulebook knowledge, and seamless state management — without reading documentation or debugging errors.

## Problem Statement

### Current State

All subsystems pass their unit tests individually. The DM persona file, slash commands, and agent definitions exist. A basic end-to-end playtest was conducted during the dm-persona-gameloop epic.

However:

```
Known unknowns:
├── How do agents behave under sustained multi-turn sessions? (token budget, context drift)
├── What happens when the player does something unexpected? (edge cases)
├── Is the narrative quality consistent across different models? (Opus vs Sonnet vs Haiku)
├── How does a brand-new user experience the first 5 minutes? (onboarding)
├── What does the error experience look like in practice? (not in tests)
├── Does session resume actually preserve narrative context? (not just data)
├── ModuleKeeper agent is fully implemented but never wired into sessions (dead code)
└── Library search uses TF-IDF keywords — does it find what players actually need? (semantic gap)
```

### Why Now?

- All code is written — this is purely about integration, testing, and polish
- The installer is ready — new users can install the MCP server
- Model quality profiles exist — but haven't been validated against real gameplay
- The risk is shipping a product where individual parts work but the whole doesn't gel

### Target User

First-time dm20-protocol user who:
- Just installed via the installer (user mode)
- Has never used MCP tools before
- Wants to play D&D solo with an AI DM
- Will judge the product in the first 5 minutes

## Architecture Overview

This PRD primarily hardens and polishes the existing stack, with one key activation: wiring the already-implemented ChromaDB/RAG infrastructure into the live system.

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXISTING ARCHITECTURE                         │
│              (activation + hardening, minimal new code)          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  /dm:start ──► start_claudmaster_session ──► Orchestrator       │
│  /dm:action ──► player_action ──► Intent ──► Agent routing      │
│  /dm:combat ──► combat tools ──► Arbiter + Combat Narrator      │
│  /dm:save ──► end_claudmaster_session ──► Persistence           │
│                                                                 │
│  THIS PRD FOCUSES ON:                                           │
│  ┌──────────────┐ ┌──────────────┐ ┌────────────────────┐      │
│  │ Integration  │ │  Onboarding  │ │  Prompt Tuning     │      │
│  │ Testing      │ │  Flow        │ │  & Error UX        │      │
│  └──────────────┘ └──────────────┘ └────────────────────┘      │
│  ┌──────────────────────────────────────────────────────┐      │
│  │ RAG Activation: ModuleKeeper wiring + Library        │      │
│  │ vector search upgrade (ChromaDB + embeddings)        │      │
│  └──────────────────────────────────────────────────────┘      │
│                                                                 │
│  ALREADY IMPLEMENTED (needs wiring):                            │
│  VectorStoreManager ─► ChromaDB persistent storage              │
│  ModuleIndexer ──────► Intelligent text chunking                │
│  ModuleKeeperAgent ──► RAG retrieval (NPC, location, plot)      │
│                                                                 │
│  NEEDS UPGRADE:                                                 │
│  LibrarySearch ──────► TF-IDF → Vector embeddings               │
│  ask_books() ────────► Keyword matching → Semantic search       │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## User Stories

### US-1: First-Time Player Onboarding
**As a** new dm20-protocol user
**I want to** start playing D&D immediately after installation
**So that** I don't need to read docs or figure out tool commands

**Acceptance Criteria:**
- Running `/dm:start` with no existing campaign triggers a guided setup
- The setup creates a campaign, a character (with guided choices), and drops the player into a scene
- The entire onboarding takes < 5 minutes
- The first scene is engaging and demonstrates the system's capabilities (narration + a simple interaction)

### US-2: Session Resume with Context
**As a** returning player
**I want to** resume my session and immediately know where I left off
**So that** I don't lose narrative immersion between sessions

**Acceptance Criteria:**
- `/dm:start` with an existing session generates a "Previously on..." recap
- The recap covers: location, active quest, recent events, party status
- The DM's narration after resume feels continuous, not like a cold restart
- Recap is generated from persisted session data, not hallucinated

### US-3: Graceful Error Handling
**As a** player
**I want** errors to be handled in-character when possible
**So that** technical issues don't break immersion

**Acceptance Criteria:**
- Missing campaign data → "The mists obscure your path... (Campaign not found. Create one with /dm:start)"
- Agent timeout → DM continues with degraded but functional response
- Invalid action → DM asks for clarification in-character
- No stacktraces or raw Python errors ever reach the player

### US-4: Consistent Narrative Quality
**As a** player
**I want** the DM's narration to be vivid and consistent
**So that** every session feels like a quality tabletop experience

**Acceptance Criteria:**
- Narrator agent produces atmospheric descriptions (not generic "you enter a room")
- NPC dialogue has distinct voices (not all NPCs sound the same)
- Combat narration is dramatic and varied (not "you hit for 8 damage" every time)
- Quality is acceptable across all three model profiles (quality/balanced/economy)

### US-5: Semantic Rulebook Knowledge
**As a** player who has provided their own D&D rulebooks (PDFs/Markdown)
**I want** the DM to understand and retrieve relevant rules semantically
**So that** when I ask about a class feature, spell interaction, or obscure rule, the DM finds the right answer even if I don't use the exact wording from the book

**Acceptance Criteria:**
- Library search uses vector embeddings (ChromaDB) instead of keyword matching
- Searching "tanky frontline build" finds Fighter, Barbarian, and Paladin sections even without those exact words
- ModuleKeeper agent is active during gameplay and provides contextual lore/NPC/location info from loaded adventure modules
- RAG dependencies (chromadb, sentence-transformers) are optional — system degrades gracefully to TF-IDF if not installed
- First-time indexing of a new rulebook completes in reasonable time (< 60s per PDF)

### US-6: Multi-Turn Session Stability
**As a** player in a long session
**I want** the game to remain stable and responsive
**So that** I can play for an hour+ without issues

**Acceptance Criteria:**
- 20+ turn sessions complete without errors
- Context window management keeps responses relevant
- Game state remains consistent (no forgotten NPCs, no contradictions)
- Performance doesn't degrade over time

## Functional Requirements

| ID | Requirement | Priority | Notes |
|----|-------------|----------|-------|
| FR-1 | Integration test suite with 5+ end-to-end scenarios | Must | Exploration, combat, social, session resume, edge cases |
| FR-2 | Onboarding flow in `/dm:start` for new users | Must | Campaign + character creation + first scene |
| FR-3 | Session recap generator on resume | Must | "Previously on..." from persisted data |
| FR-4 | Narrator prompt calibration per model profile | Must | Quality/balanced/economy all produce good output |
| FR-5 | Error wrapper for all player-facing tool responses | Must | In-character error messages |
| FR-6 | Combat flow integration test (initiative → rounds → resolution) | Must | Full combat from start to XP |
| FR-7 | Stress test: 20-turn session without failures | Should | Validates context management |
| FR-8 | Agent timeout fallback responses | Should | Degraded but functional when agent is slow |
| FR-9 | Edge case handling for ambiguous player input | Should | "I do something" → clarification request |
| FR-10 | Starter adventure content (1 location, 2 NPCs, 1 encounter) | Could | Built-in "tutorial dungeon" for onboarding |
| FR-11 | Wire ModuleKeeper agent into Claudmaster session initialization | Must | Register in orchestrator, route EXPLORATION/QUESTION intents to it |
| FR-12 | Upgrade LibrarySearch to vector embeddings via ChromaDB | Must | Replace TF-IDF with semantic search for `ask_books()` and `search_library()` |
| FR-13 | Auto-index rulebooks into ChromaDB on first `scan_library()` | Should | Generate embeddings during scan, cache in persistent ChromaDB store |
| FR-14 | Graceful RAG degradation when chromadb is not installed | Must | Fall back to existing TF-IDF search; warn user once about optional deps |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Player action response time | < 15s (balanced profile) |
| NFR-2 | Session resume time | < 5s |
| NFR-3 | Onboarding completion time | < 5 minutes |
| NFR-4 | Zero raw Python errors in player output | 100% |
| NFR-5 | Session stability (no crashes) | 20+ turns |
| NFR-6 | Rulebook indexing time (per PDF) | < 60s |
| NFR-7 | Semantic search query time | < 2s |
| NFR-8 | ChromaDB storage overhead per rulebook | < 50MB |

## Dependencies

| Dependency | Status | Impact |
|------------|--------|--------|
| Claudmaster core (agents, orchestrator) | Complete | Foundation |
| DM persona + slash commands | Complete | Game loop |
| Model quality profiles | Complete | Multi-model support |
| Session persistence | Complete | Resume capability |
| Consistency engine | Complete | Narrative coherence |
| Installer (user mode) | Complete | New user path |
| VectorStoreManager (ChromaDB wrapper) | Complete | Persistent vector storage, embedding generation |
| ModuleIndexer (text chunking) | Complete | Intelligent chunking with metadata extraction |
| ModuleKeeperAgent (RAG retrieval) | Complete | NPC knowledge, locations, encounters, plot — needs wiring |
| chromadb + sentence-transformers (optional deps) | Declared | `pip install dm20-protocol[rag]` — optional install |

## Implementation Order

```
Phase 1: Integration Testing (validate what works, find what breaks)
    ├── End-to-end test scenarios
    ├── Combat flow validation
    └── Multi-turn stress test

Phase 2: Error UX & Robustness (fix what breaks)
    ├── Error wrapper for player-facing responses
    ├── Agent timeout fallbacks
    └── Edge case handling

Phase 3: Onboarding & Continuity (first impression + returning player)
    ├── Guided first-session flow
    ├── Session recap generator
    └── Starter adventure content (optional)

Phase 4: RAG Activation (connect the knowledge layer)
    ├── Wire ModuleKeeper into Claudmaster session + orchestrator
    ├── Upgrade LibrarySearch to ChromaDB vector embeddings
    ├── Auto-index rulebooks on scan_library()
    └── Graceful degradation when RAG deps not installed

Phase 5: Prompt Tuning & Quality (the "wow")
    ├── Narrator prompt calibration
    ├── NPC dialogue differentiation
    ├── Combat narration variety
    └── Model profile validation (quality/balanced/economy)
```

## Success Metrics

| Metric | Target |
|--------|--------|
| New user plays first scene without errors | 100% |
| 20-turn session completes without crashes | 100% |
| Narrative quality rated "good+" on all profiles | Subjective playtest |
| Session resume preserves full context | Verified by recap accuracy |
| Zero Python errors in player output | 100% |
| Semantic search finds relevant results for conceptual queries | Manual validation |
| ModuleKeeper provides contextual lore during gameplay | Verified in integration test |

## Open Questions

1. Should the starter adventure be a mini-module (structured content) or a procedurally generated scenario?
2. Should the onboarding create a pre-built character or walk the player through full creation?
3. What level of narrator prompt customization should be exposed to users (beyond model profile)?
4. Should vector indexing happen eagerly (on `scan_library()`) or lazily (on first search query)?
5. Should the ModuleKeeper share the same ChromaDB instance as LibrarySearch or use separate collections?
