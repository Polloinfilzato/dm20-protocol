---
name: character-model-v2
description: Extend Character model with full D&D 5e sheet fields, add creation wizard with rulebook integration, and implement level-up automation
status: backlog
created: 2026-02-12T18:04:10Z
---

# PRD: Character Model v2 & Creation Wizard

## Executive Summary

Extend dm20-protocol's Character model to cover a complete D&D 5e character sheet, replace the bare-bones `create_character` MCP tool with a rulebook-aware creation wizard, and add a `level_up_character` tool for automated progression. The current model has 30+ fields but `create_character` only populates 6 of them — everything else defaults to empty/zero, forcing the DM persona to use the `notes` field as a catch-all.

### Key Deliverables

1. **Character Model v2** — Add missing fields for progression, proficiencies, combat, and structured features
2. **Creation Wizard** — Auto-populate character from rulebook data (class, race, background) with smart defaults
3. **Level-Up Tool** — Automated progression: HP, spell slots, features, ASI/feat choices
4. **Backward Compatibility** — Existing characters load and work without migration

**Origin:** Discovered during Issue #73 (Game Loop Playtest) — tracked as Issue #74.

## Problem Statement

### Current State

The `create_character` MCP tool accepts only 6 meaningful parameters (name, class, level, race, and ability scores). It produces a Character object with:

- **HP**: defaults to 1 (should be calculated from class hit die + CON modifier)
- **Proficiency bonus**: defaults to 2 (should scale with level)
- **Skill proficiencies**: empty (should come from class + background choices)
- **Saving throw proficiencies**: empty (should come from class)
- **Languages**: empty (should come from race + background)
- **Starting equipment**: empty (should come from class + background)
- **Spell slots**: empty (should be calculated from class + level for casters)
- **Features/traits**: empty (should come from class level 1 + race)
- **Speed**: not tracked (should come from race)
- **Experience points**: not tracked
- **Conditions**: not tracked
- **Subclass/subrace**: settable in model but not via MCP tools

The DM persona compensates by dumping everything into the `notes` field as free text, which is fragile, unsearchable, and lost on session restart.

### User Scenario

> *"I want to create a Level 3 Wood Elf Ranger with the Outlander background. Currently I have to manually specify every ability score, then the DM has to manually look up and assign proficiencies, starting equipment, HP, ranger spells, favored enemy, natural explorer terrain... all by hand. A Level 1 Fighter takes 5 minutes of back-and-forth. A Level 5 Wizard is practically impossible without errors."*

## Architecture Overview

```
┌─────────────────────────────────────────────────────┐
│                  MCP Tools Layer                     │
│  create_character (wizard)  │  level_up_character    │
│  update_character (extended) │  manage_inventory      │
└──────────────┬──────────────┴────────────┬──────────┘
               │                           │
┌──────────────▼──────────────┐  ┌────────▼──────────┐
│     Character Builder       │  │  Level-Up Engine   │
│  - Auto-populate from       │  │  - HP roll/average │
│    ClassDef + RaceDef +     │  │  - New features    │
│    BackgroundDef            │  │  - Spell slots     │
│  - Ability score methods    │  │  - ASI / Feat      │
│  - Smart defaults           │  │  - Subclass @lvl 3 │
└──────────────┬──────────────┘  └────────┬──────────┘
               │                           │
┌──────────────▼───────────────────────────▼──────────┐
│              Character Model v2                      │
│  + experience_points, speed, conditions[]            │
│  + tool_proficiencies[], hit_dice (structured)       │
│  + features[] (structured Feature model)             │
│  + proficiency_bonus (auto-calculated from level)    │
│  + spell_slots_max{} (auto from class/level)         │
└──────────────┬──────────────────────────────────────┘
               │
┌──────────────▼──────────────────────────────────────┐
│         RulebookManager (read-only)                  │
│  ClassDefinition │ RaceDefinition │ BackgroundDef    │
│  (hit_die, saves, equipment, spellcasting, ...)      │
└─────────────────────────────────────────────────────┘
```

## User Stories

### US-1: Quick Character Creation

**As** a player starting a new campaign,
**I want to** create a fully-populated character by specifying just class, race, level, and background,
**So that** I can start playing immediately without manual bookkeeping.

**Acceptance Criteria:**
- Given class "Ranger", race "Wood Elf", level 3, background "Outlander"
- When I call `create_character` with these parameters
- Then the character has: correct HP (3d10 + CON×3), DEX+WIS saving throws, Ranger proficiencies, Wood Elf traits (Darkvision, Fey Ancestry, Trance, +2 DEX/+1 WIS), Outlander equipment, 35ft speed, 3 known spells, spell slots {1: 3}, proficiency bonus +2, Favored Enemy + Natural Explorer features

### US-2: Ability Score Methods

**As** a player,
**I want to** choose between Standard Array, Point Buy, or rolling 4d6 drop lowest,
**So that** I can generate ability scores using my preferred method.

**Acceptance Criteria:**
- Standard Array: [15, 14, 13, 12, 10, 8] assigned to chosen abilities
- Point Buy: 27 points, scores start at 8, costs follow PHB table
- Roll: 4d6 drop lowest, rolled via `roll_dice` tool, assigned to abilities
- Racial bonuses applied after base scores are set

### US-3: Level Up

**As** a DM managing a campaign,
**I want to** level up a character with a single tool call,
**So that** all progression mechanics are applied correctly.

**Acceptance Criteria:**
- HP increases by hit die roll (or average) + CON modifier
- New class features added at the correct level
- Spell slots updated for casters
- Proficiency bonus updated when it changes (levels 5, 9, 13, 17)
- ASI or Feat choice at levels 4, 8, 12, 16, 19
- Subclass selection prompted at the class-specific level (typically 3)

### US-4: Backward Compatibility

**As** a DM with existing campaigns,
**I want to** load characters created with the old model,
**So that** I don't lose any campaign data.

**Acceptance Criteria:**
- Characters saved with v1 model load without errors
- New fields default to sensible values (speed=30, xp=0, conditions=[])
- No data migration required — Pydantic defaults handle missing fields
- Existing `update_character` calls continue to work

### US-5: Inventory Management

**As** a DM,
**I want to** equip, unequip, and remove items from a character's inventory,
**So that** I can manage equipment beyond just adding items.

**Acceptance Criteria:**
- New tool `equip_item` moves item from inventory to equipment slot
- New tool `unequip_item` moves item from equipment slot back to inventory
- New tool `remove_item` removes item from inventory by name or ID
- Equipment slots: weapon_main, weapon_off, armor, shield (already in model)

## Functional Requirements

### FR-1: Character Model Extensions

| Area | New/Modified Fields | Type | Default |
|------|-------------------|------|---------|
| **Progression** | `experience_points` | int | 0 |
| | `hit_dice_type` | str | "d8" (from class) |
| | `hit_dice_total` | int | level (from class level) |
| | `hit_dice_remaining` | int | level (same as total) |
| **Combat** | `speed` | int | 30 (from race) |
| | `conditions` | list[str] | [] |
| | `spell_slots_max` | dict[int, int] | {} (from class/level) |
| **Proficiencies** | `tool_proficiencies` | list[str] | [] |
| **Features** | `features` | list[Feature] | [] (structured model) |
| **Auto-calculated** | `proficiency_bonus` | computed property | from level |

**Feature Model (new):**
```
Feature:
  name: str           # "Favored Enemy"
  source: str         # "Ranger 1" or "Wood Elf"
  description: str    # Full text
  level_gained: int   # Level when acquired
```

**Note:** `skill_proficiencies`, `saving_throw_proficiencies`, `languages`, `equipment` already exist in v1. They just aren't populated by `create_character`.

### FR-2: Character Builder (Enhanced create_character)

The existing `create_character` MCP tool is extended with:

| New Parameter | Type | Required | Description |
|---------------|------|----------|-------------|
| `subclass` | str \| None | No | Subclass name (required if level >= subclass_level) |
| `subrace` | str \| None | No | Subrace name (if applicable) |
| `background` | str \| None | No | Background name (existing param, now used) |
| `ability_method` | str | No | "standard_array", "point_buy", "manual" (default: "manual" = current behavior) |
| `ability_assignments` | dict | No | For standard_array/point_buy: {"strength": 15, ...} |

**Builder Logic:**
1. Look up ClassDefinition from RulebookManager (if loaded)
2. Look up RaceDefinition from RulebookManager (if loaded)
3. If rulebooks available: auto-populate saving throws, hit die, speed, languages, racial traits, starting features, spell slots, proficiency bonus
4. If rulebooks NOT available: return an error message suggesting to load rulebooks first (`load_rulebook source="srd"`). The wizard requires rulebook data to function correctly — partial character creation without rules data leads to inconsistent state.
5. Calculate HP: level 1 = max hit die + CON mod; levels 2+ = (average hit die + CON mod) × (level - 1)
6. Set proficiency bonus from level
7. Background: if known, add proficiencies and languages

### FR-3: Level-Up Tool (new MCP tool)

```
level_up_character(
    name_or_id: str,         # Character to level up
    hp_method: str = "average",  # "average" or "roll"
    asi_choices: dict | None = None,  # e.g., {"strength": 2} or {"feat": "Alert"}
    subclass: str | None = None,  # If reaching subclass level
    new_spells: list[str] | None = None,  # Spells learned this level
)
```

**Logic:**
1. Increment class level
2. Add HP (average or roll + CON modifier)
3. Update hit dice total/remaining
4. Add new class features for this level (from ClassDefinition)
5. Update spell slots if caster
6. Apply ASI (+2 to one ability or +1/+1 to two) or feat at appropriate levels
7. Update proficiency bonus if it changes
8. Set subclass if reaching subclass selection level

### FR-4: Extended update_character

Add these to the updatable fields:
- `experience_points`
- `speed`
- `conditions` (add/remove)
- `tool_proficiencies` (add/remove)
- `languages` (add/remove)
- `skill_proficiencies` (add/remove)
- `features` (add/remove)
- `spells_known` (add/remove)
- `spell_slots_used` (reset on long rest)

### FR-5: Inventory Management Tools

- `equip_item(character, item_name_or_id, slot)` — Move item to equipment slot
- `unequip_item(character, slot)` — Move equipped item back to inventory
- `remove_item(character, item_name_or_id, quantity=1)` — Remove from inventory

## Non-Functional Requirements

| Requirement | Target | Notes |
|-------------|--------|-------|
| Backward compatibility | 100% v1 characters load | Pydantic defaults, no migration |
| Creation time | < 2 seconds | Builder should be fast |
| Storage format | No schema change | New fields serialize to existing JSON |
| Test coverage | > 80% new code | Unit + integration tests |
| Existing tests | Zero regressions | All current tests pass |

## Success Criteria

| Metric | Target | Validation |
|--------|--------|------------|
| Fields populated on creation | > 20 (vs current 6) | Automated test |
| HP calculated correctly | 100% accuracy vs PHB | Test against known values |
| Level-up works levels 1-20 | All features applied | Test for Fighter, Wizard, Ranger |
| Old characters load | Zero errors | Load test with v1 JSON |
| Creation wizard + rulebook | Full auto-population | E2E test with SRD loaded |
| Creation without rulebook | Clear error message | Test: returns "load rulebook first" |

## Constraints & Assumptions

- **Single class only** — Multi-classing is out of scope for v2
- **Rulebook required** — Builder requires at least one rulebook loaded (SRD or other). Returns error if none loaded.
- **No UI** — All interaction via MCP tools, the DM persona orchestrates the wizard
- **Pydantic v2** — Model uses Pydantic BaseModel (already the case)
- **No character sheet PDF export** — Out of scope

## Out of Scope

- Multi-classing support
- Character sheet PDF/image export
- Automated encounter balancing based on character level
- Character marketplace/sharing
- Feat implementation details (just name + description stored)
- Spell preparation system (beyond spells_known list)
- Detailed encumbrance calculations

## Dependencies

### Internal (existing, read-only access)
- `RulebookManager` — ClassDefinition, RaceDefinition, BackgroundDefinition, SpellDefinition
- `Storage` layer — character CRUD operations (may need minor extensions)
- `roll_dice` MCP tool — for HP rolls and ability score generation

### Internal (modified)
- `models.py` — Character model extension
- `main.py` — MCP tool modifications and new tools
- `storage.py` — Extended update operations

### External
- None — fully offline

## Implementation Order

### Phase 1: Model Extension (Foundation)
- Extend Character model with new fields
- Add Feature model
- Ensure backward compatibility (Pydantic defaults)
- Update serialization/deserialization
- Tests for model changes

### Phase 2: Builder Logic
- Character builder module (auto-populate from rulebook data)
- Ability score methods (standard array, point buy, manual)
- HP calculation
- Enhanced `create_character` MCP tool
- Tests with and without rulebook data

### Phase 3: Level-Up Engine
- `level_up_character` MCP tool
- HP progression, feature addition, spell slot updates
- ASI/feat handling
- Subclass selection
- Tests for multiple class progressions

### Phase 4: Inventory & Update Extensions
- `equip_item`, `unequip_item`, `remove_item` tools
- Extended `update_character` with new fields
- Conditions management
- Spell slot reset (long rest)

### Phase 5: Integration & Validation
- E2E tests with Claudmaster (DM creates character via wizard)
- Backward compatibility validation with existing campaign data
- Performance benchmarks

## Estimated Effort

| Phase | Size | Hours | Tasks (est.) |
|-------|------|-------|-------------|
| Phase 1: Model Extension | M | 3-4 | 2 |
| Phase 2: Builder Logic | L | 6-8 | 3 |
| Phase 3: Level-Up Engine | M | 4-6 | 2 |
| Phase 4: Inventory & Updates | S | 2-3 | 2 |
| Phase 5: Integration | S | 2-3 | 1 |
| **Total** | **L/XL** | **17-24** | **~10** |
