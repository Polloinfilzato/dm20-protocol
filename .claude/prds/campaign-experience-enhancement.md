---
name: campaign-experience-enhancement
description: Portable Compendium Packs for cross-campaign content sharing, Multi-User permissions for group play, and Narrative Fog of War for progressive information reveal
status: backlog
created: 2026-02-17T12:00:00Z
---

# PRD: Campaign Experience Enhancement

## Executive Summary

dm20-protocol excels at single-player AI DM sessions, but three capabilities would dramatically improve the campaign management experience: **sharing content between campaigns**, **supporting multiple human players**, and **revealing information progressively** as players explore. These features are inspired by Foundry VTT's strengths in content management and multi-user collaboration, adapted for dm20's text-based paradigm.

**Key deliverables:**

1. **Compendium Packs** — Export/import NPCs, locations, quests, encounters, and items between campaigns as portable JSON packs. Create reusable content libraries.
2. **Multi-User Permissions** — Role-based access control allowing multiple players to connect to the same campaign session, each controlling their own character with appropriate visibility restrictions.
3. **Narrative Fog of War** — Progressive information reveal system where the AI DM only shares location details, NPC knowledge, and world lore as players discover them through exploration and interaction.

**Value proposition:** A DM (human or AI) builds rich content once and reuses it across campaigns; multiple friends can play together with proper information boundaries; and exploration feels genuinely rewarding because knowledge is earned, not given.

## Problem Statement

### Current State

```
Campaign experience today:
├── Content reuse              ❌ Each campaign is isolated — NPCs/locations can't be shared
├── Campaign backup            ❌ No export format — only raw JSON in data directory
├── Multi-player sessions      ⚠️  PCRegistry exists but no access control or permissions
├── Per-player visibility      ⚠️  PrivateInfo system exists but isn't wired to output filtering
├── Progressive exploration    ❌ AI DM describes everything about a location on first visit
├── Knowledge tracking         ✅ NPC knowledge system tracks what NPCs know
├── Fact database              ✅ Consistency engine tracks established facts
└── Location state             ✅ LocationState tracks doors/traps/loot changes
```

### Pain Points

1. **Content is trapped in campaigns** — A carefully crafted NPC tavern keeper can't be reused in another campaign without manually copying JSON files. Foundry VTT lets you drag content between compendiums freely.

2. **No group play story** — dm20 has `PCRegistry` and `MultiPlayerConfig` but no mechanism for multiple human users to connect, authenticate, or have separate character control. Everything runs through a single MCP connection.

3. **Exploration lacks mystery** — When the party enters a dungeon room, the AI DM describes everything (treasure, traps, exits, hidden passages) because it has no concept of "what has been revealed." Foundry VTT's fog of war makes exploration meaningful.

4. **Private information exists but isn't enforced** — The `PrivateInfo` model with visibility levels (PUBLIC, PARTY, PRIVATE, DM_ONLY, SUBSET) is implemented but never integrated into the output pipeline. The Narrator agent sees everything and shares everything.

### Target Users

- **Solo player** who runs multiple campaigns and wants to reuse their custom NPCs/locations
- **Small group** (2-4 players) who want to play together with one person's MCP server
- **Content creator** who builds adventure content and wants to distribute it as packs

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│              Campaign Experience Layer                    │
│                                                           │
│  ┌────────────────┐  ┌──────────────┐  ┌──────────────┐ │
│  │ Compendium     │  │ Multi-User   │  │ Narrative    │ │
│  │ Pack Manager   │  │ Access       │  │ Fog of War   │ │
│  │                │  │ Controller   │  │ Engine       │ │
│  └───────┬────────┘  └──────┬───────┘  └──────┬───────┘ │
│          │                  │                  │          │
│  ┌───────▼────────┐  ┌─────▼────────┐  ┌─────▼────────┐ │
│  │ Import/Export  │  │ Permission   │  │ Discovery    │ │
│  │ Serializer    │  │ Resolver     │  │ Tracker      │ │
│  └───────┬────────┘  └─────┬────────┘  └─────┬────────┘ │
│          │                  │                  │          │
│  ┌───────▼──────────────────▼──────────────────▼────────┐ │
│  │              Existing Infrastructure                  │ │
│  │  storage.py │ models.py │ private_info.py │ agents/  │ │
│  └──────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘

Fog of War data flow:
  Player: "We enter the cave"
  │
  ├─ 1. Narrator queries DiscoveryTracker:
  │     "What has the party already seen in this cave?"
  │
  ├─ 2. DiscoveryTracker returns:
  │     discovered: [entrance, first_chamber]
  │     undiscovered: [hidden_passage, treasure_room, trap]
  │
  ├─ 3. Narrator generates description using ONLY discovered info
  │     + sensory hints about undiscovered elements
  │     ("You notice a cold draft from the north wall...")
  │
  └─ 4. As players investigate, DiscoveryTracker reveals more
        and updates the party's knowledge map
```

## User Stories

### US-1: Compendium Packs — Export
**As a** DM who has created detailed NPCs and locations,
**I want** to export them as a portable pack,
**So that** I can reuse them in future campaigns or share with others.

**Acceptance Criteria:**
- [ ] Export individual entities (NPC, Location, Quest, Item) to a pack
- [ ] Export filtered sets (e.g., "all NPCs in Waterdeep", "all active quests")
- [ ] Export entire campaign as a full backup pack
- [ ] Pack format is a single JSON file with metadata (name, version, author, description, entity counts)
- [ ] Pack includes entity relationships (NPC→Location references preserved)
- [ ] `export_pack` MCP tool with flexible selection options

### US-2: Compendium Packs — Import
**As a** DM starting a new campaign,
**I want** to import NPCs and locations from a previously exported pack,
**So that** I don't have to recreate content I've already built.

**Acceptance Criteria:**
- [ ] Import pack into current campaign with conflict resolution (skip, overwrite, rename)
- [ ] Preview pack contents before importing (dry run)
- [ ] Selective import (choose which entities from the pack)
- [ ] ID regeneration to avoid collisions with existing entities
- [ ] Relationship re-linking after import (NPC references to locations updated)
- [ ] `import_pack` MCP tool with preview and selection modes
- [ ] Support importing from file path or URL

### US-3: Compendium Packs — Community Sharing
**As a** content creator,
**I want** packs to have a standard format with metadata,
**So that** the community can share and discover reusable D&D content.

**Acceptance Criteria:**
- [ ] Pack metadata: name, version, author, description, tags, system_version
- [ ] Pack validation on import (schema check, version compatibility)
- [ ] `list_packs` tool to browse available packs in a local library directory
- [ ] `validate_pack` tool to check pack integrity

### US-4: Multi-User — Player Roles
**As a** group of friends playing together,
**I want** each player to control their own character with appropriate permissions,
**So that** one player can't modify another player's character sheet.

**Acceptance Criteria:**
- [ ] Role system: DM (full access), Player (own character + shared state), Observer (read-only)
- [ ] Players can only modify their own character (identified by player_name)
- [ ] Players can view: shared game state, public NPC info, other characters' public stats (name, class, HP status)
- [ ] Players cannot view: DM notes, NPC secret bios, other characters' private notes, unvisited locations
- [ ] DM can grant/revoke temporary permissions (e.g., "player X can see NPC secret")

### US-5: Multi-User — Session Coordination
**As a** group playing a shared session,
**I want** the system to coordinate whose turn it is and what each player sees,
**So that** the session flows smoothly with proper information boundaries.

**Acceptance Criteria:**
- [ ] MCP tool calls include `player_id` parameter for permission checking
- [ ] Turn-based notification: "It's [player]'s turn" with relevant context
- [ ] Shared narrative visible to all; private info visible only to relevant player
- [ ] DM can send private messages to individual players
- [ ] Session supports async play (players don't need to be simultaneous)

### US-6: Narrative Fog of War — Location Discovery
**As a** player exploring a dungeon,
**I want** the DM to reveal room details only as I discover them,
**So that** exploration feels rewarding and mysterious.

**Acceptance Criteria:**
- [ ] Each location/room has a discovery state: undiscovered, partially_discovered, fully_explored
- [ ] First visit reveals: general atmosphere, obvious features, visible exits
- [ ] Investigation/perception reveals: hidden features, traps, secrets
- [ ] Discovery state persists across sessions
- [ ] `get_location` respects discovery state (DM sees all, players see discovered only)
- [ ] Narrator agent receives discovery context and generates appropriately scoped descriptions

### US-7: Narrative Fog of War — Knowledge Tracking
**As a** player,
**I want** the system to track what my character knows about the world,
**So that** the DM doesn't accidentally reveal information I haven't learned.

**Acceptance Criteria:**
- [ ] Party knowledge map: which facts, NPCs, locations, and quest details are known
- [ ] Knowledge sources: who told them, when, where (leveraging existing FactDatabase)
- [ ] NPC dialogue respects player knowledge (NPC won't repeat known info unless asked)
- [ ] `party_knowledge` tool to see what the party currently knows about a topic
- [ ] Integration with existing NPC Knowledge Tracker (bidirectional: NPCs know things, party knows things)

## Functional Requirements

### Compendium Packs

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-1 | CompendiumPack Pydantic model with metadata and entity collections | P0 | M |
| FR-2 | PackSerializer: Campaign entities → Pack JSON with relationship preservation | P0 | L |
| FR-3 | PackImporter: Pack JSON → Campaign entities with conflict resolution | P0 | L |
| FR-4 | Selective export by entity type, location filter, or tag | P1 | M |
| FR-5 | Selective import with preview/dry-run mode | P1 | M |
| FR-6 | ID regeneration and relationship re-linking on import | P0 | M |
| FR-7 | Pack validation (schema, version compatibility) | P1 | S |
| FR-8 | Local pack library directory (`data/packs/`) with browse support | P2 | S |
| FR-9 | `export_pack`, `import_pack`, `list_packs` MCP tools | P0 | M |
| FR-10 | Full campaign backup/restore as a single pack | P1 | M |

### Multi-User Permissions

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-11 | Role enum: DM, Player, Observer with permission matrix | P0 | S |
| FR-12 | PermissionResolver: checks tool call against caller role + ownership | P0 | M |
| FR-13 | Player identification via `player_id` parameter on sensitive MCP tools | P0 | M |
| FR-14 | Character ownership enforcement (players edit only their character) | P0 | M |
| FR-15 | Output filtering: strip DM-only content from player-visible responses | P1 | L |
| FR-16 | DM permission grants (temporary visibility elevation for specific players) | P2 | M |
| FR-17 | Session participant tracking (who's connected, who's active) | P1 | M |
| FR-18 | Async play support: action queue for non-simultaneous players | P2 | L |

### Narrative Fog of War

| ID | Requirement | Priority | Complexity |
|----|-------------|----------|------------|
| FR-19 | DiscoveryState model: per-location/per-room discovery tracking | P0 | M |
| FR-20 | DiscoveryLevel enum: UNDISCOVERED, GLIMPSED, EXPLORED, FULLY_MAPPED | P0 | S |
| FR-21 | Location feature visibility: each feature has a discovery requirement | P0 | M |
| FR-22 | DiscoveryTracker: manages what party has discovered, persists to campaign | P0 | M |
| FR-23 | PartyKnowledge model: facts, NPCs, locations known by the party | P1 | M |
| FR-24 | Integration with Narrator: discovery context injected into scene prompts | P0 | L |
| FR-25 | Integration with existing PrivateInfo system for per-player visibility | P1 | M |
| FR-26 | Integration with existing NPC Knowledge Tracker (party ↔ NPC knowledge flow) | P1 | M |
| FR-27 | `party_knowledge` MCP tool for querying what the party knows | P1 | S |
| FR-28 | Perception/Investigation check results update discovery state | P1 | M |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Pack export time for full campaign (100+ entities) | < 5 seconds |
| NFR-2 | Pack import with conflict resolution | < 10 seconds |
| NFR-3 | Pack file size for full campaign | < 5 MB (JSON) |
| NFR-4 | Permission check overhead per tool call | < 10ms |
| NFR-5 | No breaking changes to single-player experience | All features opt-in |
| NFR-6 | Discovery state storage per campaign | < 500 KB |
| NFR-7 | Backward compatibility with campaigns without discovery data | Graceful defaults (everything = EXPLORED) |
| NFR-8 | Test coverage for permission system | > 95% (security-critical) |

## Dependencies

### Internal Dependencies
- `models.py` — New models: CompendiumPack, DiscoveryState, PlayerRole
- `storage.py` — Pack serialization, discovery state persistence
- `private_info.py` — Already has InfoVisibility levels (PUBLIC, PARTY, PRIVATE, DM_ONLY, SUBSET)
- `pc_tracking.py` — Already has PCRegistry and MultiPlayerConfig
- `consistency/npc_knowledge.py` — Bidirectional knowledge flow
- `consistency/fact_database.py` — Party knowledge derived from facts
- `claudmaster/agents/narrator.py` — Discovery context in scene generation
- `main.py` — New MCP tools

### External Dependencies
- None (pure Python, no new packages)

### Existing Infrastructure to Leverage

The codebase already has significant foundations that this PRD builds on:

| Existing System | File | How This PRD Uses It |
|----------------|------|---------------------|
| PrivateInfo + InfoVisibility | `private_info.py` | Wire into output filtering for multi-user |
| PCRegistry + MultiPlayerConfig | `pc_tracking.py` | Add permission layer on top |
| NPC Knowledge Tracker | `consistency/npc_knowledge.py` | Extend with party-side knowledge |
| FactDatabase | `consistency/fact_database.py` | Facts become the source-of-truth for party knowledge |
| LocationState | `consistency/location_state.py` | Add discovery tracking alongside state changes |
| HiddenRoll | `private_info.py` | Use for per-player perception checks |

## Implementation Order

### Phase 1: Compendium Packs (standalone, no dependencies)
1. CompendiumPack model and PackSerializer
2. Export functionality (full campaign + selective)
3. Import functionality with conflict resolution
4. `export_pack`, `import_pack`, `list_packs` MCP tools
5. Pack validation

### Phase 2: Narrative Fog of War (builds on consistency engine)
6. DiscoveryState and DiscoveryLevel models
7. DiscoveryTracker with persistence
8. Location feature visibility annotations
9. Narrator agent integration (discovery context injection)
10. PartyKnowledge model linked to FactDatabase
11. `party_knowledge` MCP tool

### Phase 3: Multi-User Permissions (builds on fog of war + PCRegistry)
12. Role system and permission matrix
13. PermissionResolver middleware
14. Player identification on MCP tools
15. Output filtering (strip DM-only content)
16. Session participant tracking
17. Async play action queue

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Multi-user requires networking (MCP is single-connection) | High | Phase 1: permission model only; actual multi-connection via MCP Streamable HTTP transport or proxy in future |
| Fog of war slows down narration (extra context per query) | Medium | Cache discovery state; pre-compute visible features per location |
| Pack format may break across dm20 versions | Medium | Version field in pack metadata; migration support for breaking changes |
| Permission system adds overhead to every tool call | Low | Lazy evaluation; skip permission check in single-player mode |
| Narrator may "leak" undiscovered information | High | Explicit discovery context in prompt; test with adversarial prompts |

## Open Questions

1. **Multi-user transport**: MCP currently operates over stdio (single client). Multi-user would require either:
   - MCP Streamable HTTP transport (each player connects separately)
   - A proxy/relay layer that multiplexes player connections
   - Turn-based async where players take turns on the same connection

   This PRD defines the **permission and data model** — the transport layer is a separate concern.

2. **Pack distribution**: Should packs be shareable via URL/GitHub/npm? Phase 1 focuses on local file exchange; distribution channels are future scope.

3. **Discovery granularity**: Should discovery track per-room features (e.g., "you noticed the crack in the wall but not the hidden lever") or per-room only? This PRD proposes per-feature discovery for maximum flexibility.
