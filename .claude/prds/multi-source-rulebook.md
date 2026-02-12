---
name: multi-source-rulebook
description: Extend dm20-protocol to support multiple rulebook sources (Open5e, 5etools) beyond the current SRD-only setup
status: backlog
created: 2026-02-12T02:32:49Z
---

# PRD: Multi-Source Rulebook System

## Executive Summary

Extend dm20-protocol's rulebook system to support multiple data sources beyond the current SRD-only setup. The existing plugin architecture (`RulebookSourceBase`, `RulebookManager` with priority resolution) is already designed for this — what's missing are the concrete adapter implementations and the user-facing configuration flow.

**Key deliverables:**

1. **Open5eSource adapter** — REST API client for [Open5e](https://open5e.com/api-docs), accessing OGL content from multiple publishers (Kobold Press, Tome of Beasts, etc.)
2. **5etoolsSource adapter** — Auto-download and parse JSON data files from the [5etools GitHub repository](https://github.com/5etools-mirror-3/5etools-mirror-3.github.io), providing the broadest D&D 5e content coverage
3. **Extended `load_rulebook` MCP tool** — Add `open5e` and `5etools` as source types to the existing tool
4. **Source suggestion during campaign setup** — Prompt users to select rulebook sources when creating a new campaign
5. **Caching and offline support** — All sources cache locally for offline play and performance

**Value proposition:** Users can access the full breadth of D&D 5e content (not just the limited SRD) when running campaigns, with a simple configuration flow that "just works."

## Problem Statement

### Current State

dm20-protocol can only access D&D 5e rules from two sources:
- **SRD** via dnd5eapi.co — Limited to ~400 spells, ~300 monsters, 12 classes (no subclasses beyond SRD), basic item set
- **Custom JSON/YAML** — Requires manual authoring of homebrew content in a specific schema

This means a user playing a campaign with a Ranger (Gloom Stalker) or a Paladin (Oath of Vengeance) gets no subclass features from the rules system. A DM wanting to use a Beholder or Mind Flayer finds them missing. The system has the infrastructure to support more, but no one has plugged in the richer data sources.

```
Current experience:
  DM: "You encounter a Beholder"
  System: ❌ Monster not found in SRD
  Player: "I cast Booming Blade"
  System: ❌ Spell not found in SRD

Desired experience:
  DM: "You encounter a Beholder"
  System: ✅ Full stat block from Open5e/5etools
  Player: "I cast Booming Blade"
  System: ✅ Full spell details with upcasting rules
```

### Why Now?

- The plugin architecture (`RulebookSourceBase`) is complete and battle-tested with SRD and Custom sources
- The DM Persona & Game Loop epic (in progress) needs richer rules data to deliver a complete play experience
- Open5e provides a free, well-documented REST API
- 5etools provides the most comprehensive D&D 5e dataset available, with a stable JSON schema

### Target User

DM (human or AI) running a campaign in dm20-protocol who needs access to D&D 5e content beyond the free SRD. The user:
- Wants rules, monsters, spells, and subclasses from published books
- Does not want to manually author JSON for every piece of content
- Expects a simple "enable this source" workflow
- May play offline after initial setup

## User Stories

### US-1: Enable Open5e for a Campaign
**As a** DM setting up a new campaign,
**I want to** load Open5e as a rulebook source,
**So that** I have access to OGL content from multiple publishers.

**Acceptance Criteria:**
- `load_rulebook(source="open5e")` loads all Open5e content
- Content from Open5e is searchable via `search_rules`
- Spells, monsters, classes, races, feats from Open5e appear in queries
- Content is cached locally after first load
- Subsequent loads use cache (fast, offline-capable)

### US-2: Enable 5etools for a Campaign
**As a** DM wanting the broadest content coverage,
**I want to** load 5etools data as a rulebook source,
**So that** I have access to virtually all D&D 5e content including homebrew.

**Acceptance Criteria:**
- `load_rulebook(source="5etools")` downloads and indexes 5etools JSON data
- First load downloads data from GitHub (with progress indication)
- Data is cached locally; subsequent loads are instant
- Content maps correctly to dm20-protocol's data models
- User is informed about data freshness and update mechanism

### US-3: Source Priority Resolution
**As a** DM with multiple sources enabled,
**I want** the system to resolve conflicts when the same content exists in multiple sources,
**So that** I always get the most complete/accurate version.

**Acceptance Criteria:**
- Later-loaded sources take priority (existing `last_wins` behavior)
- User can see which source provided a given piece of content (already in `source` field)
- User can reorder priority via `list_rulebooks` and `unload_rulebook`

### US-4: Source Suggestion on Campaign Creation
**As a** new user creating their first campaign,
**I want** the system to suggest available rulebook sources,
**So that** I know my options and can set up a rich rules environment from the start.

**Acceptance Criteria:**
- After `create_campaign`, the DM persona or game loop suggests loading additional sources
- Suggestion is non-blocking (user can skip)
- Suggestion lists available sources with brief descriptions

### US-5: Offline Play After Initial Setup
**As a** player who set up sources while online,
**I want to** play without internet,
**So that** I can use dm20-protocol anywhere.

**Acceptance Criteria:**
- All fetched content is persisted to local cache
- Sources load from cache when offline
- Cache invalidation is manual (user triggers refresh)

## Architecture Overview

```
                    ┌──────────────────────┐
                    │   RulebookManager    │
                    │  (priority, dedup)   │
                    └──────────┬───────────┘
                               │
              ┌────────────────┼────────────────┐
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼────────┐
    │   SRDSource    │ │ Open5eSource │ │ 5etoolsSource │
    │ (dnd5eapi.co)  │ │ (REST API)   │ │ (JSON files)  │
    │   ✅ EXISTS    │ │  🆕 NEW      │ │   🆕 NEW      │
    └────────────────┘ └──────────────┘ └───────────────┘
              │                │                │
    ┌─────────▼──────┐ ┌──────▼───────┐ ┌──────▼────────┐
    │  Local Cache   │ │ Local Cache  │ │  Local Cache   │
    │ (JSON files)   │ │ (JSON files) │ │  (JSON files)  │
    └────────────────┘ └──────────────┘ └────────────────┘
```

### Existing Infrastructure (no changes needed)

| Component | Location | Role |
|-----------|----------|------|
| `RulebookSourceBase` | `sources/base.py` | Abstract interface — all adapters implement this |
| `RulebookManager` | `manager.py` | Orchestrates sources, priority resolution, unified search |
| `Manifest` | `manager.py` | Persists active sources to `manifest.json` |
| `SourceConfig` | `manager.py` | Serializable source configuration |
| Data models | `models.py` | `ClassDefinition`, `SpellDefinition`, etc. |

### New Components

| Component | Location | Role |
|-----------|----------|------|
| `Open5eSource` | `sources/open5e.py` | REST API client with caching |
| `FiveToolsSource` | `sources/fivetools.py` | JSON downloader/parser with caching |
| Extended `load_rulebook` | `mcp/tools/` | New source types in existing tool |
| `_create_source_from_config` | `manager.py` | Factory method extended for new types |
| `RulebookSource` enum | `models.py` | Add `OPEN5E` and `FIVETOOLS` values |

## Requirements

### Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | `Open5eSource` fetches classes, races, spells, monsters, feats, items from Open5e REST API | Must |
| FR-2 | `Open5eSource` caches all API responses locally as JSON files | Must |
| FR-3 | `Open5eSource` maps Open5e data models to dm20-protocol models | Must |
| FR-4 | `FiveToolsSource` downloads 5etools JSON data files from GitHub | Must |
| FR-5 | `FiveToolsSource` parses 5etools JSON schema into dm20-protocol models | Must |
| FR-6 | `FiveToolsSource` caches downloaded data locally | Must |
| FR-7 | `load_rulebook` tool accepts `source="open5e"` | Must |
| FR-8 | `load_rulebook` tool accepts `source="5etools"` | Must |
| FR-9 | Both sources integrate with `RulebookManager` priority system | Must |
| FR-10 | `_create_source_from_config` handles `open5e` and `5etools` types | Must |
| FR-11 | Open5e document-level filtering (select specific publishers) | Should (Phase 2) |
| FR-12 | Source suggestion after campaign creation | Should |
| FR-13 | `list_rulebooks` shows content counts per source | Should |
| FR-14 | Manual cache refresh command | Could |

### Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Open5e initial load time | < 60 seconds (with batch fetching) |
| NFR-2 | 5etools initial download time | < 120 seconds (depends on connection) |
| NFR-3 | Cached source load time | < 5 seconds |
| NFR-4 | Cache storage size (Open5e) | < 50 MB |
| NFR-5 | Cache storage size (5etools) | < 200 MB |
| NFR-6 | Offline operation after caching | 100% functional |
| NFR-7 | API error handling | Graceful degradation, retry with backoff |
| NFR-8 | Thread safety | Same as existing SRDSource (RLock in manager) |

## Technical Details

### Open5e API Integration

Base URL: `https://api.open5e.com/v1/`

Key endpoints:
- `/classes/` — Classes
- `/races/` — Races
- `/spells/` — Spells (filterable by class, level, school)
- `/monsters/` — Monsters (filterable by CR, type)
- `/magicitems/` — Magic items
- `/feats/` — Feats
- `/backgrounds/` — Backgrounds

Each result includes `document__slug` (e.g., `5esrd`, `tob`, `cc`) identifying the publisher. Phase 1 loads all; Phase 2 adds per-document filtering.

Pagination: Results are paginated (`?page=N`), adapter must handle auto-pagination.

### 5etools Data Integration

Data source: GitHub repository JSON files (e.g., `data/spells/spells-phb.json`, `data/bestiary/bestiary-mm.json`).

Strategy:
1. Download index file to discover available data files
2. Download individual category JSON files
3. Parse 5etools JSON schema (well-documented, stable)
4. Map to dm20-protocol models
5. Cache everything locally

Key mapping challenges:
- 5etools uses its own schema with `"source": "PHB"` style attribution
- Spell descriptions use a custom markup format that needs conversion
- Monster stat blocks have a richer schema than SRD API

### Manager Extension

```python
# In manager.py - _create_source_from_config
elif config.type == "open5e":
    from .sources.open5e import Open5eSource
    return Open5eSource(cache_dir=cache_dir)

elif config.type == "5etools":
    from .sources.fivetools import FiveToolsSource
    return FiveToolsSource(cache_dir=cache_dir)
```

### Model Enum Extension

```python
# In models.py
class RulebookSource(str, Enum):
    SRD = "srd"
    CUSTOM = "custom"
    OPEN5E = "open5e"      # NEW
    FIVETOOLS = "5etools"  # NEW
```

## Success Criteria

| Metric | Target |
|--------|--------|
| Open5e content loaded | 1000+ spells, 500+ monsters, all classes/races |
| 5etools content loaded | 3000+ spells, 2000+ monsters, all official classes/subclasses |
| Load from cache | < 5 seconds for any source |
| Offline functionality | 100% after initial cache |
| Existing tests | Zero regressions |
| New test coverage | > 80% for new source code |

## Constraints & Assumptions

### Constraints
- **Legal**: Open5e content is OGL-licensed; 5etools is a gray area. The system must clearly attribute sources and not redistribute data (only cache locally for personal use).
- **No bundled data**: Neither Open5e nor 5etools data is bundled with dm20-protocol. Users must opt-in and download on first use.
- **Network dependency**: First load requires internet. System must handle network failures gracefully.
- **5etools schema stability**: 5etools JSON schema may change between releases. Adapter must handle schema variations.

### Assumptions
- Open5e API remains publicly accessible and free
- 5etools JSON data files remain available on GitHub
- dm20-protocol models (`ClassDefinition`, `SpellDefinition`, etc.) are expressive enough to represent Open5e/5etools content (may need minor extensions)
- Users are comfortable with a one-time download process

## Out of Scope

- **Per-document filtering for Open5e** (Phase 2 — tracked separately)
- **Automatic schema migration** when 5etools changes format
- **Content editing UI** — users cannot modify downloaded content through dm20-protocol
- **Syncing between sources** — each source is independent, priority handles overlaps
- **Subscription/paid API sources** — only free, publicly available data
- **2024 D&D rules** — 5e only (matching existing SRD scope)

## Dependencies

### Internal
- `RulebookSourceBase` (exists, no changes)
- `RulebookManager` (exists, minor factory method extension)
- `models.py` (exists, enum extension + possible minor field additions)
- MCP tool `load_rulebook` (exists, extend `source` parameter)

### External
- `httpx` (already a dependency, used by SRDSource)
- Open5e API availability (https://api.open5e.com)
- 5etools GitHub data files availability

## Implementation Order

```
Phase 1 — Open5e (lower complexity, REST API)
  ├── Task 1: Open5eSource adapter + cache
  ├── Task 2: Model mapping + integration tests
  └── Task 3: Extend load_rulebook tool

Phase 2 — 5etools (higher complexity, custom schema)
  ├── Task 4: 5etools data downloader + cache
  ├── Task 5: 5etools schema parser + model mapping
  └── Task 6: Extend load_rulebook tool

Phase 3 — UX polish
  ├── Task 7: Source suggestion on campaign creation
  └── Task 8: Open5e document-level filtering (optional)
```

## Related Issues

- [#79](https://github.com/Polloinfilzato/dm20-protocol/issues/79) — Original feature request
- [#12](https://github.com/Polloinfilzato/dm20-protocol/issues/12) — Rulebook Source Abstraction (completed, foundation for this work)
