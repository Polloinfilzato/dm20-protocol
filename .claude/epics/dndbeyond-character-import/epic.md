---
name: dndbeyond-character-import
status: in_progress
created: 2026-02-17T16:55:58Z
progress: 14%
prd: .claude/prds/dndbeyond-character-import.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/158
---

# Epic: D&D Beyond Character Import

## Overview

One-shot import pipeline that fetches D&D Beyond character JSON (from URL or local file) and maps it to dm20's `Character` model. The architecture is a simple three-stage pipeline: **Input** (fetch/read) → **Mapper** (DDB JSON → dm20) → **Output** (add to campaign). The mapper is the core complexity — DDB stores raw values across scattered JSON sections that must be aggregated to produce computed stats.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| HTTP client | `httpx` (async) | Already a project dependency; async-capable for MCP context |
| Module location | `src/dm20_protocol/importers/dndbeyond/` | Isolated namespace; extensible for future importers (Roll20, Foundry) |
| Mapper pattern | Functional — standalone functions per domain | Each mapping function (identity, abilities, spells...) is independently testable |
| Error strategy | Graceful degradation with warnings | Partial import > no import; collect warnings instead of raising |
| Result model | Pydantic `BaseModel` (not dataclass) | Consistent with project conventions; serializable for MCP response |
| File format detection | Check for `"data"` wrapper key + `"stats"` array | Distinguishes DDB JSON from other formats without explicit version field |

## Technical Approach

### Input Layer (`fetcher.py`)

- **URL parsing**: Extract numeric character ID from various URL formats (`/characters/123`, `/characters/123/builder`, bare `123`)
- **HTTP fetch**: `httpx.AsyncClient.get()` to `character-service.dndbeyond.com/character/v5/character/{id}`
- **File reader**: Load and validate local `.json` file, detect DDB format
- **Shared output**: Both paths produce a `dict` (raw DDB JSON) passed to the mapper

### Mapper Layer (`mapper.py`)

The DDB JSON is complex because values are scattered:
- **Ability scores** = `stats[]` base + `modifiers.race` bonuses + `modifiers.class` ASIs + `bonusStats[]` + `overrideStats[]`
- **HP** = `baseHitPoints` + `bonusHitPoints` + (CON_mod × level) — or `overrideHitPoints` if set
- **Proficiencies** = filtered from `modifiers` sections where `type == "proficiency"`
- **Inventory** = `inventory[]` with nested `definition` objects
- **Spells** = `classSpells[]` or `spells.class[]` with nested `definition`

Each domain has a dedicated mapping function:
1. `map_identity()` — name, race, class, background, alignment
2. `map_abilities()` — compute final ability scores from all modifier sources
3. `map_combat()` — HP, AC, hit dice, speed
4. `map_proficiencies()` — skills, saves, tools, languages
5. `map_inventory()` — items with type classification + equipment slots
6. `map_spells()` — spell list with slots
7. `map_features()` — class/race features and feats

A top-level `map_ddb_to_character()` orchestrates all functions, collects warnings, and returns `DDBImportResult`.

### Integration Layer (`main.py`)

Two new MCP tools:
- `import_from_dndbeyond(url_or_id, player_name?)` — fetch + map + add to campaign
- `import_character_file(file_path, source_format?, player_name?)` — read + map + add to campaign

Both return a formatted import summary with mapped fields, warnings, and the created character name.

## Implementation Strategy

### Development Phases

**Phase 1 (Core):** Scaffolding → Fetcher → Core Mapper (identity + abilities + combat + proficiencies) → MCP tools → Tests
**Phase 2 (Extended):** Inventory + Spells + Features + Equipment slots → Extended tests
**Phase 3 (Polish):** Multiclass, currency, notes/bio, documentation

### Risk Mitigation

- **DDB endpoint instability**: File import fallback ensures the feature works even if the endpoint changes
- **Unknown JSON schema**: Test fixtures with real DDB JSON snapshots; mapper functions use `.get()` with defaults everywhere
- **Modifier aggregation complexity**: Ability score calculation is the hardest part — dedicated tests with known expected values

### Testing Approach

- **Unit tests**: Each `map_*()` function tested independently with DDB JSON fixtures
- **Integration test**: Full pipeline from raw JSON → Character model
- **Fixture**: A realistic DDB character JSON snapshot (anonymized) committed to `tests/fixtures/`
- **HTTP mock**: `httpx` responses mocked for fetcher tests (200, 403, 404, timeout)

## Task Breakdown

- [ ] #159: Module scaffolding and base models
- [ ] #160: DDB fetcher and file reader
- [ ] #161: Core mapper — identity, abilities, combat stats, proficiencies
- [ ] #162: Extended mapper — inventory, spells, features, equipment
- [ ] #163: MCP tool integration and import summary
- [ ] #164: Test suite with DDB JSON fixtures
- [ ] #165: Documentation update

## Dependencies

| Dependency | Type | Status | Notes |
|------------|------|--------|-------|
| `httpx>=0.24.0` | Python package | Already installed | Used for DDB API fetch |
| `pydantic>=2.0.0` | Python package | Already installed | ImportResult model |
| DDB character service v5 | External endpoint | Available (undocumented) | Public characters only; may change |
| `Character` model | Internal (`models.py`) | Stable | Target model for mapping |
| `DnDStorage` | Internal (`storage.py`) | Stable | For adding character to campaign |
| Active campaign | Runtime | Required | Must have a loaded campaign to import into |

## Success Criteria (Technical)

| Criteria | Target |
|----------|--------|
| Import a level 8 public DDB character via URL | All core stats match DDB values |
| Import the same character from saved JSON file | Identical result to URL import |
| Ability score calculation | Final scores match DDB character sheet display |
| Import time (URL) | < 5 seconds including network fetch |
| Partial import | Character created even if some fields fail to map |
| Error handling | Clear messages for 403 (private), 404 (not found), timeout |
| Test coverage | All mapper functions have unit tests |

## Estimated Effort

| Phase | Tasks | Estimate |
|-------|-------|----------|
| Phase 1 (Core) | #159-#161, #163 | ~8 hours |
| Phase 2 (Extended) | #162 | ~4 hours |
| Phase 3 (Tests + Docs) | #164-#165 | ~4 hours |
| **Total** | **7 tasks** | **~16 hours** |

**Critical path:** #159 → #160 → #161 → #163 (sequential — each depends on the previous)
**Parallelizable:** #162 can run alongside #163 after #161 completes; #164 can start after #161; #165 after #163

## Tasks Created

- [ ] 159.md - Module scaffolding and base models (parallel: false) — S, 2h
- [ ] 160.md - DDB fetcher and file reader (parallel: true) — S, 3h
- [ ] 161.md - Core mapper: identity, abilities, combat, proficiencies (parallel: true) — L, 6h
- [ ] 162.md - Extended mapper: inventory, spells, features, equipment (parallel: true) — M, 4h
- [ ] 163.md - MCP tool integration and import summary (parallel: true) — M, 3h
- [ ] 164.md - Test suite with DDB JSON fixtures (parallel: false) — M, 4h
- [ ] 165.md - Documentation update (parallel: true) — S, 2h

Total tasks: 7
Parallel tasks: 5
Sequential tasks: 2
Estimated total effort: ~24 hours

### Dependency Graph

```
#159 (scaffolding)
 ├──▶ #160 (fetcher)  ─────────────┐
 └──▶ #161 (core mapper) ──┬───────┼──▶ #163 (MCP tools) ──▶ #165 (docs)
                            │       │
                            └──▶ #162 (extended mapper)
                                    │
                                    └──────────────────────▶ #164 (tests)
```
