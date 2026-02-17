---
name: adventure-module-integration
status: completed
created: 2026-02-16T00:47:37Z
progress: 100%
prd: .claude/prds/adventure-module-integration.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/125
---

# Epic: Adventure Module Integration

## Overview

Bridge 5e.tools published adventure data with dm20-protocol's existing module infrastructure. The system downloads adventure metadata from the 5e.tools GitHub mirror, lets users discover adventures by theme/keyword/level, parses the full adventure JSON into the existing `ModuleStructure` model, and binds it to campaigns with VectorStore RAG indexing for the ModuleKeeper agent.

The core insight: **80% of the infrastructure already exists** (`ModuleStructure`, `ModuleBinding`, `ModuleKeeperAgent`, `VectorStore`, `FiveToolsSource` download patterns, markup stripper). This epic builds the missing bridge — a new `src/dm20_protocol/adventures/` package that connects 5e.tools adventure JSON to the existing module system.

## Architecture Decisions

### AD-1: Reuse FiveToolsSource patterns, don't subclass
The existing `FiveToolsSource` in `rulebooks/sources/fivetools.py` has proven download/cache/retry logic. Rather than subclassing (tight coupling), extract the reusable patterns:
- **Markup conversion**: Import `_convert_5etools_markup()` and `_render_entries()` directly (move to a shared utility if needed)
- **HTTP client**: Reuse the retry/backoff/concurrency pattern but with adventure-specific URLs
- **Cache structure**: Same `raw/metadata.json` pattern in a separate `adventures/` cache directory

**Rationale**: Adventures have a fundamentally different data shape (narrative chapters vs. structured definitions). Shared utilities, separate implementation.

### AD-2: Two-phase loading (Index → Content)
- **Phase 1**: Download `adventures.json` (~734KB) once, cache for 7 days. All discovery/search operates on this lightweight index.
- **Phase 2**: Download individual `adventure-{id}.json` (242KB-2.6MB) only when user selects one.

**Rationale**: Avoids downloading ~50MB of adventure data upfront. The index is small enough to search in-memory with simple keyword matching.

### AD-3: Keyword search on metadata, not semantic search
Discovery uses direct keyword matching on `name`, `storyline`, and `group` fields from the index — no LLM or embedding required. The adventure index has only 98 entries with rich metadata; semantic search adds complexity without benefit here.

**Rationale**: Instant results, zero dependencies, works offline once cached.

### AD-4: Extend existing ModuleStructure, don't replace
Add a `read_aloud: dict[str, list[str]]` field (keyed by section ID) to `ModuleStructure`. All other fields (`chapters`, `npcs`, `encounters`, `locations`) already fit the adventure data shape.

**Rationale**: Minimal change to existing model, maximum compatibility with ModuleKeeper and VectorStore.

### AD-5: Spoiler boundary = Chapter 1
When auto-populating a campaign, only Chapter 1 content is materialized as campaign entities (NPCs, locations, quests). The full adventure is indexed in VectorStore for the ModuleKeeper, but the DM agent controls what gets revealed progressively.

**Rationale**: Preserves discovery and surprise. The ModuleKeeper already has `mark_revealed()` and `revealed_content` tracking for this purpose.

## Technical Approach

### New Package: `src/dm20_protocol/adventures/`

```
src/dm20_protocol/adventures/
├── __init__.py
├── models.py          # AdventureIndexEntry, AdventureSearchResult, StorylineGroup
├── index.py           # AdventureIndex — download, cache, search, filter
├── parser.py          # AdventureParser — 5etools JSON → ModuleStructure
└── tools.py           # MCP tools: discover_adventures, load_adventure
```

### Shared Utility Extraction

Move `_convert_5etools_markup()` and `_render_entries()` from `fivetools.py` to a shared location (e.g., `rulebooks/sources/fivetools_utils.py`) so both the rulebook source and adventure parser can import them without circular dependencies.

### Data Models

```python
# adventures/models.py
class AdventureIndexEntry(BaseModel):
    """Single adventure from the 5e.tools index."""
    id: str                    # "CoS", "SCC-CK"
    name: str                  # "Curse of Strahd"
    source: str                # Source identifier
    storyline: str             # "Ravenloft", "Strixhaven"
    level_start: int | None    # Starting level
    level_end: int | None      # Ending level
    group: str                 # "supplement", "other", etc.
    published: str             # ISO date
    chapter_count: int         # Derived from contents[]
    contents: list[dict]       # Raw TOC structure

class StorylineGroup(BaseModel):
    """Group of adventures sharing a storyline."""
    storyline: str
    adventures: list[AdventureIndexEntry]  # Sorted by level_start
    level_range: str           # "1-10" derived
    is_multi_part: bool        # len(adventures) > 1

class AdventureSearchResult(BaseModel):
    """Formatted search result for presentation."""
    storylines: list[StorylineGroup]
    total_matches: int
    query_used: str
```

### Campaign Population Flow

```
load_adventure("SCC-CK", campaign_name="Il Risveglio")
  │
  ├── 1. Download adventure-scc-ck.json (cached)
  ├── 2. Parse → ModuleStructure
  │       ├── chapters[] (all chapters)
  │       ├── npcs[] (all NPCs with chapter context)
  │       ├── encounters[] (all encounters)
  │       ├── locations[] (all locations)
  │       └── read_aloud{} (keyed by section ID)
  │
  ├── 3. Create campaign "Il Risveglio"
  │       ├── setting = adventure intro text
  │       └── description = storyline + level range
  │
  ├── 4. Bind module via CampaignModuleManager
  │       └── ModuleBinding(module_id="SCC-CK", source_id="5etools")
  │
  ├── 5. Index in VectorStore (if ChromaDB available)
  │       └── Chunk chapters → mod_SCC-CK collection
  │
  └── 6. Populate Chapter 1 entities
          ├── create_location() for starting location
          ├── create_npc() for Ch.1 NPCs only
          ├── create_quest() for adventure hook
          └── update_game_state(current_location=...)
```

## Implementation Strategy

### Development Phases

**Phase 1 — Foundation (Tasks 1-2)**: Data models + index download/cache + search. Delivers `discover_adventures` tool. Can be tested independently.

**Phase 2 — Core Parser (Task 3)**: The main engineering effort. Parse 5etools recursive entry format into ModuleStructure. Heavy on the entry-type mapping logic.

**Phase 3 — Integration (Tasks 4-5)**: Wire parser output to campaign creation, module binding, VectorStore. Delivers `load_adventure` tool. End-to-end flow complete.

### Risk Mitigation

| Risk | Mitigation |
|------|-----------|
| 5e.tools mirror goes down (DMCA) | Support local JSON files as alternative source; cache aggressively |
| Adventure JSON format varies across modules | Test parser against multiple adventures (old + new); handle unknown entry types gracefully |
| Large adventures (2.6MB JSON) slow to parse | Lazy loading; parse on demand, not on index |
| ModuleStructure doesn't fit all content | Extend model minimally; store unrecognized entries in metadata dict |

### Testing Approach

- **Unit tests**: Index search, markup stripping, entry parsing for each type
- **Integration test**: Full flow with a small real adventure (SCC-CK ~242KB, smallest Strixhaven)
- **Fixtures**: Cache sample adventure JSON files in `tests/fixtures/adventures/` for offline testing
- **Edge cases**: Empty chapters, missing fields, unknown entry types, adventures without level data

## Tasks Created

- [x] 126.md - Adventure data models and index cache (Size S, 3h, parallel: true)
- [ ] 127.md - Adventure discovery, search, and MCP tool (Size M, 5h, parallel: true, depends: #126)
- [ ] 128.md - Adventure content parser — 5etools entries to ModuleStructure (Size L, 10h, parallel: true, depends: #126)
- [ ] 129.md - Campaign integration, module binding, and load_adventure MCP tool (Size M, 6h, parallel: false, depends: #126, #128)
- [ ] 130.md - Tests and validation with real adventure data (Size M, 5h, parallel: false, depends: #126-#129)

Total tasks: 5
Parallel tasks: 3 (#126, #127, #128 — after #126 completes, #127 and #128 run in parallel)
Sequential tasks: 2 (#129 after parser, #130 after all)
Estimated total effort: 29h

## Dependencies

### Internal (existing, ready to use)

| Component | Location | Usage |
|-----------|----------|-------|
| `ModuleStructure` | `claudmaster/models/module.py` | Target data model (extend with read_aloud) |
| `ModuleBinding` | `claudmaster/module_binding.py` | Bind adventure to campaign |
| `ModuleKeeperAgent` | `claudmaster/agents/module_keeper.py` | RAG consumer (no changes needed) |
| `VectorStore` | `claudmaster/vector_store.py` | Index adventure text (no changes needed) |
| `ModuleIndexer` | `claudmaster/module_indexer.py` | Chunk text for VectorStore |
| `_convert_5etools_markup()` | `rulebooks/sources/fivetools.py` | Markup stripping (extract to shared util) |
| `_render_entries()` | `rulebooks/sources/fivetools.py` | Recursive entry rendering (extract to shared util) |
| Campaign CRUD tools | `main.py` | `create_campaign`, `create_npc`, `create_location`, `create_quest` |

### External

| Dependency | Required? | Notes |
|-----------|-----------|-------|
| 5e.tools GitHub mirror | Yes (or local JSON) | `5etools-mirror-3/5etools-src` |
| `httpx` | Yes | Already in project dependencies |
| ChromaDB + ONNX | No | Graceful degradation — no RAG but everything else works |

## Success Criteria (Technical)

| Criteria | Target |
|----------|--------|
| `discover_adventures` returns results | < 2s (from cache) |
| `load_adventure` creates a ready-to-play campaign | < 30s including download |
| Parser handles all 98 adventures without errors | 100% (graceful on unknown entry types) |
| ModuleKeeper can answer questions about loaded adventure | Verified with Strixhaven SCC-CK |
| System works without ChromaDB installed | Full discovery + parsing, no RAG |
| Markup tags fully stripped from all output | Zero `{@...}` in any user-facing text |

## Estimated Effort

| Task | Size | Estimate |
|------|------|----------|
| Task 1: Data models + index cache | S | ~3h |
| Task 2: Discovery + search + MCP tool | M | ~5h |
| Task 3: Adventure content parser | L | ~10h |
| Task 4: Campaign integration + MCP tool | M | ~6h |
| Task 5: Tests + validation | M | ~5h |
| **Total** | | **~29h** |

**Critical path**: Task 1 → Task 3 → Task 4 (parser is the bottleneck)
**Parallelizable**: Task 2 and Task 3 can run simultaneously after Task 1
