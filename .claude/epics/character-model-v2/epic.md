---
name: character-model-v2
status: in_progress
created: 2026-02-12T18:10:15Z
progress: 33%
prd: .claude/prds/character-model-v2.md
github: https://github.com/Polloinfilzato/dm20-protocol/issues/98
---

# Epic: Character Model v2 & Creation Wizard

## Overview

Extend the Character model with missing D&D 5e fields, build a rulebook-aware creation wizard that auto-populates characters from ClassDefinition/RaceDefinition/BackgroundDefinition data, add a `level_up_character` MCP tool for automated progression, and provide inventory management tools (equip/unequip/remove). The current `create_character` populates only 6 of 30+ fields — this epic closes the gap.

## Architecture Decisions

### 1. Extend, Don't Replace the Character Model
The existing model already has most fields (spell_slots, equipment, skill_proficiencies, etc.). We add only the truly missing fields (experience_points, speed, conditions, tool_proficiencies, structured features). Backward compatibility is handled via Pydantic defaults — no migration needed.

### 2. Builder Pattern as Separate Module
The character builder logic lives in a new `character_builder.py` module, keeping `main.py` thin. The builder reads from RulebookManager (ClassDefinition, RaceDefinition, BackgroundDefinition) and returns a fully populated Character object. If no rulebook is loaded, it returns an error suggesting `load_rulebook source="srd"`.

### 3. Level-Up as Engine, Not Just a Tool
The level-up logic lives in a `level_up_engine.py` module, reusable by both the MCP tool and the builder (for creating characters above level 1). The builder calls the level-up engine iteratively for levels 2+.

### 4. Computed Properties Where Possible
`proficiency_bonus` becomes a computed property from level (formula: `2 + (level - 1) // 4`). This avoids stale data and ensures correctness.

### 5. Leverage Existing Infrastructure
- Storage layer already handles Character CRUD with O(1) lookups — no changes needed
- CharacterValidator already exists — extend it for new fields
- Item model already exists — inventory tools just move items between inventory/equipment slots
- Spell model already exists — builder just populates spells_known from rulebook data

## Technical Approach

### Model Layer (`models.py`)
- Add ~6 new fields to Character (experience_points, speed, conditions, tool_proficiencies, Feature model, hit_dice_type)
- Convert `features_and_traits: list[str]` → keep for backward compat, add `features: list[Feature]` as structured alternative
- Make `proficiency_bonus` a computed property (while keeping the field settable for edge cases)
- Ensure all new fields have sensible Pydantic defaults for backward compat

### Builder Module (`character_builder.py`)
- `CharacterBuilder` class with `build()` method
- Reads ClassDefinition → hit die, saving throws, proficiencies, starting equipment, spellcasting, level 1 features
- Reads RaceDefinition → speed, ability bonuses, languages, racial traits
- Reads BackgroundDefinition → proficiencies, languages, equipment
- Ability score methods: standard_array, point_buy, manual (current behavior)
- HP calculation: level 1 = max hit die + CON mod; levels 2+ via level-up engine

### Level-Up Module (`level_up_engine.py`)
- `LevelUpEngine` class with `level_up()` method
- HP: average (default) or roll + CON mod
- Features from ClassDefinition.class_levels[new_level]
- Spell slots from SpellcastingInfo.spell_slots[new_level]
- ASI/Feat at levels 4, 8, 12, 16, 19
- Subclass at class-specific level (typically 3)
- Proficiency bonus auto-updated

### MCP Tools (`main.py`)
- Enhanced `create_character` with new params: subclass, subrace, background (now used), ability_method, ability_assignments
- New `level_up_character` tool
- New `equip_item`, `unequip_item`, `remove_item` tools
- Extended `update_character` with conditions, proficiencies, features, XP, speed, spells

### Infrastructure
- No storage changes needed — new fields serialize to existing JSON format
- No deployment changes — pure Python, fully offline
- Test coverage > 80% on all new modules

## Implementation Strategy

### Development Flow
1. **Model first** — extend Character, verify backward compat
2. **Builder + Level-Up in parallel** — these modules are independent of each other
3. **MCP tools** — wire builder and level-up into tools
4. **Inventory + update extensions** — smaller tools, less risk
5. **Integration tests** — E2E with SRD loaded

### Risk Mitigation
- Backward compat is the #1 risk → test with existing campaign JSON files FIRST
- Builder depends on RulebookManager data quality → test against SRD data specifically
- Level-up is complex for spellcasters → test Fighter (simple), Ranger (half-caster), Wizard (full caster)

### Testing Approach
- Unit tests per module (builder, level-up engine)
- Integration tests for MCP tools
- Backward compat tests: load v1 character JSON, verify no errors
- E2E: create character with SRD loaded, verify all 20+ fields populated

## Tasks Created

- [x] 98.md - Character Model Extension (parallel: false — foundation) ✅
- [x] 99.md - Character Builder & Enhanced create_character (parallel: true) ✅
- [ ] 100.md - Level-Up Engine & MCP Tool (parallel: true)
- [ ] 101.md - Inventory Management Tools (parallel: true)
- [ ] 102.md - Extended update_character & Utility Tools (parallel: true)
- [ ] 103.md - Integration & E2E Tests (parallel: false — depends on all)

Total tasks: 6
Parallel tasks: 4 (#99, #100, #101, #102 — after #98 completes)
Sequential tasks: 2 (#98 first, #103 last)
Estimated total effort: 18-26 hours

## Dependencies

### Task Dependencies
```
Task 1 (Model) ──┬──→ Task 2 (Builder + create_character)
                  ├──→ Task 3 (Level-Up Engine)
                  ├──→ Task 4 (Inventory Tools)
                  └──→ Task 5 (Extended update_character)
                          │
Task 2 + 3 + 4 + 5 ──→ Task 6 (Integration Tests)
```

### Internal Dependencies (read-only)
- `RulebookManager` — ClassDefinition, RaceDefinition, BackgroundDefinition, SpellDefinition
- `roll_dice` MCP tool — for HP rolls and ability score generation
- Storage layer — character CRUD (no modifications needed)

### Internal Dependencies (modified)
- `models.py` — Character model extension
- `main.py` — MCP tool modifications and new tools

### External Dependencies
- None — fully offline

## Success Criteria (Technical)

| Criterion | Target | Validation |
|-----------|--------|------------|
| Fields populated on creation (with SRD) | > 20 fields (vs current 6) | Automated test |
| HP calculated correctly | 100% accuracy vs PHB formulas | Test against known values |
| Level-up works levels 1-20 | All features applied correctly | Test for Fighter, Wizard, Ranger |
| Old characters load without errors | Zero regressions | Load test with v1 JSON |
| Creation without rulebook | Clear error message | Test: returns "load rulebook first" |
| Ability score methods | Standard array + point buy correct | Unit tests with edge cases |
| Inventory management | Equip/unequip/remove all work | Integration tests |
| Test coverage | > 80% new code | pytest --cov |
| All existing tests pass | Zero regressions | Full test suite |

## Estimated Effort

| Task | Size | Hours | Parallelism |
|------|------|-------|-------------|
| Task 1: Model Extension | S | 2-3 | Sequential (foundation) |
| Task 2: Builder + create_character | L | 6-8 | After Task 1 |
| Task 3: Level-Up Engine | M | 4-6 | After Task 1, parallel with Task 2 |
| Task 4: Inventory Tools | S | 2-3 | After Task 1, parallel with Tasks 2-3 |
| Task 5: Extended update_character | S | 2-3 | After Task 1, parallel with Tasks 2-4 |
| Task 6: Integration Tests | S | 2-3 | After Tasks 1-5 |
| **Total** | **L** | **18-26** | **~3 parallel streams after Task 1** |
