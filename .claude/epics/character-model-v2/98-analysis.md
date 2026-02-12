---
issue: 99
task_file: 98.md
analyzed: 2026-02-12T18:23:12Z
---

# Analysis: Issue #99 — Character Model Extension

## Scope

Single-stream task. Modify `src/dm20_protocol/models.py` and add tests.

## Stream 1: Model Extension + Tests

**Files:**
- `src/dm20_protocol/models.py` — Add Feature model, extend Character, computed proficiency_bonus
- `tests/test_character_model_v2.py` — Unit tests for new fields and backward compat

**Approach:**
1. Add `Feature` model class between `Spell` and `Character` (line ~197)
2. Add new fields to `Character` class: experience_points, speed, conditions, tool_proficiencies, features, hit_dice_type
3. Convert `proficiency_bonus` to use a `model_validator` that auto-calculates from level when not explicitly overridden
4. Update `__all__` exports
5. Write tests: Feature model, proficiency_bonus at all levels, backward compat with v1 JSON

**Key Decision — proficiency_bonus:**
Use a `model_validator(mode='after')` that sets proficiency_bonus based on class level. The field stays as `int = 2` for backward compat, but the validator overwrites it with the computed value. This means:
- Old characters loading from JSON: validator runs, sets correct value from their level
- New characters: always correct
- Manual override: not easily possible (validator always runs) — acceptable tradeoff for v2

**Risk:** Zero — all new fields have defaults, no storage changes needed.
