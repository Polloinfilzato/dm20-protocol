---
name: dm-persona-gameloop
description: DM persona file, Claude Code sub-agents, game skills, and hybrid Python/Claude game loop for playable D&D sessions
status: backlog
created: 2026-02-09T01:00:37Z
---

# PRD: DM Persona & Game Loop

## Executive Summary

Transform dm20-protocol from a campaign management toolkit into a **playable D&D experience** by creating the bridge between the existing MCP tools and Claude as the Dungeon Master.

The system uses a **hybrid architecture**: Python handles deterministic work (intent classification, data retrieval, rule lookup, consistency checking) to save tokens, while Claude handles creative work (narration, NPC dialogue, DM decisions) through a dedicated DM persona file and specialized Claude Code sub-agents.

**Key deliverables:**

1. **DM Persona File** (`.claude/dm-persona.md`) — Instructions that tell Claude how to act as a DM, including the core game loop, tool usage patterns, output formatting, and authority rules
2. **Specialist Sub-Agents** (`.claude/agents/`) — Claude Code agents for narrator, combat-handler, and rules-lookup roles
3. **Game Skills** (`.claude/commands/dm/`) — Slash commands (`/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save`) for streamlined gameplay
4. **Tool Output Audit** — Review and improve MCP tool return values for DM consumption
5. **Session Tool Fixes** — Fix `start_claudmaster_session` campaign integration and verify tool registration
6. **Game Loop Validation** — End-to-end test of the complete play cycle including basic combat

**Value proposition:** A player can start a session, describe actions in natural language, and receive narrated outcomes with game state automatically persisted — covering exploration, social interaction, and basic combat — without ever acting as their own DM.

## Problem Statement

### Current State

dm20-protocol has 50+ MCP tools for campaign management and a complete Python agent infrastructure (Orchestrator, Narrator, Archivist, Module Keeper). However, there are no instructions telling Claude *how to be a DM*. The tools are hands without a brain directing them.

```
Current experience:
1. User: "I search the bookshelf"
2. Claude: "I can help with that. Which tool would you like me to use?"
   ← No DM behavior, no narrative voice, no autonomous game management

Desired experience:
1. Player: "I search the bookshelf"
2. DM (Claude): *rolls Perception check via tool* "Your fingers trace along dusty
   spines until they catch on a book that doesn't quite sit right. Behind it, a
   folded letter sealed with a raven crest..." *updates game state via tool*
```

### Why Now?

- All MCP tools are built and functional (campaigns, characters, NPCs, combat, dice, rulebooks, library)
- Python infrastructure provides reusable deterministic logic (intent classification, data queries)
- The hybrid approach (Python for logic + Claude for creativity) is architecturally sound and token-efficient
- [Claude Code Game Master](https://github.com/Sstobo/Claude-Code-Game-Master) validates the `.claude/agents/` + persona approach
- This is the critical "last mile" — everything is built, nothing is playable

### Target User

Solo D&D player using Claude Code (or Claude Desktop) who wants to play D&D with an AI DM. The player:
- Owns the dm20-protocol MCP server
- Has a campaign with at least one character created
- Wants to describe actions in natural language and receive narrated outcomes
- Does NOT want to make DM decisions or break immersion

## Architecture Overview

### Hybrid Architecture: Python + Claude

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CLAUDE (Host LLM = DM Brain)                     │
│                                                                         │
│  Loaded context:                                                        │
│  ├── .claude/dm-persona.md          (DM behavior instructions)          │
│  ├── .claude/agents/narrator.md     (scene/dialogue specialist)         │
│  ├── .claude/agents/combat-handler.md (combat specialist)               │
│  └── .claude/agents/rules-lookup.md (rules specialist)                  │
│                                                                         │
│  Game Loop (per player turn):                                           │
│  ┌───────┐   ┌────────┐   ┌─────────┐   ┌─────────┐   ┌──────────┐   │
│  │CONTEXT│──►│ DECIDE │──►│ EXECUTE │──►│ PERSIST │──►│ NARRATE  │   │
│  │       │   │        │   │         │   │         │   │          │   │
│  │Get    │   │Claude  │   │Call MCP │   │Update   │   │Describe  │   │
│  │state  │   │decides │   │tools to │   │state via│   │outcome   │   │
│  │via    │   │what    │   │resolve  │   │tools    │   │to player │   │
│  │tools  │   │happens │   │action   │   │         │   │          │   │
│  └───────┘   └────────┘   └─────────┘   └─────────┘   └──────────┘   │
│       ▲                        │                                        │
│       │                        ▼                                        │
│  ┌─────────────────────────────────────────────────────┐               │
│  │              MCP TOOLS (dm20-protocol)                │               │
│  │                                                       │               │
│  │  Python-backed deterministic operations:              │               │
│  │  ├── get_game_state()     → campaign/session state    │               │
│  │  ├── get_character()      → full character sheet      │               │
│  │  ├── roll_dice()          → dice results              │               │
│  │  ├── search_rules()       → rule lookups              │               │
│  │  ├── start/next/end_combat() → combat state mgmt     │               │
│  │  ├── update_character()   → HP, inventory changes     │               │
│  │  ├── add_event()          → adventure log             │               │
│  │  └── ...50+ existing tools                            │               │
│  │                                                       │               │
│  │  Orchestrator (Python, internal):                     │               │
│  │  ├── classify_intent()    → intent type (0 tokens)    │               │
│  │  ├── Archivist data queries → structured data         │               │
│  │  └── Consistency checks   → fact validation           │               │
│  └─────────────────────────────────────────────────────┘               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Token Savings Strategy

| Operation | Handled By | Tokens Used |
|-----------|-----------|-------------|
| Intent classification | Python (Orchestrator) | 0 |
| Character stats lookup | Python (Archivist) | 0 |
| Rule search | Python (existing search_rules tool) | 0 |
| HP calculation | Python | 0 |
| Dice rolling | Python | 0 |
| Fact/consistency checking | Python (Consistency Engine) | 0 |
| Scene narration | Claude (narrator agent) | ~200-500 |
| NPC dialogue | Claude (DM persona) | ~100-300 |
| DM decisions | Claude (DM persona) | ~50-150 |
| Combat narration | Claude (combat-handler agent) | ~150-400 |

### File Structure

```
.claude/
├── dm-persona.md              # NEW: DM behavior, game loop, authority rules
├── agents/
│   ├── narrator.md            # NEW: Scene description, atmosphere, NPC voice
│   ├── combat-handler.md      # NEW: Combat management, tactics, resolution
│   └── rules-lookup.md        # NEW: Rules queries, spell details, monster stats
├── commands/
│   └── dm/
│       ├── start.md           # NEW: /dm:start - Begin/resume game session
│       ├── action.md          # NEW: /dm:action - Process player action
│       ├── combat.md          # NEW: /dm:combat - Enter/manage combat
│       └── save.md            # NEW: /dm:save - Save session and pause
└── prds/
    └── dm-persona-gameloop.md # This PRD
```

## User Stories

### US-1: Starting a Game Session

**As a** player with an existing campaign and character
**I want** to start a DM'd game session with a simple command
**So that** I can immediately begin playing without setup overhead

**Acceptance Criteria:**
- [ ] `/dm:start` loads the active campaign and character
- [ ] Claude assumes DM persona automatically
- [ ] Session state is initialized or resumed from last save
- [ ] DM provides a scene-setting introduction (new session) or recap (resumed session)
- [ ] Player can begin describing actions immediately after intro

### US-2: Natural Action Resolution

**As a** player describing actions in natural language
**I want** the DM to resolve them using appropriate game mechanics
**So that** the game feels like a real D&D session

**Acceptance Criteria:**
- [ ] Player describes action: "I try to pick the lock on the chest"
- [ ] DM determines ability check needed (Dexterity, Thieves' Tools)
- [ ] DM rolls dice via `roll_dice` tool (or asks player to roll)
- [ ] DM narrates outcome based on roll result
- [ ] Game state is updated (chest status, inventory if opened)
- [ ] DM advances the scene naturally

### US-3: NPC Interaction

**As a** player talking to an NPC
**I want** the DM to roleplay the NPC with personality and memory
**So that** conversations feel natural and NPCs feel like real characters

**Acceptance Criteria:**
- [ ] DM speaks as the NPC using distinct voice/personality
- [ ] NPC knowledge is consistent with `get_npc()` data
- [ ] NPC reacts to player reputation and previous interactions
- [ ] DM updates NPC notes after significant interactions
- [ ] NPC can refuse, negotiate, or have their own agenda

### US-4: Basic Combat

**As a** player entering combat
**I want** the DM to manage combat mechanics automatically
**So that** combat flows smoothly without me tracking initiative and rules

**Acceptance Criteria:**
- [ ] DM initiates combat via `start_combat` tool when combat begins
- [ ] Initiative is rolled for all participants
- [ ] DM tracks turn order and announces whose turn it is
- [ ] Player describes their combat action on their turn
- [ ] DM resolves attacks: roll to hit, roll damage, apply to target
- [ ] DM plays enemies tactically (not suicidally, not omnisciently)
- [ ] Combat ends naturally when enemies are defeated/flee/surrender
- [ ] DM calls `end_combat` and narrates aftermath
- [ ] XP/loot is handled post-combat

### US-5: Session Save and Resume

**As a** player ending a session
**I want** all game state to be saved automatically
**So that** I can resume exactly where I left off next time

**Acceptance Criteria:**
- [ ] `/dm:save` saves current session state
- [ ] Game state, character changes, and session notes are persisted
- [ ] `/dm:start` with existing session resumes with a recap
- [ ] DM summarizes what happened and sets the scene for continuation
- [ ] No game state is lost between sessions

### US-6: Immersive DM Behavior

**As a** player
**I want** the DM to never break character or ask me to make DM decisions
**So that** immersion is maintained throughout the session

**Acceptance Criteria:**
- [ ] DM never says "What would you like to happen?"
- [ ] DM never asks player to arbitrate rules
- [ ] DM resolves ambiguous situations autonomously
- [ ] DM maintains consistent narrative tone throughout session
- [ ] DM uses tools proactively (doesn't wait to be told to roll dice)

## Requirements

### Functional Requirements

#### FR-1: DM Persona File

| ID | Requirement |
|----|-------------|
| FR-1.1 | Create `.claude/dm-persona.md` with comprehensive DM behavior instructions |
| FR-1.2 | Define the core game loop: CONTEXT → DECIDE → EXECUTE → PERSIST → NARRATE |
| FR-1.3 | Specify tool usage patterns (when to use which MCP tool) |
| FR-1.4 | Define output formatting: boxed text for read-aloud, NPC dialogue style, combat logs |
| FR-1.5 | Define DM authority rules: never ask player to DM, resolve ambiguity, rule of fun |
| FR-1.6 | Include narrative style guidelines (adjustable via `configure_claudmaster` settings) |
| FR-1.7 | Define session lifecycle: start, play, save, resume |

#### FR-2: Claude Code Sub-Agents

| ID | Requirement |
|----|-------------|
| FR-2.1 | Create `narrator.md` agent for scene descriptions, atmosphere, NPC voice |
| FR-2.2 | Create `combat-handler.md` agent for combat management and resolution |
| FR-2.3 | Create `rules-lookup.md` agent for rules queries, spell/monster lookups |
| FR-2.4 | Each agent must specify which MCP tools it uses |
| FR-2.5 | Agents must coordinate: combat-handler gets data, narrator describes it |

#### FR-3: Game Skills (Slash Commands)

| ID | Requirement |
|----|-------------|
| FR-3.1 | `/dm:start` — Load campaign, initialize session, begin or resume play |
| FR-3.2 | `/dm:action` — Process a player action through the game loop |
| FR-3.3 | `/dm:combat` — Initiate or manage a combat encounter |
| FR-3.4 | `/dm:save` — Save session state with session notes |

#### FR-4: Tool Output Audit

| ID | Requirement |
|----|-------------|
| FR-4.1 | Review all MCP tool return values for DM consumption suitability |
| FR-4.2 | Ensure `get_game_state` returns sufficient context for scene-setting |
| FR-4.3 | Ensure `get_character` provides all stats needed for checks and combat |
| FR-4.4 | Ensure `get_npc` provides personality/knowledge for roleplay |
| FR-4.5 | Ensure combat tools (`start_combat`, `next_turn`, `end_combat`) provide turn state |
| FR-4.6 | Document which tools need output improvements |
| FR-4.7 | Implement any critical output improvements identified |

#### FR-5: Session Tool Fixes

| ID | Requirement |
|----|-------------|
| FR-5.1 | Fix `start_claudmaster_session` to properly load campaign state |
| FR-5.2 | Verify all Claudmaster session tools are registered and functional |
| FR-5.3 | Ensure session state survives across conversation restarts |
| FR-5.4 | Test session pause/resume cycle |

#### FR-6: Hybrid Python Integration

| ID | Requirement |
|----|-------------|
| FR-6.1 | Expose Orchestrator `classify_intent()` as internal helper for tool processing |
| FR-6.2 | Expose Archivist data retrieval methods via existing MCP tools |
| FR-6.3 | Ensure Consistency Engine fact tracking integrates with session persistence |
| FR-6.4 | Python components that duplicate Claude's capabilities (Narrator LLM calls) should be documented as "available but not used in game loop" |

#### FR-7: Basic Combat Loop

| ID | Requirement |
|----|-------------|
| FR-7.1 | DM can initiate combat with `start_combat` tool |
| FR-7.2 | Initiative rolled for all participants |
| FR-7.3 | Turn-by-turn progression via `next_turn` |
| FR-7.4 | Attack resolution: to-hit roll → damage roll → HP update |
| FR-7.5 | Enemy tactics: basic AI (attack nearest, retreat when low HP) |
| FR-7.6 | Combat end: `end_combat` + aftermath narration |
| FR-7.7 | Death/unconsciousness handling (death saves for PCs) |

### Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | DM persona loads and activates within 2 seconds of `/dm:start` |
| NFR-2 | Simple action resolution (non-combat) completes in one Claude turn |
| NFR-3 | Combat round resolution within 3 Claude turns (player + enemies) |
| NFR-4 | Zero "what should happen?" prompts to the player during normal play |
| NFR-5 | Game state persists correctly across session save/resume cycles |
| NFR-6 | DM persona works with both Claude Code and Claude Desktop as hosts |
| NFR-7 | Token usage for a typical turn < 1000 tokens (excluding model output) |

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Playable session | Complete a 30-minute exploration + social + combat session | Manual test |
| DM autonomy | Zero DM-decision-deflection moments | Count during playtest |
| State persistence | 100% state recovery after save/resume | Automated check |
| Combat completion | Full combat from initiative to aftermath | Manual test |
| NPC consistency | NPC remembers facts from earlier in session | Manual test |
| Tool integration | All required tools called correctly by DM | Log review |

## Constraints & Assumptions

### Constraints

1. **Claude Code agents are markdown files** — They define behavior through prompts, not executable code
2. **MCP tool availability** — All 50+ tools must be accessible; no new Python tools needed for MVP
3. **Single player focus** — Phase 1 targets solo play only (multiplayer is Phase 4+)
4. **No module integration** — No PDF adventure modules; homebrew/freeform only in Phase 1
5. **Existing Python code is not refactored** — Reuse what works, document what's deprecated, don't rewrite

### Assumptions

1. Claude Code sub-agents (`.claude/agents/`) can access MCP tools from the parent session
2. The DM persona file is loaded automatically when game skills (`/dm:*`) are invoked
3. Existing `configure_claudmaster` settings (narrative_style, difficulty, etc.) are accessible
4. The player has already created a campaign and at least one character before using `/dm:start`
5. Combat tracking tools (`start_combat`, `next_turn`, `end_combat`) work as documented

## Out of Scope

The following are explicitly **NOT** included in this PRD:

1. **PDF module integration** — No adventure module loading or RAG (Phase 2)
2. **Multiplayer support** — Solo play only (existing multiplayer infra untouched)
3. **Companion NPC system** — AI-controlled party members (future phase)
4. **Improvisation control** — Module fidelity levels not relevant without modules
5. **Voice/visual output** — Text-only interface
6. **Python agent refactoring** — No rewrites of existing Orchestrator/Narrator/Archivist code
7. **New MCP tool creation** — Use existing 50+ tools; at most minor output improvements
8. **Context window management** — Session compression/recap for very long sessions (Phase 3)
9. **Advanced enemy AI** — Complex tactical behavior beyond basic combat patterns

## Dependencies

### Internal Dependencies

```
DM Persona & Game Loop (this PRD)
    ├── depends on → Campaign/Character System (existing, working)
    ├── depends on → Combat System (existing: start_combat, next_turn, end_combat)
    ├── depends on → Dice System (existing: roll_dice)
    ├── depends on → NPC/Location/Quest System (existing, working)
    ├── depends on → Session Management (existing: start/end_claudmaster_session)
    ├── depends on → Rulebook System (existing: search_rules, get_spell_info, etc.)
    ├── reuses → Orchestrator.classify_intent() (Python, internal)
    ├── reuses → Archivist data retrieval (Python, internal)
    └── reuses → Consistency Engine (Python, internal)
```

### External Dependencies

| Dependency | Purpose | Risk |
|------------|---------|------|
| Claude Code | Host LLM, agent runner | None (required platform) |
| Claude Desktop | Alternative host | Low (MCP tools portable) |

### Recommended Implementation Order

1. **Tool Output Audit** — Understand what data is available before writing persona
2. **Session Tool Fixes** — Ensure session lifecycle works before building on it
3. **DM Persona File** — Core behavior instructions (depends on knowing tool outputs)
4. **Specialist Sub-Agents** — Narrator, combat-handler, rules-lookup
5. **Game Skills** — `/dm:start`, `/dm:action`, `/dm:combat`, `/dm:save`
6. **Hybrid Python Integration** — Wire up intent classification and data queries
7. **Game Loop Validation** — End-to-end playtest

## Technical Notes

### DM Persona File Structure (`.claude/dm-persona.md`)

The persona file should include:

```markdown
# DM Persona: dm20-protocol

## Identity
You are a Dungeon Master for a D&D 5e campaign. [tone, style, personality]

## Core Game Loop
For every player action, follow: CONTEXT → DECIDE → EXECUTE → PERSIST → NARRATE
1. CONTEXT: Use get_game_state, get_character to understand current situation
2. DECIDE: Determine what happens (check needed? combat? NPC reaction?)
3. EXECUTE: Call appropriate tools (roll_dice, search_rules, etc.)
4. PERSIST: Update state (update_character, add_event, update_quest, etc.)
5. NARRATE: Describe the outcome to the player

## Tool Usage Patterns
[When to use each category of tools: combat, character, NPC, etc.]

## Output Formatting
[Read-aloud text, NPC dialogue, combat log, skill check format]

## Authority Rules
[Never ask player to DM, resolve ambiguity, rule of fun, etc.]

## Combat Protocol
[Initiative, turn management, attack resolution, enemy tactics]

## Session Management
[Start, save, resume, recap generation]
```

### Game Skill Example (`/dm:start`)

```markdown
# DM Start

## Trigger
Player runs /dm:start [campaign_name]

## Steps
1. Load campaign via get_campaign_info
2. Load all characters via list_characters
3. Get current game state via get_game_state
4. Check for existing Claudmaster session
5. If resuming: generate recap from session notes
6. If new: set the opening scene
7. Activate DM persona
8. Present scene to player, await first action
```

### Hybrid Integration Points

The existing Python code provides these token-saving shortcuts:

| Python Component | MCP Tool Surface | Token Savings |
|-----------------|------------------|---------------|
| `Orchestrator.classify_intent()` | Internal to `player_action` processing | Avoids asking Claude "what type of action is this?" |
| `Archivist.get_hp_status()` | Via `get_character` tool | Structured data, no LLM parsing needed |
| `Archivist.get_character_stats()` | Via `get_character` tool | Full stat block as structured data |
| `ConsistencyEngine.check_facts()` | Via session state tools | Validates narrative against established facts |
| `Orchestrator._get_agents_for_intent()` | Internal routing logic | Determines which sub-agent to dispatch |

## References

### Projects
- [Claude Code Game Master](https://github.com/Sstobo/Claude-Code-Game-Master) — Validates .claude/agents + persona approach
- [dm20-protocol Claudmaster PRD](./claudmaster-ai-dm.md) — Original multi-agent architecture (Python-based)

### Architecture Decisions
- [ROADMAP.md Phase 1](../../ROADMAP.md) — Source requirements for this PRD
- "Claude Code *is* the DM brain; the MCP tools are its hands" — Core architectural principle
