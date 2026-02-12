---
issue: 101
task_file: 100.md
analyzed: 2026-02-12T19:45:25Z
---

# Analysis: Issue #101 — Level-Up Engine & MCP Tool

## Scope

Single-stream task. Create `level_up_engine.py` module + add `level_up_character` MCP tool to `main.py`.

## Stream 1: Engine Module + MCP Integration

**Files:**
- `src/dm20_protocol/level_up_engine.py` (new) — LevelUpEngine class + LevelUpResult model
- `src/dm20_protocol/main.py` — New level_up_character tool
- `tests/test_level_up_engine.py` (new) — Unit + integration tests

**RulebookManager API to use:**
- `manager.get_class(index)` → ClassDefinition (hit_die, class_levels with features, spellcasting, subclasses)
- Access via `storage.rulebook_manager` (already available in main.py scope)

**Key design decisions:**
1. LevelUpResult as Pydantic model for structured output
2. HP calculation: average (default) vs roll — average is `die//2 + 1 + CON mod`
3. ASI at levels 4, 8, 12, 16, 19 — accept dict of ability: bonus, validate total = 2
4. Subclass at level 3 (standard) — validate against ClassDefinition.subclasses if available
5. Fighter gets extra ASI at 6, 14 — need class-specific ASI level detection
6. Spell slots from SpellcastingInfo.spell_slots[new_level] — same conversion as builder
7. Proficiency bonus auto-updates via model_validator (already in Character model)

**Risk:** Low — new file, minimal changes to main.py (one new tool function).
