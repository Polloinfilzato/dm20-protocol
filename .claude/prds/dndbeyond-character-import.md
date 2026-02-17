---
name: dndbeyond-character-import
description: Import D&D Beyond characters into dm20 campaigns via URL fetch or local JSON file, with automatic mapping from DDB's proprietary format to dm20's Character model
status: draft
created: 2026-02-17T18:00:00Z
---

# PRD: D&D Beyond Character Import

## Executive Summary

Players who already manage characters on D&D Beyond should be able to bring them into dm20-protocol without manually re-entering stats. This feature provides a **one-shot import** that fetches a public character's JSON data from D&D Beyond's character service endpoint and maps it to dm20's `Character` model, with a **local file fallback** for when the endpoint is unreachable or the character is private.

**Key deliverables:**

1. **URL/ID Import** — Paste a D&D Beyond character URL or numeric ID; dm20 fetches the JSON and creates a fully populated Character in the current campaign.
2. **Local JSON File Import** — Import from a `.json` file saved from D&D Beyond (via browser dev tools or bookmarklet), as a robust fallback.
3. **DDB-to-dm20 Mapper** — A dedicated mapping layer that translates D&D Beyond's proprietary, raw-value JSON format into dm20's computed `Character` model.

**Value proposition:** Players with existing D&D Beyond characters can start playing in dm20 within seconds, without re-entering ability scores, spells, inventory, and features by hand. The import is one-shot — once imported, the character lives entirely in dm20.

## Problem Statement

### Current State

```
Character creation today:
├── Manual creation via create_character tool    ✅ Works but tedious for existing characters
├── Rulebook-powered auto-population             ✅ CharacterBuilder fills from SRD/rulebooks
├── Import from external services                ❌ No integration with any external platform
├── Import from file                             ❌ No character file import (packs are world-content only)
└── D&D Beyond integration                       ❌ Not supported
```

### Pain Points

1. **Double data entry** — A player who has a level 8 character on D&D Beyond must manually re-enter ~50+ data points (6 ability scores, 15+ skill proficiencies, 20+ inventory items, 10+ spells, features, etc.) to recreate the character in dm20.

2. **Error-prone manual transfer** — Copying stats by hand leads to mistakes: wrong modifier calculations, missed proficiencies, forgotten features. The character in dm20 may not match the "real" character on D&D Beyond.

3. **Friction to adoption** — Players already invested in D&D Beyond are reluctant to try dm20 if it means rebuilding their characters from scratch.

### Target Users

- **Existing D&D Beyond player** who wants to use dm20 for AI-assisted sessions with their current character
- **DM** who wants to quickly import a player's character for a one-shot or campaign
- **Group** transitioning from traditional play (with DDB character sheets) to dm20-assisted sessions

## Architecture Overview

```
┌──────────────────────────────────────────────────────────┐
│                  DDB Import Pipeline                      │
│                                                           │
│  ┌─────────────┐     ┌─────────────┐     ┌────────────┐ │
│  │ Input       │     │ DDB JSON    │     │ dm20       │ │
│  │ Handler     │────▶│ Mapper      │────▶│ Character  │ │
│  │             │     │             │     │ Builder    │ │
│  └─────────────┘     └─────────────┘     └────────────┘ │
│        │                    │                    │        │
│   URL or File         Raw DDB JSON          Character    │
│   → fetch/read        → parse & map         → campaign   │
└──────────────────────────────────────────────────────────┘

Input flows:

  Flow A (URL):
    User provides URL/ID
    │
    ├─ Extract numeric ID from URL
    ├─ GET character-service.dndbeyond.com/character/v5/character/{id}
    ├─ Validate response (200, has expected fields)
    └─ Pass JSON to Mapper

  Flow B (File):
    User provides file path
    │
    ├─ Read JSON file from disk
    ├─ Validate structure (detect DDB format)
    └─ Pass JSON to Mapper

  Mapper:
    Raw DDB JSON
    │
    ├─ Extract identity (name, race, class, background, alignment)
    ├─ Map ability scores (DDB stats array → dm20 abilities dict)
    ├─ Calculate combat stats (HP, AC, proficiency bonus)
    ├─ Map proficiencies (skills, saves, tools, languages)
    ├─ Map inventory (DDB items → dm20 Item objects)
    ├─ Map spells (DDB spells → dm20 Spell objects)
    ├─ Map features (class/race features → dm20 Feature objects)
    └─ Construct Character model
```

## User Stories

### US-1: Import public character from URL
**As a** player with a public D&D Beyond character,
**I want to** paste my character's URL and have it imported into my dm20 campaign,
**So that** I can start playing immediately without manual data entry.

**Acceptance Criteria:**
- User provides a DDB URL (e.g., `https://www.dndbeyond.com/characters/12345678`) or numeric ID
- System fetches the character JSON from DDB's character service endpoint
- All mapped fields are correctly populated in the new dm20 Character
- Character is added to the current campaign
- User receives a summary of what was imported and any unmapped fields

### US-2: Import character from local JSON file
**As a** player whose character is private on D&D Beyond (or when the endpoint is down),
**I want to** import my character from a JSON file I saved from my browser,
**So that** I have a reliable fallback that doesn't depend on DDB's endpoint availability.

**Acceptance Criteria:**
- User provides a path to a `.json` file containing DDB character data
- System validates the JSON structure matches DDB format
- Same mapping pipeline is used as URL import
- Character is added to the current campaign
- Clear error message if the JSON format is unrecognized

### US-3: Import summary with warnings
**As a** player importing a character,
**I want to** see a summary of what was imported and what couldn't be mapped,
**So that** I know if any manual adjustments are needed.

**Acceptance Criteria:**
- After import, system reports: mapped fields count, unmapped/skipped fields, warnings
- Warnings for: homebrew content not in SRD, custom items without full stats, features that couldn't be resolved
- Character is created even with partial mapping — better to have 80% than nothing

## Functional Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-1 | Parse DDB character URL to extract numeric character ID | Must |
| FR-2 | Fetch character JSON from `character-service.dndbeyond.com/character/v5/character/{id}` using httpx | Must |
| FR-3 | Read and validate DDB character JSON from local file | Must |
| FR-4 | Map DDB `name`, `race`, `classes`, `background` to dm20 identity fields | Must |
| FR-5 | Map DDB `stats` array (6 objects with `id` and `value`) to dm20 `abilities` dict | Must |
| FR-6 | Map DDB `baseHitPoints` + constitution modifier to dm20 HP fields | Must |
| FR-7 | Map DDB `classes` array to dm20 `CharacterClass` (primary class) | Must |
| FR-8 | Calculate proficiency bonus from character level | Must |
| FR-9 | Map DDB skill/save proficiencies from `modifiers` section | Must |
| FR-10 | Map DDB `inventory` to dm20 `Item` objects with type classification | Should |
| FR-11 | Map DDB `spells` to dm20 `Spell` objects (name, level, school) | Should |
| FR-12 | Map DDB class/race features to dm20 `Feature` objects | Should |
| FR-13 | Map DDB `currencies` to a note or inventory entry | Could |
| FR-14 | Map equipped items to dm20 `equipment` slots | Should |
| FR-15 | Generate import summary with mapped/unmapped/warning counts | Must |
| FR-16 | Handle multiclass characters (use highest-level class as primary) | Should |
| FR-17 | Expose as MCP tool `import_from_dndbeyond(url_or_id, player_name?)` | Must |
| FR-18 | Expose as MCP tool `import_character_file(file_path, source_format?, player_name?)` | Must |
| FR-19 | Handle HTTP errors gracefully (404=not found, 403=private, timeout, etc.) | Must |

## Non-Functional Requirements

| ID | Requirement | Target |
|----|-------------|--------|
| NFR-1 | Import completes in < 5 seconds for URL fetch | Performance |
| NFR-2 | No D&D Beyond authentication required (public characters only for URL) | Simplicity |
| NFR-3 | Mapper is isolated from fetch logic (testable independently) | Testability |
| NFR-4 | DDB JSON format changes should only require mapper updates, not pipeline changes | Maintainability |
| NFR-5 | httpx (already a dependency) used for HTTP requests | Dependency |
| NFR-6 | Graceful degradation — partial import is better than failure | Reliability |

## Technical Design

### Module Structure

```
src/dm20_protocol/
└── importers/
    ├── __init__.py          # Public API: import_from_dndbeyond, import_from_file
    ├── dndbeyond/
    │   ├── __init__.py
    │   ├── fetcher.py       # HTTP fetch logic (URL parsing, GET request)
    │   ├── mapper.py        # DDB JSON → dm20 Character mapping
    │   └── schema.py        # DDB JSON field constants and type hints
    └── base.py              # ImportResult model, shared utilities
```

### DDB JSON Structure (Key Fields to Map)

The DDB character JSON (v5) contains these relevant top-level fields:

```python
# Identity
ddb["name"]                          → Character.name
ddb["race"]["fullName"]              → Race.name
ddb["race"]["baseName"]              → Race.name (fallback)
ddb["race"]["subRaceShortName"]      → Race.subrace
ddb["classes"][0]["definition"]["name"]  → CharacterClass.name
ddb["classes"][0]["level"]           → CharacterClass.level
ddb["classes"][0]["subclassDefinition"]["name"]  → CharacterClass.subclass
ddb["background"]["definition"]["name"]  → Character.background
ddb["alignmentId"]                   → Character.alignment (lookup table)

# Ability Scores
ddb["stats"]  # Array of 6 objects: [{"id": 1, "value": 16}, ...]
# id mapping: 1=STR, 2=DEX, 3=CON, 4=INT, 5=WIS, 6=CHA
# Note: These are BASE scores. Racial bonuses and ASIs are in ddb["modifiers"]
# and ddb["bonusStats"] — must be summed for final values.

# HP
ddb["baseHitPoints"]                 → base HP (before CON modifier per level)
ddb["bonusHitPoints"]                → extra HP from items/feats
# Final HP = baseHitPoints + bonusHitPoints + (CON_mod × level)
# Current HP needs: overrideHitPoints or baseHitPoints - removedHitPoints

# Inventory
ddb["inventory"]  # Array of item objects with:
#   "definition" → {"name", "description", "filterType", "weight", "cost"}
#   "equipped" → bool
#   "quantity" → int

# Spells
ddb["classSpells"]  # Array per class with spell lists
ddb["spells"]["class"]  # Alternative path
# Each spell has: "definition" → {"name", "level", "school", "castingTime", ...}

# Features
ddb["classes"][*]["classFeatures"]  # Class features with level
ddb["race"]["racialTraits"]         # Racial traits
ddb["feats"]                        # Feats

# Proficiencies
ddb["modifiers"]  # Complex section with racial, class, item modifiers
# Filter by type "proficiency" and subType for skills/saves/tools

# Other
ddb["currencies"]                    → gold, silver, copper, etc.
ddb["notes"]                         → Character notes sections
ddb["traits"]                        → personality, ideals, bonds, flaws
```

### Import Result Model

```python
@dataclass
class DDBImportResult:
    character: Character              # The created character
    mapped_fields: list[str]          # Successfully mapped field names
    unmapped_fields: list[str]        # Fields that couldn't be mapped
    warnings: list[str]              # Non-fatal issues (homebrew, unknown items)
    source: str                       # "url" or "file"
    ddb_character_id: int | None     # Original DDB ID for reference
```

### Ability Score Calculation

DDB stores ability scores across multiple locations that must be summed:

```
Final Score = base (stats[]) + racial bonus (modifiers.race)
            + ASI bonus (modifiers.class) + bonus (bonusStats[])
            + item bonus (modifiers.item) + feat bonus (modifiers.feat)
```

The mapper must:
1. Start with base scores from `stats[]`
2. Add racial modifiers from `modifiers.race` where `type == "bonus"` and `entityId` matches stat ID
3. Add class modifiers (ASIs) from `modifiers.class`
4. Add bonus stats from `bonusStats[]` (manual overrides)
5. Check for `overrideStats[]` (full overrides, e.g., headband of intellect)

## Dependencies

| Dependency | Type | Status |
|------------|------|--------|
| `httpx` | Python package | Already in pyproject.toml |
| `pydantic` | Python package | Already in pyproject.toml |
| D&D Beyond character service endpoint | External API | Undocumented, may change |
| dm20 `Character` model | Internal | Stable |
| dm20 `storage.py` | Internal | Stable — for adding character to campaign |

## Implementation Order

### Phase 1: Core Import Pipeline (Must Have)

1. **Module scaffolding** — Create `importers/` directory structure with base classes
2. **DDB Fetcher** — URL parsing + httpx GET for public characters
3. **DDB Mapper (Identity + Stats)** — Map name, race, class, abilities, HP, AC
4. **DDB Mapper (Proficiencies)** — Map skill/save/tool proficiencies and languages
5. **File import handler** — Read and validate local JSON files
6. **MCP tool integration** — Register `import_from_dndbeyond` and `import_character_file` tools
7. **Import summary** — Generate and return mapped/unmapped/warning report

### Phase 2: Extended Mapping (Should Have)

8. **Inventory mapper** — Map DDB items to dm20 Item objects
9. **Spell mapper** — Map DDB spells to dm20 Spell objects
10. **Feature mapper** — Map class/race features to dm20 Feature objects
11. **Equipment slot mapper** — Detect equipped items and assign to dm20 equipment slots

### Phase 3: Polish (Could Have)

12. **Multiclass support** — Handle multiple classes, pick primary by highest level
13. **Currency mapping** — Map DDB currencies to inventory or notes
14. **Character notes** — Map DDB traits (personality, ideals, bonds, flaws) to bio/notes
15. **Documentation** — Update README and GUIDE with import instructions

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| DDB endpoint changes or breaks | URL import stops working | File import fallback; mapper is isolated for easy updates |
| DDB JSON schema changes | Mapper produces incorrect values | Version detection in schema.py; comprehensive test fixtures with real DDB JSON |
| Homebrew content not mappable | Partial import for custom content | Warnings in import result; character still created with available data |
| Rate limiting by DDB | Repeated imports may be throttled | Single-request design (one fetch per import); no polling or batch operations |
| Character is private | 403 response from endpoint | Clear error message suggesting file import as alternative |

## Out of Scope

- **Live sync with D&D Beyond** — This is one-shot import only. No polling, no write-back.
- **Authentication with DDB** — Only public characters via URL. Private characters use file fallback.
- **DDB campaign import** — Only individual characters, not full DDB campaigns.
- **Export to DDB format** — One-way import only (DDB → dm20).
- **Other platforms** — No Roll20, Fantasy Grounds, or Foundry VTT import (future PRDs).
