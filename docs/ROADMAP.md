# Roadmap

> Last updated: 2026-02-13

## Current Status

DM20 Protocol is a fully functional MCP server with **66 tools** for D&D campaign management. The system includes multi-source rulebook support (SRD 2014/2024, Open5e, 5etools, custom JSON), a dual-agent Narrator/Archivist architecture, a bilingual terminology resolver (EN/IT), a PDF rulebook library with keyword and semantic search, and a complete Claudmaster AI DM session lifecycle.

**Architecture insight:** The MCP server provides structured game data (state, rules, dice, modules). The host LLM — Claude, via Claude Code or Claude Desktop — provides the intelligence: narration, decisions, NPC dialogue. No separate LLM integration or API key is needed. Claude Code *is* the DM brain; the MCP tools are its hands.

**What works today:** Campaign management, Character v2 sheets (with experience, conditions, speed, tool proficiencies, structured features), NPCs, locations, quests, combat tracking, session notes and summarization, dice rolls, multi-source rulebook system, PDF library with content extraction and campaign bindings, character builder with standard array/point buy, level-up engine, Claudmaster session lifecycle, bilingual term resolution, and a configurable AI DM system.

**What's next:** End-to-end gameplay validation with real modules, narrative quality tuning, and PyPI distribution.

---

## Phase 1 — DM Persona & Game Loop (**Complete**)

Claude Code is already the LLM. The MCP tools already return game state data. This phase built the **bridge**: instructions that tell Claude how to act as a DM using these tools, and the game loop that ties it all together.

The core DM loop is: **CONTEXT -> DECIDE -> EXECUTE -> PERSIST -> NARRATE** — always update game state via tools *before* describing outcomes to the player.

| Task | Description | Status |
|------|-------------|--------|
| DM system prompt | `.claude/dm-persona.md` — DM identity, CONTEXT->DECIDE->EXECUTE->PERSIST->NARRATE game loop, tool usage patterns, output formatting, combat protocol, session management, authority rules | **Done** |
| Specialist sub-agents | `.claude/agents/` — narrator (scene descriptions, NPC dialogue), combat-handler (initiative, tactics, resolution), rules-lookup (spells, monsters, classes) | **Done** |
| Game skills | `/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save` — player-facing slash commands with dynamic persona injection and auto-approved MCP tools | **Done** |
| Tool output review | Audited and enriched `get_character`, `get_npc`, `get_game_state` and other key tools for AI DM consumption | **Done** |
| Session tool fixes | Fixed `start_claudmaster_session` campaign loading; registered `player_action` as MCP tool | **Done** |
| Hybrid Python integration | Wired intent classification and data retrieval from existing Orchestrator/Archivist into tool flow | **Done** |
| Basic game loop test | End-to-end playtest covering exploration, social, and combat scenarios | **Done** |

## Phase 2 — Module Testing with Real PDFs

The PDF library system (parser, indexer, vector store, search) is built. This phase validates that Claude can DM a published module using the existing tools.

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
| Combat flow validation | Test complete combat: initiative roll -> round tracking -> attacks with damage -> conditions -> resolution -> XP | Not started |
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
| Spell slot and resource tracking | Track spell slots, ki points, rage uses, and other class resources across rests | **Done** — `use_spell_slot`, `long_rest`, `short_rest` tools handle slot tracking and recovery |

---

## Future Direction

Realistic next steps beyond the current phase plan:

- **Party Mode** — Multi-player web relay: lightweight web server on the host machine lets N players connect via browser (phone/tablet/PC) with QR code authentication. Phase 2A (host-driven, zero extra cost) → Phase 2B (autonomous Claudmaster via Claude API). See [PARTY_MODE.md](PARTY_MODE.md) for full architecture
- **PyPI distribution** — Publish as a pip/uvx-installable package (`uvx dm20-protocol`) for zero-setup installation
- **Module playtesting** — Validate the PDF library pipeline with real published adventures (Lost Mine of Phandelver, Curse of Strahd)
- **Narrative quality tuning** — Style calibration for different DM personas (gritty realism, high fantasy, comedic)
- **Session transcript export** — Export gameplay sessions as formatted markdown with speaker attribution and timestamps
- **Campaign import from VTT formats** — Import campaigns from Foundry VTT and Roll20 export formats
- **Performance profiling** — Benchmark tool response times under heavy use, optimize hot paths

---

## Architecture Notes

### Why No Separate LLM Integration?

The original Claudmaster architecture planned for internal Claude API calls (Anthropic SDK inside the MCP server). This was redesigned based on a key realization:

- **MCP servers run inside LLM sessions.** When loaded in Claude Code or Claude Desktop, the host LLM already processes all tool results.
- **The host LLM is the narrator.** Claude receives game state from tools and generates narrative responses naturally — no second API call needed.
- **Sub-agents provide parallelism.** Claude Code can spawn specialist agents (`.claude/agents/`) that work in parallel, each with access to the MCP tools.
- **Zero additional cost.** Users with Claude Pro/Max plans pay nothing extra. No API key management, no token budget accounting, no billing surprises.

The existing Python agent classes (Narrator, Archivist, Module Keeper, Arbiter) remain as tested infrastructure. The dual-agent architecture (Narrator + Archivist) handles the core gameplay loop, with the Arbiter resolving rule disputes. Their data-retrieval methods power the Claudmaster session tools. The `LLMClient` protocol and prompt templates may be repurposed or simplified in a future cleanup pass.

### Multi-Source Rulebook System

The rulebook system supports loading D&D content from multiple sources simultaneously:
- **SRD 2014/2024** — Built-in System Reference Document data
- **Open5e API** — Remote fetch from the Open5e community API
- **5etools JSON** — Import from 5etools data files
- **Custom JSON** — User-provided content in CustomSource format

Content from all loaded sources is merged and searchable through a unified query interface.

### Bilingual Terminology Resolution

The `terminology/` subsystem resolves Italian D&D terms to their canonical English equivalents (and vice versa). This allows Italian-speaking players to use natural Italian terms in commands while the system maps them to the correct English game entities. The resolver uses a YAML-based term database with fuzzy matching.

### Reference Project

[Claude Code Game Master](https://github.com/Sstobo/Claude-Code-Game-Master) by Sstobo validates this approach: CLAUDE.md persona + specialist agents + bash tools (we use MCP tools instead, which are more portable across clients).

---

## Completed Milestones

- **v0.1.0** — Core MCP server: campaigns, characters, NPCs, locations, quests, combat, dice
- **v0.2.0** — PDF Rulebook Library: import PDFs, keyword search, semantic search (RAG), content extraction
- **Claudmaster Architecture** — Multi-agent AI DM system: Narrator, Archivist, Module Keeper, Arbiter agents; consistency engine (facts, contradictions, timeline, NPC knowledge); improvisation control (5 levels, element locks, fidelity enforcement); multi-player support (companions, split party, private info, turn management); session management with recovery and auto-save; performance optimization (caching, parallel execution, context compression)
- **DM Persona & Game Loop** (Complete) — DM persona file with structured game loop; 3 specialist Claude Code sub-agents (narrator, combat-handler, rules-lookup); 4 game slash commands (`/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save`); tool output enrichment; session tool fixes; hybrid Python integration; end-to-end gameplay validation
- **Multi-Source Rulebook System** — Unified rulebook manager loading from SRD (2014/2024), Open5e API, 5etools JSON, and custom JSON sources; merged search across all loaded sources; character validation against rulebook data
- **Character v2 Model** — Extended character sheet with experience points, speed, conditions, tool proficiencies, hit dice type, structured Feature model (name, source, description, level); character builder with standard array/point buy; level-up engine
- **Bilingual Terminology Resolver** — Italian-to-English D&D term resolution with fuzzy matching; YAML-based term database; style tracking for consistent output language
- **Dual-Agent Architecture** — Narrator + Archivist agent pipeline for Claudmaster sessions; Arbiter agent for rule dispute resolution; intent classification and orchestrated multi-agent responses
