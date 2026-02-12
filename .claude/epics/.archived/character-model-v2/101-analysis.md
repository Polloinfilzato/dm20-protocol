---
issue: 102
task_file: 101.md
analyzed: 2026-02-12T19:59:31Z
---

# Analysis: Issue #102 — Inventory Management Tools

## Scope

Single-stream task. Add 3 new MCP tools to `main.py`: equip_item, unequip_item, remove_item.

## Stream 1: MCP Tools + Tests

**Files:**
- `src/dm20_protocol/main.py` — 3 new tool functions
- `tests/test_inventory_tools.py` (new) — Unit tests

**Key design decisions:**
1. Item lookup: case-insensitive name match first, then ID match
2. Auto-unequip when slot is occupied (move current item back to inventory)
3. Partial quantity removal for stackable items
4. Valid slots: weapon_main, weapon_off, armor, shield (from existing Character model)
5. All tools use storage.save() for persistence

**Risk:** Very low — only adding new functions to main.py, no modifications to existing code.
