---
name: rulebook-system
description: Add rulebook management system for loading D&D 5e SRD, Open5e content, and custom homebrew rules
status: backlog
created: 2026-02-02T03:42:01Z
---

# PRD: Rulebook Management System

## Executive Summary

This PRD defines a comprehensive rulebook management system that enables gamemaster-mcp to load, manage, and enforce TTRPG rules from multiple sources.

**Key deliverables:**
1. **Rulebook Manager** — Core system to load and manage rulebooks from multiple sources
2. **SRD Integration** — Native integration with D&D 5e SRD API for official content
3. **Open5e Integration** — Optional integration for expanded OGL content
4. **Custom Rulebook Support** — Load homebrew content from local JSON/YAML files
5. **Character Validation** — Validate characters against loaded rulebooks
6. **Dynamic Content Tools** — MCP tools to search, query, and apply rules

**Value proposition:** Transform gamemaster-mcp from a campaign data manager into a rules-aware game engine that can validate characters, suggest level-up options, and provide accurate rule references during play.

## Problem Statement

### Current State

The gamemaster-mcp stores character data but has no knowledge of game rules:

```python
# Current: Just stores strings, no validation
character_class = CharacterClass(name="Wizard", level=5, subclass="Bladesinger")
# ❌ No way to know if "Bladesinger" is a valid subclass
# ❌ No way to know what features a level 5 Wizard should have
# ❌ No way to validate ability score assignments
```

### Problems

1. **No Rule Enforcement:** Characters can have invalid combinations (e.g., Barbarian with 8 STR)
2. **No Content Library:** DM must manually type all spell descriptions, feat effects, etc.
3. **No Level-Up Guidance:** System cannot suggest class features for new levels
4. **Manual Data Entry:** Every race trait, class feature must be typed manually
5. **No Consistency:** Same spell might be described differently across characters
6. **Limited AI Context:** LLM has no structured rules to reference during play

### Why Now?

- Project has stable storage architecture (split files, TOON encoding)
- Excellent external APIs exist (5e-srd-api, Open5e)
- Community demand for rules-aware game masters
- Competing project (mnehmos.rpg.mcp) demonstrates viability of rules engine approach

### Inspiration: mnehmos.rpg.mcp

The mnehmos.rpg.mcp project demonstrates a rules-enforced approach where:
- LLMs propose intentions; the engine validates and executes
- Anti-hallucination validation prevents casting unlearned spells
- 1,100+ creature templates with presets
- Mathematical integrity preserved while maintaining narrative freedom

This PRD aims to bring similar capabilities to gamemaster-mcp in a modular, extensible way.

## User Stories

### US-1: DM Loading Official Rules

**As a** Dungeon Master
**I want** to load the D&D 5e SRD into my campaign
**So that** I have access to official classes, races, spells, and monsters

**Acceptance Criteria:**
- [ ] Tool to load SRD rulebook into campaign
- [ ] SRD data cached locally after first fetch
- [ ] Classes, races, spells, monsters available for query
- [ ] Campaign tracks which rulebooks are active

### US-2: DM Adding Homebrew Content

**As a** Dungeon Master
**I want** to add my custom races, classes, and items
**So that** my homebrew content integrates with official rules

**Acceptance Criteria:**
- [ ] Support loading custom JSON/YAML rulebook files
- [ ] Custom content follows same schema as SRD content
- [ ] Can override or extend official content
- [ ] Custom content persists with campaign

### US-3: DM Validating a Character

**As a** Dungeon Master
**I want** to validate a character against loaded rules
**So that** I can ensure characters are rules-legal

**Acceptance Criteria:**
- [ ] Validate ability scores meet minimums (e.g., multiclass requirements)
- [ ] Validate class/subclass combinations exist in rulebooks
- [ ] Validate race/subrace combinations exist
- [ ] Report missing or extra proficiencies
- [ ] Suggest corrections for invalid configurations

### US-4: DM Leveling Up a Character

**As a** Dungeon Master
**I want** to see what features a character gains at a new level
**So that** I can apply them correctly

**Acceptance Criteria:**
- [ ] Query available class features for a level
- [ ] Show spell slots progression
- [ ] Show ability score improvements / feat opportunities
- [ ] Optionally auto-apply mandatory features

### US-5: AI Agent Querying Rules

**As an** AI agent (LLM)
**I want** to query spell details, monster stats, and class features
**So that** I can accurately describe effects during play

**Acceptance Criteria:**
- [ ] Search spells by name, level, school, class
- [ ] Search monsters by name, CR, type
- [ ] Get full details for any rule element
- [ ] Results in TOON format for token efficiency

### US-6: DM Using Expanded Content

**As a** Dungeon Master
**I want** to optionally load Open5e content
**So that** I have access to more monsters and spells

**Acceptance Criteria:**
- [ ] Open5e integration as separate optional rulebook
- [ ] Clear indication of content source (SRD vs Open5e vs Custom)
- [ ] Can enable/disable per campaign

## Requirements

### Functional Requirements

#### FR-1: Rulebook Manager Core

| ID | Requirement |
|----|-------------|
| FR-1.1 | Create RulebookManager class to manage loaded rulebooks |
| FR-1.2 | Support multiple rulebooks per campaign |
| FR-1.3 | Track rulebook source (srd, open5e, custom) |
| FR-1.4 | Store rulebook manifest in campaign directory |
| FR-1.5 | Lazy-load rulebook content on first access |
| FR-1.6 | Provide unified query interface across all loaded rulebooks |
| FR-1.7 | Handle content conflicts (custom overrides official) |

#### FR-2: Data Models

| ID | Requirement |
|----|-------------|
| FR-2.1 | Create Rulebook model with metadata |
| FR-2.2 | Create ClassDefinition model with features per level |
| FR-2.3 | Create SubclassDefinition model with features |
| FR-2.4 | Create RaceDefinition model with traits and ability bonuses |
| FR-2.5 | Create SubraceDefinition model |
| FR-2.6 | Create Feat model with prerequisites and effects |
| FR-2.7 | Create Background model with proficiencies and features |
| FR-2.8 | Create SpellDefinition model (extended from existing Spell) |
| FR-2.9 | Create MonsterDefinition model with full stat block |
| FR-2.10 | Create ItemDefinition model with properties |

#### FR-3: SRD Integration

| ID | Requirement |
|----|-------------|
| FR-3.1 | Implement SRD API client (5e-srd-api) |
| FR-3.2 | Fetch and cache class data |
| FR-3.3 | Fetch and cache race data |
| FR-3.4 | Fetch and cache spell data |
| FR-3.5 | Fetch and cache monster data |
| FR-3.6 | Fetch and cache equipment data |
| FR-3.7 | Support both 2014 and 2024 SRD versions |
| FR-3.8 | Handle API rate limits gracefully |
| FR-3.9 | Work offline with cached data |

#### FR-4: Open5e Integration (Optional)

| ID | Requirement |
|----|-------------|
| FR-4.1 | Implement Open5e API client |
| FR-4.2 | Tag all content with source attribution |
| FR-4.3 | Support filtering by source book |
| FR-4.4 | Merge with SRD content without duplicates |

#### FR-5: Custom Rulebook Support

| ID | Requirement |
|----|-------------|
| FR-5.1 | Define JSON schema for custom rulebooks |
| FR-5.2 | Support YAML as alternative format |
| FR-5.3 | Validate custom content against schema |
| FR-5.4 | Support partial rulebooks (e.g., only custom races) |
| FR-5.5 | Store custom rulebooks in campaign directory |

#### FR-6: Character Validation

| ID | Requirement |
|----|-------------|
| FR-6.1 | Validate class exists in loaded rulebooks |
| FR-6.2 | Validate subclass is valid for class |
| FR-6.3 | Validate race exists in loaded rulebooks |
| FR-6.4 | Validate subrace is valid for race |
| FR-6.5 | Validate ability scores meet multiclass requirements |
| FR-6.6 | Validate proficiency selections are legal |
| FR-6.7 | Check for missing class features |
| FR-6.8 | Return detailed validation report |
| FR-6.9 | Suggest fixes for validation errors |

#### FR-7: MCP Tools

| ID | Requirement |
|----|-------------|
| FR-7.1 | `load_rulebook` — Load SRD, Open5e, or custom rulebook |
| FR-7.2 | `list_rulebooks` — List active rulebooks in campaign |
| FR-7.3 | `unload_rulebook` — Remove a rulebook from campaign |
| FR-7.4 | `search_rules` — Search across all loaded content |
| FR-7.5 | `get_class` — Get full class definition with all levels |
| FR-7.6 | `get_race` — Get full race definition with traits |
| FR-7.7 | `get_spell` — Get spell details |
| FR-7.8 | `get_monster` — Get monster stat block |
| FR-7.9 | `get_feat` — Get feat details |
| FR-7.10 | `get_background` — Get background details |
| FR-7.11 | `validate_character` — Validate character against rules |
| FR-7.12 | `get_level_features` — Get features for class at level |
| FR-7.13 | `apply_level_up` — Apply level-up to character with features |

### Non-Functional Requirements

#### NFR-1: Performance

| ID | Requirement |
|----|-------------|
| NFR-1.1 | Initial SRD load < 30 seconds (first time, with network) |
| NFR-1.2 | Cached rulebook load < 500ms |
| NFR-1.3 | Rule query response < 100ms |
| NFR-1.4 | Character validation < 500ms |

#### NFR-2: Reliability

| ID | Requirement |
|----|-------------|
| NFR-2.1 | Graceful degradation if API unavailable |
| NFR-2.2 | Offline mode with cached data |
| NFR-2.3 | Validation errors are warnings, not blocks |
| NFR-2.4 | Corrupted cache auto-rebuilds |

#### NFR-3: Compatibility

| ID | Requirement |
|----|-------------|
| NFR-3.1 | All existing tools work without rulebooks loaded |
| NFR-3.2 | Rulebook features are opt-in |
| NFR-3.3 | No breaking changes to existing models |
| NFR-3.4 | Support campaigns with no rulebooks |

#### NFR-4: Token Efficiency

| ID | Requirement |
|----|-------------|
| NFR-4.1 | All rule queries support TOON format output |
| NFR-4.2 | Summary mode for large results |
| NFR-4.3 | Pagination for list operations |

## Success Criteria

| Metric | Target | Measurement |
|--------|--------|-------------|
| SRD coverage | 100% | All SRD classes, races, spells, monsters accessible |
| Query performance | < 100ms | Measure p95 query latency |
| Character validation | Accurate | Manual review of validation results |
| Offline functionality | Full | All queries work with cached data |
| Test coverage | ≥ 80% | Unit tests for all models and validators |
| Backward compatibility | 100% | All existing campaigns work unchanged |

## Constraints & Assumptions

### Constraints

1. **OGL Content Only:** Cannot include non-OGL content (e.g., full PHB)
2. **API Dependencies:** SRD API and Open5e may have rate limits or downtime
3. **Storage Size:** Full SRD cache ~10-20MB per campaign
4. **Fork Repository:** Changes must be pushed to fork remote

### Assumptions

1. Users have internet for initial rulebook download
2. SRD is sufficient for most use cases
3. Custom homebrew follows D&D 5e conventions
4. Users understand SRD vs full rulebook limitations

## Out of Scope

The following are explicitly **NOT** included in this PRD:

1. ❌ Non-D&D game systems (Pathfinder, Call of Cthulhu, etc.)
2. ❌ Combat automation (initiative, damage calculation)
3. ❌ Dice rolling with rule application
4. ❌ Character builder wizard/UI
5. ❌ PDF/book parsing (only structured data)
6. ❌ Encounter balancing calculations
7. ❌ Automatic character sheet generation
8. ❌ Integration with D&D Beyond or other paid services

## Dependencies

### External Dependencies

| Dependency | Version | Purpose | Risk |
|------------|---------|---------|------|
| httpx | ≥0.24 | Async HTTP client for APIs | Low |
| pyyaml | ≥6.0 | YAML parsing for custom rulebooks | Low |
| 5e-srd-api | v2014/v2024 | Official SRD data | Medium - external API |
| Open5e API | latest | Extended OGL content | Medium - external API |

### Internal Dependencies

```
Rulebook System (this PRD)
    └── depends on → Split Storage (completed)
    └── depends on → TOON Output (completed)
    └── enhances → Character Management (existing)
```

### Recommended Implementation Order

1. **Phase 1:** Data Models & Rulebook Manager Core (FR-1, FR-2)
2. **Phase 2:** SRD Integration (FR-3)
3. **Phase 3:** Custom Rulebook Support (FR-5)
4. **Phase 4:** Character Validation (FR-6)
5. **Phase 5:** MCP Tools (FR-7)
6. **Phase 6:** Open5e Integration (FR-4) — Optional

## Technical Notes

### Target Directory Structure

```
src/gamemaster_mcp/
├── rulebooks/
│   ├── __init__.py
│   ├── manager.py              # RulebookManager class
│   ├── models.py               # Rulebook data models
│   ├── validators.py           # Character validation logic
│   └── sources/
│       ├── __init__.py
│       ├── base.py             # Abstract base for sources
│       ├── srd.py              # 5e-srd-api client
│       ├── open5e.py           # Open5e client
│       └── custom.py           # Local file loader

campaigns/
└── my_campaign/
    ├── campaign.toon
    ├── characters/
    ├── rulebooks/              # New!
    │   ├── manifest.json       # Active rulebooks
    │   ├── cache/
    │   │   ├── srd_2014/       # Cached SRD data
    │   │   └── open5e/         # Cached Open5e data
    │   └── custom/
    │       ├── my_races.json
    │       └── house_rules.yaml
```

### Rulebook Manifest Structure

```json
{
  "active_rulebooks": [
    {
      "id": "srd-2014",
      "source": "srd",
      "version": "2014",
      "loaded_at": "2026-02-02T14:00:00Z"
    },
    {
      "id": "homebrew-races",
      "source": "custom",
      "path": "custom/my_races.json",
      "loaded_at": "2026-02-02T14:05:00Z"
    }
  ],
  "conflict_resolution": "custom_overrides_official"
}
```

### Custom Rulebook Schema (Example)

```json
{
  "$schema": "gamemaster-mcp/rulebook-v1",
  "name": "DM's Homebrew Races",
  "version": "1.0",
  "content": {
    "races": [
      {
        "name": "Aetherborn",
        "ability_bonuses": {"charisma": 2, "any": 1},
        "size": "Medium",
        "speed": 30,
        "traits": [
          {
            "name": "Born of Aether",
            "description": "You don't need to breathe..."
          }
        ],
        "languages": ["Common", "one of your choice"]
      }
    ]
  }
}
```

### Validation Report Structure

```json
{
  "character_id": "char_abc123",
  "valid": false,
  "errors": [
    {
      "type": "invalid_subclass",
      "message": "Bladesinger is not available in SRD",
      "field": "character_class.subclass",
      "suggestion": "Available Wizard subclasses: School of Evocation"
    }
  ],
  "warnings": [
    {
      "type": "missing_feature",
      "message": "Level 5 Wizard should have Arcane Recovery",
      "suggestion": "Add 'Arcane Recovery' to features_and_traits"
    }
  ],
  "info": [
    {
      "type": "homebrew_detected",
      "message": "Race 'Aetherborn' found in homebrew-races rulebook"
    }
  ]
}
```

## References

- [5e-srd-api Documentation](https://5e-bits.github.io/docs/)
- [5e-database GitHub](https://github.com/5e-bits/5e-database)
- [Open5e Website](https://open5e.com/)
- [Open5e GitHub](https://github.com/open5e/open5e)
- [dnd-character Python Library](https://github.com/tassaron/dnd-character)
- [mnehmos.rpg.mcp](https://github.com/Mnehmos/mnehmos.rpg.mcp) — Inspiration for rules engine approach
