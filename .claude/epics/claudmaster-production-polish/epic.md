---
name: claudmaster-production-polish
status: backlog
created: 2026-02-15T01:03:54Z
updated: 2026-02-15T01:39:36Z
progress: 0%
prd: .claude/prds/claudmaster-production-polish.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/115
---

# Epic: Claudmaster Production Polish

## Overview

Harden Claudmaster from "code complete" to "product ready" by validating the full game loop under realistic conditions, activating the ChromaDB-powered RAG pipeline (ModuleKeeper wiring + Library vector search upgrade), adding a guided onboarding flow for new users, implementing session recap on resume, and tuning agent prompts for narrative quality. Minimal new architecture — this is activation of existing code, integration testing, error UX polish, and the "last mile" that makes users say "wow."

## Architecture Decisions

- **Activate, don't rebuild** — VectorStoreManager, ModuleIndexer, and ModuleKeeperAgent are fully implemented. The work is wiring them into the live system, not writing new RAG infrastructure.
- **Single ChromaDB instance, separate collections** — ModuleKeeper uses per-module collections (adventure content); Library uses per-source collections (rulebooks). Same `VectorStoreManager`, different collection namespaces.
- **Graceful degradation is mandatory** — When `chromadb`/`sentence-transformers` are not installed, the system falls back to TF-IDF search silently. RAG is an enhancement, not a requirement.
- **Integration tests use MockLLMClient** — Validates orchestration flow without API calls; separate manual playtest validates narrative quality
- **Onboarding logic lives in `start_claudmaster_session()`** — Extends the existing session tool rather than creating a new entry point
- **Error wrapping is centralized** — `ErrorMessageFormatter` already exists in `recovery/error_messages.py`; extend coverage to all player-facing tool responses
- **Session recap uses persisted data** — `SessionSerializer` already saves action history and state snapshots; recap generator reads these, no new storage needed
- **Prompt tuning via DM persona + agent prompts** — Calibrate existing prompt strings, not new prompt infrastructure

## Technical Approach

### Integration Testing (Phase 1)

The test infrastructure exists (`MockLLMClient`, async test patterns, `test_manual_integration.py`). Create end-to-end scenario tests that exercise the full pipeline:

- **Exploration flow:** Intent classification → Narrator + ModuleKeeper → response aggregation
- **Combat flow:** `start_combat` → initiative → turns → damage → `end_combat` → XP calculation
- **Social/roleplay flow:** NPC interaction → Arbiter resolution → consistency tracking
- **Session lifecycle:** Start → multi-turn play → save → load → resume → verify state continuity
- **Error scenarios:** Agent timeout → fallback response; invalid input → clarification; missing campaign → helpful error
- **Stress test:** 20+ turn session validating context management and state consistency

### Error UX & Robustness (Phase 2)

`ErrorMessageFormatter` and the error hierarchy already exist. The gap is ensuring **every** player-facing code path uses them:

- Wrap `player_action()` and `start_claudmaster_session()` return paths with error formatting
- Add timeout fallback responses when individual agents exceed their deadline
- Handle ambiguous/empty player input with in-character clarification requests
- Ensure zero raw Python exceptions leak to player output

### Onboarding & Session Continuity (Phase 3)

**Onboarding:** When `start_claudmaster_session()` detects no existing campaign:
- Auto-create campaign with sensible defaults
- Guide character creation through Narrator-driven prompts
- Drop player into an engaging first scene that demonstrates narration + interaction
- Target: playing within 5 minutes of install

**Session recap:** When resuming an existing session:
- Read `action_history.json` and `state_snapshot.json` from persisted session
- Generate "Previously on..." summary covering: location, active quest, recent events, party status
- Feed recap into Narrator for atmospheric delivery

### RAG Activation (Phase 4)

**A) Wire ModuleKeeper into Claudmaster sessions:**
- Register ModuleKeeperAgent in `start_claudmaster_session()` (resolve the existing TODO)
- Add ModuleKeeper to orchestrator's agent routing for EXPLORATION and QUESTION intents
- Initialize VectorStoreManager with campaign-specific storage path
- Index adventure module content on session start (if not already indexed)

**B) Upgrade LibrarySearch to vector embeddings:**
- Extend `VectorStoreManager` usage to the Library module (reuse existing ChromaDB wrapper)
- Create per-source collections in ChromaDB during `scan_library()`
- Chunk TOC content + extracted text using `ModuleIndexer`'s chunking logic (or shared utility)
- Replace `LibrarySearch.search()` scoring with ChromaDB similarity query
- Keep TF-IDF as fallback when RAG deps not installed

**C) Graceful degradation:**
- Detect `chromadb`/`sentence-transformers` availability at import time (already uses try/except)
- Log one-time warning when falling back to TF-IDF
- All public APIs (`ask_books()`, `search_library()`) work identically regardless of backend

### Prompt Tuning (Phase 5)

- Calibrate Narrator prompts for vivid, varied descriptions across model profiles
- Differentiate NPC dialogue voices (accent, vocabulary, personality markers)
- Vary combat narration beyond "you hit for X damage"
- Validate quality/balanced/economy profiles all produce acceptable output

## Implementation Strategy

### Development Phases

1. **Integration Testing** — Write tests first to discover real issues. This drives all subsequent work.
2. **Error UX & Robustness** — Fix issues found by integration tests + harden error paths.
3. **Onboarding & Continuity** — Build the first-time and returning-player experience.
4. **RAG Activation** — Wire ModuleKeeper, upgrade Library search, ensure graceful degradation.
5. **Prompt Tuning** — Final quality pass on narrative output.

### Risk Mitigation

- Integration tests may reveal bugs in existing code → budget time for fixes
- ChromaDB indexing may be slow on large PDFs → benchmark and optimize chunk size
- Embedding model download on first use → document in install instructions
- Prompt tuning is subjective → define minimum quality bar, not perfection
- MockLLMClient tests validate flow but not narrative quality → complement with manual playtest

### Testing Approach

- Automated: End-to-end tests with MockLLMClient covering all major flows
- Automated: RAG pipeline tests (index → query → retrieve) with test fixtures
- Manual: Playtesting sessions (quality + economy profiles) to validate narrative quality
- Stress: 20+ turn automated session to validate stability

## Task Breakdown Preview

- [ ] Task 1: End-to-end integration test suite (exploration, combat, social, session lifecycle, error scenarios)
- [ ] Task 2: Stress test — 20-turn session stability and context management validation
- [ ] Task 3: Error UX hardening — wrap all player-facing responses, timeout fallbacks, input validation
- [ ] Task 4: Onboarding flow — guided first-session in `start_claudmaster_session()` for new users
- [ ] Task 5: Session recap generator — "Previously on..." from persisted session data on resume
- [ ] Task 6: RAG activation — Wire ModuleKeeper into sessions + upgrade LibrarySearch to ChromaDB vector embeddings
- [ ] Task 7: Prompt tuning & narrative quality — Narrator calibration, NPC voices, combat narration variety
- [ ] Task 8: Starter adventure content — built-in tutorial scenario (1 location, 2 NPCs, 1 encounter)

## Dependencies

| Dependency | Status | Impact |
|------------|--------|--------|
| Orchestrator + agents (Narrator, Archivist, Arbiter, ModuleKeeper) | Complete | Core game loop |
| DM persona + slash command workflow | Complete | Player-facing interface |
| Model quality profiles (quality/balanced/economy) | Complete | Multi-model support |
| Session persistence (SessionSerializer) | Complete | Save/load/resume |
| Consistency engine (fact tracking, contradiction detection) | Complete | Narrative coherence |
| ErrorMessageFormatter + error hierarchy | Complete | Error UX foundation |
| MockLLMClient + async test infrastructure | Complete | Test tooling |
| Installer (user mode) | Complete | New user install path |
| VectorStoreManager (ChromaDB wrapper) | Complete | Persistent vector storage with embeddings |
| ModuleIndexer (text chunking + metadata) | Complete | Intelligent chunking for RAG pipeline |
| ModuleKeeperAgent (RAG retrieval) | Complete | NPC/location/encounter/plot queries — needs wiring |
| chromadb + sentence-transformers (optional) | Declared | `pip install dm20-protocol[rag]` |

All core dependencies are complete. RAG optional dependencies are declared but require user installation.

## Success Criteria (Technical)

| Criteria | Target |
|----------|--------|
| Integration test coverage | 5+ end-to-end scenarios passing |
| Stress test stability | 20+ turns without errors |
| Error leakage | Zero raw Python exceptions in player output |
| Onboarding time | < 5 minutes from install to first scene |
| Session resume | Accurate recap from persisted data |
| Narrative quality | Acceptable on all 3 model profiles (manual validation) |
| Semantic search accuracy | Conceptual queries find relevant rulebook content |
| ModuleKeeper integration | Provides contextual lore during gameplay |
| RAG degradation | System fully functional without chromadb installed |

## Estimated Effort

| Task | Size | Estimate |
|------|------|----------|
| Integration test suite | M | 4-6h |
| Stress test | S | 2-3h |
| Error UX hardening | M | 4-6h |
| Onboarding flow | M | 4-6h |
| Session recap generator | S | 2-3h |
| RAG activation (ModuleKeeper + Library vector search) | L | 6-8h |
| Prompt tuning & quality | M | 4-6h |
| Starter adventure content | S | 2-3h |
| **Total** | **L** | **28-40h** |

**Critical path:** Integration tests → Error UX → Onboarding → RAG activation → Prompt tuning (sequential dependency: tests reveal issues that inform later work; RAG activation before prompt tuning because ModuleKeeper affects narrative context).

## Tasks Created
- [ ] 116.md - End-to-End Integration Test Suite (parallel: true)
- [ ] 117.md - 20-Turn Stress Test for Session Stability (parallel: true, depends: 116)
- [ ] 118.md - Error UX Hardening (parallel: false, depends: 116)
- [ ] 119.md - Guided Onboarding Flow for New Users (parallel: false, depends: 118)
- [ ] 120.md - Session Recap Generator (parallel: true, depends: 118)
- [ ] 121.md - RAG Activation — ModuleKeeper Wiring + Library Vector Search (parallel: false, depends: 119, 120)
- [ ] 122.md - Prompt Tuning and Narrative Quality (parallel: true, depends: 121)
- [ ] 123.md - Starter Adventure Content (parallel: true, depends: 119)

Total tasks: 8
Parallel tasks: 5
Sequential tasks: 3
Estimated total effort: 28-40h

### Dependency Graph
```
#116 Integration Tests ──┬──► #117 Stress Test
                         │
                         └──► #118 Error UX ──┬──► #119 Onboarding ──┬──► #121 RAG Activation ──► #122 Prompt Tuning
                                              │                      │
                                              └──► #120 Recap ───────┘
                                                                     │
                                              #119 ─────────────────►└──► #123 Starter Adventure
```
