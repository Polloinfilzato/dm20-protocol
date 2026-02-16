---
name: adventure-module-integration
description: Integrate 5e.tools adventure modules into campaign creation with discovery, parsing, and RAG indexing
status: planned
created: 2026-02-16T10:00:00Z
---

# PRD: Adventure Module Integration

## Executive Summary

Enable DM20 Protocol to discover, download, parse, and integrate published D&D adventure modules from the 5e.tools data mirror. Users can search adventures by theme, name, or level range — even without knowing what exists — and bind them to campaigns. The system extracts chapters, NPCs, encounters, locations, and read-aloud text into the existing `ModuleStructure` model, indexes them in the VectorStore for the ModuleKeeper RAG agent, and guides gameplay chapter-by-chapter.

### Key Deliverables

1. **Adventure Discovery Tool** — Search/browse the 5e.tools adventure index by theme, keyword, or level range
2. **Adventure Loader** — Download and parse adventure JSON into `ModuleStructure`
3. **Campaign Binding** — Wire parsed adventure into campaign with ModuleKeeper RAG
4. **Spoiler-Free Presentation** — Present adventure options without revealing plot details

## Problem Statement

### Current State

DM20 Protocol has substantial module infrastructure (`ModuleStructure`, `ModuleBinding`, `ModuleKeeperAgent`, `VectorStore`) but **no way to populate it from published adventures**. The `FiveToolsSource` downloads rulebook data (spells, monsters, classes) but not adventure content. Users must manually create all campaign structure.

### User Scenario

> "I want to play D&D but I don't know which adventure to pick. Is there something set in a magic school? Or maybe a gothic horror campaign? I just want to say what I'm in the mood for and have the system set everything up for me."

### Pain Points

- Users don't know what adventures exist (98 published modules)
- Setting up a campaign from scratch is time-consuming
- The ModuleKeeper agent has no content to work with
- No bridge between 5e.tools adventure data and dm20 module system

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interaction Layer                    │
│                                                              │
│  "What adventures are about undead?"                         │
│  "I want to play Curse of Strahd"                           │
│  "Show me adventures for levels 1-5"                        │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Adventure Discovery                         │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Index Cache   │    │ Theme Search │    │ Spoiler-Free │   │
│  │ adventures.   │───▶│ keyword +    │───▶│ Presentation │   │
│  │ json (cached) │    │ metadata     │    │ (menu)       │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
└──────────────────────┬───────────────────────────────────────┘
                       │ User selects adventure
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Adventure Loader                            │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Download      │    │ 5etools JSON │    │ Module       │   │
│  │ adventure-    │───▶│ Parser       │───▶│ Structure    │   │
│  │ {id}.json     │    │ (entries →   │    │ (chapters,   │   │
│  │              │    │  dm20 model) │    │  NPCs, etc.) │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
└──────────────────────┬───────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                  Campaign Integration                        │
│                                                              │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
│  │ Module       │    │ VectorStore  │    │ Campaign     │   │
│  │ Binding      │    │ Indexing     │    │ Population   │   │
│  │ (campaign ↔  │    │ (ChromaDB    │    │ (NPCs, locs, │   │
│  │  module)     │    │  RAG ready)  │    │  quests)     │   │
│  └──────────────┘    └──────────────┘    └──────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

### Data Flow

```
5e.tools GitHub Mirror
  │
  ├── data/adventures.json          ──▶ AdventureIndex (cached)
  │     (metadata for 98 adventures)      │
  │                                       ▼
  │                                 Discovery/Search
  │                                       │
  │                                       ▼ (user picks one)
  │
  └── data/adventure/adventure-{id}.json ──▶ AdventureParser
        (full chapter content)                  │
                                                ▼
                                          ModuleStructure
                                          ├── chapters[]
                                          ├── npcs[]
                                          ├── encounters[]
                                          ├── locations[]
                                          └── read_aloud{}
                                                │
                                    ┌───────────┼───────────┐
                                    ▼           ▼           ▼
                              ModuleBinding  VectorStore  Campaign
                              (link to       (RAG index)  (populate
                               campaign)                   entities)
```

## User Stories

### US-1: Thematic Discovery

**As a** new player who doesn't know D&D adventures,
**I want to** describe the kind of story I'm in the mood for,
**So that** the system suggests matching adventures without spoilers.

**Acceptance Criteria:**
- User can ask open-ended questions: "something with vampires", "a dungeon crawl", "political intrigue"
- System searches adventure index by storyline, name, and level metadata
- Results are presented as a concise, spoiler-free menu with: name, theme, level range, number of chapters
- No plot details, twists, or NPC secrets are revealed

### US-2: Direct Adventure Selection

**As a** player who knows which adventure they want,
**I want to** say the adventure name and have it loaded,
**So that** I can start playing immediately.

**Acceptance Criteria:**
- User can specify by name ("Curse of Strahd"), ID ("CoS"), or partial match ("strahd")
- If exact match: proceed directly to loading
- If multiple matches: present disambiguation menu

### US-3: Multi-Part Adventure Selection

**As a** player choosing an anthology or multi-part adventure (e.g., Strixhaven),
**I want to** see the sub-adventures listed with spoiler-free descriptions,
**So that** I can choose where to start (or play them in order).

**Acceptance Criteria:**
- System detects when a storyline contains multiple linked adventures
- Presents them in chronological/suggested order
- Shows level range for each part
- Recommends starting from Part 1 for new players

### US-4: Campaign Creation from Adventure

**As a** player who has selected an adventure,
**I want to** have a campaign automatically created and populated,
**So that** the world is ready with NPCs, locations, and quests from Chapter 1.

**Acceptance Criteria:**
- Campaign is created with adventure name and setting description
- Starting location is created from Chapter 1 data
- Key NPCs from Chapter 1 are created (not future chapters — no spoilers)
- Initial quest is created from adventure hook
- ModuleKeeper is loaded with full adventure for RAG queries
- Game state is set to starting location

### US-5: Adventure Browsing by Level

**As a** DM planning for a specific party level,
**I want to** filter adventures by level range,
**So that** I find appropriate challenges for my group.

**Acceptance Criteria:**
- User can specify: "adventures for level 3", "tier 2 adventures", "levels 5-10"
- System filters by `level.start` and `level.end` fields
- Results sorted by relevance to requested level

## Functional Requirements

| ID | Requirement | Priority |
|----|------------|----------|
| FR-1 | Download and cache `adventures.json` index from 5e.tools mirror | Must |
| FR-2 | Search adventures by keyword matching on name, storyline, and group | Must |
| FR-3 | Filter adventures by level range | Must |
| FR-4 | Present adventure results in spoiler-free format (name, theme, levels, chapter count) | Must |
| FR-5 | Detect and present multi-part adventures as grouped options | Must |
| FR-6 | Download individual adventure JSON files on demand | Must |
| FR-7 | Parse 5e.tools adventure entry format into `ModuleStructure` | Must |
| FR-8 | Extract chapters with hierarchical section structure | Must |
| FR-9 | Extract NPC references with location and chapter context | Must |
| FR-10 | Extract encounter references with type and difficulty | Must |
| FR-11 | Extract location references with hierarchy | Must |
| FR-12 | Extract read-aloud text (`insetReadaloud` entries) | Must |
| FR-13 | Strip 5e.tools markup tags (`{@creature ...}`, `{@spell ...}`, etc.) | Must |
| FR-14 | Bind parsed module to campaign via `ModuleBinding` | Must |
| FR-15 | Index module content in VectorStore for ModuleKeeper RAG | Should |
| FR-16 | Auto-populate campaign with Chapter 1 NPCs, locations, starting quest | Should |
| FR-17 | Cache downloaded adventure JSON locally to avoid re-downloads | Must |
| FR-18 | Support `--offline` mode using cached data | Nice |
| FR-19 | Expose as MCP tools: `discover_adventures`, `load_adventure` | Must |
| FR-20 | Integrate with `start_claudmaster_session(module_id=...)` | Should |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|------------|--------|
| NFR-1 | Adventure index download < 5 seconds | Performance |
| NFR-2 | Individual adventure download < 10 seconds | Performance |
| NFR-3 | Parsing adventure → ModuleStructure < 3 seconds | Performance |
| NFR-4 | VectorStore indexing < 30 seconds per adventure | Performance |
| NFR-5 | Cache invalidation after 7 days (configurable) | Maintainability |
| NFR-6 | Graceful degradation without ChromaDB (no RAG, but parsing still works) | Reliability |
| NFR-7 | No spoiler content in discovery/menu presentation | UX |
| NFR-8 | 5e.tools markup fully stripped from all output text | Data Quality |

## Success Criteria

1. User can ask "what adventures involve dragons?" and get a relevant, spoiler-free list
2. User can select an adventure and have a campaign auto-created in < 30 seconds
3. ModuleKeeper can answer questions about the loaded adventure during gameplay
4. Multi-part adventures (Strixhaven, Tales from the Yawning Portal) are handled correctly
5. System works without ChromaDB (reduced functionality but no errors)

## Constraints and Assumptions

### Constraints

- **Data Source Stability**: 5e.tools mirror (`5etools-mirror-3`) may be DMCA'd. The system should support alternative mirrors or local JSON files as fallback.
- **Copyright**: Adventure content is copyrighted by Wizards of the Coast. The system downloads data for personal use, same as the existing `FiveToolsSource` for rulebooks.
- **No Images/Maps**: Map images are large and not needed for text-based gameplay. Only text content is parsed.

### Assumptions

- The 5e.tools JSON format for adventures remains stable
- Users have internet access for initial download (cached afterward)
- The existing `ModuleStructure` model is sufficient for most adventure content (may need minor extensions)
- The 5e.tools entry markup system (`{@tag ...}`) is consistent across all adventures

## Out of Scope

- **Map rendering**: Visual maps are not supported in text-based MCP
- **Homebrew adventure support**: Only official 5e.tools content in v1
- **Adventure progression tracking UI**: The `ModuleProgress` model exists but detailed chapter-by-chapter tracking UI is a separate feature
- **Multiple concurrent modules**: One module per campaign for v1
- **Encounter balancing/scaling**: Use adventure encounters as-is, no auto-scaling

## Dependencies

### Internal Dependencies

| Component | Dependency Type | Notes |
|-----------|----------------|-------|
| `ModuleStructure` model | Extends | May need minor field additions for read-aloud text |
| `ModuleBinding` | Uses as-is | Bind adventure to campaign |
| `ModuleKeeperAgent` | Uses as-is | RAG queries over adventure content |
| `VectorStore` | Uses as-is | Index adventure text chunks |
| `FiveToolsSource` | Pattern reference | Reuse download/cache/retry patterns |
| `5etools markup stripper` | Reuse | Already exists in `fivetools.py` for spell/monster descriptions |

### External Dependencies

| Dependency | Purpose | Required? |
|-----------|---------|-----------|
| 5e.tools GitHub mirror | Adventure data source | Yes (or local JSON) |
| ChromaDB + ONNX | VectorStore for RAG | No (graceful degradation) |
| `httpx` / `aiohttp` | Async HTTP downloads | Yes (already in project) |

## Technical Notes

### 5e.tools Adventure JSON Structure

**Index** (`adventures.json`):
```json
{
  "adventure": [
    {
      "name": "Strixhaven: Campus Kerfuffle",
      "id": "SCC-CK",
      "source": "SCC",
      "storyline": "Strixhaven",
      "level": {"start": 1, "end": 4},
      "published": "2021-12-07",
      "contents": [{"name": "Chapter 1: ...", "headers": [...]}]
    }
  ]
}
```

**Content** (`adventure/adventure-scc-ck.json`):
```json
{
  "data": [
    {
      "type": "section",
      "name": "Chapter Title",
      "page": 1,
      "id": "001",
      "entries": [
        "Narrative paragraph with {@creature goblin} references...",
        {"type": "insetReadaloud", "entries": ["Read this aloud to players..."]},
        {"type": "entries", "name": "Location Name", "entries": [...]},
        {"type": "table", "caption": "Random Encounters", "rows": [...]}
      ]
    }
  ]
}
```

### Key Entry Types to Parse

| 5e.tools Type | dm20 Mapping | Priority |
|--------------|-------------|----------|
| `section` | `ModuleElement` (chapter) | Must |
| `entries` | `ModuleElement` (subsection) | Must |
| `insetReadaloud` | Read-aloud text field | Must |
| `inset` | DM notes/tips | Should |
| `table` | Structured data (encounters, loot) | Should |
| `statblock` / `statblockInline` | Creature reference | Should |
| `image` (maps) | Skip (text-only) | Out of scope |
| `gallery` | Skip | Out of scope |
| `flowchart` | Skip | Out of scope |

### Markup Tags to Strip

Reuse/extend the existing `_strip_5etools_tags()` from `fivetools.py`:

| Tag | Conversion |
|-----|-----------|
| `{@creature Name\|Source}` | → `Name` |
| `{@spell name}` | → `name` |
| `{@item name}` | → `name` |
| `{@dc N}` | → `DC N` |
| `{@dice expr}` | → `expr` |
| `{@damage expr}` | → `expr` |
| `{@skill name}` | → `name` |
| `{@area Name\|ID}` | → `Name` |
| `{@b text}` | → `text` |
| `{@i text}` | → `text` |
| `{@condition name}` | → `name` |
| `{@sense name}` | → `name` |

### Multi-Part Adventure Detection

Adventures sharing the same `storyline` field are grouped:

```python
# Group by storyline
storylines = defaultdict(list)
for adv in index["adventure"]:
    storylines[adv["storyline"]].append(adv)

# Multi-part if > 1 adventure in same storyline
# Sort by level.start for chronological order
```

Storylines with notable multi-part structures:
- **Strixhaven**: 4 adventures (SCC-CK, SCC-HfMT, SCC-TMM, SCC-ARiR)
- **Tales from the Yawning Portal**: 7 classic dungeons
- **Tyranny of Dragons**: 2 adventures (HotDQ, RoT)
- **Ghosts of Saltmarsh**: 7 adventures
- **Keys from the Golden Vault**: 13 heists

### New MCP Tools

```python
# Tool 1: Discovery
@tool
async def discover_adventures(
    query: str = "",           # "vampires", "school", "dungeon crawl"
    level_min: int | None,     # Filter by minimum level
    level_max: int | None,     # Filter by maximum level
    storyline: str | None,     # Filter by storyline name
    limit: int = 10,           # Max results
) -> str:
    """Search and browse available D&D adventure modules."""

# Tool 2: Load
@tool
async def load_adventure(
    adventure_id: str,         # "CoS", "SCC-CK", etc.
    campaign_name: str | None, # Auto-create campaign if provided
    populate_chapter_1: bool = True,  # Auto-create starting NPCs/locations
) -> str:
    """Download, parse, and bind an adventure module to a campaign."""
```

### File Structure

```
src/dm20_protocol/
├── adventures/
│   ├── __init__.py
│   ├── index.py           # AdventureIndex — download, cache, search
│   ├── parser.py          # AdventureParser — 5etools JSON → ModuleStructure
│   ├── discovery.py       # Discovery logic — theme search, spoiler-free presentation
│   └── campaign_setup.py  # Auto-populate campaign from Chapter 1
├── rulebooks/sources/
│   └── fivetools.py       # (existing — reuse download/markup patterns)
└── claudmaster/
    └── models/
        └── module.py      # (existing — may extend with read_aloud field)
```

## References

- [5e.tools adventure page](https://5e.tools/adventure.html) — Web interface for browsing adventures
- [5etools-mirror-3/5etools-src](https://github.com/5etools-mirror-3/5etools-src) — GitHub data mirror
- [5etools JSON schema](https://github.com/TheGiddyLimit/5etools-utils/tree/master/schema/brew-fast) — Official schema definitions
- Existing `FiveToolsSource` at `src/dm20_protocol/rulebooks/sources/fivetools.py` — Pattern reference
- Existing `ModuleStructure` at `src/dm20_protocol/claudmaster/models/module.py` — Target data model
- Existing `ModuleKeeperAgent` at `src/dm20_protocol/claudmaster/agents/module_keeper.py` — RAG consumer

## Appendix

### Adventure Storyline Categories (sample)

| Storyline | Adventures | Level Range | Theme |
|-----------|-----------|-------------|-------|
| Starter Set | 2 | 1-5 | Introductory |
| Tyranny of Dragons | 2 | 1-15 | Dragon cult |
| Elemental Evil | 1 | 1-15 | Elemental cults |
| Ravenloft | 1 | 1-10 | Gothic horror |
| Strixhaven | 4 | 1-10 | Magic school |
| Spelljammer | 1 | 5-8 | Space fantasy |
| Dragonlance | 1 | 1-11 | War / dragons |
| Planescape | 1 | 3-10 | Multiverse |
| Vecna | 1 | 10-20 | Cosmic threat |
| Keys from the Golden Vault | 13 | 1-11 | Heists |
| Tales from the Yawning Portal | 7 | 1-15 | Classic dungeons |

### Spoiler-Free Presentation Format

```
╔═══════════════════════════════════════════════════╗
║  📚 STRIXHAVEN — Magic School Adventures         ║
║  Levels 1-10 · 4 linked adventures               ║
╠═══════════════════════════════════════════════════╣
║                                                   ║
║  1) Campus Kerfuffle (Lv 1-4)                    ║
║     Your first year at Strixhaven University.     ║
║     New friendships, rivalries, and strange        ║
║     events on campus.                              ║
║                                                   ║
║  2) Hunt for Mage Tower (Lv 4-6)                 ║
║     Second year. A student competition leads       ║
║     to unexpected discoveries.                     ║
║                                                   ║
║  3) The Magister's Masquerade (Lv 6-8)           ║
║     Third year. A grand social event hides         ║
║     growing dangers.                               ║
║                                                   ║
║  4) A Reckoning in Ruins (Lv 8-10)               ║
║     Final year. Everything comes to a head.        ║
║                                                   ║
║  ⭐ Recommended: Start with #1 for the full arc   ║
╚═══════════════════════════════════════════════════╝
```
