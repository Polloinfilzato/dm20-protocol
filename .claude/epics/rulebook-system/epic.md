---
name: rulebook-system
status: completed
created: 2026-02-02T03:43:04Z
progress: 100%
prd: .claude/prds/rulebook-system.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/11
---

# Epic: Rulebook Management System

## Overview

Implement a modular rulebook system that transforms gamemaster-mcp from a data manager into a rules-aware game engine. The system will:

1. Load official D&D 5e SRD content via API
2. Support custom homebrew rulebooks (JSON/YAML)
3. Validate characters against loaded rules
4. Provide query tools for spells, monsters, classes, etc.

## Architecture Decisions

### Technology Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| HTTP Client | `httpx` | Async support, modern API, already common in Python ecosystem |
| YAML Parser | `pyyaml` | Standard, lightweight, user-friendly for homebrew |
| Caching | File-based JSON | Consistent with existing split-storage pattern |
| Models | Pydantic v2 | Consistency with existing codebase |

### Design Patterns

1. **Source Abstraction** — Abstract base class for data sources (SRD, Open5e, Custom)
2. **Lazy Loading** — Rulebook content loaded on first access, not at startup
3. **Priority Resolution** — Custom content overrides official (configurable)
4. **Graceful Degradation** — System works without rulebooks loaded

### Key Decisions

1. **Separate models file** — New `rulebooks/models.py` to avoid bloating existing `models.py`
2. **Global cache directory** — SRD cache at `dnd_data/rulebook_cache/` (shared across campaigns)
3. **Campaign manifest** — Per-campaign `rulebooks/manifest.json` tracks active rulebooks
4. **Validation as warnings** — Invalid characters still work, validation is informational

## Technical Approach

### Module Structure

```
src/gamemaster_mcp/
├── rulebooks/
│   ├── __init__.py           # Public API exports
│   ├── models.py             # ClassDefinition, RaceDefinition, etc.
│   ├── manager.py            # RulebookManager orchestration
│   ├── validators.py         # Character validation logic
│   └── sources/
│       ├── __init__.py
│       ├── base.py           # Abstract RulebookSource
│       ├── srd.py            # 5e-srd-api client
│       └── custom.py         # Local JSON/YAML loader
```

### Data Flow

```
Campaign Load
    ↓
RulebookManager.load_from_manifest()
    ↓
For each source in manifest:
    → SRDSource.load() OR CustomSource.load()
    ↓
Unified query interface ready
    ↓
Tools call manager.get_class(), manager.search_spells(), etc.
```

### Storage Layout

```
dnd_data/
├── rulebook_cache/           # Global, shared
│   └── srd_2014/
│       ├── classes.json
│       ├── races.json
│       ├── spells.json
│       └── monsters.json
└── campaigns/
    └── {campaign}/
        └── rulebooks/
            ├── manifest.json    # Which rulebooks are active
            └── custom/
                └── homebrew.json
```

### Integration with Existing Code

- **storage.py** — Add `rulebooks_dir` property to split-storage campaigns
- **main.py** — Register 8 new MCP tools (consolidated from 13 in PRD)
- **models.py** — No changes (new models in separate file)

## Implementation Strategy

### Phased Delivery

| Phase | Scope | Deliverable |
|-------|-------|-------------|
| 1 | Foundation | Models, RulebookManager skeleton, Source base class |
| 2 | SRD Integration | httpx client, caching, full SRD 2014 support |
| 3 | Custom Rulebooks | JSON/YAML loader, schema validation |
| 4 | MCP Tools | 8 consolidated tools for querying and management |
| 5 | Character Validation | Validator logic, validation report |

### Risk Mitigation

| Risk | Mitigation |
|------|------------|
| 5e-srd-api rate limits | Aggressive caching, cache-first strategy |
| API downtime | Offline mode with cached data |
| Large cache size | Lazy loading, only cache what's accessed |
| Model drift | Version field in cache, invalidation on version mismatch |

### Testing Approach

- Unit tests for each source (mock HTTP responses)
- Integration tests with real SRD API (marked slow, optional)
- Validation tests with known-good and known-bad characters
- Test fixtures with sample homebrew files

## Task Breakdown Preview

Tasks are consolidated to maximize efficiency:

- [ ] **Task 1: Rulebook Models** — Pydantic models for ClassDefinition, RaceDefinition, SpellDefinition, MonsterDefinition, Feat, Background, Rulebook
- [ ] **Task 2: Source Abstraction** — Base class + CustomSource for local JSON/YAML files
- [ ] **Task 3: SRD Client** — httpx-based client for 5e-srd-api with caching
- [ ] **Task 4: RulebookManager** — Orchestration class with unified query interface
- [ ] **Task 5: Storage Integration** — Add rulebook support to campaign storage
- [ ] **Task 6: Character Validator** — Validation logic with detailed reports
- [ ] **Task 7: MCP Tools (Management)** — load_rulebook, list_rulebooks, unload_rulebook
- [ ] **Task 8: MCP Tools (Query)** — search_rules, get_class, get_race, get_spell, get_monster, validate_character

## Dependencies

### External (New)

| Package | Version | Purpose |
|---------|---------|---------|
| httpx | ≥0.24 | Async HTTP client for SRD API |
| pyyaml | ≥6.0 | Parse YAML homebrew files |

### Internal (Existing)

- `storage.py` — Campaign data access
- `models.py` — Character model for validation
- `toon_encoder.py` — Token-efficient output format

### Prerequisite Work

- ✅ Split storage architecture (completed)
- ✅ TOON output support (completed)

## Success Criteria (Technical)

| Criterion | Target | Verification |
|-----------|--------|--------------|
| SRD data accessibility | All 12 classes, 9 races, 319 spells | Query tests |
| Cache performance | Load < 500ms after first fetch | Benchmark |
| Validation accuracy | Detect invalid subclass/race | Test suite |
| Offline mode | Full functionality with cache | Disconnect test |
| Backward compatibility | No changes to existing tools | Existing test suite passes |
| Test coverage | ≥ 80% for new code | pytest-cov |

## Estimated Effort

### Task Estimates

| Task | Complexity | Notes |
|------|------------|-------|
| Task 1: Models | Medium | 10+ Pydantic models, follow existing patterns |
| Task 2: Source Abstraction | Low | Simple ABC + JSON/YAML loader |
| Task 3: SRD Client | Medium | HTTP calls, response mapping, caching |
| Task 4: RulebookManager | Medium | Orchestration, query routing |
| Task 5: Storage Integration | Low | Minor additions to existing code |
| Task 6: Validator | Medium | Logic for multiple validation rules |
| Task 7: MCP Tools (Mgmt) | Low | 3 straightforward tools |
| Task 8: MCP Tools (Query) | Medium | 5 tools with search/filter logic |

### Critical Path

```
Task 1 (Models)
    ↓
Task 2 (Sources) + Task 3 (SRD) [parallel]
    ↓
Task 4 (Manager)
    ↓
Task 5 (Storage) + Task 6 (Validator) [parallel]
    ↓
Task 7 + Task 8 (Tools) [parallel]
```

## Open5e Integration (Future Phase)

Deferred to a future phase:
- Same architecture as SRD source
- Adds `sources/open5e.py`
- Requires source attribution tagging
- Can be added without breaking changes

## Notes

### API Reference

- **5e-srd-api**: `https://www.dnd5eapi.co/api/`
  - Classes: `/api/classes/{index}`
  - Races: `/api/races/{index}`
  - Spells: `/api/spells/{index}`
  - Monsters: `/api/monsters/{index}`

- **Documentation**: https://5e-bits.github.io/docs/

### Simplifications from PRD

1. **13 tools → 8 tools**: Consolidated `get_feat`, `get_background`, `get_level_features`, `apply_level_up` into search/get tools
2. **No Open5e in v1**: Deferred to future phase for faster delivery
3. **Shared cache**: Global cache instead of per-campaign reduces duplication
4. **JSON only for cache**: YAML for input only, JSON for internal storage

## Tasks Created

| File | Name | Parallel | Depends On |
|------|------|----------|------------|
| [11.md](11.md) | Rulebook Data Models | ✅ | - |
| [12.md](12.md) | Rulebook Source Abstraction | ❌ | 11 |
| [13.md](13.md) | SRD API Client | ❌ | 11, 12 |
| [14.md](14.md) | RulebookManager Orchestration | ❌ | 11, 12, 13 |
| [15.md](15.md) | Storage Integration | ✅ | 14 |
| [16.md](16.md) | Character Validator | ✅ | 14 |
| [17.md](17.md) | MCP Tools - Rulebook Management | ✅ | 14, 15 |
| [18.md](18.md) | MCP Tools - Rule Queries | ✅ | 14, 15, 16 |

**Summary:**
- Total tasks: 8
- Parallel tasks: 5
- Sequential tasks: 3
- Critical path: 11 → 12 → 13 → 14 → 15/16 → 17/18
