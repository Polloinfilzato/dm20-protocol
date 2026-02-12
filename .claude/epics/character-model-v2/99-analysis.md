---
issue: 100
task_file: 99.md
analyzed: 2026-02-12T19:26:25Z
---

# Analysis: Issue #100 — Character Builder & Enhanced create_character

## Scope

Single-stream task. Create `character_builder.py` module + modify `create_character` in `main.py`.

## Stream 1: Builder Module + MCP Integration

**Files:**
- `src/dm20_protocol/character_builder.py` (new) — CharacterBuilder class
- `src/dm20_protocol/main.py` — Enhanced create_character tool
- `tests/test_character_builder.py` (new) — Unit + integration tests

**RulebookManager API to use:**
- `manager.get_class(index)` → ClassDefinition (hit_die, saving_throws, proficiencies, spellcasting, class_levels, starting_equipment)
- `manager.get_race(index)` → RaceDefinition (speed, ability_bonuses, languages, traits)
- `manager.get_background(index)` → BackgroundDefinition (starting_proficiencies, language_options, starting_equipment, feature)
- Access via `storage.rulebook_manager` (already available in main.py scope)

**Key design decisions:**
1. Index format: RulebookManager uses lowercase-hyphenated indexes ("wood-elf", not "Wood Elf"). Builder must normalize user input.
2. Ability bonuses use uppercase abbreviations ("STR", "DEX"). Map to lowercase model field names.
3. SRD class_levels.features has only feature NAMES (no descriptions). Store in Feature model with name + source.
4. HP for level > 1: use average formula inline (no dependency on Level-Up Engine yet).
5. spell_slots in SpellcastingInfo is dict[int, list[int]] where key=char_level, value=[1st, 2nd, 3rd...]. Need to convert to Character's dict[int, int] format.

**Risk:** Low — new file, minimal changes to main.py.
