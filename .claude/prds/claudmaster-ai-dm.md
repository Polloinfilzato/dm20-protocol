---
name: claudmaster-ai-dm
description: Autonomous AI Dungeon Master system with multi-agent architecture, published module support, and configurable improvisation levels
status: complete
created: 2026-02-05T10:00:00Z
---

# PRD: Claudmaster - Autonomous AI Dungeon Master

## Executive Summary

This PRD defines an autonomous AI Dungeon Master system ("Claudmaster") that can run complete D&D campaigns with minimal human intervention. The system supports both solo play and multi-player sessions with AI as the Dungeon Master.

**Key deliverables:**
1. **Multi-Agent Architecture** — Specialized agents for narrative, game state, and module knowledge
2. **Module Integration** — RAG-based system to follow published adventure modules
3. **Improvisation Control** — Configurable levels of AI creative freedom vs module fidelity
4. **Narrative Engine** — Coherent storytelling with memory and consistency
5. **Autonomous Resolution** — AI handles all DM decisions without human intervention
6. **Scalable Sessions** — Same system works for solo play and multi-player groups

**Value proposition:** Transform gamemaster-mcp from a campaign tracker into a complete AI Dungeon Master that can run published adventures (Curse of Strahd, Lost Mines of Phandelver, etc.) autonomously, eliminating the need for solo-specific adventure books and enabling groups to play D&D without a human DM.

## Problem Statement

### Current State

Gamemaster-mcp provides excellent campaign tracking but requires humans to:
- Generate narrative and descriptions
- Roleplay NPCs and make their decisions
- Determine encounter outcomes beyond dice rolls
- Maintain story consistency and pacing
- Adapt published modules on the fly

```python
# Current: Human must drive everything
roll_dice("1d20+5")  # System rolls
# Human: "You rolled 18. The guard believes your lie and lets you pass."
# Human: "He says 'Alright, move along citizen.'"
# Human must decide what happens next, consult module, etc.
```

### Problems

1. **Not True Solo Play:** Players must act as both player AND DM
2. **No Module Support:** Cannot automatically follow published adventures
3. **No Narrative Generation:** System doesn't describe scenes, NPCs, or outcomes
4. **No Autonomous Decisions:** AI cannot decide what NPCs do or say
5. **No Consistency Engine:** Nothing ensures story coherence over sessions
6. **No Improvisation Control:** When modules are used, no way to configure how strictly to follow them

### Why Now?

- Research validates multi-agent approach (arxiv:2502.19519v2 - "Static vs Agentic GM AI")
- PDF Rulebook Library provides foundation for module content access
- MCP architecture supports multi-agent orchestration
- Existing projects prove concept viable (GameMasterAI, D&D Solo Adventure, etc.)
- Competitive opportunity: No existing solution handles modules with configurable fidelity

### Target User Scenarios

**Scenario 1: Solo Player**
```
Player: "I want to play Curse of Strahd alone this weekend."

Current: Must use solo-specific books with oracle tables, or act as both player and DM.

With Claudmaster:
1. Load "Curse of Strahd" PDF into library
2. Create campaign with module binding
3. Set improvisation level to "Medium" (follow plot, improvise dialogue)
4. Play naturally - Claudmaster describes scenes, runs NPCs, tracks story
5. Make player decisions, roll dice - Claudmaster handles everything else
```

**Scenario 2: Group Without DM**
```
Group: "We're 4 players, no one wants to DM. Can we play Lost Mines of Phandelver?"

With Claudmaster:
1. One player sets up campaign with module
2. All players connect their characters
3. Claudmaster runs the adventure for all players
4. Players focus purely on roleplaying and decisions
```

**Scenario 3: Experienced DM Assistance**
```
DM: "I'm running Rime of the Frostmaiden but need help with NPC dialogue and
     random encounter descriptions while I focus on the main plot."

With Claudmaster:
1. Set improvisation to "High" (loose module adherence)
2. Claudmaster generates on-demand descriptions and NPC dialogue
3. DM maintains control over major plot decisions
4. Best of both: AI assistance with human creative control
```

## Prior Art & Inspiration

### Academic Research

| Source | Key Finding | Application |
|--------|-------------|-------------|
| [arxiv:2502.19519v2](https://arxiv.org/html/2502.19519v2) | Multi-agent (Narrator + Archivist) beats single-agent in 9/14 metrics | Adopt dual-agent minimum architecture |
| Same paper | Players felt "guided by a GM" vs "guiding the GM" with agentic approach | Agents must be proactive, not reactive |
| Same paper | ReAct framework enables better reasoning | Use ReAct pattern for agent decisions |

### Existing Projects

| Project | What to Adopt | What to Avoid |
|---------|---------------|---------------|
| [GameMasterAI](https://github.com/deckofdmthings/GameMasterAI) | Persistent JSON state, MongoDB integration | Weak documentation, no module support |
| [D&D Solo Adventure](https://github.com/MarcosN7/dnd-ai-beta) | Character context integration, companion system, shareable adventures | Only generated content, no published modules |
| [GPT Dungeon Master](https://github.com/SverreNystad/gpt-dungeon-master) | ReAct architecture, good rule reference | Limited narrative capability |
| [Mnehmos' D&D MCP](https://skywork.ai/skypage/en/ai-dungeon-master-toolkit/1980458059440967680) | ASCII battlefield, persistent game state, modular Python architecture | No module integration |
| [Oracle-RPG methodology](https://oracle-rpg.com/) | PDF upload + custom instructions pattern | Still requires human arbitration |

### Key Insight from Research

Traditional "solo RPG" books from DMsGuild include oracle tables, yes/no mechanics, and random generators because they assume no DM. **With an AI DM, these mechanics become unnecessary** — the AI IS the oracle. This means Claudmaster can use **standard adventure modules** designed for human DMs, not solo-specific products.

## Architecture Overview

### Multi-Agent System

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CLAUDMASTER ORCHESTRATOR                          │
│  (Coordinates agents, manages turn flow, handles player input)              │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────────────┐   │
│  │    NARRATOR     │   │    ARCHIVIST    │   │     MODULE KEEPER       │   │
│  │     Agent       │   │     Agent       │   │        Agent            │   │
│  │                 │   │                 │   │                         │   │
│  │ Responsibilities│   │ Responsibilities│   │ Responsibilities        │   │
│  │ - Scene descrip.│   │ - Game state    │   │ - RAG on module PDF     │   │
│  │ - NPC dialogue  │   │ - Rules lookup  │   │ - Plot knowledge        │   │
│  │ - Atmosphere    │   │ - Combat mgmt   │   │ - NPC canon info        │   │
│  │ - Improvisation │   │ - Dice/checks   │   │ - Location details      │   │
│  │ - Pacing        │   │ - HP/resources  │   │ - Secret/reveal timing  │   │
│  │                 │   │ - Initiative    │   │ - Encounter triggers    │   │
│  └────────┬────────┘   └────────┬────────┘   └────────────┬────────────┘   │
│           │                     │                         │                 │
│           └─────────────────────┼─────────────────────────┘                 │
│                                 │                                           │
│                                 ▼                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      CONSISTENCY ENGINE                              │   │
│  │  - Validates narrative against established facts                     │   │
│  │  - Tracks NPC knowledge states ("X knows Y but not Z")              │   │
│  │  - Enforces module constraints based on improvisation level         │   │
│  │  - Detects and prevents contradictions                              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
├─────────────────────────────────────────────────────────────────────────────┤
│                           CAMPAIGN CONFIGURATION                            │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │ module: "curse-of-strahd"                                             │ │
│  │ improvisation_level: "medium"  # none | low | medium | high | full    │ │
│  │ locked_elements:                                                       │ │
│  │   - main_plot_beats                                                   │ │
│  │   - character_deaths_canonical                                        │ │
│  │ flexible_elements:                                                     │ │
│  │   - npc_dialogue                                                      │ │
│  │   - side_quests                                                       │ │
│  │   - encounter_difficulty                                              │ │
│  │ player_mode: "solo" | "multiplayer"                                   │ │
│  │ companion_npcs: true  # AI controls party NPCs in solo mode          │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow

```
PLAYER INPUT                    CLAUDMASTER PROCESSING                  OUTPUT
     │                                   │                                │
     ▼                                   ▼                                ▼
"I search the   ──►  ┌─────────────────────────────────────┐  ──►  "You find a
 bookshelf"          │ 1. Orchestrator receives input      │        hidden
     │               │ 2. Archivist: Check game state      │        compartment
     │               │    - Location: Strahd's study       │        behind the
     │               │    - Time: Night                    │        books. Inside,
     │               │ 3. Module Keeper: Query module      │        a yellowed
     │               │    - "What's in Strahd's study?"    │        letter sealed
     │               │    - Returns: Hidden letter, trap   │        with a raven
     │               │ 4. Archivist: Perception check?     │        crest..."
     │               │    - DC 15, player rolls 18 ✓       │
     │               │ 5. Narrator: Describe discovery     │        [Letter prop
     │               │    - Atmosphere: Gothic, tense      │         revealed]
     │               │    - Detail level: Medium           │
     │               │ 6. Consistency: Log discovery       │
     │               │    - Player now knows about letter  │
     │               └─────────────────────────────────────┘
```

### Improvisation Levels

| Level | Module Adherence | AI Freedom | Use Case |
|-------|------------------|------------|----------|
| **None** | 100% - Script only | Zero | Reading module aloud |
| **Low** | 95% - Minor embellishments | Descriptions only | Faithful playthrough |
| **Medium** | 70% - Plot intact, details flexible | Dialogue, side content | Recommended default |
| **High** | 40% - Major beats only | Most narrative decisions | Experienced groups |
| **Full** | 0% - Module as inspiration | Complete freedom | Sandbox/homebrew |

### Directory Structure

```
dnd_data/
├── claudmaster/                    # NEW: Claudmaster system
│   ├── agents/                     # Agent definitions
│   │   ├── narrator.py
│   │   ├── archivist.py
│   │   └── module_keeper.py
│   ├── orchestrator.py             # Main coordination logic
│   ├── consistency/                # Consistency engine
│   │   ├── fact_tracker.py
│   │   └── contradiction_detector.py
│   └── prompts/                    # System prompts for agents
│       ├── narrator_base.md
│       ├── archivist_base.md
│       └── module_keeper_base.md
│
├── library/                        # Existing PDF library
│   ├── pdfs/
│   │   ├── curse_of_strahd.pdf     # Adventure modules here
│   │   └── lost_mines.pdf
│   ├── index/
│   └── extracted/
│
└── campaigns/
    └── my_solo_campaign/
        ├── campaign.json
        ├── claudmaster_config.json  # NEW: Claudmaster settings
        ├── session_memory/          # NEW: Per-session narrative state
        │   ├── session_001.json
        │   └── session_002.json
        └── fact_database.json       # NEW: Established facts
```

## User Stories

### US-1: Starting a Module-Based Solo Campaign

**As a** solo player
**I want** to start a campaign using a published adventure module I own
**So that** I can experience the adventure without needing another person to DM

**Acceptance Criteria:**
- [ ] Load adventure module PDF into library
- [ ] Create campaign and bind to module
- [ ] Configure improvisation level (default: medium)
- [ ] Create player character
- [ ] Optionally add AI-controlled companion NPCs
- [ ] Claudmaster begins the adventure with appropriate intro

### US-2: Playing a Session

**As a** player in a Claudmaster session
**I want** to interact naturally with the game world
**So that** I can focus on playing my character without DM responsibilities

**Acceptance Criteria:**
- [ ] Describe actions in natural language
- [ ] Receive atmospheric scene descriptions
- [ ] Interact with NPCs through dialogue
- [ ] Roll dice for checks (system or player rolls)
- [ ] Combat runs with initiative, attacks, tactics
- [ ] Session state persists between plays

### US-3: NPC Interaction

**As a** player
**I want** NPCs to feel like autonomous characters
**So that** conversations feel natural, not scripted

**Acceptance Criteria:**
- [ ] NPCs respond based on personality and knowledge
- [ ] NPCs remember previous interactions
- [ ] NPCs have goals and motivations
- [ ] NPCs react to player reputation
- [ ] NPCs can refuse, lie, or have hidden agendas

### US-4: Module Fidelity Control

**As a** player familiar with a module
**I want** to configure how closely the AI follows the written adventure
**So that** I can balance surprise with the experience I want

**Acceptance Criteria:**
- [ ] Set improvisation level at campaign creation
- [ ] Lock specific plot elements
- [ ] Allow flexibility in specific areas
- [ ] Change settings mid-campaign if desired
- [ ] See what is "canonical" vs "improvised"

### US-5: Companion NPC Management (Solo Mode)

**As a** solo player
**I want** the AI to control companion party members
**So that** I can experience party dynamics without playing multiple characters

**Acceptance Criteria:**
- [ ] Define which NPCs join the party
- [ ] AI makes tactical decisions for companions in combat
- [ ] AI roleplays companion dialogue and reactions
- [ ] Player can give companions general guidance
- [ ] Companions have distinct personalities

### US-6: Multi-Player Session

**As a** group of players without a DM
**I want** Claudmaster to run a session for all of us
**So that** everyone can play as players instead of one being the DM

**Acceptance Criteria:**
- [ ] Multiple player characters in same campaign
- [ ] Turn order managed by Claudmaster
- [ ] All players receive scene descriptions
- [ ] Claudmaster addresses players by name/character
- [ ] Handles split party situations

### US-7: Session Continuity

**As a** returning player
**I want** the game to remember everything from previous sessions
**So that** the story feels continuous and consequences matter

**Acceptance Criteria:**
- [ ] NPCs remember player actions
- [ ] World state persists (doors opened, items taken, etc.)
- [ ] Reputation and relationships tracked
- [ ] Plot progress maintained
- [ ] Recap available on session start

### US-8: Autonomous Problem Resolution

**As a** player
**I want** Claudmaster to handle edge cases without asking me to arbitrate
**So that** I never have to "break character" to make DM decisions

**Acceptance Criteria:**
- [ ] Ambiguous rules resolved reasonably
- [ ] NPC decisions made autonomously
- [ ] Narrative dead-ends handled gracefully
- [ ] Combat tactics determined by AI
- [ ] No "what do you want to happen?" prompts to player

## Requirements

### Functional Requirements

#### FR-1: Agent System

| ID | Requirement |
|----|-------------|
| FR-1.1 | Implement Narrator agent with ReAct pattern |
| FR-1.2 | Implement Archivist agent for game state |
| FR-1.3 | Implement Module Keeper agent with RAG |
| FR-1.4 | Implement Orchestrator for agent coordination |
| FR-1.5 | Define agent communication protocol |
| FR-1.6 | Support concurrent agent queries |
| FR-1.7 | Implement agent response aggregation |

#### FR-2: Module Integration

| ID | Requirement |
|----|-------------|
| FR-2.1 | Parse adventure module structure (chapters, encounters) |
| FR-2.2 | Index module locations, NPCs, items |
| FR-2.3 | Implement RAG search across module content |
| FR-2.4 | Track module progression state |
| FR-2.5 | Handle module "read-aloud" text appropriately |
| FR-2.6 | Support encounter trigger conditions |
| FR-2.7 | Parse and use module maps/locations |

#### FR-3: Narrative Engine

| ID | Requirement |
|----|-------------|
| FR-3.1 | Generate atmospheric scene descriptions |
| FR-3.2 | Produce consistent NPC dialogue |
| FR-3.3 | Maintain narrative pacing |
| FR-3.4 | Handle player action interpretation |
| FR-3.5 | Generate appropriate combat narration |
| FR-3.6 | Support different tones (horror, comedy, etc.) |
| FR-3.7 | Adapt description detail to context |

#### FR-4: Consistency System

| ID | Requirement |
|----|-------------|
| FR-4.1 | Track established narrative facts |
| FR-4.2 | Track NPC knowledge states |
| FR-4.3 | Detect potential contradictions |
| FR-4.4 | Enforce module constraints per improv level |
| FR-4.5 | Maintain timeline consistency |
| FR-4.6 | Track location states (doors, traps, etc.) |

#### FR-5: Improvisation Control

| ID | Requirement |
|----|-------------|
| FR-5.1 | Support 5 improvisation levels |
| FR-5.2 | Configure locked elements per campaign |
| FR-5.3 | Configure flexible elements per campaign |
| FR-5.4 | Real-time improv level adjustment |
| FR-5.5 | Tag outputs as canonical vs improvised |

#### FR-6: Session Management

| ID | Requirement |
|----|-------------|
| FR-6.1 | Save session state on pause/end |
| FR-6.2 | Resume session with context |
| FR-6.3 | Generate session recap on start |
| FR-6.4 | Track session duration and events |
| FR-6.5 | Support mid-session saves |

#### FR-7: Companion NPC System

| ID | Requirement |
|----|-------------|
| FR-7.1 | Define companion NPC profiles |
| FR-7.2 | AI-controlled combat tactics |
| FR-7.3 | AI-controlled roleplay responses |
| FR-7.4 | Player guidance system ("stay back", "heal me") |
| FR-7.5 | Companion personality differentiation |
| FR-7.6 | Companion relationship with player |

#### FR-8: Multi-Player Support

| ID | Requirement |
|----|-------------|
| FR-8.1 | Multiple PC tracking |
| FR-8.2 | Player identification in prompts |
| FR-8.3 | Turn distribution and management |
| FR-8.4 | Split party handling |
| FR-8.5 | Player-specific information (notes to DM equivalent) |

#### FR-9: MCP Tools

| ID | Requirement |
|----|-------------|
| FR-9.1 | `start_claudmaster_session` - Begin or resume session |
| FR-9.2 | `player_action` - Submit player action for processing |
| FR-9.3 | `end_session` - Save and close session |
| FR-9.4 | `configure_claudmaster` - Adjust settings |
| FR-9.5 | `get_session_state` - Check current game state |
| FR-9.6 | `claudmaster_query` - Ask Claudmaster a meta question |
| FR-9.7 | `add_companion` - Add AI-controlled companion |
| FR-9.8 | `guide_companion` - Give companion guidance |

### Non-Functional Requirements

#### NFR-1: Response Quality

| ID | Requirement |
|----|-------------|
| NFR-1.1 | Responses feel natural and engaging |
| NFR-1.2 | NPCs have distinct voices |
| NFR-1.3 | Descriptions match tone of module |
| NFR-1.4 | No obvious contradictions |
| NFR-1.5 | Appropriate length (not too verbose/terse) |

#### NFR-2: Performance

| ID | Requirement |
|----|-------------|
| NFR-2.1 | Simple action response < 5 seconds |
| NFR-2.2 | Complex scene < 15 seconds |
| NFR-2.3 | Combat round < 10 seconds |
| NFR-2.4 | Session resume < 3 seconds |
| NFR-2.5 | Module query < 2 seconds |

#### NFR-3: Reliability

| ID | Requirement |
|----|-------------|
| NFR-3.1 | No data loss on crash |
| NFR-3.2 | Graceful handling of ambiguous input |
| NFR-3.3 | Recovery from agent failures |
| NFR-3.4 | Consistent behavior across sessions |

#### NFR-4: Autonomy

| ID | Requirement |
|----|-------------|
| NFR-4.1 | Zero player-as-DM prompts in solo mode |
| NFR-4.2 | Self-resolving edge cases |
| NFR-4.3 | Proactive narrative advancement |
| NFR-4.4 | No "I don't know what to do" responses |

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| Solo session completion | Player never acts as DM | User testing |
| Module fidelity | Major plot points hit at Low/Medium | Compare playthrough to module |
| NPC consistency | No contradictions noticed | User feedback |
| Response time p95 | < 10 seconds | Timing logs |
| Session continuity | 100% state recovery | Automated tests |
| User engagement | Player wants to continue | Survey/retention |
| Multi-player support | 4 players successfully | Integration test |

## Constraints and Assumptions

### Constraints

1. **LLM Dependency:** System requires capable LLM (Claude/GPT-4 class)
2. **Context Window:** Long campaigns may exceed context limits
3. **Module Copyright:** Users must own PDFs they use
4. **Processing Cost:** Multi-agent system uses significant tokens
5. **No Voice:** Text-only interface (no TTS/STT integration)

### Assumptions

1. Users have legally obtained adventure module PDFs
2. PDF library system is implemented and functional
3. Existing game state tracking (HP, inventory, etc.) works reliably
4. Users accept occasional AI mistakes as part of the experience
5. LLM APIs remain available and affordable

## Out of Scope

The following are explicitly NOT included in this PRD:

1. Voice input/output (speech-to-text, text-to-speech)
2. Visual map generation or display
3. Integration with VTT platforms (Roll20, Foundry)
4. Real-time multiplayer networking (async only for now)
5. Mobile app
6. Non-D&D 5e systems
7. AI-generated original campaign content (use module or homebrew)
8. Automated miniature/token movement

## Dependencies

### External Dependencies

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| Claude API | claude-3+ | LLM for agents | Medium - API costs |
| LangChain | >=0.1 | Agent framework, RAG | Low |
| ChromaDB | >=0.4 | Vector store for RAG | Low |
| Existing MCP | Current | Tool framework | None |

### Internal Dependencies

```
Claudmaster (this PRD)
    ├── depends on -> PDF Rulebook Library (for module content)
    ├── depends on -> Game State System (HP, inventory, etc.)
    ├── depends on -> Combat System (initiative, rounds)
    ├── depends on -> Character System (PCs, NPCs)
    ├── extends -> Session Notes (auto-generation)
    └── enhances -> All existing tools (autonomous usage)
```

### Recommended Implementation Order

1. **Phase 1: Foundation**
   - Orchestrator skeleton
   - Basic Narrator agent (descriptions only)
   - Integration with existing game state

2. **Phase 2: Module Integration**
   - Module Keeper agent
   - RAG pipeline for PDF modules
   - Module structure parsing

3. **Phase 3: Full Narrative**
   - Complete Narrator agent
   - NPC dialogue generation
   - Archivist agent

4. **Phase 4: Consistency**
   - Fact tracker
   - Contradiction detection
   - NPC knowledge states

5. **Phase 5: Improvisation Control**
   - Improv level configuration
   - Locked/flexible elements
   - Module fidelity enforcement

6. **Phase 6: Companion System**
   - AI-controlled companions
   - Combat tactics
   - Personality system

7. **Phase 7: Multi-Player**
   - Multiple PC support
   - Turn management
   - Split party handling

8. **Phase 8: Polish**
   - Session continuity
   - Error handling
   - Performance optimization

## Technical Notes

### Agent Prompt Structure (Narrator Example)

```markdown
# Narrator Agent

You are the narrative voice of a D&D adventure. Your role is to describe
scenes, portray NPCs, and create atmosphere.

## Current Context
- Module: {{module_name}}
- Location: {{current_location}}
- Time: {{in_game_time}}
- Tone: {{module_tone}} (e.g., gothic horror, heroic fantasy)
- Improvisation Level: {{improv_level}}

## Constraints
{{#if improv_level == "low"}}
- Use module read-aloud text when available
- Embellish only minor sensory details
- Do not add major elements not in module
{{/if}}
{{#if improv_level == "medium"}}
- Follow module themes and tone
- Freely generate NPC dialogue
- May add minor side details
- Keep major plot intact
{{/if}}

## Current Scene
{{scene_context_from_module_keeper}}

## Established Facts (DO NOT CONTRADICT)
{{facts_from_consistency_engine}}

## Player Action
{{player_input}}

## Your Task
Generate a vivid, engaging response to the player's action that:
1. Maintains the established tone
2. Respects module/consistency constraints
3. Advances the narrative appropriately
4. Provides clear information about outcomes
```

### Module RAG Structure

```json
{
  "module_id": "curse-of-strahd",
  "chapters": [
    {
      "id": "chapter-1",
      "title": "Into the Mists",
      "locations": ["death-house", "village-of-barovia"],
      "npcs": ["ismark", "ireena", "mad-mary"],
      "encounters": ["death-house-dungeon"],
      "trigger_conditions": {
        "death-house-reveal": "players approach house"
      }
    }
  ],
  "npcs": {
    "strahd": {
      "personality": "charismatic, cruel, obsessive",
      "goals": ["claim Ireena", "torment adventurers"],
      "knowledge": ["all about Barovia", "players observed since arrival"],
      "secrets": ["tatyana reincarnation cycle"]
    }
  },
  "locations": {
    "castle-ravenloft": {
      "description_chunks": ["chunk_id_1", "chunk_id_2"],
      "sub_locations": ["dining-hall", "crypts", "tower"],
      "encounters": ["dinner-with-strahd", "crypt-guardians"]
    }
  }
}
```

### Consistency Engine Schema

```json
{
  "campaign_id": "my-cos-campaign",
  "facts": [
    {
      "id": "fact-001",
      "category": "event",
      "statement": "Party freed Ireena from Death House",
      "session": 1,
      "timestamp": "2026-02-05T14:30:00Z",
      "source": "module" | "improvised"
    },
    {
      "id": "fact-002",
      "category": "npc_knowledge",
      "npc": "ismark",
      "knows": ["party rescued Ireena", "party killed zombies"],
      "does_not_know": ["party found secret letter"]
    }
  ],
  "contradictions_resolved": [
    {
      "conflict": "NPC said tavern was closed, but it was open earlier",
      "resolution": "Tavern closes at midnight, time passed",
      "session": 2
    }
  ]
}
```

## References

### Research
- [Static vs Agentic GM AI (arxiv:2502.19519v2)](https://arxiv.org/html/2502.19519v2)

### Projects
- [GameMasterAI](https://github.com/deckofdmthings/GameMasterAI)
- [D&D Solo Adventure](https://github.com/MarcosN7/dnd-ai-beta)
- [GPT Dungeon Master](https://github.com/SverreNystad/gpt-dungeon-master)
- [Mnehmos' D&D MCP Server](https://skywork.ai/skypage/en/ai-dungeon-master-toolkit/1980458059440967680)
- [DnD-MCP](https://github.com/procload/dnd-mcp)

### Methodologies
- [Oracle-RPG Solo DM Guide](https://oracle-rpg.com/2023/03/solo-dm-guide-part-3-chatgpt-as-assistant-ai-dungeon-master/)
- [Wisps of Time: Soloing Published Modules](https://wispsoftime.com/content/thoughts-soloing-published-adventure-module/)
- [LitRPG Reads: Rise of Solo RPG](https://litrpgreads.com/blog/rpg/rise-solo-rpg-ai-dungeon-masters)

### Related PRDs
- [PDF Rulebook Library](./pdf-rulebook-library.md) - Required for module content
- [Rulebook System](./rulebook-system.md) - Rules reference foundation

## Appendix A: Improvisation Level Details

### Level: None (Script Mode)
- Read module text verbatim
- No embellishment
- Encounters exactly as written
- Use case: Module reading/audiobook style

### Level: Low (Faithful)
- Add sensory details (smells, sounds)
- Vary NPC tone within personality
- Same outcomes as module
- Use case: First-time module experience

### Level: Medium (Adaptive) - RECOMMENDED DEFAULT
- Follow major plot structure
- Generate NPC dialogue freely
- Add minor NPCs, side details
- Adjust encounter difficulty
- Use case: Engaging solo/group play

### Level: High (Inspired)
- Key beats only (Strahd is villain, Ireena is target)
- Major creative freedom
- Can add substantial side content
- May alter secondary outcomes
- Use case: Module-inspired sandbox

### Level: Full (Sandbox)
- Module as setting/inspiration only
- Complete narrative freedom
- Player can go anywhere, do anything
- Use case: Homebrew with module assets

## Appendix B: Companion Behavior Profiles

### Tank Companion
- Positions in front
- Taunts enemies
- Uses defensive abilities
- Protects low-HP allies

### Healer Companion
- Stays in back
- Monitors party HP
- Prioritizes healing over damage
- Warns of status effects

### Striker Companion
- Focuses high-value targets
- Uses positioning for advantage
- Aggressive tactics
- May need player protection

### Support Companion
- Buffs before combat
- Controls battlefield
- Flexible positioning
- Coordinates with player

## Appendix C: Error Handling Philosophy

When Claudmaster encounters ambiguity:

1. **Rules Ambiguity:** Rule in favor of fun, note decision
2. **Module Gap:** Improvise consistent content, tag as improvised
3. **Player Intent Unclear:** Interpret most reasonable action, confirm
4. **Contradiction Detected:** Use most recent/consistent fact, log
5. **Technical Failure:** Graceful degradation, save state, retry

**Never:**
- Ask player to make DM decision
- Say "I don't know what happens"
- Break immersion with meta-discussion
- Ignore player action without response
