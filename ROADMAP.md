# Roadmap

> Last updated: 2026-02-08

## Current Status

DM20 Protocol is a fully functional MCP server with **50+ tools** for D&D campaign management. The **Claudmaster** autonomous AI DM system has been architecturally completed — all agents, game state systems, and MCP tools are implemented and tested.

**What works today:** Campaign management, character sheets, NPCs, locations, quests, combat, session notes, dice rolls, PDF rulebook library with keyword and semantic search.

**What's next:** Bringing Claudmaster from architecture to production — real LLM integration, tested PDF module loading, and player-facing quality of life improvements.

---

## Phase 1 — LLM Integration (High Priority)

The multi-agent system (Narrator, Archivist, Module Keeper) has complete interfaces, prompt templates, and response models — but no actual Claude API calls yet. This is the critical gap between "architecture" and "working AI DM".

| Task | Description | Status |
|------|-------------|--------|
| Agent LLM execution | Wire Narrator/Archivist/Module Keeper to Claude API via Anthropic SDK | Not started |
| Prompt engineering | Validate and tune agent prompts with real gameplay scenarios | Not started |
| Agent coordination | Test multi-agent response merging when agents produce conflicting outputs | Not started |
| Token budget management | Validate context window management under real token counts | Not started |
| Streaming responses | Stream narrative output for better UX during long generations | Not started |

## Phase 2 — Module Testing with Real PDFs

The module system (parser, indexer, vector store, Module Keeper agent) is built but untested with actual published adventures.

| Task | Description | Status |
|------|-------------|--------|
| PDF chunking validation | Test module parser with real adventure PDFs (varying layouts and structures) | Not started |
| Retrieval quality benchmarks | Measure RAG accuracy for NPC knowledge, location descriptions, plot queries | Not started |
| Module-specific tuning | Optimize chunk size, overlap, and retrieval parameters per module type | Not started |
| DM-only content separation | Ensure player-visible queries never leak DM-only information | Not started |

## Phase 3 — Integration Testing

Individual components are well-tested in isolation. The full loop (player input → orchestrator → agents → response) needs end-to-end validation.

| Task | Description | Status |
|------|-------------|--------|
| End-to-end session flow | Test complete gameplay loop from `start_claudmaster_session` to multi-turn play | Not started |
| Error recovery in gameplay | Validate crash recovery, agent timeouts, and degradation under real conditions | Not started |
| Session persistence | Test save/resume across multiple sessions with real game state | Not started |
| Multi-player scenarios | Validate split party handling, private info routing, turn distribution | Not started |

## Phase 4 — Narrative Quality

Evaluate and improve the actual output quality of the AI DM.

| Task | Description | Status |
|------|-------------|--------|
| Narrative style consistency | Test all styles (descriptive, concise, dramatic, cinematic) for quality | Not started |
| NPC voice consistency | Validate character voices stay consistent across sessions | Not started |
| Improvisation level fidelity | Test levels 0-4 actually produce the expected module adherence | Not started |
| Companion personality | Verify AI companions maintain personality over multi-session arcs | Not started |

## Phase 5 — Quality of Life

Improvements that make the overall experience smoother.

| Task | Description | Status |
|------|-------------|--------|
| Session transcript export | Export gameplay sessions as formatted markdown with origin tags | Not started |
| Campaign migration tool | Import campaigns from other VTT formats (Foundry, Roll20) | Not started |
| Batch NPC/location creation | Generate multiple NPCs or locations from a single prompt | Not started |
| Spell slot and resource tracking | Track spell slots, ki points, and other class resources | Not started |

---

## Completed Milestones

- **v0.1.0** — Core MCP server: campaigns, characters, NPCs, locations, quests, combat, dice
- **v0.2.0** — PDF Rulebook Library: import PDFs, keyword search, semantic search (RAG), content extraction
- **Claudmaster Architecture** — Multi-agent AI DM system: Narrator, Archivist, Module Keeper agents; consistency engine (facts, contradictions, timeline, NPC knowledge); improvisation control (5 levels, element locks, fidelity enforcement); multi-player support (companions, split party, private info, turn management); session management with recovery and auto-save; performance optimization (caching, parallel execution, context compression)
