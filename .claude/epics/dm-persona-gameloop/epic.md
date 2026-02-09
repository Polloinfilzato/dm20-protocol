---
name: dm-persona-gameloop
status: in_progress
created: 2026-02-09T01:27:42Z
progress: 57%
prd: .claude/prds/dm-persona-gameloop.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/66
---

# Epic: DM Persona & Game Loop

## Overview

Make dm20-protocol playable end-to-end by creating the bridge between the existing 55 MCP tools and Claude as the Dungeon Master. Uses a **hybrid architecture**: Python handles deterministic work (intent classification, data retrieval, rule lookup) to save tokens; Claude handles creative work (narration, NPC dialogue, DM decisions) through a dedicated DM persona file and Claude Code sub-agents.

## Architecture Decisions

### 1. DM Persona as Dedicated File (not CLAUDE.md)
**Decision:** DM behavior instructions live in `.claude/dm-persona.md`, loaded only during gameplay.
**Rationale:** CLAUDE.md contains project-level instructions (language, git, conventions) that are always active. Mixing DM persona instructions there would cause Claude to speak "as a DM" during development tasks. Separation allows clean context switching.

### 2. Hybrid Python + Claude
**Decision:** Reuse existing Python Orchestrator/Archivist for deterministic operations; Claude handles creativity.
**Rationale:** Python intent classification, data queries, and consistency checks use zero tokens. The Narrator's `LLMClient` calls are NOT used (they would double-charge tokens). Only Python logic that runs locally on CPU is leveraged.

### 3. Fix Existing Tools Before Building New Features
**Decision:** Fix `start_claudmaster_session` and register `player_action` before writing DM persona.
**Rationale:** The DM persona references these tools in its instructions. Writing persona instructions against broken tools creates misalignment. Fix first, instruct second.

### 4. Slash Commands as Game Interface
**Decision:** `/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save` as the player-facing interface.
**Rationale:** Slash commands provide a structured entry point, load the DM persona context, and orchestrate the tool calls. This matches the Claude Code Game Master pattern.

### 5. Claude Code Agents for Specialist Roles
**Decision:** `.claude/agents/` for narrator, combat-handler, rules-lookup — markdown-defined agents.
**Rationale:** These agents can be spawned by Claude during complex scenarios (multi-step combat, extended NPC dialogue) while sharing access to MCP tools. They parallelize the DM's work.

## Technical Approach

### Critical Fixes (Foundation)
- **`start_claudmaster_session`**: Currently returns hardcoded error. Must integrate with `DnDStorage` to load campaign by name and initialize `SessionManager` with actual campaign data.
- **`player_action` tool registration**: The tool exists in `claudmaster/tools/action_tools.py` but is not registered as `@mcp.tool` in `main.py`. Must be registered and wired.
- **Tool output enrichment**: Key tools (`get_character`, `get_npc`, `get_game_state`) return formatted strings. Must be enriched to include all data an AI DM needs (inventory details, NPC relationships, combat state).

### DM Persona Design
- Single markdown file defining: identity, game loop, tool usage patterns, output formatting, authority rules, combat protocol, session management
- Core loop: **CONTEXT → DECIDE → EXECUTE → PERSIST → NARRATE**
- Always update game state *before* narrating outcomes (prevents state desync)
- References `configure_claudmaster` settings for narrative_style, difficulty, dialogue_style

### Sub-Agent Design
- **narrator.md**: Scene descriptions, atmosphere, NPC voices. Tools: `get_location`, `get_npc`, `search_rules`
- **combat-handler.md**: Initiative, turn management, attack resolution, enemy AI. Tools: `start_combat`, `next_turn`, `end_combat`, `roll_dice`, `update_character`, `get_monster_info`
- **rules-lookup.md**: Spell details, monster stats, class features. Tools: `search_rules`, `get_spell_info`, `get_monster_info`, `get_class_info`

### Game Skills Design
- `/dm:start` — Load campaign, check for existing session, activate DM persona, set/resume scene
- `/dm:action` — Core game loop: receive player action, resolve via tools, narrate outcome
- `/dm:combat` — Enter combat mode: initiative, turn tracking, attack resolution
- `/dm:save` — Save session state, generate session notes, provide cliffhanger ending

## Implementation Strategy

### Phase 1: Fix Foundation (Tasks 1-2)
Fix broken tools and enrich output. No new features — just make existing infrastructure work.

### Phase 2: Create DM Layer (Tasks 3-5)
Write DM persona, sub-agents, and game skills. This is the "brain" layer that tells Claude how to use the tools.

### Phase 3: Integrate and Validate (Tasks 6-7)
Wire hybrid Python integration, then playtest the complete loop.

### Risk Mitigation
- **Risk**: DM persona instructions too long for context → **Mitigation**: Keep persona under 3000 tokens, use sub-agents for detail
- **Risk**: Tool output not sufficient for DM decisions → **Mitigation**: Task 1 audits and fixes tool outputs before persona is written
- **Risk**: Combat too complex for MVP → **Mitigation**: Scope to basic melee/ranged combat, no concentration/reactions/legendary actions
- **Risk**: Session state lost between conversations → **Mitigation**: Task 2 fixes session persistence, Task 7 validates it

## Task Breakdown Preview

- [ ] **Task 1**: Tool Output Audit & Enrichment — Fix critical tool outputs for DM consumption
- [ ] **Task 2**: Session Tool Fixes — Fix `start_claudmaster_session`, register `player_action`
- [ ] **Task 3**: DM Persona File — Write `.claude/dm-persona.md` with game loop and behavior rules
- [ ] **Task 4**: Specialist Sub-Agents — Create narrator, combat-handler, rules-lookup agents
- [ ] **Task 5**: Game Skills — Create `/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save`
- [ ] **Task 6**: Hybrid Python Integration — Wire intent classification and data queries into tool flow
- [ ] **Task 7**: Game Loop Validation — End-to-end playtest covering exploration, social, and combat

## Dependencies

### Internal (all existing and working)
- Campaign/Character/NPC/Location/Quest system
- Combat tracking (`start_combat`, `next_turn`, `end_combat`)
- Dice system (`roll_dice`)
- Rulebook system (`search_rules`, `get_spell_info`, `get_monster_info`)
- Session management (`end_claudmaster_session`, `get_claudmaster_session_state`)
- Event/session notes system (`add_event`, `add_session_note`)

### Internal (existing but broken — fixed in Tasks 1-2)
- `start_claudmaster_session` — hardcoded error, needs campaign loading
- `player_action` — exists but not registered as MCP tool
- Tool output formats — strings instead of structured data

### External
- Claude Code or Claude Desktop as host LLM (required platform)

## Success Criteria (Technical)

| Criteria | Target | Validation |
|----------|--------|------------|
| `/dm:start` loads campaign and sets scene | Works for any existing campaign | Manual test |
| Player action → narrated outcome | Complete loop in single Claude turn | Manual test |
| Basic combat from initiative to aftermath | Full combat with 2+ enemies | Manual test |
| Session save/resume with full state | Zero data loss on round-trip | Manual test |
| NPC remembers earlier conversation | In-session memory consistency | Manual test |
| DM never asks player to arbitrate | Zero "what should happen?" prompts | Playtest audit |
| `start_claudmaster_session` loads campaign | Returns session state, not error | Automated test |
| `player_action` is callable via MCP | Tool appears in tool list | Automated test |

## Estimated Effort

| Task | Size | Est. Hours | Notes |
|------|------|------------|-------|
| Task 1: Tool Output Audit & Enrichment | M | 4-6h | Modify ~6 tool functions |
| Task 2: Session Tool Fixes | M | 3-5h | Fix campaign loading + register tool |
| Task 3: DM Persona File | L | 6-8h | Core deliverable, iterative writing |
| Task 4: Specialist Sub-Agents | S | 2-3h | 3 markdown files, follows persona patterns |
| Task 5: Game Skills | M | 4-6h | 4 slash commands orchestrating tools |
| Task 6: Hybrid Python Integration | S | 2-3h | Wire existing code, no new logic |
| Task 7: Game Loop Validation | M | 4-6h | Playtest + fix issues found |
| **Total** | | **25-37h** | |

**Critical path:** Task 1 → Task 2 → Task 3 → Task 5 → Task 7
**Parallelizable:** Task 4 (after Task 3), Task 6 (after Task 2)

## Tasks Created

- [ ] 67.md - Tool Output Audit & Enrichment (parallel: true, Size M, 4-6h)
- [ ] 68.md - Session Tool Fixes & player_action Registration (parallel: true, Size M, 3-5h)
- [ ] 69.md - DM Persona File (parallel: false, depends: 67+68, Size L, 6-8h)
- [ ] 70.md - Specialist Sub-Agents (parallel: true, depends: 69, Size S, 2-3h)
- [ ] 71.md - Game Skills / Slash Commands (parallel: true, depends: 69, Size M, 4-6h)
- [ ] 72.md - Hybrid Python Integration (parallel: true, depends: 68, Size S, 2-3h)
- [ ] 73.md - Game Loop Validation / End-to-End Playtest (parallel: false, depends: all, Size M, 4-6h)

Total tasks: 7
Parallel tasks: 5 (67, 68, 70, 71, 72)
Sequential tasks: 2 (69, 73)
Estimated total effort: 25-37 hours

### Dependency Graph

```
     ┌──── 67 (Tool Audit) ────┐
     │                          ├──── 69 (DM Persona) ──┬── 70 (Sub-Agents) ──┐
     │                          │                        └── 71 (Game Skills) ─┤
     └──── 68 (Session Fix) ───┤                                               ├── 73 (Validation)
                                └──── 72 (Python Integration) ────────────────┘
```
