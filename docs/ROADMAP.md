# Roadmap

> Last updated: 2026-02-08

## Current Status

DM20 Protocol is a fully functional MCP server with **50+ tools** for D&D campaign management. The Claudmaster architecture (agents, consistency engine, improvisation, companions, multiplayer, session management) is complete and tested.

**Architecture insight:** The MCP server provides structured game data (state, rules, dice, modules). The host LLM — Claude, via Claude Code or Claude Desktop — provides the intelligence: narration, decisions, NPC dialogue. No separate LLM integration or API key is needed. Claude Code *is* the DM brain; the MCP tools are its hands.

**What works today:** Campaign management, character sheets, NPCs, locations, quests, combat tracking, session notes, dice rolls, PDF rulebook library with keyword and semantic search, Claudmaster session lifecycle tools, configuration system.

**What's next:** Making the system playable end-to-end — DM persona instructions, real PDF testing, and gameplay validation.

---

## Phase 1 — DM Persona & Game Loop (High Priority)

Claude Code is already the LLM. The MCP tools already return game state data. What's missing is the **bridge**: instructions that tell Claude how to act as a DM using these tools, and the game loop that ties it all together.

The core DM loop is: **CONTEXT → DECIDE → EXECUTE → PERSIST → NARRATE** — always update game state via tools *before* describing outcomes to the player.

| Task | Description | Status |
|------|-------------|--------|
| DM system prompt | Write CLAUDE.md section (or dedicated file) defining DM persona, game loop, tool usage patterns, output formatting, and authority rules | Not started |
| Specialist sub-agents | Create `.claude/agents/` for specialized roles: narrator (descriptions, atmosphere), combat-handler (initiative, rounds, resolution), rules-lookup (spell/monster/class queries), module-keeper (adventure content retrieval) | Not started |
| Game skills | Create slash commands (`/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save`) for streamlined gameplay workflow | Not started |
| Tool output review | Audit all MCP tool return values — ensure they provide sufficient structured data for Claude to DM effectively without needing internal LLM calls | Not started |
| Session tool fixes | Fix `start_claudmaster_session` campaign integration; verify `player_action` tool registration and return format | Not started |
| Basic game loop test | Test minimal loop: start session → player says something → Claude uses tools → narrates result → state persists | Not started |

## Phase 2 — Module Testing with Real PDFs

The PDF library system (parser, indexer, vector store, search) is built but untested with actual published adventures. This phase validates that Claude can DM a published module using the existing tools.

| Task | Description | Status |
|------|-------------|--------|
| PDF loading validation | Load a real adventure module (e.g., Curse of Strahd, Lost Mine of Phandelver) and verify indexing quality | Not started |
| Retrieval quality benchmarks | Query module content and measure accuracy: NPC info, location descriptions, encounter triggers, plot points | Not started |
| DM-only content separation | Ensure player-facing queries never leak spoilers or DM-only information (read-aloud vs DM notes) | Not started |
| Search output optimization | Tune search result format and context size for optimal Claude consumption within the conversation window | Not started |

## Phase 3 — End-to-End Gameplay

Play real sessions and identify gaps. This is where theory meets practice.

| Task | Description | Status |
|------|-------------|--------|
| Full session playtest | Play a complete session covering exploration, social interaction, and combat — document every friction point | Not started |
| Session persistence | Test save/resume across multiple sessions — verify game state, NPC knowledge, and quest progress survive | Not started |
| Combat flow validation | Test complete combat: initiative roll → round tracking → attacks with damage → conditions → resolution → XP | Not started |
| Context window management | Validate behavior when conversations grow long — test context compression, session recaps, state recovery | Not started |

## Phase 4 — Narrative Quality

Evaluate and improve the actual DM experience. Tune the system for enjoyable gameplay.

| Task | Description | Status |
|------|-------------|--------|
| Narrative style tuning | Test and refine DM persona instructions for different styles (descriptive, concise, dramatic, cinematic) | Not started |
| NPC voice consistency | Validate NPC personalities persist across turns and sessions — test with recurring NPCs | Not started |
| Improvisation calibration | Test that improvisation level settings (0-4) produce the expected balance of module fidelity vs creative freedom | Not started |
| Companion personality | Verify AI-controlled companion NPCs maintain consistent personality over multi-session arcs | Not started |

## Phase 5 — Quality of Life

Improvements that make the overall experience smoother for daily use.

| Task | Description | Status |
|------|-------------|--------|
| Session transcript export | Export gameplay sessions as formatted markdown with clear speaker attribution | Not started |
| Campaign migration tool | Import campaigns from other VTT formats (Foundry, Roll20) | Not started |
| Batch NPC/location creation | Generate multiple NPCs or locations from a single prompt | Not started |
| Spell slot and resource tracking | Track spell slots, ki points, rage uses, and other class resources across rests | Not started |

---

## Architecture Notes

### Why No Separate LLM Integration?

The original Claudmaster architecture planned for internal Claude API calls (Anthropic SDK inside the MCP server). This was redesigned based on a key realization:

- **MCP servers run inside LLM sessions.** When loaded in Claude Code or Claude Desktop, the host LLM already processes all tool results.
- **The host LLM is the narrator.** Claude receives game state from tools and generates narrative responses naturally — no second API call needed.
- **Sub-agents provide parallelism.** Claude Code can spawn specialist agents (`.claude/agents/`) that work in parallel, each with access to the MCP tools.
- **Zero additional cost.** Users with Claude Pro/Max plans pay nothing extra. No API key management, no token budget accounting, no billing surprises.

The existing Python agent classes (Narrator, Archivist, Module Keeper) remain as tested infrastructure. Their data-retrieval methods are useful as tool backends. The `LLMClient` protocol and prompt templates may be repurposed or simplified in a future cleanup pass.

### Reference Project

[Claude Code Game Master](https://github.com/Sstobo/Claude-Code-Game-Master) by Sstobo validates this approach: CLAUDE.md persona + specialist agents + bash tools (we use MCP tools instead, which are more portable across clients).

---

## Completed Milestones

- **v0.1.0** — Core MCP server: campaigns, characters, NPCs, locations, quests, combat, dice
- **v0.2.0** — PDF Rulebook Library: import PDFs, keyword search, semantic search (RAG), content extraction
- **Claudmaster Architecture** — Multi-agent AI DM system: Narrator, Archivist, Module Keeper agents; consistency engine (facts, contradictions, timeline, NPC knowledge); improvisation control (5 levels, element locks, fidelity enforcement); multi-player support (companions, split party, private info, turn management); session management with recovery and auto-save; performance optimization (caching, parallel execution, context compression)
