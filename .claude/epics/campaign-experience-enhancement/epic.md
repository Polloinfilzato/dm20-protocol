---
name: campaign-experience-enhancement
status: completed
created: 2026-02-16T23:37:42Z
progress: 100%
prd: .claude/prds/campaign-experience-enhancement.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/140
---

# Epic: Campaign Experience Enhancement

## Overview

Three capabilities to transform dm20 from a single-player solo tool into a shareable, explorable campaign platform: **Compendium Packs** for content portability, **Narrative Fog of War** for progressive discovery, and **Multi-User Permissions** for group play. All features are opt-in — zero impact on the existing single-player experience.

## Architecture Decisions

1. **Pydantic-first serialization** — CompendiumPack is a Pydantic model using `model_dump(mode='json')` / `model_validate()`, consistent with all existing models. No custom serialization layer needed.
2. **DiscoveryTracker lives alongside LocationStateManager** — Both track per-location state. Discovery data persists to `discovery_state.json` in the campaign's split-storage directory, following the same pattern as `location_state.json`.
3. **PermissionResolver as middleware, not decorator** — A single resolver function checks `(caller_role, tool_name, target_entity)` before execution. Avoids scattering permission logic across 50+ tool functions.
4. **Leverage existing PrivateInfo system** — The `InfoVisibility` enum (PUBLIC, PARTY, PRIVATE, DM_ONLY, SUBSET) and `PrivateInfoManager` already model per-player visibility. Multi-user output filtering wires into this rather than building a parallel system.
5. **PCRegistry as identity source** — Player identification uses the existing `PCRegistry.player_name` field. No new auth system — trust is at the MCP connection level.
6. **PartyKnowledge derives from FactDatabase** — Rather than a separate knowledge store, party knowledge is a filtered view of existing facts tagged with `discovered_by_party: true`.

## Technical Approach

### Compendium Packs (Phase 1 — standalone)

- **CompendiumPack model**: metadata (name, version, author, description, tags, system_version) + entity collections (npcs, locations, quests, items, encounters, facts)
- **PackSerializer**: extracts entities from Campaign using `model_dump()`, preserves inter-entity references (NPC→Location by name/id)
- **PackImporter**: validates schema, regenerates IDs to avoid collisions, re-links relationships, supports skip/overwrite/rename conflict modes
- **MCP tools**: `export_pack`, `import_pack`, `list_packs`, `validate_pack`
- **Storage**: packs saved to `{storage_dir}/packs/` directory as `.json` files

### Narrative Fog of War (Phase 2 — builds on consistency engine)

- **DiscoveryLevel enum**: UNDISCOVERED → GLIMPSED → EXPLORED → FULLY_MAPPED
- **DiscoveryState model**: per-location tracking with feature-level granularity (each notable_feature has its own discovery level)
- **DiscoveryTracker**: manages party discovery state, persists to `discovery_state.json`, provides `get_visible_features(location_id)` for filtered output
- **Narrator integration**: discovery context injected into scene description templates — narrator receives only visible features + sensory hints for hidden ones
- **PartyKnowledge**: filtered view over FactDatabase + NPC Knowledge Tracker, exposed via `party_knowledge` MCP tool
- **Perception/Investigation**: check results update discovery levels (GLIMPSED → EXPLORED)

### Multi-User Permissions (Phase 3 — builds on fog of war + PCRegistry)

- **PlayerRole enum**: DM (full access), PLAYER (own character + shared state), OBSERVER (read-only)
- **PermissionResolver**: checks `(role, action, target)` tuples against a permission matrix. Skipped entirely in single-player mode (no overhead).
- **Player identification**: `player_id` optional parameter on sensitive MCP tools (character updates, private info queries). Falls back to single-player mode when absent.
- **Output filtering**: `get_location`, `get_npc`, etc. strip DM_ONLY content when called by a PLAYER. Uses existing `InfoVisibility` levels.
- **Session coordination**: participant tracking, turn notifications, DM private messages via `PrivateMessage` model

## Implementation Strategy

### Development Phases
- **Phase 1 (Compendium Packs)**: Fully standalone. No dependencies on other phases. Can ship independently.
- **Phase 2 (Fog of War)**: Builds on consistency engine (LocationState, FactDatabase, NPC Knowledge). Requires understanding of narrator agent prompt flow.
- **Phase 3 (Multi-User)**: Builds on fog of war (discovery filtering) and PCRegistry. Permission model only — actual multi-connection transport is future scope.

### Risk Mitigation
- All features are **opt-in with graceful defaults**: campaigns without discovery data treat everything as EXPLORED; missing `player_id` = single-player mode.
- Pack format includes `schema_version` field for forward compatibility.
- Permission system has < 10ms overhead (dict lookup, no DB queries).

### Testing Approach
- Unit tests for each model and manager class
- Integration tests for export→import round-trip (entities survive serialization)
- Permission matrix tests: verify every (role, action) combination
- Narrator integration tests: verify discovery context produces scoped descriptions

## Tasks Created

- [ ] 141.md - CompendiumPack Model and Export (parallel: true, Size M, 8-10h)
- [ ] 142.md - Pack Import with Conflict Resolution and MCP Tools (parallel: false, depends: #141, Size M, 8-10h)
- [ ] 143.md - Discovery Models and DiscoveryTracker (parallel: true, Size M, 8-10h)
- [ ] 144.md - Narrator Discovery Integration and Perception Updates (parallel: false, depends: #143, Size L, 10-12h)
- [ ] 145.md - Party Knowledge System and MCP Tool (parallel: true, depends: #143, Size M, 8-10h)
- [ ] 146.md - Role System and PermissionResolver (parallel: true, depends: #143, Size L, 10-12h)
- [ ] 147.md - Output Filtering and Multi-User Session Coordination (parallel: false, depends: #144 #146, Size L, 10-12h)

Total tasks: 7
Parallel tasks: 4 (#141, #143, #145, #146)
Sequential tasks: 3 (#142, #144, #147)
Estimated total effort: 63-76 hours

### Dependency Graph

```
Phase 1 (Compendium):     #141 ──→ #142
                            │
Phase 2 (Fog of War):     #143 ──┬──→ #144 ──┐
                                 │            │
                                 ├──→ #145    ├──→ #147
                                 │            │
Phase 3 (Multi-User):           └──→ #146 ──┘
```

### Parallel Execution Strategy

- **Stream A**: #141 → #142 (Compendium Packs, standalone)
- **Stream B**: #143 → #144 + #145 (Fog of War core + knowledge)
- **Stream C**: #146 (Permissions, after #143)
- **Capstone**: #147 (after #144 + #146)

## Dependencies

### Internal (existing code to modify/extend)
- `dm20_protocol/models.py` — New models (CompendiumPack, DiscoveryState, PlayerRole)
- `dm20_protocol/storage.py` — Pack storage, discovery persistence
- `dm20_protocol/main.py` — New MCP tools (6-8 new tools)
- `claudmaster/private_info.py` — Wire InfoVisibility into output filtering
- `claudmaster/pc_tracking.py` — Add role field to PCState
- `consistency/location_state.py` — Co-locate with DiscoveryTracker
- `consistency/fact_database.py` — Tag facts as party-known
- `consistency/npc_knowledge.py` — Bidirectional party↔NPC knowledge
- `claudmaster/agents/narrator.py` — Discovery context in templates

### External
- None (pure Python, no new packages)

## Success Criteria (Technical)

- Pack export/import round-trip preserves all entity data and relationships
- Discovery state persists across sessions and defaults gracefully for old campaigns
- Permission checks add zero overhead in single-player mode
- Narrator generates scoped descriptions respecting discovery state
- All existing tests continue to pass (no regressions)
- > 90% test coverage on permission-critical code paths

## Estimated Effort

| Phase | Tasks | Estimated Size | Critical Path |
|-------|-------|---------------|---------------|
| Phase 1: Compendium Packs | 2 tasks | M (each) | No blockers |
| Phase 2: Fog of War | 3 tasks | M-L | Narrator integration |
| Phase 3: Multi-User | 2 tasks | M-L | Depends on Phase 2 |
| **Total** | **7 tasks** | **~L overall** | Phase 2→3 sequential |

Phases 1 and 2 can be developed **in parallel** (no shared files). Phase 3 depends on Phase 2's discovery filtering.
