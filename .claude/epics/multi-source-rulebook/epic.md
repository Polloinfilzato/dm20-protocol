---
name: multi-source-rulebook
status: backlog
created: 2026-02-12T02:41:42Z
progress: 0%
prd: .claude/prds/multi-source-rulebook.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/80
---

# Epic: Multi-Source Rulebook System

## Overview

Extend dm20-protocol's rulebook system from SRD-only to multi-source by implementing two new adapters (Open5e REST API, 5etools JSON files) that plug into the existing `RulebookSourceBase` / `RulebookManager` architecture. The infrastructure is already designed for this — the work is implementing concrete adapters and wiring them into the existing MCP tool.

## Architecture Decisions

### 1. Follow SRDSource pattern exactly
Both new sources follow the same architecture as `SRDSource`: HTTP fetch → local JSON cache → in-memory dict storage → query via abstract interface. This keeps the codebase consistent and leverages proven patterns.

### 2. Cache-first architecture
All external data is cached locally on first fetch. Subsequent loads read from cache only. Cache refresh is manual (user-triggered). This ensures offline play and fast startup.

### 3. httpx for all HTTP (already a dependency)
No new HTTP dependencies. Both Open5e (REST API) and 5etools (GitHub raw file download) use httpx with retry logic.

### 4. Minimal model changes
The existing `ClassDefinition`, `SpellDefinition`, etc. models are expressive enough for Open5e and 5etools data. The only model change needed is adding `FIVETOOLS` to the `RulebookSource` enum (`OPEN5E` already exists).

### 5. Shared infrastructure changes are minimal
The `load_rulebook` MCP tool needs its `Literal` type extended from `["srd", "custom"]` to `["srd", "custom", "open5e", "5etools"]`. The `_create_source_from_config` factory method needs two new `elif` branches. These are ~10 lines of code total.

## Technical Approach

### New Source Files
```
src/dm20_protocol/rulebooks/sources/
├── base.py       # ✅ EXISTS - No changes
├── srd.py        # ✅ EXISTS - Template for new sources
├── custom.py     # ✅ EXISTS - No changes
├── open5e.py     # 🆕 NEW - REST API client
└── fivetools.py  # 🆕 NEW - JSON file downloader/parser
```

### Open5e Integration
- **API**: `https://api.open5e.com/v1/` — paginated REST, JSON responses
- **Endpoints**: `/spells/`, `/monsters/`, `/classes/`, `/races/`, `/magicitems/`, `/feats/`, `/backgrounds/`
- **Pagination**: `?page=N`, auto-paginate all results
- **Caching**: One JSON file per endpoint (e.g., `open5e_spells.json`)
- **Mapping**: Open5e schema is close to SRD API but with different field names. Dedicated `_map_*` methods needed.

### 5etools Integration
- **Data source**: GitHub raw files (e.g., `https://raw.githubusercontent.com/.../data/spells/index.json`)
- **Strategy**: Download index → discover data files → download each → parse → cache
- **Schema**: 5etools uses custom markup in descriptions (e.g., `{@dice 1d6}`, `{@spell fireball}`). Need a lightweight markup converter.
- **Caching**: Raw JSON files stored locally, parsed models cached separately

### MCP Tool Extension (in `main.py`)
```python
# Line 1303: Extend Literal type
Literal["srd", "custom", "open5e", "5etools"]

# Add elif branches for new sources (lines ~1340)
elif source == "open5e":
    open5e_source = Open5eSource(cache_dir=storage.rulebook_cache_dir)
    await storage.rulebook_manager.load_source(open5e_source)
    ...

elif source == "5etools":
    fivetools_source = FiveToolsSource(cache_dir=storage.rulebook_cache_dir)
    await storage.rulebook_manager.load_source(fivetools_source)
    ...
```

### Manager Extension (in `manager.py`)
```python
# _create_source_from_config: add two elif branches
elif config.type == "open5e":
    from .sources.open5e import Open5eSource
    return Open5eSource(cache_dir=cache_dir)

elif config.type == "5etools":
    from .sources.fivetools import FiveToolsSource
    return FiveToolsSource(cache_dir=cache_dir)
```

## Implementation Strategy

### Phased approach (Open5e first, then 5etools)

Open5e is simpler (standard REST API, closer to SRD schema) and provides immediate value. 5etools is more complex (custom JSON schema, markup conversion) but provides the richest content. Building Open5e first validates the integration pattern.

### Testing approach
- Unit tests: Mock HTTP responses, test model mapping
- Integration tests: Test with real API (gated behind network availability flag)
- Regression: Existing SRD and Custom source tests must pass unchanged

## Task Breakdown Preview

- [ ] Task 1: Open5eSource adapter with caching, model mapping, and full test suite
- [ ] Task 2: Extend load_rulebook MCP tool and manager factory for open5e + 5etools types
- [ ] Task 3: FiveToolsSource data downloader with caching and schema discovery
- [ ] Task 4: FiveToolsSource model mapping with 5etools markup conversion and tests
- [ ] Task 5: End-to-end integration tests (multi-source priority, conflict resolution, offline cache)

## Dependencies

### Internal (all exist, minor changes only)
- `RulebookSourceBase` — abstract interface (no changes)
- `RulebookManager` — factory method extension (~5 lines)
- `models.py` — add `FIVETOOLS` enum value (~1 line)
- `main.py` — extend `load_rulebook` tool (~20 lines)

### External
- `httpx` — already a dependency
- Open5e API availability (free, public)
- 5etools GitHub data availability (public repository)

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Open5e: spells loaded | > 700 |
| Open5e: monsters loaded | > 1000 |
| 5etools: spells loaded | > 500 |
| 5etools: monsters loaded | > 1500 |
| Cache load time | < 5 seconds per source |
| Existing test suite | Zero regressions |
| New code test coverage | > 80% |

## Estimated Effort

| Task | Size | Hours |
|------|------|-------|
| Open5eSource adapter | M | 4-6 |
| MCP tool + manager extension | S | 1-2 |
| 5etools downloader | M | 3-4 |
| 5etools model mapping | M | 4-6 |
| Integration tests | S | 2-3 |
| **Total** | **L** | **14-21** |

**Critical path**: Task 1 (Open5e) → Task 2 (integration) → Task 3+4 (5etools, can partially parallel)

## Tasks Created

- [ ] 80.md - Open5eSource Adapter (parallel: true)
- [ ] 81.md - MCP Tool and Manager Integration (parallel: true)
- [ ] 82.md - FiveToolsSource Data Downloader (parallel: true)
- [ ] 83.md - FiveToolsSource Model Mapping (parallel: false, depends on #82)
- [ ] 84.md - Multi-Source Integration Tests (parallel: false, depends on #80, #81, #82, #83)

Total tasks: 5
Parallel tasks: 3 (#80, #81, #82 can start simultaneously)
Sequential tasks: 2 (#83 after #82, #84 after all)
Estimated total effort: 14-21 hours
